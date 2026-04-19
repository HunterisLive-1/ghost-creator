"""
backends/tts/omnivoice_tts.py — OmniVoice TTS Backend
=======================================================
Supports two modes based on whether `tts.omnivoice_server_path` is configured:

SERVER MODE  (recommended)
  - `tts.omnivoice_server_path` points to OmniVoice's run.bat
  - Backend auto-starts the server, waits for it to come online, then calls
    the HTTP /tts endpoint.
  - Server is killed after synthesis to free VRAM for image generation.

PACKAGE MODE  (fallback)
  - No server path set; uses the `omnivoice` pip package directly on GPU/CPU.
  - Requires: pip install torch torchaudio omnivoice
"""

from __future__ import annotations

import asyncio
import gc
import io
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests
from pydub import AudioSegment

from backends.base import TTSBackend
from config import get_base_dir, get_ffmpeg_executable
from core.config_manager import config

AudioSegment.converter = get_ffmpeg_executable()
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

logger = logging.getLogger("ghost.tts.omnivoice")

MAX_RETRIES  = 2
RETRY_DELAY  = 5
CHUNK_SIZE   = 220
CHUNK_TIMEOUT = 10800  # 3 hours — covers even 40-min video TTS generation

# ── Package-mode globals ──────────────────────────────────────────────────────
_model = None
_load_lock = threading.Lock()

SPEAKING_STYLE_PRESETS: dict[str, dict] = {
    "default": {"instruct": None, "speed": None, "gen": {}},
    "narrator": {"instruct": "middle-aged, moderate pitch", "speed": 0.92, "gen": {"guidance_scale": 2.15}},
    "storyteller": {"instruct": "young adult, moderate pitch", "speed": 0.94, "gen": {"guidance_scale": 2.28, "class_temperature": 0.1}},
    "excited": {"instruct": "young adult, high pitch", "speed": 1.08, "gen": {"guidance_scale": 2.45, "class_temperature": 0.2}},
    "news": {"instruct": "middle-aged, moderate pitch, american accent", "speed": 1.02, "gen": {"guidance_scale": 2.05}},
    "whisper": {"instruct": "whisper, low pitch", "speed": 0.88, "gen": {"guidance_scale": 2.22}},
    "casual": {"instruct": "young adult, moderate pitch", "speed": 1.0, "gen": {"class_temperature": 0.06}},
}

QUALITY_PRESETS: dict[str, dict] = {
    "fast": {"gen": {"num_step": 24, "audio_chunk_duration": 18.0, "audio_chunk_threshold": 40.0}},
    "balanced": {"gen": {}},
    "high": {"gen": {"num_step": 46, "guidance_scale": 2.35, "audio_chunk_duration": 12.0, "audio_chunk_threshold": 22.0}},
}

DESIGN_VOICE_PROFILES: dict[str, dict] = {
    "custom": {"instruct": None, "speed": None},
    "vf_warm": {"instruct": "female, young adult, moderate pitch", "speed": None},
    "vf_story": {"instruct": "female, young adult, low pitch", "speed": 0.95},
    "vm_news": {"instruct": "male, middle-aged, moderate pitch, american accent", "speed": 1.02},
    "vm_narrator": {"instruct": "male, middle-aged, low pitch", "speed": 0.92},
    "vm_young": {"instruct": "male, young adult, high pitch", "speed": 1.06},
    "neutral_auto": {"instruct": None, "speed": None},
}


# ── Config helpers ────────────────────────────────────────────────────────────

def _server_path() -> Path | None:
    """Return run.bat Path when server mode is configured, else None."""
    raw = config.get("tts.omnivoice_server_path", "").strip()
    return Path(raw) if raw else None


def _server_url() -> str:
    return config.get("tts.omnivoice_url", "http://127.0.0.1:8004")


def _ref_audio_path() -> Path:
    raw = config.get("tts.reference_audio", "my_voice_reference.wav")
    p = Path(raw)
    if not p.is_absolute():
        p = get_base_dir() / p
    return p.resolve()


def _ref_transcript() -> str:
    return (
        config.get("tts.omnivoice_ref_transcript", "").strip()
        or "Transcription of the reference audio."
    )


def _model_id() -> str:
    return config.get("tts.omnivoice_model_id", "k2-fsa/OmniVoice").strip() or "k2-fsa/OmniVoice"


def _omnivoice_mode() -> str:
    raw = (config.get("tts.omnivoice_mode", "clone") or "").strip().lower()
    return "design" if raw in {"design", "sound_design", "sound-design"} else "clone"


def _sanitize_preset_key(raw: str | None, allowed: dict[str, dict], *, fallback: str) -> str:
    k = (raw or "").strip().lower()
    return k if k in allowed else fallback


def _normalized_gender(raw: str | None) -> str | None:
    g = (raw or "").strip().lower()
    return g if g in ("male", "female") else None


def _resolve_style_and_quality(style_raw: str | None, quality_raw: str | None) -> tuple[dict, float | None]:
    st = SPEAKING_STYLE_PRESETS[_sanitize_preset_key(style_raw, SPEAKING_STYLE_PRESETS, fallback="default")]
    qu = QUALITY_PRESETS[_sanitize_preset_key(quality_raw, QUALITY_PRESETS, fallback="balanced")]
    gen: dict = {**st["gen"], **qu["gen"]}
    speed = st.get("speed")
    return gen, speed if isinstance(speed, (int, float)) else None


def _instruct_for_clone(style_raw: str | None, gender_raw: str | None) -> str | None:
    st = SPEAKING_STYLE_PRESETS[_sanitize_preset_key(style_raw, SPEAKING_STYLE_PRESETS, fallback="default")]
    ins = st.get("instruct")
    base = ins if isinstance(ins, str) and ins.strip() else None
    g = _normalized_gender(gender_raw)
    parts = [p for p in (g, base) if p]
    return ", ".join(parts) if parts else None


def _instruct_for_design(
    style_raw: str | None,
    user_instruct: str | None,
    *,
    voice_profile_raw: str | None,
    gender_raw: str | None,
) -> str | None:
    vp_key = _sanitize_preset_key(voice_profile_raw, DESIGN_VOICE_PROFILES, fallback="custom")
    vp = DESIGN_VOICE_PROFILES[vp_key]
    parts: list[str] = []

    if vp_key == "custom":
        st = SPEAKING_STYLE_PRESETS[_sanitize_preset_key(style_raw, SPEAKING_STYLE_PRESETS, fallback="default")]
        pi = st.get("instruct")
        pi = pi if isinstance(pi, str) and pi.strip() else None
        g = _normalized_gender(gender_raw)
        if g:
            parts.append(g)
        if pi:
            parts.append(pi)
    else:
        p_ins = vp.get("instruct")
        if isinstance(p_ins, str) and p_ins.strip():
            parts.append(p_ins.strip())
        else:
            g = _normalized_gender(gender_raw)
            if g:
                parts.append(g)

    ui = (user_instruct or "").strip()
    if ui:
        parts.append(ui)
    return ", ".join(parts) if parts else None


def _design_voice_speed_override(voice_profile_raw: str | None) -> float | None:
    vp_key = _sanitize_preset_key(voice_profile_raw, DESIGN_VOICE_PROFILES, fallback="custom")
    sp = DESIGN_VOICE_PROFILES[vp_key].get("speed")
    return float(sp) if isinstance(sp, (int, float)) else None


def _build_design_params(mode: str, language: str) -> dict:
    style = config.get("tts.omnivoice_speaking_style", "default")
    quality = config.get("tts.omnivoice_quality_preset", "balanced")
    profile = config.get("tts.omnivoice_design_voice", "custom")
    gender = config.get("tts.omnivoice_voice_gender", "")
    extra_instruct = config.get("tts.omnivoice_extra_instruct", "")
    language_hint = (config.get("tts.omnivoice_language_hint", "") or "").strip()

    gen_kw, speed_style = _resolve_style_and_quality(style, quality)
    speed_prof = _design_voice_speed_override(profile)
    speed = speed_prof if speed_prof is not None else speed_style

    if mode == "clone":
        instruct = _instruct_for_clone(style, gender)
    else:
        instruct = _instruct_for_design(
            style,
            extra_instruct,
            voice_profile_raw=profile,
            gender_raw=gender,
        )

    out: dict = {**gen_kw}
    if instruct:
        out["instruct"] = instruct
    if speed is not None:
        out["speed"] = speed
    if language_hint and language_hint.lower() not in ("auto", "none", "default"):
        out["language"] = language_hint
    elif language and language.lower() not in ("auto", "none", "default"):
        out["language"] = language
    return out


# ── Server-mode helpers ───────────────────────────────────────────────────────

def _check_server() -> bool:
    """
    Return True if OmniVoice server is already listening on its port.
    Uses a raw TCP connect so it works even when the server doesn't
    respond to HTTP GET on the root URL.
    """
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(_server_url())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8004
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def _start_server(cb=None) -> bool:
    """Launch run.bat in its own console window and wait up to 8 min."""
    def _notify(msg: str) -> None:
        logger.info(msg)
        if cb:
            cb(msg)

    bat = _server_path()
    if bat is None or not bat.exists():
        _notify(f"❌ OmniVoice run.bat nahi mila: {bat}")
        return False

    _notify(f"🚀 OmniVoice server launch ho raha hai: {bat.name} …")
    try:
        # CREATE_NEW_CONSOLE gives the bat its own visible console so it can
        # run properly; CREATE_NO_WINDOW would silently block it from starting.
        subprocess.Popen(
            ["cmd", "/c", str(bat)],
            cwd=str(bat.parent),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    except Exception as exc:
        _notify(f"❌ run.bat launch karne mein error: {exc}")
        return False

    _notify("⏳ Server ke online hone ka wait kar rahe hain (pehli baar mein 2–5 min lag sakte hain) …")
    MAX_WAIT = 240   # 8 minutes
    for i in range(MAX_WAIT):
        time.sleep(2)
        if _check_server():
            _notify(f"✅ OmniVoice server online! (~{(i + 1) * 2}s mein ready)")
            return True
        elapsed = (i + 1) * 2
        if elapsed % 20 == 0:
            _notify(f"  ⏳ {elapsed}s ho gaye, ab bhi wait kar rahe hain …")

    _notify(f"❌ OmniVoice server {MAX_WAIT * 2 // 60} minutes mein online nahi hua.")
    return False


def _kill_server() -> None:
    """Kill the process listening on the configured port to free VRAM."""
    port = _server_url().rstrip("/").split(":")[-1]
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=10,
            creationflags=_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F", "/T"],
                    capture_output=True, timeout=10,
                    creationflags=_NO_WINDOW,
                )
                logger.info("OmniVoice server killed (PID %s) — VRAM freed.", pid)
                time.sleep(3)
                return
        logger.warning("No process found on port %s — server may already be stopped.", port)
    except Exception as exc:
        logger.warning("Could not kill OmniVoice server: %s", exc)


# ── Package-mode helpers ──────────────────────────────────────────────────────

def _ensure_model_loaded() -> None:
    global _model
    with _load_lock:
        if _model is not None:
            return
        import torch
        from omnivoice import OmniVoice

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device.startswith("cuda") else torch.float32
        mid = _model_id()
        logger.info("Loading OmniVoice %s on %s (dtype=%s) …", mid, device, dtype)
        _model = OmniVoice.from_pretrained(mid, device_map=device, dtype=dtype)


def _unload_model() -> None:
    global _model
    with _load_lock:
        _model = None
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    logger.info("OmniVoice model unloaded — VRAM freed.")


# ── Backend class ─────────────────────────────────────────────────────────────

class OmniVoiceTTS(TTSBackend):
    """
    OmniVoice TTS — server mode (auto-start run.bat) or package mode.
    Mode is determined by whether `tts.omnivoice_server_path` is set.
    """

    @property
    def name(self) -> str:
        return "OmniVoice TTS"

    @property
    def requires_key(self) -> bool:
        return False

    @property
    def is_local(self) -> bool:
        return True

    # ── Text splitting ────────────────────────────────────────────────────

    @staticmethod
    def _split_text(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
        sentences = re.split(r"(?<=[।.!?])\s+", text.strip())
        chunks: list[str] = []
        current = ""
        for sent in sentences:
            if current and len(current) + len(sent) + 1 > max_chars:
                chunks.append(current.strip())
                current = sent
            else:
                current = f"{current} {sent}" if current else sent
        if current.strip():
            chunks.append(current.strip())
        return chunks if chunks else [text]

    # ── Progress helper ───────────────────────────────────────────────────

    def _cb(self, msg: str) -> None:
        """Emit a message to both the logger and the GUI progress callback (if set)."""
        logger.info(msg)
        cb = getattr(self, "_progress_cb", None)
        if cb:
            cb(msg)

    # ── Server mode: ensure running ───────────────────────────────────────

    def ensure_running(self, language: str = "hi") -> bool:
        cb = getattr(self, "_progress_cb", None)

        if _server_path() is None:
            return True

        if _check_server():
            self._cb("✅ OmniVoice server already running — reuse kar rahe hain.")
            return True

        if not config.get("tts.omnivoice_autostart", True):
            logger.warning(
                "OmniVoice server not running and autostart is disabled."
            )
            if cb:
                cb("⚠️ OmniVoice server nahi chal raha aur autostart OFF hai — manually start karo.")
            return False

        self._cb("🔌 OmniVoice server nahi chal raha — auto-start kar rahe hain …")
        if _start_server(cb=cb):
            return True

        logger.error("OmniVoice server failed to start!")
        return False

    # ── Server mode: model-ready check ───────────────────────────────────

    def _wait_for_model_ready(self, timeout_sec: int = 300) -> bool:
        """Poll /api/status until the model is loaded (up to timeout_sec)."""
        self._cb("⏳ OmniVoice model load ho raha hai, wait karo …")
        start = time.time()
        while time.time() - start < timeout_sec:
            try:
                resp = requests.get(f"{_server_url()}/api/status", timeout=5)
                data = resp.json()
                if data.get("error"):
                    self._cb("❌ OmniVoice model load error — server console window check karo.")
                    return False
                if data.get("ready"):
                    device = data.get("device", "")
                    self._cb(f"✅ OmniVoice model ready! ({device})")
                    return True
                device = data.get("device", "")
                if device:
                    self._cb(f"  ⏳ Model load ho raha hai … Device: {device}")
            except Exception:
                pass
            time.sleep(5)
        self._cb(f"❌ OmniVoice model {timeout_sec}s mein ready nahi hua.")
        return False

    # ── Server mode: HTTP synthesis ───────────────────────────────────────

    def _http_generate(self, text: str, language: str, mode: str) -> AudioSegment:
        """
        Call the OmniVoice WebUI API and return an AudioSegment.

        Clone mode  → POST /generate       (multipart, uploads WAV file)
        Design mode → POST /generate-design (multipart, no file)
        Response    → raw WAV bytes
        """
        speaking_style = config.get("tts.omnivoice_speaking_style", "default")
        quality_preset = config.get("tts.omnivoice_quality_preset", "balanced")
        voice_gender   = config.get("tts.omnivoice_voice_gender", "")

        if mode == "clone":
            ref_audio = config.get("tts.reference_audio", "my_voice_reference.wav")
            ref_path = Path(ref_audio)
            if not ref_path.is_absolute():
                ref_path = get_base_dir() / ref_path
            ref_text = _ref_transcript()

            with open(str(ref_path), "rb") as wav_f:
                resp = requests.post(
                    f"{_server_url()}/generate",
                    files={"ref_audio": ("ref.wav", wav_f, "audio/wav")},
                    data={
                        "text":           text,
                        "ref_text":       ref_text,
                        "speaking_style": speaking_style,
                        "quality_preset": quality_preset,
                        "voice_gender":   voice_gender,
                    },
                    timeout=CHUNK_TIMEOUT,
                )
        else:
            # design mode
            extra_instruct = config.get("tts.omnivoice_extra_instruct", "")
            design_voice   = config.get("tts.omnivoice_design_voice", "custom")
            language_hint  = config.get("tts.omnivoice_language_hint", "")
            lang = language_hint or (
                language if language and language.lower() not in ("auto", "none", "default") else ""
            )
            form: dict = {
                "text":           text,
                "speaking_style": speaking_style,
                "quality_preset": quality_preset,
                "voice_gender":   voice_gender,
                "design_voice":   design_voice,
            }
            if extra_instruct:
                form["instruct"] = extra_instruct
            if lang:
                form["language"] = lang

            resp = requests.post(
                f"{_server_url()}/generate-design",
                data=form,
                timeout=CHUNK_TIMEOUT,
            )

        if not resp.ok:
            raise RuntimeError(
                f"OmniVoice WebUI error {resp.status_code}: {resp.text[:300]}"
            )
        return AudioSegment.from_wav(io.BytesIO(resp.content))

    def _synthesize_server(self, text: str, language: str, output_path: str) -> str:
        """HTTP-based synthesis via the OmniVoice WebUI server."""

        # 1. Make sure server process is running
        if not self.ensure_running(language):
            raise RuntimeError(
                "OmniVoice server could not be started. "
                "Settings → TTS → SERVER PATH (run.bat) check karo, "
                "ya manually server start karo."
            )

        # 2. Wait for the model to finish loading
        if not self._wait_for_model_ready():
            raise RuntimeError(
                "OmniVoice model load nahi hua. "
                "Server console window mein error check karo."
            )

        mode = _omnivoice_mode()
        self._cb(f"🎙️ Voice generate ho raha hai (mode={mode}, {len(text)} chars) …")

        # 3. Generate — retry on transient errors
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if attempt > 1:
                    self._cb(f"  🔄 Retry attempt {attempt} …")
                audio = self._http_generate(text, language, mode)
                break
            except Exception as exc:
                last_exc = exc
                self._cb(f"  ⚠️ Attempt {attempt} failed: {exc}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
        else:
            raise RuntimeError(f"OmniVoice synthesis failed: {last_exc}") from last_exc

        # 4. Export WAV → MP3
        audio.export(output_path, format="mp3")
        size_kb = os.path.getsize(output_path) / 1024
        dur_s   = len(audio) // 1000
        self._cb(
            f"✅ Voiceover ready! ({size_kb:.0f} KB, {dur_s}s) → {Path(output_path).name}"
        )

        _kill_server()
        return output_path

    # ── Package mode: direct synthesis ────────────────────────────────────

    def _synthesize_chunk_pkg(self, chunk: str, call_kw: dict, idx: int, total: int):
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    "  [PKG] Chunk %s/%s (try %s) — %s chars",
                    idx, total, attempt, len(chunk),
                )
                with _load_lock:
                    if _model is None:
                        raise RuntimeError("OmniVoice model not loaded")
                    audio = _model.generate(text=chunk, **call_kw)
                return audio[0]
            except Exception as exc:
                last_exc = exc
                logger.warning("  Chunk %s failed (try %s): %s", idx, attempt, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
        raise RuntimeError(f"OmniVoice chunk {idx} failed: {last_exc}") from last_exc

    def _synthesize_package(self, text: str, language: str, output_path: str) -> str:
        """Direct synthesis via omnivoice pip package."""
        import torch
        import torchaudio

        mode = _omnivoice_mode()
        call_kw = _build_design_params(mode, language)
        if mode == "clone":
            call_kw["ref_audio"] = str(_ref_audio_path())
            call_kw["ref_text"] = _ref_transcript()

        os.makedirs(str(Path(output_path).resolve().parent), exist_ok=True)

        _ensure_model_loaded()

        chunks = self._split_text(text)
        logger.info(
            "OmniVoice [package:%s]: %s chars → %s chunk(s), ref=%s",
            mode, len(text), len(chunks), Path(call_kw["ref_audio"]).name if mode == "clone" else "none",
        )

        tensors: list = []
        try:
            for i, chunk in enumerate(chunks, start=1):
                t = self._synthesize_chunk_pkg(chunk, call_kw, i, len(chunks))
                t = t.detach().cpu().float()
                if t.dim() == 1:
                    t = t.unsqueeze(0)
                tensors.append(t)
            full = torch.cat(tensors, dim=-1)

            tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_wav.close()
            try:
                torchaudio.save(tmp_wav.name, full, 24000)
                combined = AudioSegment.from_wav(tmp_wav.name)
                combined.export(output_path, format="mp3")
            finally:
                try:
                    os.unlink(tmp_wav.name)
                except OSError:
                    pass

            size_kb = os.path.getsize(output_path) / 1024
            logger.info(
                "Voiceover saved → %s (%.1f KB, %dms)",
                output_path, size_kb, len(combined),
            )
        finally:
            _unload_model()

        return output_path

    # ── Public API ─────────────────────────────────────────────────────────

    async def synthesize(self, text: str, language: str, output_path: str) -> str:
        if _server_path() is not None:
            return await asyncio.to_thread(
                self._synthesize_server, text, language, output_path
            )
        return await asyncio.to_thread(
            self._synthesize_package, text, language, output_path
        )

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        mode = _omnivoice_mode()
        bat = _server_path()
        if bat is not None:
            # Server mode: check run.bat exists
            if not bat.exists():
                return (
                    False,
                    f"OmniVoice run.bat not found: {bat}\n"
                    "Settings → TTS → OmniVoice Server Path mein sahi path daalo.",
                )
            if mode == "clone":
                ref = _ref_audio_path()
                if not ref.exists():
                    return (False, f"Reference audio not found: {ref}")
            return (True, "")

        # Package mode: check omnivoice pip package + reference audio
        try:
            import omnivoice  # noqa: F401
        except ImportError:
            return (
                False,
                "OmniVoice server path configure nahi hai aur pip package "
                "'omnivoice' bhi install nahi hai.\n"
                "Settings → TTS → OMNIVOICE SERVER PATH mein run.bat ka path daalo, "
                "ya: pip install torch torchaudio omnivoice",
            )
        if mode == "clone":
            ref = _ref_audio_path()
            if not ref.exists():
                return (False, f"Reference audio not found: {ref}")
        return (True, "")
