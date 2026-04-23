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
# Legacy default; effective size comes from `tts.omnivoice_text_chunk_chars` (see `_text_chunk_size_chars()`).
CHUNK_SIZE_FALLBACK = 800
# Per-request read timeout (seconds) for one OmniVoice HTTP / generate call. CPU or long
# chunks (e.g. ~40 min of audio) can take many hours; default 5h, override via config.
CHUNK_TIMEOUT = 18000
_CONNECT_TIMEOUT = 30.0
_MIN_READ_TIMEOUT = 120.0
_HTTP_READ_TIMEOUT_MAX = 86400.0  # 24h cap when overridden in config

# Match OmniVoice `webui.py` reference trim (mono, resample, cap length).
REF_TRIM_THRESHOLD_SEC = 10.0
REF_TARGET_MAX_SEC = 8.0
REF_MIN_WARN_SEC = 3.0

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

# Target max chars *per sent chunk* after packing full sentences; splitting prefers
# `।.!?` then commas — not arbitrary character windows (avoids tone/pause glitches between chunks).
_OMNIVOICE_CHUNK_MIN = 120
_OMNIVOICE_CHUNK_MAX = 800


def _text_chunk_size_chars() -> int:
    """Resolve `tts.omnivoice_text_chunk_chars` with a safe numeric clamp."""
    raw = config.get("tts.omnivoice_text_chunk_chars", CHUNK_SIZE_FALLBACK)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = int(CHUNK_SIZE_FALLBACK)
    return max(_OMNIVOICE_CHUNK_MIN, min(_OMNIVOICE_CHUNK_MAX, n))


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


def _manual_ref_transcript() -> str:
    """Exact words in the reference WAV (only used when auto-transcribe is off)."""
    return (config.get("tts.omnivoice_ref_transcript", "") or "").strip()


def _use_auto_transcribe_ref() -> bool:
    v = config.get("tts.omnivoice_auto_transcribe_ref", 1)
    if isinstance(v, bool):
        return v
    try:
        return int(v) != 0
    except (TypeError, ValueError):
        return True


def _normalize_chunking_text(text: str) -> str:
    """Hindi / Sanskrit danda → period+space so model chunking splits like WebUI."""
    if not text:
        return text
    t = text.replace("\u0965", ". ")  # ॥
    t = t.replace("\u0964", ". ")  # ।
    return t


def _is_hindi_language_hint(language: str | None) -> bool:
    if not language:
        return False
    s = language.strip().lower()
    return "hindi" in s or s in ("hi", "hin")


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


def _unwrap_gen_container(x, max_depth: int = 8):
    t = x
    d = 0
    while d < max_depth and isinstance(t, (list, tuple)) and len(t) == 1:
        t = t[0]
        d += 1
    return t


def _coerce_model_generate_out(gout) -> object:
    if gout is None:
        raise ValueError("Model returned no audio")
    if isinstance(gout, (list, tuple)) and len(gout) == 0:
        raise ValueError("Model returned empty audio")
    o = gout[0] if isinstance(gout, (list, tuple)) else gout
    if o is None:
        raise ValueError("Model returned no audio")
    return _unwrap_gen_container(o)


def _preprocess_reference_wav(in_path: str, out_path: str, target_sr: int) -> tuple[list[str], float]:
    import torchaudio
    from omnivoice.utils.audio import trim_long_audio

    warnings: list[str] = []
    w, sr = torchaudio.load(in_path)
    if w.dim() == 1:
        w = w.unsqueeze(0)
    if w.size(0) > 1:
        w = w.mean(dim=0, keepdim=True)
    if sr != target_sr:
        w = torchaudio.functional.resample(w, sr, target_sr)
    dur = w.shape[1] / float(target_sr)
    if dur < REF_MIN_WARN_SEC:
        warnings.append(
            f"Reference audio is only {dur:.1f}s; 3–10s of clear speech is recommended."
        )
    w = trim_long_audio(
        w,
        target_sr,
        max_duration=REF_TARGET_MAX_SEC,
        min_duration=2.0,
        trim_threshold=REF_TRIM_THRESHOLD_SEC,
    )
    torchaudio.save(out_path, w, target_sr)
    return warnings, w.shape[1] / float(target_sr)


def _clone_target_duration_seconds(model, ref_text: str, text: str, ref_wav_path: str) -> float | None:
    import torchaudio

    ref_sec: float | None = None
    try:
        w, sr = torchaudio.load(ref_wav_path)
        if w.dim() > 1 and w.size(0) > 1:
            w = w.mean(dim=0, keepdim=True)
        ref_sec = w.shape[1] / float(sr)
    except (OSError, RuntimeError):
        try:
            import wave as _wave
            with _wave.open(ref_wav_path, "rb") as _wf:
                ref_sec = _wf.getnframes() / float(_wf.getframerate())
        except Exception:
            return None
    if ref_sec is None or ref_sec <= 0.05:
        return None

    est = model.duration_estimator
    rw = float(est.calculate_total_weight(ref_text.strip()))
    tw = float(est.calculate_total_weight(text.strip()))
    if tw <= 0:
        return None
    min_rw = max(12.0, ref_sec * 7.0)
    rw_eff = max(rw, min_rw)
    pred_sec = ref_sec * (tw / rw_eff)
    pred_sec = max(0.35, min(pred_sec, 600.0))
    return float(pred_sec)


def _ensure_whisper_pipeline(model) -> None:
    if getattr(model, "_asr_pipe", None) is not None:
        return
    mid = (os.environ.get("OMNIVOICE_WHISPER_MODEL") or "").strip() or "openai/whisper-large-v3-turbo"
    model.load_asr_model(model_name=mid)


def _gen_out_to_chw_tensor(audio) -> "torch.Tensor":
    """Single chunk waveform → 1xN float tensor for torch.cat."""
    import numpy as np
    import torch

    o = _coerce_model_generate_out(audio)
    if isinstance(o, np.ndarray):
        t = torch.from_numpy(np.asarray(o, dtype=np.float32).ravel())
        t = t.clamp(-1.0, 1.0).float()
    elif hasattr(o, "detach"):
        t = o.detach()
        if t.dim() > 1:
            t = t.mean(dim=0) if t.size(0) > 1 else t.squeeze(0)
        t = t.clamp(-1.0, 1.0).float().cpu()
    else:
        t = torch.as_tensor(o, dtype=torch.float32).ravel()
    if t.dim() == 0:
        t = t.view(1)
    return t.unsqueeze(0) if t.dim() == 1 else t


def _http_read_timeout_sec() -> float:
    """
    Per-request read timeout (seconds) for OmniVoice HTTP calls.
    Config `tts.omnivoice_http_read_timeout` overrides; each *single* generate call
    (one text chunk) must finish within this window. Long CPU jobs may need several hours.
    """
    v = config.get("tts.omnivoice_http_read_timeout", None)
    if v is None:
        return float(CHUNK_TIMEOUT)
    try:
        return max(_MIN_READ_TIMEOUT, min(_HTTP_READ_TIMEOUT_MAX, float(v)))
    except (TypeError, ValueError):
        return float(CHUNK_TIMEOUT)


def _http_timeout() -> tuple[float, float]:
    return (_CONNECT_TIMEOUT, _http_read_timeout_sec())


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
    # WebUI `generate-design` only: Hindi → slightly slower pacing
    if mode != "clone":
        _lang = out.get("language") or language
        ls = _lang if isinstance(_lang, str) else str(_lang or "")
        if _is_hindi_language_hint(ls):
            sp = out.get("speed")
            if sp is not None:
                out["speed"] = float(sp) * 0.88
            else:
                out["speed"] = 0.88
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
    def _hard_split_oversize(text: str, max_chars: int) -> list[str]:
        """Last resort: length-based split (prefers word boundaries). No sentence delimiters left."""
        t = text.strip()
        if not t:
            return []
        if len(t) <= max_chars:
            return [t]
        out: list[str] = []
        i = 0
        n = len(t)
        while i < n:
            j = min(i + max_chars, n)
            if j < n:
                window = t[i:j]
                sp = window.rfind(" ")
                if sp > max(8, max_chars // 8):
                    j = i + sp
            piece = t[i:j].strip()
            if piece:
                out.append(piece)
            if j <= i:
                j = i + 1
            i = j
        return out

    @staticmethod
    def _split_raw_sentences(work: str) -> list[str]:
        """Split on `।` `।`-style danda, `.` `!` `?` `…` — keeps natural sentence boundaries."""
        s = (work or "").strip()
        if not s:
            return []
        return [p.strip() for p in re.split(r"(?<=[।.!?…\u0964\u0965])[\s\u00a0]+", s) if p.strip()]

    @staticmethod
    def _split_oversize_natural(text: str, max_chars: int) -> list[str]:
        """
        One *sentence* (no `।.!?` inside) is longer than max_chars: split on commas / colons
        (natural pauses), pack into <= max_chars, then hard-split only if a clause is still too long.
        """
        t = text.strip()
        if not t:
            return []
        if len(t) <= max_chars:
            return [t]
        # Clause boundaries: comma, semicolon, em/en dash, colon (common in Hinglish lists / dialogue)
        parts = re.split(r"(?<=[,;:，；—–])[\s\u00a0]+", t)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) <= 1:
            return OmniVoiceTTS._hard_split_oversize(t, max_chars)
        return OmniVoiceTTS._pack_units(parts, max_chars)

    @staticmethod
    def _pack_units(units: list[str], max_chars: int) -> list[str]:
        """Greedy pack text units (sentences or clauses) into runs of at most `max_chars`."""
        out: list[str] = []
        cur = ""
        for u in units:
            u = (u or "").strip()
            if not u:
                continue
            if len(u) > max_chars:
                if cur:
                    out.append(cur.strip())
                    cur = ""
                out.extend(OmniVoiceTTS._split_oversize_natural(u, max_chars))
                continue
            joiner = f"{cur} {u}" if cur else u
            if cur and len(joiner) > max_chars:
                out.append(cur.strip())
                cur = u
            else:
                cur = joiner
        if cur.strip():
            out.append(cur.strip())
        return out if out else [""]

    @staticmethod
    def _split_text(text: str, max_chars: int | None = None) -> list[str]:
        if max_chars is None:
            max_chars = _text_chunk_size_chars()
        raw = (text or "").strip()
        if not raw:
            return [""]
        if "\n" in raw:
            parts = re.split(r"\n\s*\n+", raw)
            if len(parts) > 1:
                out_para: list[str] = []
                for para in parts:
                    p = (para or "").strip()
                    if not p:
                        continue
                    out_para.extend(OmniVoiceTTS._split_text(p, max_chars))
                return out_para if out_para else [raw]
        work = re.sub(r"[\n\r]+", " ", raw).strip()
        sentences = OmniVoiceTTS._split_raw_sentences(work)
        if not sentences:
            sentences = [work]
        # Atomic units: full sentences, or clause splits only when a sentence is huge
        units: list[str] = []
        for sent in sentences:
            if len(sent) <= max_chars:
                units.append(sent)
            else:
                units.extend(OmniVoiceTTS._split_oversize_natural(sent, max_chars))
        merged = OmniVoiceTTS._pack_units(units, max_chars)
        return merged if merged and merged != [""] else [work]

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
            auto = _use_auto_transcribe_ref()
            data = {
                "text": text,
                "speaking_style": speaking_style,
                "quality_preset": quality_preset,
                "voice_gender": voice_gender,
            }
            if auto:
                # WebUI default: Whisper transcript + duration (same as checked "Auto-transcribe")
                data["auto_transcribe_ref"] = "1"
            else:
                data["ref_text"] = _manual_ref_transcript()

            with open(str(ref_path), "rb") as wav_f:
                resp = requests.post(
                    f"{_server_url()}/generate",
                    files={"ref_audio": ("ref.wav", wav_f, "audio/wav")},
                    data=data,
                    timeout=_http_timeout(),
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
                timeout=_http_timeout(),
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

        text = _normalize_chunking_text((text or "").strip())
        mode = _omnivoice_mode()
        cmax = _text_chunk_size_chars()
        chunks = self._split_text(text)
        n = len(chunks)
        if n > 1:
            self._cb(
                f"🎙️ Voice generate ho raha hai (mode={mode}, {len(text)} chars, "
                f"{n} chunk(s) @ ≤{cmax} chars) …"
            )
        else:
            self._cb(
                f"🎙️ Voice generate ho raha hai (mode={mode}, {len(text)} chars, "
                f"1 chunk @ ≤{cmax} chars) …"
            )

        def _synth_one_chunk(chunk: str, idx: int) -> AudioSegment:
            last_exc: Exception | None = None
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    if attempt > 1:
                        self._cb(f"  🔄 Chunk {idx}/{n} retry {attempt} …")
                    return self._http_generate(chunk, language, mode)
                except Exception as exc:
                    last_exc = exc
                    self._cb(f"  ⚠️ Chunk {idx}/{n} try {attempt} failed: {exc}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY)
            raise RuntimeError(
                f"OmniVoice chunk {idx}/{n} failed after {MAX_RETRIES} tries: {last_exc}"
            ) from last_exc

        audio: AudioSegment | None = None
        for i, ch in enumerate(chunks, start=1):
            if n > 1 and (i == 1 or i % 4 == 0 or i == n):
                self._cb(f"  🎵 Chunk {i}/{n} ({len(ch)} chars) …")
            seg = _synth_one_chunk(ch, i)
            audio = seg if audio is None else (audio + seg)
        if audio is None:
            raise RuntimeError("OmniVoice: no audio produced (empty text?)")

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

    def _synthesize_chunk_pkg(self, call_kw: dict, idx: int, total: int) -> "torch.Tensor":
        last_exc: Exception | None = None
        chunk = (call_kw.get("text") or "")
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    "  [PKG] Chunk %s/%s (try %s) — %s chars",
                    idx, total, attempt, len(chunk),
                )
                with _load_lock:
                    if _model is None:
                        raise RuntimeError("OmniVoice model not loaded")
                    audio = _model.generate(**call_kw)
                return _gen_out_to_chw_tensor(audio)
            except Exception as exc:
                last_exc = exc
                logger.warning("  Chunk %s failed (try %s): %s", idx, attempt, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
        raise RuntimeError(f"OmniVoice chunk {idx} failed: {last_exc}") from last_exc

    def _synthesize_package(self, text: str, language: str, output_path: str) -> str:
        """Direct synthesis via omnivoice pip package (WebUI-matched clone/design)."""
        import torch
        import torchaudio

        text = _normalize_chunking_text((text or "").strip())
        mode = _omnivoice_mode()
        os.makedirs(str(Path(output_path).resolve().parent), exist_ok=True)
        _ensure_model_loaded()
        if _model is None:
            raise RuntimeError("OmniVoice model failed to load")
        m = _model
        sr = int(getattr(m, "sampling_rate", None) or 24000)

        style = config.get("tts.omnivoice_speaking_style", "default")
        quality = config.get("tts.omnivoice_quality_preset", "balanced")
        gender = config.get("tts.omnivoice_voice_gender", "")
        gen_kw, speed_style = _resolve_style_and_quality(style, quality)
        clone_instruct = _instruct_for_clone(style, gender)
        ref_for_dur: str | None = None
        vcp: object | None = None
        tmp_proc: str | None = None
        pre_warnings: list[str] = []
        if mode == "clone":
            raw_ref = str(_ref_audio_path())
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            tmp_proc = tmp.name
            tmp.close()
            try:
                pre_warnings, _ = _preprocess_reference_wav(raw_ref, tmp_proc, sr)
            except Exception as exc:
                for p in (tmp_proc,):
                    try:
                        if p:
                            os.unlink(p)
                    except OSError:
                        pass
                raise RuntimeError(
                    f"Reference WAV preprocess failed ({raw_ref}): {exc}"
                ) from exc
            for w in pre_warnings:
                logger.warning("OmniVoice ref: %s", w)
            if _use_auto_transcribe_ref():
                with _load_lock:
                    _ensure_whisper_pipeline(m)
                    vcp = m.create_voice_clone_prompt(
                        ref_audio=tmp_proc,
                        ref_text=None,
                        preprocess_prompt=True,
                    )
                ref_for_dur = vcp.ref_text
                if ref_for_dur:
                    logger.info("OmniVoice auto ref transcript: %s…", ref_for_dur[:80])
            else:
                man = _manual_ref_transcript()
                if not man:
                    try:
                        if tmp_proc:
                            os.unlink(tmp_proc)
                    except OSError:
                        pass
                    raise RuntimeError(
                        "Manual reference transcript khali hai — Settings → Auto-transcribe ON karo "
                        "ya REF TRANSCRIPT mein WAV ke exact shabd likho."
                    )
                ref_for_dur = man

        design_base: dict | None = _build_design_params(mode, language) if mode == "design" else None
        cmax = _text_chunk_size_chars()
        chunks = self._split_text(text)
        ref_label = (
            Path(_ref_audio_path()).name
            if mode == "clone"
            else "none"
        )
        logger.info(
            "OmniVoice [package:%s]: %s chars → %s chunk(s) (≤%s chars each), ref=%s",
            mode, len(text), len(chunks), cmax, ref_label,
        )

        tensors: list = []
        try:
            for i, chunk in enumerate(chunks, start=1):
                if mode == "design":
                    assert design_base is not None
                    ckw: dict = {**design_base, "text": chunk}
                else:
                    assert tmp_proc is not None
                    ckw = {**gen_kw, "text": chunk}
                    if clone_instruct:
                        ckw["instruct"] = clone_instruct
                    if vcp is not None:
                        ckw["voice_clone_prompt"] = vcp
                    else:
                        ckw["ref_audio"] = tmp_proc
                        ckw["ref_text"] = _manual_ref_transcript()
                    if ref_for_dur:
                        est = _clone_target_duration_seconds(
                            m, ref_for_dur, chunk, tmp_proc
                        )
                        if est is not None:
                            ckw["duration"] = est
                        elif speed_style is not None:
                            ckw["speed"] = speed_style
                    elif speed_style is not None:
                        ckw["speed"] = speed_style

                t = self._synthesize_chunk_pkg(ckw, i, len(chunks))
                tensors.append(t)
            full = torch.cat(tensors, dim=-1)

            tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_wav.close()
            try:
                torchaudio.save(tmp_wav.name, full, sr)
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
            if tmp_proc and os.path.isfile(tmp_proc):
                try:
                    os.unlink(tmp_proc)
                except OSError:
                    pass
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
        if mode == "clone" and (not _use_auto_transcribe_ref()) and not _manual_ref_transcript():
            return (
                False,
                "Reference transcript khali hai jab 'Auto-transcribe reference' OFF hai.\n"
                "Settings → auto-transcribe ON karo (WebUI jaisa) ya REF TRANSCRIPT bharo.",
            )
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
