"""
graph/nodes/assemble_node.py — Assembly Node
============================================
Handles video assembly for both documentary mode (YouTube footage) and shorts/custom_script mode (image slideshow).
"""

import logging
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from config import get_logger, get_ffmpeg_executable, OUTPUT_DIR
from core.config_manager import config
from api.routes.pipeline import get_broadcaster
from graph.state import GhostCreatorState

log = get_logger("assemble_node")

def emit_progress(step: int, message: str, level: str = "INFO", run_id: str = ""):
    """Helper to emit progress directly to the WebSocket broadcaster."""
    broadcaster = get_broadcaster()
    if broadcaster:
        broadcaster.put({
            "step": step,
            "message": message,
            "level": level,
            "timestamp": datetime.now().isoformat(),
            "run_id": run_id,
        })

def compile_slideshow(image_paths: list[str], audio_path: str, output_path: str, run_id: str = "") -> str:
    """Stitches parallel generated images into a slideshow synced with voiceover audio."""
    from core.clip_manager import get_clip_duration
    
    emit_progress(5, "🎬 Loading audio duration for slideshow ...", "INFO", run_id)
    audio_dur = get_clip_duration(Path(audio_path))
    
    num_images = len(image_paths)
    if num_images == 0:
        raise ValueError("No images generated for slideshow.")
        
    dur_per_img = audio_dur / num_images
    log.info(f"Slideshow: {audio_dur:.2f}s total audio, {num_images} images. {dur_per_img:.2f}s per image.")
    emit_progress(5, f"Stitching {num_images} images at {dur_per_img:.2f}s per slide ...", "INFO", run_id)
    
    run_dir = Path(output_path).parent
    temp_dir = run_dir / "temp_segments"
    temp_dir.mkdir(exist_ok=True)
    
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    w, h = config.get_resolution()
    
    segment_paths = []
    for i, img_path in enumerate(image_paths):
        seg_path = temp_dir / f"seg_{i:02d}.mp4"
        # Render a silent high-quality segment of the image for the specific duration
        cmd = [
            get_ffmpeg_executable(), "-y",
            "-loop", "1",
            "-i", str(img_path),
            "-c:v", "libx264",
            "-t", f"{dur_per_img:.3f}",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
            str(seg_path)
        ]
        subprocess.run(cmd, check=True, creationflags=_NO_WINDOW)
        segment_paths.append(seg_path)
        
    # Write segment lists for FFmpeg concat demuxer
    concat_file = temp_dir / "concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for seg in segment_paths:
            f.write(f"file '{seg.as_posix()}'\n")
            
    emit_progress(5, "Muxing images with voiceover narration ...", "INFO", run_id)
    
    # Concatenate the images and bind with the audio file
    cmd = [
        get_ffmpeg_executable(), "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-i", audio_path,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
    subprocess.run(cmd, check=True, creationflags=_NO_WINDOW)
    
    # Clean up temporary segments
    for seg in segment_paths:
        try:
            seg.unlink()
        except OSError:
            pass
    try:
        concat_file.unlink()
        temp_dir.rmdir()
    except OSError:
        pass
        
    emit_progress(5, f"Slideshow compiled successfully! Saved: {output_path}", "SUCCESS", run_id)
    return output_path


def assemble_node(state: GhostCreatorState) -> dict:
    """LangGraph node to compile the final video file."""
    mode = state.get("mode", "shorts")
    audio_path = state.get("audio_path", "")
    run_dir_str = state.get("run_dir", "")
    run_id = state.get("run_id", "")
    script = state.get("script") or {}
    
    if not run_dir_str:
        # Fallback to output directory if run_dir not specified
        run_dir_str = str(OUTPUT_DIR)
        
    run_dir = Path(run_dir_str)
    
    try:
        # 1. Validation
        if not audio_path or not Path(audio_path).exists():
            raise ValueError(f"Audio file is missing or invalid: {audio_path}")
            
        # 2. DOCUMENTARY MODE
        if mode == "documentary":
            emit_progress(5, "🎬 Starting documentary assembly ...", "INFO", run_id)
            
            # Since LangGraph runs nodes sequentially, we do the fetching & editing here
            from modules.video_fetcher import fetch_clips_for_pipeline, footage_source_label
            from core.clip_manager import generate_srt_from_segments, load_clips
            from modules.documentary_assembler import (
                assemble_documentary,
                wants_burned_subtitles,
                _audio_duration_sec,
                _normalized_segment_durations,
                _resolution,
                _make_filler,
                _trim_or_loop_clip,
                _vf_scale,
            )
            
            segments = script.get("segments", [])
            if not segments:
                raise ValueError("No script segments found for documentary mode.")
                
            num_segs = len(segments)
            target_duration = int(config.get("target_duration", 180))
            aspect_ratio = config.get("aspect_ratio", "9:16")
            
            # Step A: Download clips
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
                progress_callback=_fetch_progress
            )
            
            # Step B: Voice sync editing
            audio_dur = _audio_duration_sec(Path(audio_path))
            srt_entries = generate_srt_from_segments(segments, audio_dur)
            durations = _normalized_segment_durations(segments, audio_dur)
            vf = _vf_scale(aspect_ratio)
            w, h = _resolution(aspect_ratio)
            
            clips_for_edit = run_dir / "clips_for_edit"
            clips_for_edit.mkdir(exist_ok=True)
            edit_paths = []
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
                        log.warning(f"Trim failed for clip {i+1}: {exc}")
                        _make_filler(dst, dur, w, h, last_good, clips_for_edit, i)
                        last_good = dst
                else:
                    _make_filler(dst, dur, w, h, last_good, clips_for_edit, i)
                    last_good = dst
                edit_paths.append(dst)
                
            clip_infos = load_clips(edit_paths, segments, target_durations=durations)
            
            # Step C: Assemble
            def _asm_progress(msg: str) -> None:
                emit_progress(5, msg, "INFO", run_id)
                
            _pb_speed = float(config.get("documentary.playback_speed", 1.0))
            _burn = wants_burned_subtitles(config)
            _output_filename = f"documentary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            
            emit_progress(5, "🎬 Assembling documentary with FFmpeg ...", "INFO", run_id)
            video_path_obj = assemble_documentary(
                clips=clip_infos,
                audio_path=Path(audio_path),
                segments=segments,
                output_dir=run_dir,
                output_filename=_output_filename,
                aspect_ratio=aspect_ratio,
                progress_callback=_asm_progress,
                playback_speed=_pb_speed,
                burn_subtitles=_burn,
            )
            video_path = str(video_path_obj)
            emit_progress(5, f"Documentary rendered: {video_path}", "SUCCESS", run_id)

        # 3. SHORTS OR CUSTOM SCRIPT SLIDESHOW MODE
        else:
            emit_progress(5, "🎬 Starting image slideshow assembly ...", "INFO", run_id)
            image_paths = state.get("image_paths", [])
            if not image_paths:
                raise ValueError("No images generated for slideshow assembly.")
                
            _output_filename = f"short_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            target_video_path = str(run_dir / _output_filename)
            
            video_path = compile_slideshow(image_paths, audio_path, target_video_path, run_id)
            
        return {
            "video_path": video_path,
            "last_failed_node": ""
        }
        
    except Exception as exc:
        log.error(f"Assembly Node failed: {exc}", exc_info=True)
        return {
            "errors": [f"Assembly failed: {exc}"],
            "video_path": "",
            "last_failed_node": "assemble"
        }
