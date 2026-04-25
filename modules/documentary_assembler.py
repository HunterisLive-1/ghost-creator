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

log = get_logger("doc_assembler")

# Hide console flashes when running bundled ffmpeg/ffprobe on Windows (PyInstaller .exe)
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_CB = Callable[[str], None] | None


def _notify(fn: _CB, msg: str) -> None:
    log.info(msg)
    if fn:
        fn(msg)


def _ffmpeg(*args: str, timeout: int = 600) -> None:
    """Run ffmpeg. Pass `timeout=` as keyword if the last positional args would conflict."""
    cmd = [get_ffmpeg_executable(), "-y"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-2000:]}")


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


def _segment_durations(segments: list[dict], total_sec: float) -> list[float]:
    """
    Distribute total_sec among segments proportional to voiceover character count.
    Minimum 2s per segment.
    """
    lengths = [max(10, len(seg.get("voiceover", ""))) for seg in segments]
    total_len = sum(lengths)
    raw = [total_sec * (l / total_len) for l in lengths]
    # Enforce minimum 2s
    return [max(2.0, d) for d in raw]


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
    """Split total output duration across segments by voiceover length; sum == total_out."""
    n = len(segments)
    if n == 0 or total_out <= 0:
        return []
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
) -> int:
    w, h = _resolution(aspect_ratio)
    fs = 32 if h >= 1600 else 28
    margin_v = 72 if h >= 1600 else 56
    durs = _normalized_segment_durations(segments, total_duration_sec)
    font = _ass_fontname()
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
        "Style: DocSub,{font},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,20,20,{mv},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    ).format(w=w, h=h, font=font, fs=fs, mv=margin_v)

    max_chars = 40 if w >= 1080 else 34
    t0 = 0.0
    events: list[str] = []
    for seg, dur in zip(segments, durs):
        body = (seg.get("voiceover") or "").strip()
        if not body:
            t0 += dur
            continue
        t1 = t0 + dur
        line = _wrap_subtitle_text(body, max_chars=max_chars)
        if not line:
            t0 = t1
            continue
        events.append(
            f"Dialogue: 0,{_sec_to_ass_time(t0)},{_sec_to_ass_time(t1)},DocSub,,0,0,0,,{line}"
        )
        t0 = t1

    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return len(events)


def _ffmpeg_ass_path(ass_p: Path) -> str:
    """Path string for ffmpeg `ass=` filter on Windows (escape `C:`)."""
    p = ass_p.resolve()
    s = str(p).replace("\\", "/")
    if sys.platform == "win32" and len(s) >= 2 and s[1] == ":":
        s = s[0] + r"\:" + s[2:]
    return s


def wants_burned_subtitles(config) -> bool:
    """True when user enabled burn-in and documentary run is long-form (not short pipeline)."""
    if not bool(config.get("documentary.burn_subtitles", False)):
        return False
    if (config.get("documentary.length_mode", "short") or "short") != "long":
        return False
    return True


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
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _assemble(
    clips, audio_path, segments, output_dir,
    output_filename, aspect_ratio, progress_callback, tmp_dir,
    playback_speed: float = 1.0,
    burn_subtitles: bool = False,
) -> Path:
    tmp = Path(tmp_dir)

    # ── 1. Voiceover total duration ──────────────────────────────────────
    total_sec = _audio_duration_sec(audio_path)
    _notify(progress_callback, f"  🕐 Voiceover: {total_sec:.1f}s total")

    # ── 2. Per-segment allocations ───────────────────────────────────────
    durations = _segment_durations(segments, total_sec)

    vf = _vf_scale(aspect_ratio)
    w, h = _resolution(aspect_ratio)

    # ── 3. Trim / loop / fallback each clip ─────────────────────────────
    trimmed: list[Path] = []
    last_good: Path | None = None   # used as filler when a clip is missing

    for i, (seg, dur) in enumerate(zip(segments, durations)):
        src = clips[i] if i < len(clips) else None
        dst = tmp / f"t_{i:02d}.mp4"

        _notify(progress_callback, f"  ✂️  Clip {i+1}/{len(segments)}: {dur:.1f}s")

        if src and src.exists() and src.stat().st_size > 5000:
            try:
                _trim_or_loop_clip(src, dst, dur, vf)
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
        "\n".join(f"file '{p}'" for p in trimmed),
        encoding="utf-8",
    )
    concat_out = tmp / "concat.mp4"
    _ffmpeg(
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy",
        str(concat_out),
    )

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

    if burn_subtitles and segments:
        d_out = _probe_duration(final)
        if d_out > 0.2:
            ass_p = tmp / "doc_subs.ass"
            n_cues = _write_documentary_ass(segments, d_out, ass_p, aspect_ratio)
            if n_cues > 0:
                _notify(progress_callback, "  📝 Burning subtitles (bottom, white, bold) …")
                vout = tmp / "subbed_out.mp4"
                apf = _ffmpeg_ass_path(ass_p)
                _ffmpeg(
                    "-i", str(final),
                    "-vf", f"ass={apf}",
                    "-c:a", "copy",
                    "-c:v", "libx264", "-crf", "22", "-preset", "fast",
                    str(vout),
                    timeout=7200,
                )
                try:
                    final.unlink()
                except OSError:
                    pass
                shutil.move(str(vout), str(final))
            else:
                log.info("No subtitle cues — skipping burn-in.")

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
