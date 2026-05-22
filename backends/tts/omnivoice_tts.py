"""
backends/tts/omnivoice_tts.py — OmniVoice TTS Backend (server-only)
====================================================================
OmniVoice works only in server mode:

- `tts.omnivoice_server_path` must point to OmniVoice's run.bat
- Backend auto-starts server, waits for readiness, then calls WebUI HTTP endpoints
  `/generate` (clone) or `/generate-design` (design)
- Reference transcript is required in clone mode (WebUI behavior; no Whisper)

OmniVoice weights/torch are NOT bundled in Ghost Creator — install separately
(e.g. D:\\omnivoice\\OmniVoice) and set the server path in Settings.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from pydub import AudioSegment

from backends.base import TTSBackend
from config import get_base_dir, get_ffmpeg_executable
from core.config_manager import config


def _ensure_pydub_ffmpeg() -> None:
    AudioSegment.converter = get_ffmpeg_executable()


_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

logger = logging.getLogger("ghost.tts.omnivoice")

MAX_RETRIES = 2
RETRY_DELAY = 5
CHUNK_TIMEOUT = 18000
_CONNECT_TIMEOUT = 30.0
_MIN_READ_TIMEOUT = 120.0
_HTTP_READ_TIMEOUT_MAX = 86400.0

REF_AUDIO_MAX_DURATION_SEC = 15.0


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
    """Exact words spoken in the reference WAV (required — WebUI no longer uses Whisper)."""
    return (config.get("tts.omnivoice_ref_transcript", "") or "").strip()


def _ref_voice_name_config() -> str:
    """Optional label for WebUI reference_voices.json / transcript memory."""
    return (config.get("tts.omnivoice_ref_voice_name", "") or "").strip()[:120]


def _normalize_input_text(text: str) -> str:
    """Hindi danda / double danda → period+space for consistent TTS input."""
    if not text:
        return text
    t = text.replace("\u0965", ". ")  # ॥
    t = text.replace("\u0964", ". ")  # ।
    return t


def _reference_wav_duration_sec(path: str) -> float | None:
    import wave

    try:
        with wave.open(path, "rb") as wf:
            r = wf.getframerate()
            n = wf.getnframes()
            if r > 0 and n >= 0:
                return n / float(r)
    except (wave.Error, OSError, EOFError):
        pass
    try:
        seg = AudioSegment.from_file(path)
        if seg.frame_rate > 0:
            return len(seg) / 1000.0
    except Exception:
        return None
    return None


def _effective_omnivoice_lang(pipeline_lang: str) -> str:
    """k2-fsa OmniVoice language tag (e.g. Odia ISO `or` → API `ory`)."""
    from modules.tts_lang_support import resolve_omnivoice_language_tag

    hint = (config.get("tts.omnivoice_language_hint", "") or "").strip()
    return resolve_omnivoice_language_tag(pipeline_lang, hint)


def _omnivoice_mode() -> str:
    raw = (config.get("tts.omnivoice_mode", "clone") or "").strip().lower()
    return "design" if raw in {"design", "sound_design", "sound-design"} else "clone"


def _http_read_timeout_sec() -> float:
    v = config.get("tts.omnivoice_http_read_timeout", None)
    if v is None:
        return float(CHUNK_TIMEOUT)
    try:
        return max(_MIN_READ_TIMEOUT, min(_HTTP_READ_TIMEOUT_MAX, float(v)))
    except (TypeError, ValueError):
        return float(CHUNK_TIMEOUT)


def _http_timeout() -> tuple[float, float]:
    return (_CONNECT_TIMEOUT, _http_read_timeout_sec())


def _check_server() -> bool:
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
        subprocess.Popen(
            ["cmd", "/c", str(bat)],
            cwd=str(bat.parent),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    except Exception as exc:
        _notify(f"❌ run.bat launch karne mein error: {exc}")
        return False

    _notify("⏳ Server ke online hone ka wait kar rahe hain (pehli baar mein 2–5 min lag sakte hain) …")
    max_wait = 240
    for i in range(max_wait):
        time.sleep(2)
        if _check_server():
            _notify(f"✅ OmniVoice server online! (~{(i + 1) * 2}s mein ready)")
            return True
        elapsed = (i + 1) * 2
        if elapsed % 20 == 0:
            _notify(f"  ⏳ {elapsed}s ho gaye, ab bhi wait kar rahe hain …")

    _notify(f"❌ OmniVoice server {max_wait * 2 // 60} minutes mein online nahi hua.")
    return False


def _kill_server() -> None:
    """Kill the process listening on the configured port to free VRAM."""
    port = _server_url().rstrip("/").split(":")[-1]
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F", "/T"],
                    capture_output=True,
                    timeout=10,
                    creationflags=_NO_WINDOW,
                )
                logger.info("OmniVoice server killed (PID %s) — VRAM freed.", pid)
                time.sleep(3)
                return
        logger.warning("No process found on port %s — server may already be stopped.", port)
    except Exception as exc:
        logger.warning("Could not kill OmniVoice server: %s", exc)


class OmniVoiceTTS(TTSBackend):
    """OmniVoice TTS — external server only (HTTP to WebUI)."""

    @property
    def name(self) -> str:
        return "OmniVoice TTS"

    @property
    def requires_key(self) -> bool:
        return False

    @property
    def is_local(self) -> bool:
        return True

    def _cb(self, msg: str) -> None:
        logger.info(msg)
        cb = getattr(self, "_progress_cb", None)
        if cb:
            cb(msg)

    def ensure_running(self, language: str = "hi") -> bool:
        cb = getattr(self, "_progress_cb", None)

        if _server_path() is None:
            msg = (
                "OmniVoice server path missing. "
                "Settings → TTS → OMNIVOICE SERVER PATH mein run.bat set karo."
            )
            logger.warning(msg)
            if cb:
                cb(f"❌ {msg}")
            return False

        if _check_server():
            self._cb("✅ OmniVoice server already running — reuse kar rahe hain.")
            return True

        if not config.get("tts.omnivoice_autostart", True):
            logger.warning("OmniVoice server not running and autostart is disabled.")
            if cb:
                cb("⚠️ OmniVoice server nahi chal raha aur autostart OFF hai — manually start karo.")
            return False

        self._cb("🔌 OmniVoice server nahi chal raha — auto-start kar rahe hain …")
        if _start_server(cb=cb):
            return True

        logger.error("OmniVoice server failed to start!")
        return False

    def _wait_for_model_ready(self, timeout_sec: int = 300) -> bool:
        self._cb("⏳ OmniVoice WebUI /api/status check …")
        start = time.time()
        while time.time() - start < timeout_sec:
            try:
                resp = requests.get(f"{_server_url()}/api/status", timeout=5)
                data = resp.json()
                if data.get("error"):
                    self._cb("❌ OmniVoice load error — server console check karo.")
                    return False
                if data.get("defer_load"):
                    self._cb("✅ OmniVoice server ready — GPU pehle HTTP generate par load hoga.")
                    return True
                if data.get("ready"):
                    device = data.get("device", "")
                    self._cb(f"✅ OmniVoice model already in memory ({device})")
                    return True
                device = data.get("device", "")
                if device:
                    self._cb(f"  ⏳ Status… Device: {device}")
            except Exception:
                pass
            time.sleep(5)
        self._cb(f"❌ OmniVoice server {timeout_sec}s tak respond nahi kiya.")
        return False

    def _http_generate(self, text: str, language: str, mode: str) -> AudioSegment:
        speaking_style = config.get("tts.omnivoice_speaking_style", "default")
        quality_preset = config.get("tts.omnivoice_quality_preset", "balanced")
        voice_gender = config.get("tts.omnivoice_voice_gender", "")

        if mode == "clone":
            ref_audio = config.get("tts.reference_audio", "my_voice_reference.wav")
            ref_path = Path(ref_audio)
            if not ref_path.is_absolute():
                ref_path = get_base_dir() / ref_path
            ref_tx = _manual_ref_transcript()
            if not ref_tx:
                raise RuntimeError(
                    "OmniVoice WebUI ab reference transcript maangta hai (Whisper hata diya). "
                    "Settings → tts.omnivoice_ref_transcript mein WAV ke exact shabd likho."
                )
            dur = _reference_wav_duration_sec(str(ref_path))
            if dur is not None and dur > REF_AUDIO_MAX_DURATION_SEC:
                raise RuntimeError(
                    f"Reference audio too long ({dur:.1f}s). Maximum {REF_AUDIO_MAX_DURATION_SEC:g}s "
                    f"(same as OmniVoice WebUI). Trim the file: {ref_path}"
                )
            data = {
                "text": text,
                "speaking_style": speaking_style,
                "quality_preset": quality_preset,
                "voice_gender": voice_gender,
                "ref_text": ref_tx,
            }
            vn = _ref_voice_name_config()
            if vn:
                data["ref_voice_name"] = vn

            lang_ov = _effective_omnivoice_lang(language)
            if lang_ov and lang_ov.lower() not in ("auto", "none", "default"):
                data["language"] = lang_ov

            with open(str(ref_path), "rb") as wav_f:
                resp = requests.post(
                    f"{_server_url()}/generate",
                    files={"ref_audio": ("ref.wav", wav_f, "audio/wav")},
                    data=data,
                    timeout=_http_timeout(),
                )
        else:
            extra_instruct = config.get("tts.omnivoice_extra_instruct", "")
            design_voice = config.get("tts.omnivoice_design_voice", "custom")
            lang_ov = _effective_omnivoice_lang(language)
            form: dict = {
                "text": text,
                "speaking_style": speaking_style,
                "quality_preset": quality_preset,
                "voice_gender": voice_gender,
                "design_voice": design_voice,
            }
            if extra_instruct:
                form["instruct"] = extra_instruct
            if lang_ov and lang_ov.lower() not in ("auto", "none", "default"):
                form["language"] = lang_ov

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
        if not self.ensure_running(language):
            raise RuntimeError(
                "OmniVoice server could not be started. "
                "Settings → TTS → SERVER PATH (run.bat) check karo, "
                "ya manually server start karo."
            )

        if not self._wait_for_model_ready():
            raise RuntimeError(
                "OmniVoice model load nahi hua. "
                "Server console window mein error check karo."
            )

        text = _normalize_input_text((text or "").strip())
        mode = _omnivoice_mode()
        self._cb(
            f"🎙️ Voice generate ho raha hai (mode={mode}, {len(text)} chars, single pass) …"
        )

        last_exc: Exception | None = None
        audio: AudioSegment | None = None
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

        if audio is None:
            raise RuntimeError("OmniVoice: no audio produced (empty text?)")

        audio.export(output_path, format="mp3")
        size_kb = os.path.getsize(output_path) / 1024
        dur_s = len(audio) // 1000
        self._cb(
            f"✅ Voiceover ready! ({size_kb:.0f} KB, {dur_s}s) → {Path(output_path).name}"
        )

        _kill_server()
        return output_path

    async def synthesize(self, text: str, language: str, output_path: str) -> str:
        _ensure_pydub_ffmpeg()
        if _server_path() is None:
            raise RuntimeError(
                "OmniVoice server-only backend mein SERVER PATH required hai. "
                "Settings → TTS → OmniVoice Server Path mein run.bat ka path set karo."
            )
        return await asyncio.to_thread(
            self._synthesize_server, text, language, output_path
        )

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        mode = _omnivoice_mode()
        bat = _server_path()
        if mode == "clone" and not _manual_ref_transcript():
            return (
                False,
                "OmniVoice clone ke liye reference transcript zaroori hai (WebUI mein Whisper hata diya).\n"
                "Settings → tts.omnivoice_ref_transcript mein WAV ke exact shabd likho.\n"
                "Optional: tts.omnivoice_ref_voice_name — WebUI transcript memory ke liye.",
            )
        if bat is None:
            return (
                False,
                "OmniVoice ab server-only hai.\n"
                "Settings → TTS → OMNIVOICE SERVER PATH mein run.bat ka path daalo.",
            )
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
