"""
modules/video_fetcher.py
========================
Downloads real footage clips for documentary mode.

Priority:
  1. Pexels API  — free HD stock footage, no slideshows, very fast direct download.
                   Requires api_keys.pexels in config (free at pexels.com/api).
  2. yt-dlp      — YouTube fallback. Uses --download-sections to grab only the
                   first 90 s instead of the whole video (huge speed improvement).
                   Appends "footage b-roll" to queries to avoid photo slideshows.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from config import get_logger
from core.config_manager import config

log = get_logger("video_fetcher")

# Hide console window when yt-dlp runs on Windows (frozen .exe / python -m yt_dlp)
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_CB = Callable[[str], None] | None

# How many seconds to download from YouTube when Pexels fails.
# The assembler will trim the clip further if needed.
_YT_SECTION_SECS = 90


# ── Helpers ───────────────────────────────────────────────────────────────────

def _notify(fn: _CB, msg: str) -> None:
    log.info(msg)
    if fn:
        fn(msg)


def _yt_dlp_cmd() -> list[str]:
    """How to run yt-dlp: frozen .exe uses bundled module; dev uses PATH or python -m."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "-m", "yt_dlp"]
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    return [sys.executable, "-m", "yt_dlp"]


def _run_yt_dlp(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            _yt_dlp_cmd() + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        raise RuntimeError(
            "yt-dlp not found. Install: pip install yt-dlp (or add yt-dlp to PATH)."
        )
    except subprocess.TimeoutExpired:
        return 1, "", "yt-dlp timed out"


def _find_output(output_path: Path) -> Path | None:
    """Return the actual file yt-dlp wrote (extension varies)."""
    stem = output_path.stem
    for ext in (".mp4", ".mkv", ".webm", ".m4v", ""):
        candidate = output_path.with_suffix(ext) if ext else output_path
        if candidate.exists() and candidate.stat().st_size > 10_000:
            return candidate
    # Broad glob — yt-dlp sometimes appends video ID
    for match in sorted(output_path.parent.glob(f"{stem}*")):
        if match.stat().st_size > 10_000:
            return match
    return None


# ── Source 1: Pexels ──────────────────────────────────────────────────────────

def _try_pexels(
    query: str,
    output_path: Path,
    progress_callback: _CB,
) -> Path | None:
    """
    Search Pexels for a landscape video matching *query*, download it directly.
    Returns the output path on success, None if API key missing or search fails.
    """
    api_key = config.get("api_keys.pexels", "").strip()
    if not api_key:
        return None

    # Strip any invisible non-ASCII chars (e.g. Unicode BOM copied from browser)
    # HTTP headers must be latin-1 encodable; ASCII-only keys are always safe.
    api_key = api_key.encode("ascii", errors="ignore").decode("ascii").strip()
    if not api_key:
        return None

    try:
        import requests as _req

        # Pick orientation to match the project aspect ratio
        aspect_ratio = config.get("aspect_ratio", "9:16")
        orientation = "portrait" if aspect_ratio == "9:16" else "landscape"

        # Ensure the query is ASCII-safe for the URL params
        safe_query = query.encode("ascii", errors="ignore").decode("ascii").strip()
        if not safe_query:
            safe_query = query[:80]   # last resort: let requests handle it

        _notify(progress_callback, f"  🎬 Searching Pexels ({orientation}) …")
        resp = _req.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": api_key},
            params={
                "query": safe_query,
                "per_page": 5,
                "orientation": orientation,
                "size": "medium",   # small / medium / large
            },
            timeout=15,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])

        if not videos:
            _notify(progress_callback, "  ⚠️ Pexels: no results — trying YouTube …")
            return None

        # Find best ≤720 p MP4 link
        download_url = None
        for vid in videos:
            files = vid.get("video_files", [])
            # Prefer HD files ≤720 p
            hd = [
                f for f in files
                if f.get("file_type", "") == "video/mp4"
                and 0 < f.get("height", 0) <= 720
            ]
            hd.sort(key=lambda f: f.get("height", 0), reverse=True)
            if hd:
                download_url = hd[0]["link"]
                break
            # Fallback: any mp4
            any_mp4 = [f for f in files if f.get("file_type", "") == "video/mp4"]
            if any_mp4:
                download_url = any_mp4[0]["link"]
                break

        if not download_url:
            _notify(progress_callback, "  ⚠️ Pexels: no MP4 file found — trying YouTube …")
            return None

        # Stream-download the file
        with _req.get(download_url, stream=True, timeout=60) as dl:
            dl.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as fh:
                for chunk in dl.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                    fh.write(chunk)

        if output_path.exists() and output_path.stat().st_size > 10_000:
            size_kb = output_path.stat().st_size // 1024
            _notify(
                progress_callback,
                f"  ✅ Pexels clip: {output_path.name} ({size_kb} KB)",
            )
            return output_path

    except Exception as exc:
        _notify(progress_callback, f"  ⚠️ Pexels error: {exc} — trying YouTube …")

    return None


# ── Source 2: YouTube via yt-dlp ──────────────────────────────────────────────

def _try_youtube(
    query: str,
    output_path: Path,
    progress_callback: _CB,
) -> Path | None:
    """
    Search YouTube for *query*, download only the first ~90 seconds.
    Appends 'footage b-roll' to the query to avoid photo slideshows.
    """
    # Append footage keywords so YouTube prefers real video over slideshows
    yt_query = f"{query} footage b-roll"
    _notify(progress_callback, f"  🔍 YouTube search: {yt_query!r}")

    stem = output_path.stem
    out_template = str(output_path.parent / f"{stem}.%(ext)s")

    section = f"*00:00:00-00:00:{_YT_SECTION_SECS:02d}"

    args = [
        f"ytsearch5:{yt_query}",
        # Download only the first N seconds — huge speed improvement
        "--download-sections", section,
        # Format: prefer real video streams, ≤720 p
        "-f", (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=720][ext=mp4]+bestaudio"
            "/bestvideo[height<=720]+bestaudio"
            "/best[height<=720]"
            "/best"
        ),
        "--merge-output-format", "mp4",
        "-o", out_template,
        "--no-playlist",
        "--max-downloads", "1",
        "--no-warnings",
        "--socket-timeout", "30",
        "--retries", "3",
        "--fragment-retries", "3",
        # Hard cap — avoids accidentally downloading huge files
        "--max-filesize", "150M",
        # Speed up fragment downloads
        "--concurrent-fragments", "4",
    ]

    rc, out, err = _run_yt_dlp(args, timeout=180)

    found = _find_output(output_path)
    if found:
        if found != output_path:
            found.rename(output_path)
        size_kb = output_path.stat().st_size // 1024
        _notify(
            progress_callback,
            f"  ✅ YouTube clip: {output_path.name} ({size_kb} KB)",
        )
        return output_path

    detail = (err or out).strip()[:300]
    _notify(progress_callback, f"  ⚠️ YouTube: clip not found (rc={rc}): {detail}")
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def download_clip(
    query: str,
    output_path: Path,
    max_duration: int = 120,   # kept for API compatibility, not used as hard filter
    progress_callback: _CB = None,
) -> Path | None:
    """
    Download a footage clip for *query*.

    Tries Pexels first (fast, real footage), then YouTube as fallback.
    Returns the Path on success, None on failure.
    """
    # 1 — Pexels (needs API key in settings)
    result = _try_pexels(query, output_path, progress_callback)
    if result:
        return result

    # 2 — YouTube via yt-dlp
    return _try_youtube(query, output_path, progress_callback)


def fetch_clips(
    segments: list[dict],
    output_dir: Path,
    max_clip_duration: int = 120,
    progress_callback: _CB = None,
) -> list[Path | None]:
    """
    Download one footage clip per script segment.

    Args:
        segments:          list of dicts with ``video_query`` key
        output_dir:        where to save clip_01.mp4 … clip_N.mp4
        max_clip_duration: hint passed through to download_clip
        progress_callback: optional fn(str) for GUI updates

    Returns:
        list[Path | None] — None where download failed
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Path | None] = []
    total = len(segments)

    for i, seg in enumerate(segments, 1):
        query = seg.get("video_query", "")
        if not query:
            query = seg.get("voiceover", "nature scenery documentary")[:60]

        _notify(progress_callback, f"📥 Fetching clip {i}/{total}: {query!r}")
        clip_path = output_dir / f"clip_{i:02d}.mp4"

        result = download_clip(query, clip_path, max_clip_duration, progress_callback)
        clips.append(result)

        # Small polite pause between requests
        if i < total:
            time.sleep(1)

    success = sum(1 for c in clips if c is not None)
    _notify(progress_callback, f"📥 Clips ready: {success}/{total} downloaded")
    return clips


def footage_source_label() -> str:
    src = (config.get("documentary.footage_source") or "stock").strip().lower()
    if src == "meta_ai":
        return "Meta AI (browser)"
    if src == "grok":
        return "Grok (browser)"
    return "Stock (Pexels + YouTube)"


def fetch_clips_for_pipeline(
    segments: list[dict],
    output_dir: Path,
    max_clip_duration: int = 120,
    progress_callback: _CB = None,
) -> list[Path | None]:
    """
    Route footage download to stock (Pexels/yt-dlp) or AI browser automation.
    """
    source = (config.get("documentary.footage_source") or "stock").strip().lower()
    if source == "meta_ai":
        from modules.ai_video.meta_ai_browser import fetch_clips_meta_ai

        return fetch_clips_meta_ai(
            segments,
            output_dir,
            max_clip_duration=max_clip_duration,
            progress_callback=progress_callback,
        )
    if source == "grok":
        from modules.ai_video.grok_browser import fetch_clips_grok

        return fetch_clips_grok(
            segments,
            output_dir,
            max_clip_duration=max_clip_duration,
            progress_callback=progress_callback,
        )
    return fetch_clips(
        segments,
        output_dir,
        max_clip_duration=max_clip_duration,
        progress_callback=progress_callback,
    )
