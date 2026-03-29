"""
modules/video_builder.py — FFmpeg Video Assembly (9:16 / 16:9) + ASS Subtitles
================================================================================
Assembles images + MP3 into a final MP4 with configurable aspect ratio,
cycled Ken Burns–style motion, optional cinematic intro, and xfade transitions.

All operations via FFmpeg subprocess — no MoviePy dependency.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# -- Bundle Support --
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
LOCAL_FFMPEG = os.path.join(BASE_DIR, "ffmpeg", "ffmpeg.exe")
LOCAL_FFPROBE = os.path.join(BASE_DIR, "ffmpeg", "ffprobe.exe")
FFMPEG = LOCAL_FFMPEG if os.path.exists(LOCAL_FFMPEG) else "ffmpeg"
FFPROBE = LOCAL_FFPROBE if os.path.exists(LOCAL_FFPROBE) else "ffprobe"

from config import (
    get_logger,
    OUTPUT_DIR,
    TEMP_DIR,
)

# Suppress CMD window flash on Windows for all subprocess calls
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

from core.config_manager import config

log = get_logger("video_builder")

# ── Motion (zoompan) — frame math uses 25 fps per v3 spec ─────────────────────
MOTION_FPS = 25

MOTION_EFFECTS = {
    "zoom_in": lambda d: (
        f"z='min(zoom+{1.5 / d:.5f},1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    ),
    "zoom_out": lambda d: (
        f"z='if(lte(zoom,1.0),1.5,max(1.0,zoom-{1.5 / d:.5f}))':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    ),
    "pan_right": lambda d: (
        f"z='1.3':x='min(iw*0.15+on*(iw*0.15/{d}),iw*0.3)':y='ih/2-(ih/zoom/2)'"
    ),
    "pan_left": lambda d: (
        f"z='1.3':x='max(iw*0.15,iw*0.3-on*(iw*0.15/{d}))':y='ih/2-(ih/zoom/2)'"
    ),
    "pan_up": lambda d: (
        f"z='1.3':x='iw/2-(iw/zoom/2)':y='max(ih*0.05,ih*0.2-on*(ih*0.15/{d}))'"
    ),
    "diagonal": lambda d: (
        f"z='min(zoom+{0.8 / d:.5f},1.3)':"
        f"x='min(on*(iw*0.1/{d}),iw*0.1)':y='min(on*(ih*0.08/{d}),ih*0.08)'"
    ),
}
MOTION_KEYS = list(MOTION_EFFECTS.keys())

# ── Transitions (xfade) — FFmpeg names; aliases map user config → filter ───────
TRANSITION_POOLS = {
    "cinematic_mix": ["fade", "zoom", "wipeleft", "wiperight", "dissolve", "slideleft", "circleopen"],
    "fade_only": ["fade"],
    "zoom_only": ["zoom"],
    "minimal": ["fade", "dissolve"],
}

# xfade `transition` values supported by FFmpeg (zoom/dissolve are friendly aliases)
XFADE_ALIASES = {
    "zoom": "zoomin",
    "dissolve": "smoothleft",
}

TRANSITION_DURATION = 0.5

# ── Video Pace Settings ────────────────────────────────────────────────────────
# Controls Ken Burns zoom speed multiplier and transition duration per pace preset
PACE_SETTINGS = {
    "slow":   {"zoom_speed_mult": 1.6, "transition_sec": 0.8},
    "medium": {"zoom_speed_mult": 1.0, "transition_sec": 0.5},
    "fast":   {"zoom_speed_mult": 0.55, "transition_sec": 0.25},
}

# ── Subtitle styling ──────────────────────────────────────────────────────────
WORDS_PER_CHUNK = 4
ASS_FONT_NAME   = "Impact"            # Bold impact font — classic YT subtitle look

# ASS colour format: &HAABBGGRR  (alpha, blue, green, red)
# Rotating colour pool — one colour per subtitle chunk for "colorful" effect
ASS_COLORS = [
    "&H0000FFFF",   # Yellow  (most readable on any background)
    "&H00FFFFFF",   # White
    "&H0000D7FF",   # Gold / orange-yellow
    "&H0040FFFF",   # Bright yellow-green
    "&H00FFFFFF",   # White  (repeat for balance)
]
ASS_OUTLINE_COLOR = "&H00000000"   # Black outline
ASS_SHADOW_COLOR  = "&H88000000"   # Semi-transparent black shadow
ASS_OUTLINE_WIDTH = 3              # Thick outline for visibility
ASS_SHADOW_DEPTH  = 2


def _strip_emojis(text: str) -> str:
    """Remove emojis and problematic Unicode symbols."""
    return re.sub(r'[^\w\s.,!?"\'\-\+\=]', "", text)


def get_audio_duration(audio_path: str | Path) -> float:
    """Duration of an audio file in seconds (ffprobe)."""
    cmd = [
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def _xfade_transition_name(user_name: str) -> str:
    return XFADE_ALIASES.get(user_name, user_name)


def _letterbox_filters(aspect_ratio: str) -> str:
    """drawbox filters for intro letterboxing (enabled 0–2s)."""
    if aspect_ratio == "16:9":
        return (
            "drawbox=x=0:y=0:w=96:h=ih:color=black@1:t=fill:enable='between(t,0,2)',"
            "drawbox=x=iw-96:y=0:w=96:h=ih:color=black@1:t=fill:enable='between(t,0,2)'"
        )
    return (
        "drawbox=x=0:y=0:w=iw:h=80:color=black@1:t=fill:enable='between(t,0,2)',"
        "drawbox=x=0:y=ih-80:w=iw:h=80:color=black@1:t=fill:enable='between(t,0,2)'"
    )


def _zoompan_chain(
    motion_key: str,
    d_frames: int,
    width: int,
    height: int,
    zoom_speed_mult: float = 1.0,
) -> str:
    """Build a zoompan filter chain. zoom_speed_mult > 1 = slower/smoother, < 1 = faster/tighter."""
    # Scale effective d_frames for zoom math — more frames → slower zoom
    effective_d = max(1, int(d_frames * zoom_speed_mult))
    inner = MOTION_EFFECTS[motion_key](effective_d)
    return (
        f"scale={width * 2}:{height * 2},"
        f"zoompan={inner}:d={d_frames}:s={width}x{height}:fps={MOTION_FPS}"
    )


def _subtitle_font_size(height: int) -> int:
    """
    Scale subtitle font size to ~5.5% of video height.
    Produces nicely readable text on both 1080p (16:9) and 1920px-tall (9:16).
    """
    return max(38, min(int(height * 0.055), 120))


def _subtitle_margin_v(height: int, aspect_ratio: str) -> int:
    """Bottom margin so subtitles sit in the lower band (ASS alignment 2)."""
    if aspect_ratio == "16:9":
        return int(height * 0.10)   # bottom ~10%
    return int(height * 0.12)       # 9:16 — bottom ~12%


def _generate_ass_subtitles(
    text: str,
    audio_duration: float,
    output_path: str | Path,
    width: int,
    height: int,
    aspect_ratio: str,
) -> str:
    """Generate colorful, bold-italic ASS subtitles with per-chunk colour cycling."""
    clean_text = _strip_emojis(text).strip()
    if not clean_text:
        clean_text = "Ghost Creator AI"

    words = clean_text.split()
    chunks: list[str] = []
    for i in range(0, len(words), WORDS_PER_CHUNK):
        chunks.append(" ".join(words[i : i + WORDS_PER_CHUNK]))
    if not chunks:
        chunks = [clean_text]

    chunk_duration = audio_duration / len(chunks)
    margin_v  = _subtitle_margin_v(height, aspect_ratio)
    font_size = _subtitle_font_size(height)

    log.info(f"ASS subtitle placement: MarginV={margin_v}, FontSize={font_size} (aspect {aspect_ratio})")

    # Base style: Bold=1, Italic=1, yellow fill, black outline, shadow
    base_color = ASS_COLORS[0]   # yellow — default in Style definition

    ass_content = f"""[Script Info]
Title: Ghost Creator AI Subtitles
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{ASS_FONT_NAME},{font_size},{base_color},&H000000FF,{ASS_OUTLINE_COLOR},{ASS_SHADOW_COLOR},1,1,0,0,100,100,1,0,1,{ASS_OUTLINE_WIDTH},{ASS_SHADOW_DEPTH},2,30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    n_colors = len(ASS_COLORS)
    for idx, chunk_text in enumerate(chunks):
        start_str  = _seconds_to_ass_time(idx * chunk_duration)
        end_str    = _seconds_to_ass_time((idx + 1) * chunk_duration)
        safe_text  = chunk_text.replace("\\", "\\\\")
        # Inline colour override rotates through the colour pool
        color_tag  = ASS_COLORS[idx % n_colors]
        colored    = f"{{\\c{color_tag}}}{safe_text}"
        ass_content += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{colored}\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    log.info(f"ASS subtitles: {len(chunks)} chunks, font={font_size}px → {output_path}")
    return str(output_path)


def _seconds_to_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _run_ffmpeg(cmd: list[str], step_name: str) -> None:
    log.debug(f"FFmpeg [{step_name}]: {' '.join(cmd[:8])}…")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
        creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        log.error(f"FFmpeg [{step_name}] stderr: {result.stderr[-500:]}")
        raise RuntimeError(f"FFmpeg [{step_name}] failed: {result.stderr[-300:]}")


def _transition_for_index(i: int, n: int, style: str) -> str:
    """Pick xfade transition: first and last are always fade; middle cycles pool."""
    pool = TRANSITION_POOLS.get(style, TRANSITION_POOLS["cinematic_mix"])
    if n <= 1:
        return "fade"
    if i == 0 or i == n - 2:
        return "fade"
    return pool[i % len(pool)]


def _build_xfade_filter_complex(n: int, scene_duration: float, transition_sec: float, style: str) -> tuple[str, str]:
    """
    Chain n-1 xfade filters with equal per-scene duration.
    Offset for transition i: cumulative sum of (scene_duration - transition_sec).
    """
    parts: list[str] = []
    label_in = "0:v"
    for i in range(n - 1):
        offset = (i + 1) * (scene_duration - transition_sec)
        t_user = _transition_for_index(i, n, style)
        t_ff = _xfade_transition_name(t_user)
        label_out = f"v{i}" if i < n - 2 else "vout"
        parts.append(
            f"[{label_in}][{i + 1}:v]xfade=transition={t_ff}:duration={transition_sec}:offset={offset:.6f}[{label_out}]"
        )
        label_in = label_out
    return ";".join(parts), "vout"


def _build_xfade_filter_complex_variable(
    scene_durations: list[float], transition_sec: float, style: str
) -> tuple[str, str]:
    """
    Chain n-1 xfade filters with variable per-scene durations.
    Offsets are computed cumulatively so clips of different lengths transition correctly.
    """
    n = len(scene_durations)
    parts: list[str] = []
    label_in = "0:v"
    cumulative = 0.0
    for i in range(n - 1):
        cumulative += scene_durations[i] - transition_sec
        t_user = _transition_for_index(i, n, style)
        t_ff = _xfade_transition_name(t_user)
        label_out = f"v{i}" if i < n - 2 else "vout"
        parts.append(
            f"[{label_in}][{i + 1}:v]xfade=transition={t_ff}:duration={transition_sec}:offset={cumulative:.6f}[{label_out}]"
        )
        label_in = label_out
    return ";".join(parts), "vout"


def _calc_scene_durations(
    scene_data: list[dict],
    total_duration: float,
    transition_sec: float,
    enable_transitions: bool,
) -> list[float]:
    """
    Smart per-scene duration calculation:
    - video_clips: use their natural duration (probed via ffprobe), capped at max
    - images: share remaining time equally
    - If clips consume more than available time: proportionally shrink all clips
    - If no clips (all images) or no images (all clips): equal share for everyone

    Returns a list of floats (seconds), one per scene.
    """
    n = len(scene_data)
    t = transition_sec if enable_transitions and n > 1 else 0.0
    # Total "timeline slots" including overlap budget
    total_with_overlap = total_duration + (n - 1) * t
    equal_share = total_with_overlap / n

    clip_indices: list[int] = []
    image_indices: list[int] = []
    clip_natural: dict[int, float] = {}

    for i, scene in enumerate(scene_data):
        if scene.get("type") == "video_clip":
            clip_indices.append(i)
            try:
                d = get_audio_duration(scene["path"])
                clip_natural[i] = max(0.5, d)
            except Exception:
                clip_natural[i] = 5.0  # safe fallback
        else:
            image_indices.append(i)

    # No clips or no images → equal share for all
    if not clip_indices or not image_indices:
        return [equal_share] * n

    # Mixed: clips take natural time, images fill the rest
    total_clip_natural = sum(clip_natural.values())
    max_clip_budget = total_with_overlap - len(image_indices) * max(1.5, equal_share * 0.3)

    if total_clip_natural > max_clip_budget:
        # Clips collectively too long → shrink proportionally
        scale = max_clip_budget / total_clip_natural
        for i in clip_indices:
            clip_natural[i] *= scale
        total_clip_natural = max_clip_budget

    remaining = total_with_overlap - total_clip_natural
    image_share = remaining / len(image_indices)

    durations: list[float] = []
    for i in range(n):
        if i in clip_indices:
            durations.append(clip_natural[i])
        else:
            durations.append(max(1.0, image_share))

    return durations


def _build_concat_filter_complex(n: int) -> str:
    """filter_complex for concat demuxer-style join without re-encoding inputs (concat filter)."""
    ins = "".join(f"[{i}:v]" for i in range(n))
    return f"{ins}concat=n={n}:v=1:a=0[vout]"


def _build_simple_video(
    scene_data: list[dict],
    audio_path: Path,
    output_path: Path,
    width: int,
    height: int,
    audio_duration: float,
    log_fn=None,
) -> None:
    """
    Simple mode: no Ken Burns, no transitions, no cinematic effects.
    Each scene held for equal duration, then concat + audio mux.
    """
    _log = log_fn or log.info
    _log("[INFO] Simple mode — rendering without effects")

    temp_dir = TEMP_DIR / "ffmpeg_simple"
    temp_dir.mkdir(parents=True, exist_ok=True)
    n = len(scene_data)
    clip_dur = audio_duration / n
    scene_clips: list[Path] = []

    try:
        for idx, scene in enumerate(scene_data):
            src = scene["path"]
            clip_out = temp_dir / f"sclip_{idx}.mp4"
            if scene["type"] == "video_clip":
                cmd = [
                    FFMPEG, "-y", "-stream_loop", "-1", "-i", str(src),
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setpts=PTS-STARTPTS,format=yuv420p",
                    "-t", str(clip_dur), "-r", "25",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    str(clip_out),
                ]
            else:
                cmd = [
                    FFMPEG, "-y", "-loop", "1", "-i", str(src),
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p",
                    "-t", str(clip_dur), "-r", "25",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    str(clip_out),
                ]
            _run_ffmpeg(cmd, f"simple_clip_{idx}")
            scene_clips.append(clip_out)

        fc = _build_concat_filter_complex(n)
        joined = temp_dir / "simple_joined.mp4"
        cmd = [FFMPEG, "-y"]
        for p in scene_clips:
            cmd.extend(["-i", str(p)])
        cmd.extend(["-filter_complex", fc, "-map", "[vout]", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(joined)])
        _run_ffmpeg(cmd, "simple_concat")

        cmd = [
            FFMPEG, "-y", "-i", str(joined), "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac", "-shortest", str(output_path),
        ]
        _run_ffmpeg(cmd, "simple_audio")

    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def build_video(
    image_paths: list[Path] | list[dict] | None = None,
    audio_path: Path = None,
    voiceover_text: str = "",
    title: str = "",
    output_filename: str = "final_short.mp4",
    english_subtitle_text: str = "",
    aspect_ratio: str | None = None,
    cinematic_effects: dict | None = None,
    target_duration: int | None = None,
    scene_data: list[dict] | None = None,
    output_dir: "Path | str | None" = None,
) -> Path:
    """
    Assemble final MP4 from images/video-clips + audio + subtitles (FFmpeg only).

    Accepts either ``scene_data`` (list of dicts with type+path) or the legacy
    ``image_paths`` (list of Path/str). When both are given, ``scene_data`` wins.

    When ``aspect_ratio``, ``cinematic_effects``, or ``target_duration`` are
    omitted, values are read from ``config``.
    """
    # ── Resolve scene_data from legacy image_paths ─────────────────────────
    if scene_data is None:
        if image_paths is not None and len(image_paths) > 0:
            if isinstance(image_paths[0], dict):
                scene_data = image_paths  # type: ignore[assignment]
            else:
                scene_data = [{"type": "image", "path": str(p)} for p in image_paths]
        else:
            scene_data = []

    if aspect_ratio is None:
        aspect_ratio = config.get("aspect_ratio", "9:16")
    if target_duration is None:
        target_duration = config.get("target_duration", 60)
    if cinematic_effects is None:
        cinematic = config.get("cinematic_effects", {})
    else:
        cinematic = cinematic_effects
    enable_intro = cinematic.get("intro", True)
    enable_transitions = cinematic.get("transitions", True)
    transition_style = cinematic.get("transition_style", "cinematic_mix")

    # ── Pace settings ───────────────────────────────────────────────────────
    pace = config.get("video_pace", "medium")
    pace_cfg = PACE_SETTINGS.get(pace, PACE_SETTINGS["medium"])
    zoom_speed_mult = pace_cfg["zoom_speed_mult"]
    t_trans_override = pace_cfg["transition_sec"]

    width, height = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)

    # Resolve output directory:
    # 1. output_dir param (from pipeline run_dir) takes highest priority
    # 2. user-configured pipeline.output_folder
    # 3. fallback to OUTPUT_DIR
    if output_dir is not None:
        _out_dir = Path(output_dir)
    else:
        _configured_folder = config.get("pipeline.output_folder", "").strip()
        if _configured_folder:
            _out_dir = Path(_configured_folder)
            if not _out_dir.is_absolute():
                _out_dir = OUTPUT_DIR.parent / _out_dir
        else:
            _out_dir = OUTPUT_DIR
    try:
        _out_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        _out_dir = OUTPUT_DIR
        _out_dir.mkdir(parents=True, exist_ok=True)
    out_path = _out_dir / output_filename
    log.info(f"Building video: {title!r} ({width}×{height}, aspect {aspect_ratio}) → {_out_dir}")

    # ── Master video features toggle ───────────────────────────────────────
    if not config.get("video_features_enabled", True):
        log.info("video_features_enabled=False — using simple (no-effects) render")
        total_dur = get_audio_duration(str(audio_path))
        _build_simple_video(scene_data, audio_path, out_path, width, height, total_dur)
        return out_path

    sub_text = english_subtitle_text or voiceover_text
    temp_dir = TEMP_DIR / "ffmpeg_build"
    temp_dir.mkdir(parents=True, exist_ok=True)

    scene_clips: list[Path] = []

    try:
        log.info("Probing voiceover audio duration …")
        total_duration = get_audio_duration(str(audio_path))
        log.info(f"Audio duration: {total_duration:.2f}s (target {target_duration}s)")
        if abs(total_duration - target_duration) > 15:
            log.debug("Audio length differs notably from target_duration — using actual audio length.")

        n = len(scene_data)
        num_images = n
        if n == 0:
            raise ValueError("No images/clips provided for video build.")

        log.info(f"Dynamic image count: {num_images} clip(s); per-clip duration from full audio.")

        t_trans = t_trans_override
        log.info(f"Video pace: {pace!r} — zoom_speed_mult={zoom_speed_mult}, transition_sec={t_trans}")
        if enable_transitions and n > 1:
            scene_duration = (total_duration + (n - 1) * t_trans) / n
        else:
            scene_duration = total_duration / num_images

        # ── Smart per-scene durations ──────────────────────────────────────
        scene_durations = _calc_scene_durations(
            scene_data, total_duration, t_trans, enable_transitions
        )
        has_variable_durations = len(set(round(d, 3) for d in scene_durations)) > 1

        log.info(
            f"Each clip: {scene_duration:.2f}s base (total {total_duration:.2f}s / {num_images} scenes"
            + (f", overlap {t_trans}s" if enable_transitions and n > 1 else "")
            + f"); motion @ {MOTION_FPS}fps; transitions={enable_transitions}"
        )
        if has_variable_durations:
            log.info(
                "Variable scene durations (clips+images mixed): "
                + ", ".join(f"s{i+1}={d:.2f}s" for i, d in enumerate(scene_durations))
            )

        log.info("Encoding per-scene clips …")
        for idx, scene in enumerate(scene_data):
            scene_path = temp_dir / f"clip_{idx}.mp4"
            src_path = scene["path"]
            scene_type = scene.get("type", "image")
            this_duration = scene_durations[idx]
            d_frames = max(1, int(this_duration * MOTION_FPS))

            if scene_type == "video_clip":
                log.info(f"  Clip {idx + 1}/{n} → {scene_path.name} — video_clip (target={this_duration:.2f}s)")
                # Probe actual clip duration to decide loop vs speed-adjust
                try:
                    actual_dur = get_audio_duration(str(src_path))
                except Exception:
                    actual_dur = this_duration

                base_vf = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},format=yuv420p"
                )

                if actual_dur > this_duration * 1.05:
                    # Clip is longer than needed → speed it up with setpts
                    speed_factor = actual_dur / this_duration
                    log.info(f"    Speeding up {actual_dur:.2f}s clip → {this_duration:.2f}s (×{speed_factor:.2f})")
                    vf = (
                        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                        f"crop={width}:{height},setpts=PTS/{speed_factor:.6f},fps={MOTION_FPS},format=yuv420p"
                    )
                    cmd = [
                        FFMPEG, "-y", "-i", str(src_path),
                        "-vf", vf,
                        "-t", str(this_duration), "-r", str(MOTION_FPS),
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                        str(scene_path),
                    ]
                else:
                    # Clip is shorter or equal → loop it to fill this_duration
                    cmd = [
                        FFMPEG, "-y", "-stream_loop", "-1", "-i", str(src_path),
                        "-vf", f"{base_vf.replace(',format=yuv420p', ',setpts=PTS-STARTPTS,format=yuv420p')}",
                        "-t", str(this_duration), "-r", str(MOTION_FPS),
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                        str(scene_path),
                    ]
                _run_ffmpeg(cmd, f"clip_{idx}_video")
            else:
                if idx == 0 and enable_intro:
                    motion_key = "zoom_in"
                    base = _zoompan_chain(motion_key, d_frames, width, height, zoom_speed_mult)
                    lb = _letterbox_filters(aspect_ratio)
                    vf = (
                        f"{base},fade=t=in:st=0.3:d=0.8:c=black,{lb},format=yuv420p"
                    )
                    step = f"clip_{idx}_intro"
                else:
                    motion_key = MOTION_KEYS[idx % len(MOTION_KEYS)]
                    vf = f"{_zoompan_chain(motion_key, d_frames, width, height, zoom_speed_mult)},format=yuv420p"
                    step = f"clip_{idx}_{motion_key}"

                log.info(
                    f"  Clip {idx + 1}/{n} → {scene_path.name} — {motion_key} (target={this_duration:.2f}s)"
                    + (" + intro" if idx == 0 and enable_intro else "")
                )

                cmd = [
                    FFMPEG, "-y", "-loop", "1", "-i", str(src_path),
                    "-vf", vf,
                    "-t", str(this_duration),
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    str(scene_path),
                ]
                _run_ffmpeg(cmd, step)
            scene_clips.append(scene_path)

        # ── Join scenes (xfade or concat filter) ──────────────────────────
        if enable_transitions and n > 1:
            log.info("Joining clips with xfade (filter_complex) …")
            if has_variable_durations:
                fc, vlabel = _build_xfade_filter_complex_variable(scene_durations, t_trans, transition_style)
            else:
                fc, vlabel = _build_xfade_filter_complex(n, scene_duration, t_trans, transition_style)
            joined_path = temp_dir / "scenes_joined.mp4"
            cmd = [FFMPEG, "-y"]
            for p in scene_clips:
                cmd.extend(["-i", str(p)])
            cmd.extend(
                [
                    "-filter_complex",
                    fc,
                    "-map",
                    f"[{vlabel}]",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-pix_fmt",
                    "yuv420p",
                    str(joined_path),
                ]
            )
            _run_ffmpeg(cmd, "xfade_chain")
            concat_path = joined_path
        else:
            log.info("Joining clips with concat filter (filter_complex, no transitions) …")
            fc = _build_concat_filter_complex(n)
            concat_path = temp_dir / "scenes_concat.mp4"
            cmd = [FFMPEG, "-y"]
            for p in scene_clips:
                cmd.extend(["-i", str(p)])
            cmd.extend(
                [
                    "-filter_complex",
                    fc,
                    "-map",
                    "[vout]",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-pix_fmt",
                    "yuv420p",
                    str(concat_path),
                ]
            )
            _run_ffmpeg(cmd, "concat_filter")

        # ── Mix audio ───────────────────────────────────────────────────
        log.info("Muxing video with voiceover audio …")
        no_subs_path = temp_dir / "final_no_subs.mp4"
        cmd = [
            FFMPEG,
            "-y",
            "-i",
            str(concat_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(no_subs_path),
        ]
        _run_ffmpeg(cmd, "mix_audio")

        log.info("Generating ASS subtitles …")
        ass_path = temp_dir / "subtitles.ass"
        _generate_ass_subtitles(sub_text, total_duration, ass_path, width, height, aspect_ratio)

        log.info("Burning subtitles into final video …")
        ass_filter_path = str(ass_path).replace("\\", "/").replace(":", "\\:")
        cmd = [
            FFMPEG,
            "-y",
            "-i",
            str(no_subs_path),
            "-vf",
            f"ass='{ass_filter_path}'",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "copy",
            str(out_path),
        ]
        _run_ffmpeg(cmd, "burn_subtitles")

        log.info(f"Video rendered → {out_path}")

        log.info("Removing per-clip temp files (clip_0.mp4 …) …")
        for cp in scene_clips:
            try:
                if cp.exists():
                    cp.unlink()
                    log.info(f"  Deleted {cp.name}")
            except OSError as exc:
                log.warning(f"  Could not delete {cp}: {exc}")

        return out_path

    finally:
        log.debug("Cleaning up remaining ffmpeg_build temp dir …")
        import shutil

        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    from config import TEMP_DIR as TD

    test_audio = TD / "voiceover.mp3"
    if test_audio.exists():
        print(f"Audio duration: {get_audio_duration(str(test_audio)):.2f}s")
    else:
        print(f"No test audio at {test_audio}")
