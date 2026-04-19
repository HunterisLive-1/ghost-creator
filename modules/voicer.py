"""
modules/voicer.py — TTS Dispatcher (Thin Wrapper)
===================================================
Routes voiceover synthesis to the configured TTS backend.
All backend-specific logic lives in backends/tts/*.py.

Usage:
    from modules.voicer import run_voiceover, ensure_tts_ready

    ensure_tts_ready()              # Validates config + starts server if needed
    path = run_voiceover(text, language, output_path)
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from config import get_base_dir, get_ffmpeg_executable, get_logger
from core.config_manager import config

_FFMPEG = get_ffmpeg_executable()

# Suppress CMD window flash on Windows for all subprocess calls
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Pace → atempo multiplier (FFmpeg atempo: 0.5–2.0)
PACE_ATEMPO = {
    "slow":   0.85,   # ~15% slower speech
    "medium": 1.0,    # no change
    "fast":   1.18,   # ~18% faster speech
}

log = get_logger("voicer")

# ── Backend registry ──────────────────────────────────────────────────────────
# Lazy imports to avoid loading unused heavy SDKs

BACKEND_MAP: dict[str, type] = {}


def _get_backend_map() -> dict[str, type]:
    """Return a map of backend name → class, importing only the selected backend."""
    global BACKEND_MAP
    if BACKEND_MAP:
        return BACKEND_MAP

    # Import each backend lazily so a missing optional dependency only fails
    # when that backend is actually used.
    def _load(module_path: str, class_name: str):
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)

    BACKEND_MAP = {
        "omnivoice":   lambda: _load("backends.tts.omnivoice_tts", "OmniVoiceTTS"),
        "elevenlabs":  lambda: _load("backends.tts.elevenlabs", "ElevenLabsTTS"),
        "edge_tts":    lambda: _load("backends.tts.edge_tts", "EdgeTTS"),
        "google_tts":  lambda: _load("backends.tts.google_tts", "GoogleTTS"),
    }
    return BACKEND_MAP


def _get_backend():
    """Instantiate the configured TTS backend."""
    backend_name = config.get("tts.backend", "omnivoice")
    backend_map = _get_backend_map()

    if backend_name not in backend_map:
        raise ValueError(
            f"Unknown TTS backend: {backend_name!r}. "
            f"Available: {list(backend_map.keys())}"
        )

    # Each entry is a loader lambda that imports the class on first call
    backend_cls = backend_map[backend_name]()
    backend = backend_cls()
    log.info(f"TTS backend: {backend.name} (local={backend.is_local}, key={backend.requires_key})")
    return backend


# ── Public API ────────────────────────────────────────────────────────────────

def ensure_tts_ready() -> bool:
    """
    Validate the configured TTS backend is ready.
    For backends with ensure_running (e.g. legacy flows): may start services.
    Returns True if ready.
    """
    backend = _get_backend()

    if hasattr(backend, "ensure_running"):
        language = config.get("pipeline.language", "hi")
        return backend.ensure_running(language)

    # For other backends, validate config
    valid, error = backend.validate_config(config.data)
    if not valid:
        log.error(f"TTS backend {backend.name} config invalid: {error}")
        return False
    return True


def run_voiceover(
    text: str,
    language: str | None = None,
    output_path: str | Path | None = None,
    progress_callback=None,
) -> Path:
    """
    Synthesize voiceover text using the configured TTS backend.

    Parameters
    ----------
    text : str
        The text to convert to speech.
    language : str, optional
        Language code ("hi", "en", etc.). Defaults to pipeline.language from config.
    output_path : str or Path, optional
        Where to save the audio. Defaults to ``<get_base_dir()>/temp/voiceover.mp3``.

    Returns
    -------
    Path
        Path to the generated audio file.
    """
    if language is None:
        language = config.get("pipeline.language", "hi")
    if output_path is None:
        output_path = get_base_dir() / "temp" / "voiceover.mp3"

    output_path = Path(output_path).resolve()
    os.makedirs(str(output_path.parent), exist_ok=True)
    voiceover_path = str(output_path)
    print(f"[DEBUG] Voiceover output path: {voiceover_path}")

    backend = _get_backend()

    # Give the backend a progress hook so it can emit GUI-visible messages
    if progress_callback is not None:
        backend._progress_cb = progress_callback

    # Validate backend config
    valid, error = backend.validate_config(config.data)
    if not valid:
        raise ValueError(f"TTS backend {backend.name} config error: {error}")

    log.info(f"Generating voiceover with {backend.name} ({len(text)} chars, lang={language})")

    # Run the async synthesize method
    result = asyncio.run(backend.synthesize(text, language, voiceover_path))

    # ── Apply pace-based speed adjustment via FFmpeg atempo ─────────────────
    result_path = _apply_pace_speed(Path(result).resolve())

    log.info(f"Voiceover saved → {result_path}")
    return result_path


def _apply_pace_speed(audio_path: Path) -> Path:
    """
    Re-encode the audio with FFmpeg atempo filter to match the selected video_pace.
    Pace mapping: slow=0.85x  medium=1.0x  fast=1.18x
    Returns the same path (in-place replacement).
    """
    pace = config.get("video_pace", "medium")
    atempo = PACE_ATEMPO.get(pace, 1.0)

    if abs(atempo - 1.0) < 0.01:
        log.debug("Pace=medium — skipping atempo (no speed change needed)")
        return audio_path

    log.info(f"Applying pace speed: {pace!r} → atempo={atempo}x on {audio_path.name}")

    tmp_path = audio_path.with_name(audio_path.stem + "_paced" + audio_path.suffix)
    cmd = [
        _FFMPEG, "-y",
        "-i", str(audio_path),
        "-filter:a", f"atempo={atempo}",
        "-vn",
        "-c:a", "libmp3lame", "-q:a", "2",
        str(tmp_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, creationflags=_NO_WINDOW)
    except FileNotFoundError as exc:
        log.error(
            "FFmpeg not found (needed for video pace). Install FFmpeg and add it to PATH, "
            "or place ffmpeg.exe + ffprobe.exe in an ffmpeg folder next to the app."
        )
        raise RuntimeError(
            "FFmpeg is required for pace/speed adjustment but was not found. "
            "Install FFmpeg or bundle ffmpeg/ffmpeg.exe next to the application."
        ) from exc
    if result.returncode != 0:
        log.warning(f"atempo filter failed (will use original): {result.stderr[-200:]}")
        return audio_path

    # Replace original with paced version
    tmp_path.replace(audio_path)
    log.info(f"Pace speed applied ({atempo}x) → {audio_path.name}")
    return audio_path


# ── Legacy compatibility ──────────────────────────────────────────────────────
# These functions maintain backward compatibility with main.py

def generate_voiceover(text: str, output_filename: str = "voiceover.mp3") -> Path:
    """Legacy wrapper — calls run_voiceover with default settings."""
    output_path = get_base_dir() / "temp" / output_filename
    return run_voiceover(text, output_path=output_path)




if __name__ == "__main__":
    sample = (
        "What if AI could replace every developer on the planet within three years? "
        "Here's what's actually happening inside the world's most secretive AI labs."
    )
    path = run_voiceover(sample, language="en")
    print(f"Output: {path}")
