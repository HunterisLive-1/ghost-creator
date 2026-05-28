"""FFmpeg-safe renderer for Ghost Editor schema v2 projects."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from config import get_ffmpeg_executable
from core.config_manager import config
from modules.documentary_assembler import assemble_documentary, wants_burned_subtitles

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _ffmpeg(*args: str, timeout: int = 7200, cwd: Path | None = None) -> None:
    cmd = [get_ffmpeg_executable(), "-y", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_NO_WINDOW,
        cwd=str(cwd) if cwd else None,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "FFmpeg failed")[-4000:])


def validate_editor_v2(project: dict, run_dir: Path) -> list[str]:
    errors: list[str] = []
    assets = {str(a.get("id")): a for a in project.get("assets") or [] if isinstance(a, dict)}
    tracks = {str(t.get("id")): t for t in project.get("tracks") or [] if isinstance(t, dict)}
    items = project.get("items") or []
    if not tracks:
        errors.append("No tracks found in editor project")
    if not items:
        errors.append("No timeline items found in editor project")
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "unknown")
        start = float(item.get("start") or 0)
        end = float(item.get("end") or 0)
        if end <= start:
            errors.append(f"{item_id}: end time must be after start time")
        track_id = str(item.get("trackId") or "")
        if track_id not in tracks:
            errors.append(f"{item_id}: missing track {track_id}")
        asset_id = item.get("assetId")
        if asset_id:
            asset = assets.get(str(asset_id))
            if not asset:
                errors.append(f"{item_id}: missing asset {asset_id}")
            else:
                path = Path(str(asset.get("path") or ""))
                if not path.is_absolute():
                    path = run_dir / path
                if not path.is_file():
                    errors.append(f"{item_id}: asset file not found: {path}")
    return errors


def _asset_path(asset: dict, run_dir: Path) -> Path:
    path = Path(str(asset.get("path") or ""))
    return path if path.is_absolute() else run_dir / path


def _legacy_segments_from_v2(project: dict) -> tuple[list[dict], list[Path | None]]:
    assets = {str(a.get("id")): a for a in project.get("assets") or [] if isinstance(a, dict)}
    tracks = {str(t.get("id")): t for t in project.get("tracks") or [] if isinstance(t, dict)}
    main_video_track = next(
        (tid for tid, t in tracks.items() if t.get("type") == "video"),
        "video-main",
    )
    video_items = [
        item for item in project.get("items") or []
        if item.get("trackId") == main_video_track and item.get("kind") == "video"
    ]
    video_items.sort(key=lambda item: float(item.get("start") or 0))
    segments: list[dict] = []
    clips: list[Path | None] = []
    for item in video_items:
        asset = assets.get(str(item.get("assetId")))
        dur = max(0.5, float(item.get("end") or 0) - float(item.get("start") or 0))
        segments.append({
            "voiceover": item.get("voiceover", ""),
            "video_query": item.get("video_query", ""),
            "duration_hint": dur,
            "clip_name": asset.get("name") if asset else "",
            "transition": item.get("transition"),
            "effect": item.get("effect"),
        })
        clips.append(Path(str(asset.get("path"))) if asset else None)
    return segments, clips


def _drawtext_filter(item: dict, width: int = 1080, height: int = 1920) -> str:
    text = str(item.get("text") or "").replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    transform = item.get("transform") or {}
    style = item.get("style") or {}
    x = int(float(transform.get("x", 0.5)) * width)
    y = int(float(transform.get("y", 0.5)) * height)
    alpha = max(0.0, min(1.0, float(transform.get("opacity", 1))))
    size = int(style.get("font_size") or style.get("fontSize") or 48)
    color = str(style.get("color") or "white").replace("#", "0x")
    start = float(item.get("start") or 0)
    end = float(item.get("end") or start + 1)
    return (
        "drawtext="
        f"text='{text}':x={x}:y={y}:fontsize={size}:fontcolor={color}@{alpha:.3f}:"
        f"box=0:enable='between(t,{start:.3f},{end:.3f})'"
    )


def _apply_text_overlays(video_path: Path, project: dict, tmp: Path, log: Callable[[str], None]) -> Path:
    text_items = [
        item for item in project.get("items") or []
        if item.get("kind") in {"text", "subtitle"} and str(item.get("text") or "").strip()
    ]
    if not text_items:
        return video_path
    log(f"Applying {len(text_items)} text overlays...")
    vf = ",".join(_drawtext_filter(item) for item in text_items)
    out = tmp / "text_overlay.mp4"
    _ffmpeg(
        "-i", str(video_path),
        "-vf", vf,
        "-c:a", "copy",
        "-c:v", "libx264", "-crf", "22", "-preset", "fast",
        str(out),
    )
    return out


def _apply_image_overlays(video_path: Path, project: dict, run_dir: Path, tmp: Path, log: Callable[[str], None]) -> Path:
    assets = {str(a.get("id")): a for a in project.get("assets") or [] if isinstance(a, dict)}
    image_items = [
        item for item in project.get("items") or []
        if item.get("kind") in {"image", "logo"} and item.get("assetId") in assets
    ]
    current = video_path
    for idx, item in enumerate(image_items):
        asset = assets[str(item.get("assetId"))]
        image_path = _asset_path(asset, run_dir)
        if not image_path.is_file():
            continue
        log(f"Applying image overlay {idx + 1}/{len(image_items)}...")
        transform = item.get("transform") or {}
        scale = max(0.05, min(3.0, float(transform.get("scale", 1))))
        opacity = max(0.0, min(1.0, float(transform.get("opacity", 1))))
        x = f"(main_w-overlay_w)*{float(transform.get('x', 0.5)):.5f}"
        y = f"(main_h-overlay_h)*{float(transform.get('y', 0.5)):.5f}"
        start = float(item.get("start") or 0)
        end = float(item.get("end") or start + 1)
        out = tmp / f"image_overlay_{idx:02d}.mp4"
        overlay_chain = (
            f"[1:v]scale=iw*{scale:.5f}:ih*{scale:.5f},format=rgba,"
            f"colorchannelmixer=aa={opacity:.5f}[ov];"
            f"[0:v][ov]overlay={x}:{y}:enable='between(t,{start:.3f},{end:.3f})'[v]"
        )
        _ffmpeg(
            "-i", str(current),
            "-i", str(image_path),
            "-filter_complex", overlay_chain,
            "-map", "[v]",
            "-map", "0:a?",
            "-c:a", "copy",
            "-c:v", "libx264", "-crf", "22", "-preset", "fast",
            str(out),
        )
        current = out
    return current


def render_editor_v2(run_dir: Path, project: dict, log: Callable[[str], None]) -> Path:
    errors = validate_editor_v2(project, run_dir)
    if errors:
        raise ValueError("Editor project is not exportable:\n" + "\n".join(errors[:12]))

    segments, clips = _legacy_segments_from_v2(project)
    if not segments:
        raise ValueError("No primary video items found for export")

    audio_path = run_dir / "voiceover_recorded.mp3"
    if not audio_path.is_file():
        audio_path = run_dir / "voiceover.mp3"
    if not audio_path.is_file():
        audio_path = run_dir / "voiceover_processed.mp3"
    if not audio_path.is_file():
        raise FileNotFoundError("voiceover.mp3 not found")

    bg_music_path = None
    bg_music_val = project.get("bg_music")
    if bg_music_val:
        p = Path(str(bg_music_val))
        if not p.is_file():
            p = Path("assets/stock/music") / str(bg_music_val)
        if p.is_file():
            bg_music_path = p

    tmp_dir = Path(tempfile.mkdtemp(prefix="ghost_editor_v2_"))
    try:
        base = assemble_documentary(
            clips=clips,
            audio_path=audio_path,
            segments=segments,
            output_dir=tmp_dir,
            output_filename="base.mp4",
            aspect_ratio=str(project.get("aspect_ratio") or config.get("aspect_ratio", "9:16")),
            progress_callback=log,
            playback_speed=float(config.get("documentary.playback_speed", 1.0)),
            burn_subtitles=bool(project.get("burn_subtitles", wants_burned_subtitles(config))),
            subtitle_style=project.get("subtitle_style"),
            bg_music_path=bg_music_path,
            bg_music_volume=float(project.get("bg_music_volume", 0.25) or 0.25),
            logo_watermark={"enabled": False},
        )
        overlaid = _apply_text_overlays(base, project, tmp_dir, log)
        overlaid = _apply_image_overlays(overlaid, project, run_dir, tmp_dir, log)
        out_name = f"documentary_reedit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        final = run_dir / out_name
        shutil.copy2(overlaid, final)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    he = run_dir / "history_entry.json"
    if he.exists():
        try:
            h = json.loads(he.read_text(encoding="utf-8"))
            h["video_path"] = str(final)
            he.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return final
