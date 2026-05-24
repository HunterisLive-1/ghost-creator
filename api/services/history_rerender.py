"""History re-render logic ported from gui/tabs/history_tab.py."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from core.clip_manager import load_clips
from core.config_manager import config
from modules.documentary_assembler import assemble_documentary, wants_burned_subtitles

_EDIT_CLIP_STEM_RE = re.compile(r"^e[_-]?(\d+)$", re.IGNORECASE)


def _sort_clips_for_edit(paths: list[Path]) -> list[Path]:
    def sort_key(p: Path) -> tuple[int, int, str]:
        m = _EDIT_CLIP_STEM_RE.match(p.stem)
        if m:
            return (0, int(m.group(1)), p.name.lower())
        return (1, 0, p.name.lower())

    return sorted(paths, key=sort_key)


def _glob_clips_for_edit(folder: Path) -> list[Path]:
    cf_dir = folder / "clips_for_edit"
    if not cf_dir.is_dir():
        return []
    return _sort_clips_for_edit([p for p in cf_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"])


def _resolve_edit_clip_paths(folder: Path, n_segments: int) -> list[Path]:
    numbered = [p for p in _glob_clips_for_edit(folder) if _EDIT_CLIP_STEM_RE.match(p.stem)]
    numbered = _sort_clips_for_edit(numbered)
    if len(numbered) >= n_segments:
        return numbered[:n_segments]

    cfe_legacy = _sort_clips_for_edit(list(folder.glob("clips_for_edit/e_*.mp4")))
    if len(cfe_legacy) >= n_segments:
        return cfe_legacy[:n_segments]

    raw = sorted(folder.glob("clips/*.mp4"))
    if len(raw) >= n_segments:
        return raw[:n_segments]

    trimmed = sorted(folder.glob("clips_trimmed/t_*.mp4"))
    if len(trimmed) >= n_segments:
        return trimmed[:n_segments]

    fallback = _glob_clips_for_edit(folder)
    if len(fallback) >= n_segments:
        return fallback[:n_segments]

    merged = sorted(folder.glob("clips_for_edit/*.mp4"))
    if len(merged) >= n_segments:
        return merged[:n_segments]
    return []


def _history_run_aspect_ratio(folder: Path) -> str:
    snap = folder / "documentary_editor.json"
    if snap.exists():
        try:
            data = json.loads(snap.read_text(encoding="utf-8"))
            if data.get("aspect_ratio"):
                return str(data["aspect_ratio"])
        except Exception:
            pass
    return str(config.get("aspect_ratio", "9:16"))


def _ffmpeg_rerender_audio_path(folder: Path, fallback_audio: Path) -> Path:
    rec = folder / "voiceover_recorded.mp3"
    if rec.is_file():
        return rec
    vo = folder / "voiceover.mp3"
    return vo if vo.is_file() else fallback_audio


def rerender_run(run_dir: Path, log: Callable[[str], None]) -> Path:
    """Re-assemble MP4 from documentary_editor.json + per-segment clips."""
    snap = run_dir / "documentary_editor.json"
    if not snap.is_file():
        raise FileNotFoundError("documentary_editor.json not found — cannot re-render.")

    run_snapshot = json.loads(snap.read_text(encoding="utf-8"))
    segments = run_snapshot.get("segments") or []
    if not segments:
        raise ValueError("No segments in documentary_editor.json")

    # Load clip paths by checking if a clip_name is defined in the segment
    clip_paths = []
    default_clip_paths = _resolve_edit_clip_paths(run_dir, len(segments))
    for i, seg in enumerate(segments):
        clip_name = seg.get("clip_name")
        if clip_name:
            # Try to resolve relative to clips_for_edit or run_dir
            p = run_dir / "clips_for_edit" / clip_name
            if not p.is_file():
                p = run_dir / "clips" / clip_name
            if not p.is_file():
                p = run_dir / clip_name
            if p.is_file():
                clip_paths.append(p)
                continue
        # Fallback to the default sorted list
        if i < len(default_clip_paths):
            clip_paths.append(default_clip_paths[i])
        else:
            clip_paths.append(None)

    clips = clip_paths
    audio_fallback = run_dir / "voiceover_processed.mp3"
    if not audio_fallback.is_file():
        audio_fallback = run_dir / "voiceover.mp3"
    audio_path = _ffmpeg_rerender_audio_path(run_dir, audio_fallback)

    aspect_ratio = _history_run_aspect_ratio(run_dir)
    _pb = float(config.get("documentary.playback_speed", 1.0))
    _burn = wants_burned_subtitles(config)

    logo_watermark = None
    if config.get("documentary.logo_enabled", False):
        lp = config.get("documentary.logo_path", "")
        if lp and Path(lp).is_file():
            logo_watermark = {
                "path": lp,
                "position": config.get("documentary.logo_position", "bottom_right"),
                "scale": float(config.get("documentary.logo_scale", 0.15)),
                "margin": int(config.get("documentary.logo_margin", 24)),
                "opacity": float(config.get("documentary.logo_opacity", 1.0)),
            }

    bg_music_val = run_snapshot.get("bg_music")
    bg_music_path = None
    if bg_music_val:
        if Path(bg_music_val).is_file():
            bg_music_path = Path(bg_music_val)
        else:
            p = Path("assets/stock/music") / bg_music_val
            if p.is_file():
                bg_music_path = p

    bg_music_volume = float(run_snapshot.get("bg_music_volume", 0.25))
    subtitle_style = run_snapshot.get("subtitle_style")

    out_name = f"documentary_reedit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    log(f"Assembling {len(segments)} segments…")

    vp = assemble_documentary(
        clips=clips,
        audio_path=audio_path,
        segments=segments,
        output_dir=run_dir,
        output_filename=out_name,
        aspect_ratio=aspect_ratio,
        progress_callback=log,
        playback_speed=_pb,
        burn_subtitles=_burn,
        subtitle_style=subtitle_style,
        bg_music_path=bg_music_path,
        bg_music_volume=bg_music_volume,
        logo_watermark=logo_watermark,
    )

    he = run_dir / "history_entry.json"
    if he.exists():
        try:
            h = json.loads(he.read_text(encoding="utf-8"))
            h["video_path"] = str(vp)
            he.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    return vp
