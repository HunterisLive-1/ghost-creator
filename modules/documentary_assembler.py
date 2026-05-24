"""
modules/documentary_assembler.py
=================================
Assembles a documentary video from footage clips + OmniVoice audio.

Steps:
  1. Measure total voiceover duration from the audio file
  2. Distribute duration across segments (proportional to text length)
  3. Scale + trim/loop each clip to its allocated duration
  4. Concatenate all clips
  5. Replace audio with the voiceover (strip original clip audio)

Optional: burn Hindi (or any) voiceover as white bold text at the bottom (long-form only — see pipeline).
Optional: PNG/JPG logo watermark (corner + scale) after subs/music — see Settings.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from config import get_logger, get_ffmpeg_executable, get_ffprobe_executable
from core.clip_manager import ClipInfo

log = get_logger("doc_assembler")

# Hide console flashes when running bundled ffmpeg/ffprobe on Windows (PyInstaller .exe)
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_CB = Callable[[str], None] | None

_LOGO_POSITIONS = frozenset({"top_left", "top_right", "bottom_left", "bottom_right"})


def _notify(fn: _CB, msg: str) -> None:
    log.info(msg)
    if fn:
        fn(msg)


def _ffmpeg(
    *args: str,
    timeout: int = 600,
    cwd: str | Path | None = None,
) -> None:
    """Run ffmpeg. Pass `timeout=` / `cwd=` as keyword if the last positional args would conflict."""
    cmd = [get_ffmpeg_executable(), "-y"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_NO_WINDOW,
        cwd=str(cwd) if cwd is not None else None,
    )
    if result.returncode != 0:
        err = (result.stderr or "") + (result.stdout or "")
        if len(err) > 6000:
            keys = (
                "error", "invalid", "failed", "no such", "could not", "not find",
                "cannot", "unsupported", "unknown decoder", "codec", "bitrate",
                "matches no streams", "divide", "opening", "permission",
            )
            lines = [L for L in err.splitlines() if any(k in L.lower() for k in keys)]
            head = "\n".join(lines[:100]) if lines else "\n".join(err.splitlines()[:40])
            err = f"{head}\n--- stderr tail ---\n{err[-3500:]}"
        raise RuntimeError(f"FFmpeg failed:\n{err}")


def _concat_demuxer_paths_line(p: Path) -> str:
    """Concat demuxer line: absolute path with forward slashes (FFmpeg-friendly on Windows)."""
    s = Path(p).resolve().as_posix()
    return f"file '{s}'"


def _concat_video_segments(concat_txt: Path, concat_out: Path) -> None:
    """
    Join segment videos. Prefer ``-c copy``; retry with ``libx264`` when clips mix stream-copy +
    transcoded GOP/SAR/etc. (often breaks demuxed MPEG-TS or mixed H.264 params).
    """
    try:
        _ffmpeg(
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-c",
            "copy",
            str(concat_out),
            timeout=1800,
            cwd=str(concat_txt.parent),
        )
        return
    except RuntimeError as exc:
        log.warning(
            "Concat stream-copy failed; re-encoding concatenated spine (libx264). First line: %s",
            str(exc).strip().splitlines()[0][:220],
        )
        try:
            if concat_out.is_file():
                concat_out.unlink()
        except OSError:
            pass
    _ffmpeg(
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_txt),
        "-map",
        "0:v:0",
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        "22",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        str(concat_out),
        timeout=7200,
        cwd=str(concat_txt.parent),
    )


def _path_needs_ffmpeg_workaround(p: Path) -> bool:
    """
    True when the file path is not pure ASCII. FFmpeg (libass) on Windows often fails
    to open files whose path contains emoji / non-Latin characters (e.g. folder name with ✅),
    so we re-stage inputs under the ASCII-only temp directory.
    """
    try:
        str(Path(p).resolve()).encode("ascii")
    except (UnicodeEncodeError, OSError, ValueError):
        return True
    return False


def _probe_duration(path: Path) -> float:
    """Return media duration in seconds via ffprobe, or 0.0 on error."""
    try:
        result = subprocess.run(
            [
                get_ffprobe_executable(),
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=_NO_WINDOW,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _audio_duration_sec(audio_path: Path) -> float:
    """Get audio duration using pydub (most reliable for mp3/aac)."""
    try:
        from pydub import AudioSegment
        return AudioSegment.from_file(str(audio_path)).duration_seconds
    except Exception:
        return _probe_duration(audio_path)


def _vf_scale(aspect_ratio: str) -> str:
    if aspect_ratio == "16:9":
        return "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
    # Default: 9:16 vertical
    return "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"


def _resolution(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "16:9":
        return 1920, 1080
    return 1080, 1920


def _normalized_segment_durations(segments: list[dict], total_out: float) -> list[float]:
    """Split total output duration across segments by duration_hint if present, else voiceover length; sum == total_out."""
    n = len(segments)
    if n == 0 or total_out <= 0:
        return []
    
    has_hints = any(seg.get("duration_hint") is not None for seg in segments)
    if has_hints:
        lengths = []
        for seg in segments:
            try:
                val = float(seg.get("duration_hint") or 1)
                lengths.append(max(0.1, val))
            except (ValueError, TypeError):
                lengths.append(1.0)
    else:
        lengths = [max(1, len((seg.get("voiceover") or "").strip())) for seg in segments]

    tot = sum(lengths)
    if tot <= 0:
        return [total_out / n] * n
    raw = [total_out * (l / tot) for l in lengths]
    if n == 1:
        return [total_out]
    s0 = sum(raw[:-1])
    raw[-1] = max(0.05, total_out - s0)
    return raw


def _sec_to_ass_time(t: float) -> str:
    """ASS timestamp 0:00:00.00 (centiseconds)."""
    t = max(0.0, float(t))
    cs_total = int(round(t * 100))
    h = cs_total // 360000
    rem = cs_total % 360000
    m = rem // 6000
    rem2 = rem % 6000
    s = rem2 // 100
    cs = rem2 % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape_line(text: str) -> str:
    text = text.replace("\\", "\\\\")
    return text.replace("{", r"\{").replace("}", r"\}")


def _wrap_subtitle_text(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        candidate = " ".join(cur + [w]).strip()
        if len(candidate) <= max_chars:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    joined = r"\N".join(_ass_escape_line(L) for L in lines)
    return joined


def _ass_fontname() -> str:
    # Nirmala UI ships on modern Windows; Libre Noto on Linux — default to a common Indic-capable UI font
    if sys.platform == "win32":
        return "Nirmala UI"
    return "Noto Sans Devanagari"


def _write_documentary_ass(
    segments: list[dict],
    total_duration_sec: float,
    ass_path: Path,
    aspect_ratio: str,
    subtitle_style: dict | None = None,
) -> int:
    w, h = _resolution(aspect_ratio)
    fs = 32 if h >= 1600 else 28
    margin_v = 72 if h >= 1600 else 56
    durs = _normalized_segment_durations(segments, total_duration_sec)
    font = _ass_fontname()
    
    style = subtitle_style or {}
    # Convert HEX like "#FFFFFF" to ASS format "&H00FFFFFF" (where 00 is alpha opaque)
    color_hex = style.get("color", "#FFFFFF").lstrip("#")
    if len(color_hex) == 6:
        color_ass = f"&H00{color_hex[4:6]}{color_hex[2:4]}{color_hex[0:2]}"
    else:
        color_ass = "&H00FFFFFF"
        
    bg_hex = style.get("bg_color", "&H80000000") # Already in ASS format if from our UI
    bold = "-1" if style.get("bold", True) else "0"
    italic = "-1" if style.get("italic", False) else "0"
    
    # "ScriptType: v4.00+" = ASS/SSA spec version (not Ghost Creator `APP_VERSION`).
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "PlayResX: {w}\n"
        "PlayResY: {h}\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: DocSub,{font},{fs},{color_ass},&H000000FF,&H00000000,{bg_hex},{bold},{italic},0,0,100,100,0,0,1,2,1,2,20,20,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    ).format(w=w, h=h, font=font, fs=fs, mv=margin_v)

    max_chars = 40 if w >= 1080 else 34
    t0 = 0.0
    events: list[str] = []
    for seg, dur in zip(segments, durs):
        lang = (subtitle_style or {}).get("language", "voiceover")
        if lang == "en":
            body = (seg.get("english_subtitle_text") or seg.get("english_subtitle") or seg.get("voiceover") or "").strip()
        else:
            body = (seg.get("voiceover") or "").strip()
        if not body:
            t0 += dur
            continue
        
        words = body.split()
        cues = []
        cur_words = []
        cur_len = 0
        # Limit to roughly 2 lines (e.g. 80 chars)
        limit = max_chars * 2
        for w_tok in words:
            if cur_len + len(w_tok) + 1 > limit and cur_words:
                cues.append(" ".join(cur_words))
                cur_words = [w_tok]
                cur_len = len(w_tok)
            else:
                cur_words.append(w_tok)
                cur_len += len(w_tok) + (1 if cur_len > 0 else 0)
        if cur_words:
            cues.append(" ".join(cur_words))
            
        total_len = sum(len(c) for c in cues)
        t_cue = t0
        for cue_text in cues:
            cue_dur = dur * (len(cue_text) / max(1, total_len))
            line = _wrap_subtitle_text(cue_text, max_chars=max_chars)
            if line:
                events.append(
                    f"Dialogue: 0,{_sec_to_ass_time(t_cue)},{_sec_to_ass_time(t_cue + cue_dur)},DocSub,,0,0,0,,{line}"
                )
            t_cue += cue_dur
            
        t0 += dur

    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return len(events)


def _ffmpeg_ass_path(ass_p: Path) -> str:
    """Path string for ffmpeg `ass=` filter. By using cwd=tmp, we just pass the filename."""
    return ass_p.name


def wants_burned_subtitles(config) -> bool:
    """True when user enabled burn-in and documentary run is long-form (not short pipeline)."""
    if not bool(config.get("documentary.burn_subtitles", False)):
        return False
    if (config.get("documentary.length_mode", "short") or "short") != "long":
        return False
    return True


def _normalize_logo_spec(logo_watermark: dict | None) -> dict | None:
    """
    Resolve logo overlay options from an explicit dict (editor / tests) or from config.
    Returns None if watermark should be skipped.
    Dict may be ``{"enabled": False}`` to force off for one export.
    """
    from core.config_manager import config as _cfg

    if logo_watermark is not None and logo_watermark.get("enabled") is False:
        return None

    def _clip(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(v)))

    def _logo_scale_fraction(raw: object) -> float:
        x = float(raw if raw is not None else 0.15)
        if x > 1.0:
            x = x / 100.0
        return _clip(x, 0.05, 0.45)

    if logo_watermark is None:
        if not bool(_cfg.get("documentary.logo_enabled", False)):
            return None
        path_s = (str(_cfg.get("documentary.logo_path", "") or "")).strip()
        if not path_s:
            return None
        path = Path(path_s)
        if not path.is_file():
            return None
        pos = str(_cfg.get("documentary.logo_position", "bottom_right") or "bottom_right")
        if pos not in _LOGO_POSITIONS:
            pos = "bottom_right"
        return {
            "path": path,
            "position": pos,
            "scale": _logo_scale_fraction(_cfg.get("documentary.logo_scale", 0.15)),
            "margin": int(max(0, min(120, int(_cfg.get("documentary.logo_margin", 24))))),
            "opacity": _clip(float(_cfg.get("documentary.logo_opacity", 1.0)), 0.05, 1.0),
        }

    path = logo_watermark.get("path")
    if path is None:
        path_s = (str(_cfg.get("documentary.logo_path", "") or "")).strip()
        path = Path(path_s) if path_s else None
    elif isinstance(path, str):
        path = Path(path.strip()) if path.strip() else None
    elif not isinstance(path, Path):
        path = Path(str(path))
    if not path or not path.is_file():
        return None

    pos = str(logo_watermark.get("position") or _cfg.get("documentary.logo_position", "bottom_right"))
    if pos not in _LOGO_POSITIONS:
        pos = "bottom_right"
    scale = _logo_scale_fraction(logo_watermark.get("scale", _cfg.get("documentary.logo_scale", 0.15)))
    margin = int(logo_watermark.get("margin", _cfg.get("documentary.logo_margin", 24)))
    margin = max(0, min(120, margin))
    opacity = _clip(float(logo_watermark.get("opacity", _cfg.get("documentary.logo_opacity", 1.0))), 0.05, 1.0)
    return {
        "path": path,
        "position": pos,
        "scale": scale,
        "margin": margin,
        "opacity": opacity,
    }


def _logo_overlay_expressions(position: str, margin: int) -> tuple[str, str]:
    m = int(max(0, margin))
    if position == "top_left":
        return str(m), str(m)
    if position == "top_right":
        return f"main_w-overlay_w-{m}", str(m)
    if position == "bottom_left":
        return str(m), f"main_h-overlay_h-{m}"
    # bottom_right
    return f"main_w-overlay_w-{m}", f"main_h-overlay_h-{m}"


def _apply_logo_watermark(
    video_path: Path,
    spec: dict,
    video_w: int,
    tmp: Path,
    progress_callback: _CB,
) -> None:
    """Burn logo onto ``video_path`` in-place (replaced via temp file)."""
    logo_path = Path(spec["path"])
    pos = spec["position"]
    margin = int(spec["margin"])
    opacity = float(spec["opacity"])
    scale = float(spec["scale"])
    logo_w = max(32, int(video_w * scale))
    logo_w = (logo_w // 2) * 2

    vin, lin = video_path, logo_path
    work_tmp = Path(tmp)
    if _path_needs_ffmpeg_workaround(video_path):
        vin = work_tmp / "_wm_video_in.mp4"
        shutil.copy2(video_path, vin)
    if _path_needs_ffmpeg_workaround(logo_path):
        ext = logo_path.suffix.lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg"):
            ext = ".png"
        lin = work_tmp / f"_wm_logo_in{ext}"
        shutil.copy2(logo_path, lin)

    ox, oy = _logo_overlay_expressions(pos, margin)
    opc = max(0.05, min(1.0, opacity))
    if opc < 0.999:
        lg_chain = f"[1:v]scale={logo_w}:-1,format=rgba,colorchannelmixer=aa={opc:.5f}[lg]"
    else:
        lg_chain = f"[1:v]scale={logo_w}:-1,format=rgba[lg]"
    fc = f"{lg_chain};[0:v][lg]overlay={ox}:{oy}[outv]"
    vout = work_tmp / "_wm_out.mp4"

    _notify(progress_callback, "  🖼 Applying logo watermark …")
    _ffmpeg(
        "-i", str(vin),
        "-i", str(lin),
        "-filter_complex", fc,
        "-map", "[outv]",
        "-map", "0:a",
        "-c:a", "copy",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        str(vout),
        timeout=7200,
        cwd=str(work_tmp) if work_tmp else None,
    )
    try:
        video_path.unlink()
    except OSError:
        pass
    shutil.move(str(vout), str(video_path))


def _trim_or_loop_clip(
    src: Path,
    dst: Path,
    duration: float,
    vf: str,
) -> None:
    """
    Trim clip to `duration` seconds, applying `vf` scale filter.
    If clip is shorter than needed, loop it.
    """
    clip_dur = _probe_duration(src)

    if clip_dur <= 0 or clip_dur < duration - 0.5:
        # Need to loop — calculate how many stream_loop iterations are enough
        loops = max(2, int(duration / max(clip_dur, 0.1)) + 2)
        _ffmpeg(
            "-stream_loop", str(loops),
            "-i", str(src),
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-crf", "22", "-preset", "fast",
            "-r", "30", "-an",
            str(dst),
        )
    else:
        _ffmpeg(
            "-i", str(src),
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-crf", "22", "-preset", "fast",
            "-r", "30", "-an",
            str(dst),
        )


def _make_black_filler(dst: Path, duration: float, w: int, h: int) -> None:
    """Generate a black silent video clip of `duration` seconds."""
    _ffmpeg(
        "-f", "lavfi",
        "-i", f"color=c=black:s={w}x{h}:r=30:d={duration}",
        "-c:v", "libx264", "-crf", "22", "-preset", "fast",
        "-an",
        str(dst),
    )


def assemble_documentary(
    clips: list[Path | None],
    audio_path: Path,
    segments: list[dict],
    output_dir: Path,
    output_filename: str = "documentary.mp4",
    aspect_ratio: str = "9:16",
    progress_callback: _CB = None,
    playback_speed: float = 1.0,
    burn_subtitles: bool = False,
    subtitle_style: dict | None = None,
    bg_music_path: Path | str | None = None,
    bg_music_volume: float = 0.25,
    narration_volume: float = 1.0,
    logo_watermark: dict | None = None,
) -> Path:
    """
    Build the final documentary video:

    Args:
        clips:           one Path (or None) per segment from video_fetcher
        audio_path:      full voiceover MP3/AAC
        segments:        list of dicts with ``voiceover`` key (for duration math)
        output_dir:      where to write the final file
        output_filename: e.g. "documentary_20260415_201527.mp4"
        aspect_ratio:    "9:16" (default) or "16:9"
        progress_callback: optional fn(str)
        playback_speed:  1.0 = normal; other values scale video + voice together (same factor)
        burn_subtitles:  if True, re-encode with burned-in ASS (white, bold, bottom)
        subtitle_style:  dict with styling options for the subtitles
        bg_music_path:   optional bed music mixed under narration at given volume
        bg_music_volume: 0.0–1.0 linear gain applied to bed before amix
        logo_watermark:  optional ``{"enabled": bool, "path", "position", "scale", "margin", "opacity"}``;
                         ``None`` uses Settings (``documentary.logo_*``). ``{"enabled": False}`` skips.

    Returns:
        Path to assembled video
    """
    tmp_dir = tempfile.mkdtemp(prefix="doc_asm_")
    try:
        return _assemble(
            clips, audio_path, segments, output_dir,
            output_filename, aspect_ratio, progress_callback, tmp_dir,
            playback_speed=playback_speed,
            burn_subtitles=burn_subtitles,
            subtitle_style=subtitle_style,
            bg_music_path=bg_music_path,
            bg_music_volume=bg_music_volume,
            narration_volume=narration_volume,
            logo_watermark=logo_watermark,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _clip_source_path(src) -> Path | None:
    """Normalize ``Path`` or :class:`~core.clip_manager.ClipInfo` to a path."""
    if src is None:
        return None
    if isinstance(src, ClipInfo):
        return src.path
    return Path(src)


def _mix_background_music(
    video_path: Path,
    music_path: Path,
    music_gain: float,
    output_path: Path,
    narration_volume: float = 1.0,
) -> None:
    """Mix narration (from video) with bed music; output length follows video/voice."""
    g  = max(0.0, min(1.5, float(music_gain)))
    vg = max(0.0, min(2.0, float(narration_volume)))
    fc = (
        f"[0:a]volume={vg:.5f}[a0];"
        f"[1:a]volume={g:.5f},apad[a1];"
        f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    _ffmpeg(
        "-i", str(video_path),
        "-i", str(music_path),
        "-filter_complex", fc,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
        timeout=1800,
    )


def _try_fast_video_trim(
    src_path: Path,
    dst: Path,
    dur: float,
) -> bool:
    """
    Try stream-copy first ``dur`` seconds of video (no audio). Returns True on success.
    Falls back to caller if False.
    """
    clip_len = _probe_duration(src_path)
    if clip_len + 0.05 < dur:
        return False
    try:
        _ffmpeg(
            "-i", str(src_path),
            "-t", str(dur),
            "-c", "copy",
            "-an",
            str(dst),
            timeout=300,
        )
        out_len = _probe_duration(dst)
        if out_len + 0.2 < dur * 0.92:
            return False
        return True
    except Exception:
        if dst.exists():
            try:
                dst.unlink()
            except OSError:
                pass
        return False


def _assemble(
    clips, audio_path, segments, output_dir,
    output_filename, aspect_ratio, progress_callback, tmp_dir,
    playback_speed: float = 1.0,
    burn_subtitles: bool = False,
    subtitle_style: dict | None = None,
    bg_music_path: Path | str | None = None,
    bg_music_volume: float = 0.25,
    narration_volume: float = 1.0,
    logo_watermark: dict | None = None,
) -> Path:
    tmp = Path(tmp_dir)

    # ── 1. Voiceover total duration ──────────────────────────────────────
    total_sec = _audio_duration_sec(audio_path)
    _notify(progress_callback, f"  🕐 Voiceover: {total_sec:.1f}s total")

    # ── 2. Per-segment allocations (same weighting as subtitle cues: sums to total_sec) ─
    durations = _normalized_segment_durations(segments, total_sec)

    vf = _vf_scale(aspect_ratio)
    w, h = _resolution(aspect_ratio)

    # ── 3. Trim / loop / fallback each clip ─────────────────────────────
    trimmed: list[Path] = []
    last_good: Path | None = None   # used as filler when a clip is missing

    for i, (seg, dur) in enumerate(zip(segments, durations)):
        src = clips[i] if i < len(clips) else None
        src_path = _clip_source_path(src)
        dst = tmp / f"t_{i:02d}.mp4"

        _notify(progress_callback, f"  ✂️  Clip {i+1}/{len(segments)}: {dur:.1f}s")

        if src_path and src_path.exists() and src_path.stat().st_size > 5000:
            try:
                if _try_fast_video_trim(src_path, dst, dur):
                    last_good = dst
                else:
                    _trim_or_loop_clip(src_path, dst, dur, vf)
                    last_good = dst
            except Exception as exc:
                log.warning("Trim failed for clip %s: %s — using filler", i + 1, exc)
                _make_filler(dst, dur, w, h, last_good, tmp, i)
        else:
            _notify(progress_callback, f"  ⚠️  Clip {i+1} missing — black filler")
            _make_filler(dst, dur, w, h, last_good, tmp, i)

        trimmed.append(dst)

    # ── 4. Concatenate ───────────────────────────────────────────────────
    _notify(progress_callback, "  🔗 Concatenating clips …")
    concat_txt = tmp / "concat.txt"
    concat_txt.write_text(
        "\n".join(_concat_demuxer_paths_line(p) for p in trimmed),
        encoding="utf-8",
    )
    concat_out = tmp / "concat.mp4"
    _concat_video_segments(concat_txt, concat_out)

    # ── 5. Attach voiceover, strip original audio; optional same-factor speedup ─
    _notify(progress_callback, "  🎵 Attaching voiceover …")
    output_dir.mkdir(parents=True, exist_ok=True)
    final = output_dir / output_filename
    # atempo supports 0.5–2.0 per filter; keep exports predictable
    spd = min(2.0, max(0.5, float(playback_speed)))
    if abs(spd - 1.0) < 0.001:
        _ffmpeg(
            "-i", str(concat_out),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(final),
        )
    else:
        _notify(progress_callback, f"  ⚡ Output playback {spd}× (video + voice in sync) …")
        fcx = f"[0:v]setpts=PTS/{spd:.6f}[v];[1:a]atempo={spd:.6f}[a]"
        _ffmpeg(
            "-i", str(concat_out),
            "-i", str(audio_path),
            "-filter_complex", fcx,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-crf", "22", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(final),
        )

    bg_p = Path(bg_music_path) if bg_music_path else None
    if bg_p and bg_p.is_file() and bg_p.stat().st_size > 100:
        _notify(progress_callback, "  🎵 Mixing background music …")
        mixed = tmp / "mixed_with_music.mp4"
        try:
            _mix_background_music(final, bg_p, float(bg_music_volume), mixed,
                                  narration_volume=float(narration_volume))
            try:
                final.unlink()
            except OSError:
                pass
            shutil.move(str(mixed), str(final))
        except Exception as exc:
            log.warning("Background music mix failed: %s — keeping voice-only video", exc)

    if burn_subtitles and segments:
        d_out = _probe_duration(final)
        if d_out > 0.2:
            ass_p = tmp / "doc_subs.ass"
            n_cues = _write_documentary_ass(segments, d_out, ass_p, aspect_ratio, subtitle_style)
            if n_cues > 0:
                _notify(progress_callback, "  📝 Burning subtitles (bottom, white, bold) …")
                vout = tmp / "subbed_out.mp4"
                apf = _ffmpeg_ass_path(ass_p)
                # Windows FFmpeg + libass often break on paths with emoji/Unicode (e.g. "✅" in folder).
                # Re-stage the muxed file next to the ASS under ASCII-only %TEMP% for this pass.
                burn_src = final
                if _path_needs_ffmpeg_workaround(final):
                    _notify(
                        progress_callback,
                        "  📁 (subtitle pass: using temp folder — path has special characters) …",
                    )
                    burn_src = tmp / "_burn_input.mp4"
                    shutil.copy2(final, burn_src)
                try:
                    _ffmpeg(
                        "-i", str(burn_src),
                        "-vf", f"ass={apf}",
                        "-c:a", "copy",
                        "-c:v", "libx264", "-crf", "23", "-preset", "ultrafast", "-threads", "0",
                        str(vout),
                        timeout=7200,
                        cwd=tmp,
                    )
                finally:
                    if burn_src is not final and burn_src.exists():
                        try:
                            burn_src.unlink()
                        except OSError:
                            pass
                try:
                    final.unlink()
                except OSError:
                    pass
                shutil.move(str(vout), str(final))
            else:
                log.info("No subtitle cues — skipping burn-in.")

    _logo_spec = _normalize_logo_spec(logo_watermark)
    if _logo_spec:
        try:
            _apply_logo_watermark(final, _logo_spec, w, tmp, progress_callback)
        except Exception as exc:
            log.warning("Logo watermark skipped: %s", exc)
            _notify(progress_callback, f"  ⚠️ Logo watermark failed — output has no logo. ({exc})")

    size_mb = final.stat().st_size / (1024 * 1024)
    _notify(progress_callback, f"  ✅ Documentary ready: {final.name} ({size_mb:.1f} MB)")
    return final


def _make_filler(dst: Path, dur: float, w: int, h: int, last_good: Path | None, tmp: Path, idx: int) -> None:
    """Use last good clip looped, or black video, as a filler."""
    if last_good and last_good.exists():
        try:
            _ffmpeg(
                "-stream_loop", "5",
                "-i", str(last_good),
                "-t", str(dur),
                "-c:v", "libx264", "-crf", "22", "-preset", "fast",
                "-r", "30", "-an",
                str(dst),
            )
            return
        except Exception:
            pass
    _make_black_filler(dst, dur, w, h)
