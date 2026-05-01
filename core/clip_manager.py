"""
core/clip_manager.py — Clip Data Model & FFmpeg Editing Operations
===================================================================
Provides all the building blocks for the Ghost Creator pre-upload video editor:
  • ClipInfo  — dataclass describing one video clip
  • SrtEntry  — dataclass for one subtitle cue
  • FFmpeg operations: trim, split, remove, replace, add, move
  • SRT parse / write / generate from segments
  • Export helpers: zip clips, copy audio

FFmpeg is called via subprocess (same as the rest of the pipeline).
Stream-copy is used by default (fast, no quality loss).
When re-encoding is explicitly requested the caller passes reencode=True.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import get_logger, get_ffmpeg_executable, get_ffprobe_executable

log = get_logger("clip_manager")

# Suppress CMD window flash in frozen Windows exe
_NO_WINDOW: int = (
    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SrtEntry:
    index: int
    start: str   # "HH:MM:SS,mmm"
    end: str     # "HH:MM:SS,mmm"
    text: str


@dataclass
class ClipInfo:
    path: Path
    duration: float          # seconds (probed by ffprobe)
    search_query: str = ""   # search term used to fetch this clip
    segment_index: int = 0
    # Voiceover-aligned target for this segment (0 = unknown / not shown)
    target_duration_sec: float = 0.0

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def effective_duration(self) -> float:
        return max(0.0, self.duration)


# ── FFprobe helpers ───────────────────────────────────────────────────────────

def get_clip_duration(path: Path) -> float:
    """Probe clip duration in seconds using ffprobe."""
    fp_bin = get_ffprobe_executable()
    try:
        result = subprocess.run(
            [fp_bin, "-v", "quiet", "-print_format", "json",
             "-show_streams", str(path)],
            capture_output=True, text=True, timeout=20,
            creationflags=_NO_WINDOW,
        )
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                dur = stream.get("duration")
                if dur:
                    return float(dur)
        # Fallback: use format-level duration
        result2 = subprocess.run(
            [fp_bin, "-v", "quiet", "-print_format", "json",
             "-show_format", str(path)],
            capture_output=True, text=True, timeout=20,
            creationflags=_NO_WINDOW,
        )
        data2 = json.loads(result2.stdout)
        dur = data2.get("format", {}).get("duration")
        return float(dur) if dur else 0.0
    except Exception as exc:
        log.warning("get_clip_duration(%s): %s", path, exc)
        return 0.0


def load_clips(
    clip_paths: list[Path | str | None],
    segments: list[dict] | None = None,
    target_durations: list[float] | None = None,
) -> list[ClipInfo]:
    """Build ClipInfo list from raw paths, probing each clip's duration."""
    clips: list[ClipInfo] = []
    for i, p in enumerate(clip_paths):
        if p is None:
            continue
        p = Path(p)
        if not p.exists():
            log.warning("load_clips: path does not exist: %s", p)
            continue
        dur = get_clip_duration(p)
        query = ""
        if segments and i < len(segments):
            query = str(segments[i].get("video_query", ""))
        tsec = 0.0
        if target_durations and i < len(target_durations):
            tsec = float(target_durations[i])
        clips.append(ClipInfo(
            path=p,
            duration=dur,
            search_query=query,
            segment_index=i,
            target_duration_sec=tsec,
        ))
    return clips


# ── FFmpeg operations ─────────────────────────────────────────────────────────

def _run_ffmpeg(args: list[str], timeout: int = 180) -> None:
    """Run an ffmpeg command, raising RuntimeError on failure."""
    cmd = [get_ffmpeg_executable(), "-y"] + args
    log.debug("ffmpeg: %s", " ".join(cmd))
    result = subprocess.run(
        cmd, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")[-600:]
        raise RuntimeError(f"FFmpeg error:\n{err}")


def trim_clip(
    clip: ClipInfo,
    start_s: float,
    end_s: float,
    output_dir: Path,
    reencode: bool = False,
) -> ClipInfo:
    """
    Trim a clip between start_s and end_s seconds.

    Parameters
    ----------
    reencode : If True, re-encodes for frame-accurate cuts (slower).
               If False, uses stream-copy (fast, may snap to nearest keyframe).
    """
    if start_s < 0:
        start_s = 0.0
    if end_s <= start_s:
        raise ValueError(f"end_s ({end_s:.2f}) must be > start_s ({start_s:.2f})")
    if end_s > clip.duration:
        end_s = clip.duration

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = clip.path.stem
    tag = f"trim_{int(start_s * 10)}_{int(end_s * 10)}"
    out_path = output_dir / f"{stem}_{tag}.mp4"

    codec_args = ["-c", "copy"] if not reencode else ["-c:v", "libx264", "-c:a", "aac", "-preset", "fast"]

    _run_ffmpeg([
        "-ss", str(start_s),
        "-to", str(end_s),
        "-i", str(clip.path),
        *codec_args,
        str(out_path),
    ])

    new_dur = get_clip_duration(out_path)
    return ClipInfo(
        path=out_path,
        duration=new_dur,
        search_query=clip.search_query,
        segment_index=clip.segment_index,
        target_duration_sec=clip.target_duration_sec,
    )


def split_clip(
    clip: ClipInfo,
    split_at_s: float,
    output_dir: Path,
    reencode: bool = False,
) -> tuple[ClipInfo, ClipInfo]:
    """
    Split a clip into two parts at split_at_s seconds from the clip's start.

    Returns
    -------
    (part_a, part_b) as new ClipInfo objects.
    part_a covers [0, split_at_s).
    part_b covers [split_at_s, end).
    """
    if split_at_s <= 0:
        raise ValueError(f"split_at_s must be > 0, got {split_at_s:.2f}")
    if split_at_s >= clip.duration:
        raise ValueError(
            f"split_at_s ({split_at_s:.2f}s) must be < clip duration ({clip.duration:.2f}s)"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = clip.path.stem
    out_a = output_dir / f"{stem}_split_A.mp4"
    out_b = output_dir / f"{stem}_split_B.mp4"

    codec_args = ["-c", "copy"] if not reencode else ["-c:v", "libx264", "-c:a", "aac", "-preset", "fast"]

    # Part A: 0 → split_at_s
    _run_ffmpeg([
        "-ss", "0",
        "-to", str(split_at_s),
        "-i", str(clip.path),
        *codec_args,
        str(out_a),
    ])

    # Part B: split_at_s → end
    _run_ffmpeg([
        "-ss", str(split_at_s),
        "-i", str(clip.path),
        *codec_args,
        str(out_b),
    ])

    dur_a = get_clip_duration(out_a)
    dur_b = get_clip_duration(out_b)

    return (
        ClipInfo(path=out_a, duration=dur_a,
                 search_query=clip.search_query, segment_index=clip.segment_index,
                 target_duration_sec=clip.target_duration_sec),
        ClipInfo(path=out_b, duration=dur_b,
                 search_query=f"{clip.search_query} (B)", segment_index=clip.segment_index,
                 target_duration_sec=0.0),
    )


def remove_clip(clips: list[ClipInfo], index: int) -> list[ClipInfo]:
    """Return a new list with the clip at *index* removed."""
    out = list(clips)
    if 0 <= index < len(out):
        out.pop(index)
    return out


def replace_clip(clips: list[ClipInfo], index: int, new_path: Path) -> list[ClipInfo]:
    """Return a new list with the clip at *index* replaced by *new_path*."""
    out = list(clips)
    if 0 <= index < len(out):
        dur = get_clip_duration(new_path)
        prev = out[index]
        out[index] = ClipInfo(
            path=new_path,
            duration=dur,
            search_query=prev.search_query,
            segment_index=prev.segment_index,
            target_duration_sec=prev.target_duration_sec,
        )
    return out


def move_clip(clips: list[ClipInfo], from_idx: int, to_idx: int) -> list[ClipInfo]:
    """Return a new list with the clip moved from from_idx to to_idx."""
    out = list(clips)
    n = len(out)
    if from_idx == to_idx or not (0 <= from_idx < n) or not (0 <= to_idx < n):
        return out
    clip = out.pop(from_idx)
    out.insert(to_idx, clip)
    return out


def add_clip(
    clips: list[ClipInfo],
    new_path: Path,
    at_index: int | None = None,
) -> list[ClipInfo]:
    """Insert a new clip from *new_path* at *at_index* (appends if None or out of range)."""
    out = list(clips)
    dur = get_clip_duration(new_path)
    ci = ClipInfo(path=new_path, duration=dur, search_query="custom")
    if at_index is None or at_index >= len(out):
        out.append(ci)
    else:
        out.insert(max(0, at_index), ci)
    return out


# ── SRT helpers ───────────────────────────────────────────────────────────────

def parse_srt(srt_path: Path) -> list[SrtEntry]:
    """Parse an SRT file and return a list of SrtEntry objects."""
    if not srt_path.exists():
        return []
    text = srt_path.read_text(encoding="utf-8", errors="replace")
    entries: list[SrtEntry] = []
    blocks = re.split(r"\n{2,}", text.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        if " --> " not in lines[1]:
            continue
        start, end = lines[1].split(" --> ", 1)
        txt = "\n".join(lines[2:]).strip()
        entries.append(SrtEntry(
            index=idx,
            start=start.strip(),
            end=end.strip(),
            text=txt,
        ))
    return entries


def write_srt(entries: list[SrtEntry], output_path: Path) -> None:
    """Write SRT entries to file, re-numbering from 1."""
    lines: list[str] = []
    for i, e in enumerate(entries, start=1):
        lines.append(str(i))
        lines.append(f"{e.start} --> {e.end}")
        lines.append(e.text)
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _sec_to_srt_time(s: float) -> str:
    """Convert seconds (float) to SRT timestamp string HH:MM:SS,mmm."""
    ms = int(round((s % 1) * 1000))
    total = int(s)
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def srt_time_to_sec(ts: str) -> float:
    """Parse SRT timestamp HH:MM:SS,mmm → float seconds."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def generate_srt_from_segments(
    segments: list[dict],
    audio_duration: float,
) -> list[SrtEntry]:
    """
    Build SRT entries from script segments when no SRT file exists.
    Timing is distributed proportionally based on narration length.
    """
    total_chars = sum(len(str(s.get("voiceover", ""))) for s in segments)
    if total_chars == 0 or audio_duration <= 0:
        return []

    entries: list[SrtEntry] = []
    t = 0.0
    idx = 1
    max_chars = 40
    limit = max_chars * 2
    for seg in segments:
        vo = str(seg.get("voiceover", "")).strip()
        if not vo:
            continue
        
        # Calculate full segment duration
        proportion = len(vo) / total_chars
        seg_dur = audio_duration * proportion
        
        words = vo.split()
        cues = []
        cur_words = []
        cur_len = 0
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
        t_cue = t
        for cue_text in cues:
            cue_dur = seg_dur * (len(cue_text) / max(1, total_len))
            start = _sec_to_srt_time(t_cue)
            end = _sec_to_srt_time(t_cue + cue_dur)
            entries.append(SrtEntry(index=idx, start=start, end=end, text=cue_text))
            idx += 1
            t_cue += cue_dur
            
        t += seg_dur
    return entries


# ── Export helpers ────────────────────────────────────────────────────────────


def export_clips_zip(clips: list[ClipInfo], output_path: Path) -> Path:
    """Zip all clip files into a single archive at *output_path*."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_STORED) as zf:
        for i, clip in enumerate(clips):
            if clip.path.exists():
                arcname = f"clip_{i + 1:02d}_{clip.path.name}"
                zf.write(clip.path, arcname)
    log.info("Exported %d clips to %s", len(clips), output_path)
    return output_path


# Aliases expected by gui/components/clip_editor.py
export_srt_file = write_srt
export_clips_to_zip = export_clips_zip


def copy_audio(audio_path: Path, dest_path: Path) -> Path:
    """Copy voiceover audio to *dest_path* (for standalone audio export)."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio_path, dest_path)
    return dest_path


# ── Total timeline duration ───────────────────────────────────────────────────

def total_clips_duration(clips: list[ClipInfo]) -> float:
    """Sum of all clip effective durations in seconds."""
    return sum(c.effective_duration for c in clips)


def trim_audio(
    src: Path,
    dest: Path,
    start_s: float = 0.0,
    end_s: float | None = None,
    *,
    reencode: bool = True,
) -> Path:
    """
    Extract [start_s, end_s] from an audio file using FFmpeg.
    If end_s is None, keeps from start_s to EOF.
    """
    if start_s < 0:
        start_s = 0.0
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if end_s is not None and end_s <= start_s:
        raise ValueError("end_s must be greater than start_s")
    if reencode:
        args: list[str] = ["-i", str(src), "-ss", str(start_s)]
        if end_s is not None:
            args += ["-t", str(end_s - start_s)]
        args += ["-c:a", "aac", "-b:a", "192k", str(dest)]
    else:
        args = ["-ss", str(start_s), "-i", str(src)]
        if end_s is not None:
            args += ["-to", str(end_s)]
        args += ["-c:a", "copy", str(dest)]
    _run_ffmpeg(args, timeout=600)
    return dest


def trim_background_music(
    src: Path,
    dest: Path,
    start_s: float = 0.0,
    end_s: float | None = None,
) -> Path:
    """Trim background music segment (re-encoded for reliable cut points)."""
    return trim_audio(src, dest, start_s, end_s, reencode=True)
