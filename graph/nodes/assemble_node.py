"""
graph/nodes/assemble_node.py — Assembly Node
============================================
Handles video assembly for both documentary mode (YouTube footage) and shorts/custom_script mode (image slideshow).
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from config import get_logger, get_ffmpeg_executable, OUTPUT_DIR
from core.config_manager import config, uses_video_footage
from api.routes.pipeline import get_broadcaster
from graph.state import GhostCreatorState

log = get_logger("assemble_node")


def _subtitle_style_from_config() -> dict:
    style = config.get("subtitle_style") or {}
    if not isinstance(style, dict):
        return {}
    return {
        "language": style.get("language", "voiceover"),
        "color": style.get("color", "#FFFFFF"),
        "bold": style.get("bold", True),
        "italic": style.get("italic", False),
        "font_size": style.get("font_size", 28),
        "bg_color": style.get("bg_color", "#80000000"),
        "font_family": style.get("font_family", "Nirmala UI"),
    }


def _save_documentary_editor_json(
    run_dir: Path,
    *,
    script: dict,
    segments: list[dict],
    durations: list[float],
    aspect_ratio: str,
    language: str,
    subtitle_style: dict,
    burn_subtitles: bool,
) -> None:
    """Persist editor snapshot so Ghost Editor + history re-render can load the run."""
    editor_segments = []
    for i, seg in enumerate(segments):
        editor_segments.append({
            "voiceover": seg.get("voiceover", ""),
            "video_query": seg.get("video_query", ""),
            "english_subtitle_text": seg.get("english_subtitle_text", ""),
            "duration_hint": round(float(durations[i]), 1) if i < len(durations) else seg.get("duration_hint", 5),
            "clip_name": f"e_{i:02d}.mp4",
            "transition": seg.get("transition", ""),
            "effect": seg.get("effect", ""),
        })

    meta = script.get("metadata") or {}
    payload = {
        "title": meta.get("title") or script.get("title") or "Untitled",
        "voiceover_text": script.get("voiceover_text", ""),
        "segments": editor_segments,
        "language": language,
        "aspect_ratio": aspect_ratio,
        "subtitle_style": subtitle_style,
        "burn_subtitles": burn_subtitles,
        "bg_music_volume": float(config.get("documentary.bg_music_volume", 0.25) or 0.25),
    }
    out = run_dir / "documentary_editor.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved editor project → %s", out)

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
            
        segments = script.get("segments", [])
        use_footage_assembly = mode == "documentary" or (uses_video_footage() and segments)

        # 2. VIDEO FOOTAGE ASSEMBLY (documentary + shorts/custom with stock/meta_ai/grok)
        if use_footage_assembly:
            asm_label = "documentary" if mode == "documentary" else "video"
            emit_progress(5, f"🎬 Starting {asm_label} assembly ...", "INFO", run_id)

            from graph.nodes.clip_prep import prepare_footage_clips
            from modules.documentary_assembler import (
                assemble_documentary,
                wants_burned_subtitles,
                _audio_duration_sec,
            )

            if not segments:
                raise ValueError("No script segments found for video footage assembly.")

            aspect_ratio = config.get("aspect_ratio", "9:16")
            language = state.get("language") or config.get("pipeline.language", "hi")

            prep = prepare_footage_clips(
                run_dir,
                script=script,
                audio_path=audio_path,
                run_id=run_id,
                language=language,
                mode=mode,
                skip_if_ready=True,
            )
            if prep is None:
                raise ValueError("Footage preparation failed.")
            clip_infos, durations, _edit_paths = prep
            audio_dur = _audio_duration_sec(Path(audio_path))

            subtitle_style = _subtitle_style_from_config()
            _burn = wants_burned_subtitles(config)

            # Step C: Assemble
            def _asm_progress(msg: str) -> None:
                emit_progress(5, msg, "INFO", run_id)
                
            _pb_speed = float(config.get("documentary.playback_speed", 1.0))
            prefix = "documentary" if mode == "documentary" else "short"
            _output_filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            
            emit_progress(5, "🎬 Assembling video with FFmpeg ...", "INFO", run_id)
            if _burn:
                emit_progress(5, "📝 Burning subtitles into video ...", "INFO", run_id)
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
                subtitle_style=subtitle_style,
            )
            video_path = str(video_path_obj)
            emit_progress(5, f"Video rendered: {video_path}", "SUCCESS", run_id)

            script_meta = script.get("metadata") or {}
            title = script_meta.get("title") or script.get("title", run_dir.name)
            ts = datetime.now().isoformat()
            meta_payload = {
                "title": title,
                "description": script_meta.get("description", ""),
                "tags": script_meta.get("tags", []),
                "video_path": video_path,
                "timestamp": ts,
            }
            meta_path = run_dir / "metadata.json"
            meta_path.write_text(
                json.dumps(meta_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            hist_path = run_dir / "history_entry.json"
            hist_path.write_text(
                json.dumps(
                    {
                        "title": title,
                        "topic": state.get("topic", ""),
                        "video_path": video_path,
                        "timestamp": ts,
                        "duration": f"{audio_dur:.1f}s",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        # 3. AI IMAGES SLIDESHOW MODE
        else:
            emit_progress(5, "🎬 Starting image slideshow assembly ...", "INFO", run_id)
            image_paths = state.get("image_paths", [])
            if not image_paths:
                raise ValueError(
                    "No images generated for slideshow assembly. "
                    "Switch Footage Source to Stock/Meta AI/Grok in Settings, "
                    "or check Gemini image quota if using AI Images."
                )
                
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
