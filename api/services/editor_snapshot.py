"""Create or restore documentary_editor.json for Ghost Editor."""

from __future__ import annotations

import json
from pathlib import Path

from core.config_manager import config
from core.clip_manager import get_clip_duration
from api.services.history_rerender import _glob_clips_for_edit


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _default_subtitle_style() -> dict:
    style = config.get("subtitle_style") or {}
    if not isinstance(style, dict):
        style = {}
    return {
        "language": style.get("language", "voiceover"),
        "color": style.get("color", "#FFFFFF"),
        "bold": style.get("bold", True),
        "italic": style.get("italic", False),
        "font_size": style.get("font_size", 28),
        "bg_color": style.get("bg_color", "#80000000"),
        "font_family": style.get("font_family", "Nirmala UI"),
    }


def run_is_editable(run_dir: Path) -> bool:
    """True when the run has an editor project or enough clips to build one."""
    if (run_dir / "documentary_editor.json").is_file():
        return True
    return len(_glob_clips_for_edit(run_dir)) > 0


def ensure_editor_json(run_dir: Path) -> Path | None:
    """
    Return path to documentary_editor.json, creating a minimal project from
    clips_for_edit + metadata when older runs lack a snapshot file.
    """
    run_dir = Path(run_dir)
    editor_path = run_dir / "documentary_editor.json"
    if editor_path.is_file():
        return editor_path

    clips = _glob_clips_for_edit(run_dir)
    if not clips:
        return None

    meta = _load_json(run_dir / "metadata.json")
    hist = _load_json(run_dir / "history_entry.json")
    script = _load_json(run_dir / "script.json")
    title = meta.get("title") or hist.get("title") or script.get("metadata", {}).get("title") or run_dir.name.replace("_", " ")

    vo_text = script.get("voiceover_text", "")
    script_segments = script.get("segments") or []

    vo = run_dir / "voiceover.mp3"
    if not vo.is_file():
        vo = run_dir / "voiceover_processed.mp3"
    total_dur = get_clip_duration(vo) if vo.is_file() else 0.0

    clip_durs = [max(0.5, get_clip_duration(c)) for c in clips]
    if total_dur <= 0:
        total_dur = sum(clip_durs)
    if total_dur <= 0:
        total_dur = float(len(clips) * 5)

    weight_sum = sum(clip_durs) or float(len(clips))
    seg_durs = [total_dur * (d / weight_sum) for d in clip_durs]

    segments = []
    for idx, (clip, dur) in enumerate(zip(clips, seg_durs)):
        seg_script = script_segments[idx] if idx < len(script_segments) else {}
        segments.append({
            "voiceover": str(seg_script.get("voiceover", "")),
            "video_query": seg_script.get("video_query") or clip.stem.replace("_", " "),
            "duration_hint": round(dur, 1),
            "clip_name": clip.name,
            "transition": seg_script.get("transition", ""),
            "effect": seg_script.get("effect", ""),
        })

    payload = {
        "title": title,
        "voiceover_text": vo_text,
        "segments": segments,
        "language": str(config.get("pipeline.language", "hi")),
        "aspect_ratio": str(config.get("aspect_ratio", "9:16")),
        "subtitle_style": _default_subtitle_style(),
        "burn_subtitles": bool(config.get("documentary.burn_subtitles", True)),
        "bg_music_volume": float(config.get("documentary.bg_music_volume", 0.25) or 0.25),
    }
    editor_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return editor_path
