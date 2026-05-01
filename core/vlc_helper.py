"""
core/vlc_helper.py — Optional VLC (64-bit) discovery for Ghost Editor preview.
Falls back gracefully when VLC or python-vlc is missing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _windows_vlc_roots() -> list[Path]:
    roots: list[Path] = []
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pfx86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    for base in (pf, pfx86):
        if base:
            roots.append(Path(base) / "VideoLAN" / "VLC")
    return roots


def configure_vlc_environment() -> Path | None:
    """
    On Windows, add the VLC install folder to the DLL search path so libvlc loads.
    Returns VLC root path if libvlc.dll is found, else None (non-Windows: always None).
    """
    if sys.platform != "win32":
        return None

    for root in _windows_vlc_roots():
        dll = root / "libvlc.dll"
        if dll.is_file():
            try:
                os.add_dll_directory(str(root))
            except (AttributeError, OSError):
                pass
            plug = root / "plugins"
            if plug.is_dir():
                os.environ["VLC_PLUGIN_PATH"] = str(plug)
            return root
    return None


def get_vlc_instance() -> tuple[object | None, str | None]:
    """
    Create a vlc.Instance for embedding, or (None, user-facing reason).
    Never raises — errors become the reason string.
    """
    if sys.platform == "win32":
        if configure_vlc_environment() is None:
            return None, (
                "VLC 64-bit not found. Install from https://www.videolan.org/vlc/\n"
                "Preview is disabled; editing and assembly still work."
            )

    try:
        import vlc  # type: ignore[import-untyped]
        inst = vlc.Instance("--quiet", "--no-video-title-show", "--avcodec-hw=any")
        if inst is None:
            return None, "VLC instance could not be created."
        return inst, None
    except Exception as exc:
        return None, (
            f"VLC preview unavailable ({exc}).\n"
            "Install VLC 64-bit and: pip install python-vlc\n"
            "You can still edit clips and finish assembly."
        )
