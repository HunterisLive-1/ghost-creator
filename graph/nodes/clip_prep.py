"""Shared clip fetch + voice-sync for editor prep and assembly."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.config_manager import config, uses_video_footage
from graph.nodes.assemble_node import _save_documentary_editor_json, _subtitle_style_from_config, emit_progress

log = logging.getLogger("clip_prep")


def save_script_json(run_dir: Path, script: dict) -> None:
    """Persist full script dict for editor backfill and history metadata."""
    if not script:
        return
    out = run_dir / "script.json"
    out.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved script → %s", out)


def clips_for_edit_ready(run_dir: Path, num_segments: int) -> bool:
    """True when all synced edit clips exist on disk."""
    if num_segments <= 0:
        return False
    cfe = run_dir / "clips_for_edit"
    for i in range(num_segments):
        p = cfe / f"e_{i:02d}.mp4"
        if not p.is_file() or p.stat().st_size <= 5000:
            return False
    return True


def prepare_footage_clips(
    run_dir: Path,
    *,
    script: dict,
    audio_path: str,
    run_id: str,
    language: str,
    mode: str,
    skip_if_ready: bool = False,
) -> tuple[list, list[float], list[Path]] | None:
    """
    Download stock clips, sync to voiceover, write documentary_editor.json.
    Returns (clip_infos, durations, edit_paths) or None when not applicable.
    """
    segments = script.get("segments", [])
    use_footage = mode == "documentary" or (uses_video_footage() and segments)
    if not use_footage or not segments:
        return None

    if not audio_path or not Path(audio_path).exists():
        raise ValueError(f"Audio file is missing or invalid: {audio_path}")

    num_segs = len(segments)
    save_script_json(run_dir, script)

    if skip_if_ready and clips_for_edit_ready(run_dir, num_segs):
        from core.clip_manager import load_clips, get_clip_duration
        from modules.documentary_assembler import _audio_duration_sec, _normalized_segment_durations

        edit_paths = [run_dir / "clips_for_edit" / f"e_{i:02d}.mp4" for i in range(num_segs)]
        audio_dur = _audio_duration_sec(Path(audio_path))
        durations = _normalized_segment_durations(segments, audio_dur)
        clip_infos = load_clips(edit_paths, segments, target_durations=durations)
        log.info("Reusing existing clips_for_edit (%d segments)", num_segs)
        return clip_infos, durations, edit_paths

    from modules.video_fetcher import fetch_clips_for_pipeline, footage_source_label
    from core.clip_manager import generate_srt_from_segments, load_clips
    from modules.documentary_assembler import (
        _audio_duration_sec,
        _normalized_segment_durations,
        _resolution,
        _make_filler,
        _trim_or_loop_clip,
        _vf_scale,
        wants_burned_subtitles,
    )

    target_duration = int(config.get("target_duration", 180))
    aspect_ratio = config.get("aspect_ratio", "9:16")

    _footage_label = footage_source_label()
    _auto_clip_dur = max(30, int(target_duration / max(1, num_segs)) + 20)
    clips_dir = run_dir / "clips"

    def _fetch_progress(msg: str) -> None:
        emit_progress(4, msg, "INFO", run_id)

    emit_progress(4, f"📹 Fetching {num_segs} clips via {_footage_label} ...", "INFO", run_id)
    clips = fetch_clips_for_pipeline(
        segments,
        clips_dir,
        max_clip_duration=_auto_clip_dur,
        progress_callback=_fetch_progress,
    )

    audio_dur = _audio_duration_sec(Path(audio_path))
    generate_srt_from_segments(segments, audio_dur)
    durations = _normalized_segment_durations(segments, audio_dur)
    vf = _vf_scale(aspect_ratio)
    w, h = _resolution(aspect_ratio)

    clips_for_edit = run_dir / "clips_for_edit"
    clips_for_edit.mkdir(exist_ok=True)
    edit_paths: list[Path] = []
    last_good = None

    emit_progress(4, f"🕐 Syncing footage to narration ({audio_dur:.1f}s) ...", "INFO", run_id)
    for i in range(num_segs):
        dur = durations[i]
        dst = clips_for_edit / f"e_{i:02d}.mp4"
        src = clips[i] if i < len(clips) else None
        if src and Path(src).exists() and Path(src).stat().st_size > 5000:
            try:
                _trim_or_loop_clip(Path(src), dst, dur, vf)
                last_good = dst
            except Exception as exc:
                log.warning("Trim failed for clip %d: %s", i + 1, exc)
                _make_filler(dst, dur, w, h, last_good, clips_for_edit, i)
                last_good = dst
        else:
            _make_filler(dst, dur, w, h, last_good, clips_for_edit, i)
            last_good = dst
        edit_paths.append(dst)

    clip_infos = load_clips(edit_paths, segments, target_durations=durations)

    subtitle_style = _subtitle_style_from_config()
    _burn = wants_burned_subtitles(config)
    _save_documentary_editor_json(
        run_dir,
        script=script,
        segments=segments,
        durations=durations,
        aspect_ratio=aspect_ratio,
        language=language,
        subtitle_style=subtitle_style,
        burn_subtitles=_burn,
    )

    return clip_infos, durations, edit_paths
