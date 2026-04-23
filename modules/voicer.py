"""
modules/voicer.py — TTS Dispatcher (Thin Wrapper)
===================================================
Routes voiceover synthesis to the configured TTS backend.
All backend-specific logic lives in backends/tts/*.py
(OmniVoice: sentence/clause–first text split + `tts.omnivoice_text_chunk_chars` / `omnivoice_http_read_timeout` in `backends/tts/omnivoice_tts.py`).

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

    result_path = Path(result).resolve()
    # ── Post-process: loudness + HPF (+ optional silence), no atempo (natural TTS speed) ──
    result_path = _apply_voice_post_process(result_path)

    log.info(f"Voiceover saved → {result_path}")
    return result_path


def _voice_post_enabled() -> bool:
    v = config.get("tts.voice_post_process", 1)
    if isinstance(v, bool):
        return v
    try:
        return int(v) != 0
    except (TypeError, ValueError):
        return True


def _voice_post_target_lufs() -> float:
    v = config.get("tts.voice_post_target_lufs", -16.0)
    try:
        x = float(v)
        return max(-30.0, min(-10.0, x))
    except (TypeError, ValueError):
        return -16.0


def _silence_trim_enabled() -> bool:
    if not _voice_post_enabled():
        return False
    v = config.get("tts.voice_post_silence_trim", 1)
    if isinstance(v, bool):
        return v
    try:
        return int(v) != 0
    except (TypeError, ValueError):
        return True


def _float_cfg(key: str, default: float, lo: float, hi: float) -> float:
    try:
        x = float(config.get(key, default))
        return max(lo, min(hi, x))
    except (TypeError, ValueError):
        return default


def _silence_params() -> tuple[float, float, float]:
    """
    (min_internal_sec, keep_gap_sec, threshold_db)
    min_internal: only treat continuous quiet longer than this as removable dead air
    (keeps short word/sentence gaps).
    keep_gap: when trimming long silences, leave at most this much pause (natural breath).
    """
    mn = _float_cfg("tts.voice_post_silence_min_internal", 0.42, 0.20, 1.20)
    keep = _float_cfg("tts.voice_post_silence_keep", 0.22, 0.10, 0.50)
    thr = _float_cfg("tts.voice_post_silence_threshold_db", -46.0, -60.0, -30.0)
    if keep >= mn * 0.95:
        keep = max(0.10, mn * 0.45)
    return mn, keep, thr


def _voice_post_filter_candidates(lufs: float) -> list[tuple[str, str]]:
    """
    (label, -af) chains — try in order. Silence filters use silenceremove (FFmpeg 4+).
    """
    loud = f"loudnorm=I={lufs}:TP=-1.5:LRA=11:linear=true:print_format=none"
    cands: list[tuple[str, str]] = [
        ("hpf+loudnorm", f"highpass=f=80,{loud}"),
    ]
    if not _silence_trim_enabled():
        return cands

    mn, keep, thr_db = _silence_params()
    thr = f"{thr_db:.1f}dB"
    # start: trim leading quiet; stop_periods=-1: scan whole file; stop_duration: long dead-air only;
    # stop_silence: leave a short natural gap where long silence was removed
    sil_full = (
        f"highpass=f=80,"
        f"silenceremove="
        f"start_periods=1:start_threshold={thr}:start_duration=0.04:start_silence=0:"
        f"detection=peak:window=0.03:stop_mode=any:"
        f"stop_periods=-1:stop_duration={mn:.3f}:stop_threshold={thr}:"
        f"stop_silence={keep:.3f},"
        f"{loud}"
    )
    cands.insert(0, ("hpf+silence+loudnorm", sil_full))

    # Lead + trail only (no middle surgery) — safe fallback
    sil_edges = (
        f"highpass=f=80,"
        f"silenceremove=start_periods=1:start_threshold={thr}:start_duration=0.04:detection=peak:window=0.03,"
        f"areverse,"
        f"silenceremove=start_periods=1:start_threshold={thr}:start_duration=0.04:detection=peak:window=0.03,"
        f"areverse,{loud}"
    )
    cands.insert(1, ("hpf+trim_edges+loudnorm", sil_edges))
    return cands


def _apply_voice_post_process(audio_path: Path) -> Path:
    """
    HPF → optional silenceremove (long dead air collapsed to short gaps) → loudnorm.
    Tries a full internal trim first, then edge-only, then HPF+loudnorm only.
    """
    if not _voice_post_enabled():
        log.debug("Voice post-process OFF — skipping FFmpeg filters")
        return audio_path
    if not audio_path.is_file():
        return audio_path

    lufs = _voice_post_target_lufs()
    tmp_path = audio_path.with_name(audio_path.stem + "_post" + audio_path.suffix)
    suf = audio_path.suffix.lower()
    if suf in (".wav", ".wave"):
        enc_args = ["-c:a", "pcm_s16le"]
    else:
        enc_args = ["-c:a", "libmp3lame", "-q:a", "2"]

    for label, af in _voice_post_filter_candidates(lufs):
        cmd = [
            _FFMPEG, "-y",
            "-i", str(audio_path),
            "-af", af,
            "-vn",
        ] + enc_args + [str(tmp_path)]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                creationflags=_NO_WINDOW,
            )
        except FileNotFoundError:
            log.warning("FFmpeg missing — voice post-process skipped")
            return audio_path
        except subprocess.TimeoutExpired:
            log.warning("Voice post-process timed out — using original audio")
            if tmp_path.is_file():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            return audio_path

        if proc.returncode == 0 and tmp_path.is_file():
            try:
                tmp_path.replace(audio_path)
            except OSError as exc:
                log.warning("Could not replace audio with post-processed file: %s", exc)
                return audio_path
            if _silence_trim_enabled() and "silence" in label:
                mn, keep, _thr = _silence_params()
                log.info(
                    "Voice post (%s) → %s  [min_internal=%.2fs, keep_gap=%.2fs, LUFS=%.1f]",
                    label,
                    audio_path.name,
                    mn,
                    keep,
                    lufs,
                )
            else:
                log.info("Voice post (%s) → %s  [LUFS=%.1f]", label, audio_path.name, lufs)
            return audio_path

        err = (proc.stderr or "")[-500:]
        if tmp_path.is_file():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        log.debug("Voice post try %r failed: %s", label, err)

    log.warning("Voice post-process failed (using original) — all filter chains failed")
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
