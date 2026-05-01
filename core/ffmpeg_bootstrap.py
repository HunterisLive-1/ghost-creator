"""
core/ffmpeg_bootstrap.py — One-time FFmpeg download for lightweight installers
==============================================================================
PyInstaller builds omit FFmpeg (~100MB). On first run of the frozen Windows
app, binaries are downloaded from BtbN builds (same source as ensure_ffmpeg.ps1)
and cached under:

    %LOCALAPPDATA%\\GhostCreatorAI\\ffmpeg\\

**End users do not need Python installed.** The shipped ``GhostCreatorAI.exe``
embeds a Python runtime and libraries (including ``requests``); this module
runs inside that executable.

Developers can still use ``ensure_ffmpeg.ps1`` or PATH for non-frozen runs.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

log = logging.getLogger("ghost.ffmpeg_bootstrap")

# Same archive as ensure_ffmpeg.ps1
FFMPEG_ZIP_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

_USER_AGENT = "GhostCreatorAI-FFmpegBootstrap/4.2.2"


def runtime_ffmpeg_dir() -> Path:
    """Writable directory for ffmpeg.exe / ffprobe.exe (created on demand)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path.home() / ".cache"
    d = base / "GhostCreatorAI" / "ffmpeg"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _exe_names() -> tuple[str, str]:
    if sys.platform == "win32":
        return "ffmpeg.exe", "ffprobe.exe"
    return "ffmpeg", "ffprobe"


def ffmpeg_binaries_present() -> bool:
    """True if cached (or discoverable) FFmpeg + ffprobe exist."""
    ff_n, fp_n = _exe_names()
    rd = runtime_ffmpeg_dir()
    if (rd / ff_n).is_file() and (rd / fp_n).is_file():
        return True
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True
    return False


_download_lock = threading.Lock()


def ensure_ffmpeg_downloaded(
    *,
    progress=None,
    progress_ratio=None,
    ui_tick=None,
) -> Path:
    """
    Ensure ffmpeg + ffprobe exist in ``runtime_ffmpeg_dir()``.

    No-op when not Windows or when binaries already cached / on PATH.
    Raises ``RuntimeError`` on network or extract failure.

    Parameters
    ----------
    progress : Callable[[str], Any] | None
        Status messages for UI.
    progress_ratio : Callable[[float], Any] | None
        0.0–1.0 for progress bars (download ~0–88%%, extract/install to 100%%).
    ui_tick : Callable[[], Any] | None
        Called periodically so Tk can ``update_idletasks()`` during download.
    """
    if sys.platform != "win32":
        if ffmpeg_binaries_present():
            return runtime_ffmpeg_dir()
        raise RuntimeError(
            "FFmpeg is not bundled. Install ffmpeg and ffprobe (e.g. apt install ffmpeg) "
            "or ensure they are on PATH."
        )

    dest = runtime_ffmpeg_dir()
    ff_n, fp_n = _exe_names()
    ff_path = dest / ff_n
    fp_path = dest / fp_n
    if ff_path.is_file() and fp_path.is_file():
        return dest

    with _download_lock:
        if ff_path.is_file() and fp_path.is_file():
            return dest

        if progress:
            progress("Downloading FFmpeg (one-time, ~100 MB)…")
        if progress_ratio:
            progress_ratio(0.02)
        if ui_tick:
            ui_tick()
        log.info("Downloading FFmpeg from %s → %s", FFMPEG_ZIP_URL, dest)

        try:
            import requests
        except ImportError as exc:
            raise RuntimeError("Install the `requests` package to download FFmpeg.") from exc

        tmp_zip: Path | None = None
        extract_root: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as zf:
                tmp_zip = Path(zf.name)

            with requests.get(
                FFMPEG_ZIP_URL,
                stream=True,
                timeout=(30, 600),
                headers={"User-Agent": _USER_AGENT},
            ) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                last_pct_shown = -1
                last_ratio_sent = -1.0
                assumed = 100 * 1024 * 1024  # fallback cap when server omits Content-Length
                with tmp_zip.open("wb") as out:
                    for chunk in resp.iter_content(chunk_size=1024 * 512):
                        if not chunk:
                            continue
                        out.write(chunk)
                        done += len(chunk)
                        if total and progress:
                            pct = min(100, done * 100 // total)
                            if pct >= last_pct_shown + 5 or done >= total:
                                last_pct_shown = pct
                                progress(f"Downloading FFmpeg… {pct}%")
                        elif (not total) and progress and done % (10 * 1024 * 1024) < len(chunk):
                            mb = done // (1024 * 1024)
                            progress(f"Downloading FFmpeg… {mb} MB …")
                        if progress_ratio:
                            if total > 0:
                                r = min(0.88, (done / total) * 0.88)
                            else:
                                r = min(0.85, done / assumed * 0.85)
                            if r >= last_ratio_sent + 0.015 or (total > 0 and done >= total):
                                last_ratio_sent = r
                                progress_ratio(r)
                        if ui_tick:
                            ui_tick()

            if progress:
                progress("Extracting FFmpeg…")
            if progress_ratio:
                progress_ratio(0.92)
            if ui_tick:
                ui_tick()
            extract_root = Path(tempfile.mkdtemp(prefix="gc_ffprobe_"))
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                zf.extractall(extract_root)

            subdirs = [p for p in extract_root.iterdir() if p.is_dir()]
            if not subdirs:
                raise RuntimeError("FFmpeg archive has no top-level folder")
            top = subdirs[0]
            bin_dir = top / "bin"
            if not bin_dir.is_dir():
                raise RuntimeError(f"No bin folder in FFmpeg archive ({top.name})")

            src_ff = bin_dir / ff_n
            src_fp = bin_dir / fp_n
            if not src_ff.is_file() or not src_fp.is_file():
                raise RuntimeError("ffmpeg.exe / ffprobe.exe missing in archive bin/")

            shutil.copy2(src_ff, ff_path)
            shutil.copy2(src_fp, fp_path)
            if progress_ratio:
                progress_ratio(1.0)
            if ui_tick:
                ui_tick()
        finally:
            if tmp_zip is not None and tmp_zip.is_file():
                try:
                    tmp_zip.unlink()
                except OSError:
                    pass
            if extract_root is not None and extract_root.is_dir():
                shutil.rmtree(extract_root, ignore_errors=True)

        log.info("FFmpeg installed to %s", dest)
        if progress:
            progress("FFmpeg ready.")
        return dest


_pydub_patched = False


def configure_pydub_subprocess() -> None:
    """
    Patch pydub so that:
      1. It uses our cached ffmpeg / ffprobe binaries (frozen or dev).
      2. Its subprocess calls never spawn a visible CMD window on Windows.

    Safe to call multiple times (idempotent).  Call once at app startup,
    before any AudioSegment operations.
    """
    global _pydub_patched
    if _pydub_patched:
        return
    _pydub_patched = True

    try:
        import pydub
        import pydub.utils

        # ── point pydub at our ffmpeg / ffprobe binaries ──────────────────
        ff_dir = runtime_ffmpeg_dir()
        ff_n, fp_n = _exe_names()
        ff_exe = ff_dir / ff_n
        fp_exe = ff_dir / fp_n

        # Also check PATH fallbacks
        if not ff_exe.is_file():
            _found = shutil.which("ffmpeg")
            if _found:
                ff_exe = Path(_found)
        if not fp_exe.is_file():
            _found = shutil.which("ffprobe")
            if _found:
                fp_exe = Path(_found)

        if ff_exe.is_file():
            pydub.AudioSegment.converter = str(ff_exe)
        if fp_exe.is_file():
            pydub.AudioSegment.ffprobe = str(fp_exe)

        # ── suppress CMD window flash on Windows ──────────────────────────
        if sys.platform == "win32":
            import subprocess as _sp

            _OrigPopen = pydub.utils.Popen

            class _SilentPopen(_OrigPopen):  # type: ignore[misc]
                def __init__(self, args, **kwargs):
                    kwargs.setdefault("creationflags", _sp.CREATE_NO_WINDOW)
                    # Ensure null handles so a windowless parent doesn't cause hangs
                    kwargs.setdefault("stdin", _sp.DEVNULL)
                    super().__init__(args, **kwargs)

            pydub.utils.Popen = _SilentPopen

    except Exception:
        pass  # pydub not installed or import failed — waveforms just won't render


def prepare_ffmpeg_runtime(*, progress=None, progress_ratio=None, ui_tick=None) -> None:
    """
    For frozen Windows .exe only: download FFmpeg if missing.
    Silent no-op when not frozen or when binaries already available.
    """
    if not getattr(sys, "frozen", False):
        return
    if sys.platform != "win32":
        return
    if ffmpeg_binaries_present():
        return
    ensure_ffmpeg_downloaded(progress=progress, progress_ratio=progress_ratio, ui_tick=ui_tick)
