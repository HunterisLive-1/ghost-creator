"""
gui/components/clip_editor.py — Ghost Editor
============================================
Timeline clip editor with optional VLC preview, trim/split, subtitles,
voice replace/trim, background music (+ trim + volume), then DONE for assembly.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from config import get_ffmpeg_executable
from core.config_manager import config
from core.clip_manager import (
    ClipInfo,
    SrtEntry,
    _sec_to_srt_time,
    add_clip,
    export_srt_file,
    generate_srt_from_segments,
    load_clips,
    move_clip,
    remove_clip,
    replace_clip,
    split_clip,
    srt_time_to_sec,
    trim_audio,
    trim_background_music,
    trim_clip,
    write_srt,
)
from core.vlc_helper import get_vlc_instance
from modules.documentary_assembler import (
    _audio_duration_sec,
    assemble_documentary,
    wants_burned_subtitles,
)

BG_MAIN = "#050A10"
BG_SEC = "#0A121A"
BG_CARD = "#0F1A24"
BORDER = "#1A2B3D"
ACCENT_PRI = "#0088FF"
ACCENT_SEC = "#00BFFF"
ACCENT_DOC = "#A020F0"
ACCENT_GRN = "#00CC66"
ACCENT_RED = "#FF4444"
ACCENT_WARN = "#FFB020"
TEXT_PRI = "#E6F0FF"
TEXT_SEC = "#88AADD"
TEXT_HINT = "#4A6080"

_LOGO_POS_TO_LABEL = {
    "bottom_right": "Bottom-right",
    "bottom_left": "Bottom-left",
    "top_right": "Top-right",
    "top_left": "Top-left",
}
_LOGO_LABEL_TO_POS = {v: k for k, v in _LOGO_POS_TO_LABEL.items()}

_SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def _srt_time_to_sec(t: str) -> float:
    """Convert SRT timestamp string 'HH:MM:SS,mmm' to seconds."""
    try:
        return srt_time_to_sec(t)
    except Exception:
        try:
            t = t.replace(",", ".")
            parts = t.split(":")
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            return h * 3600 + m * 60 + s
        except Exception:
            return 0.0


def _compute_waveform_envelope(path: Path, n_bars: int) -> list[float]:
    """Peak envelope 0..1 for timeline drawing (~Filmora-style)."""
    if not path.is_file() or n_bars < 8:
        return []
    try:
        from pydub import AudioSegment
    except ImportError:
        return []
    try:
        audio = AudioSegment.from_file(str(path))
        if len(audio) < 1:
            return []
        audio = audio.set_channels(1)
        ms_total = len(audio)
        chunk = max(1, ms_total // n_bars)
        out: list[float] = []
        for i in range(n_bars):
            chunk_audio = audio[i * chunk : (i + 1) * chunk]
            if len(chunk_audio) == 0:
                out.append(0.0)
                continue
            samples = chunk_audio.get_array_of_samples()
            if not samples:
                out.append(0.0)
            else:
                mx = max(abs(int(x)) for x in samples)
                out.append(float(mx))
        peak = max(out) or 1.0
        return [min(1.0, v / peak) for v in out]
    except Exception:
        return []


def _ffmpeg_filter_path_esc(p: Path) -> str:
    s = str(p.resolve()).replace("\\", "/")
    return s.replace(":", r"\:").replace("'", r"\'")


def _slice_srt_for_preview(entries: list[SrtEntry], window_start: float, window_dur: float) -> list[SrtEntry]:
    out: list[SrtEntry] = []
    w_end = window_start + window_dur
    idx = 1
    for e in entries:
        st = srt_time_to_sec(e.start)
        en = srt_time_to_sec(e.end)
        if en <= window_start or st >= w_end:
            continue
        st2 = max(0.0, st - window_start)
        en2 = min(window_dur, en - window_start)
        if en2 <= st2 + 0.05:
            continue
        out.append(SrtEntry(idx, _sec_to_srt_time(st2), _sec_to_srt_time(en2), e.text))
        idx += 1
    return out


def _windows_drawtext_fontfile() -> Path | None:
    if sys.platform != "win32":
        return None
    for name in ("C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\segoeui.ttf"):
        p = Path(name)
        if p.is_file():
            return p
    return None


def _ffmpeg_mux_preview(
    video: Path,
    voice: Path,
    video_ss: float,
    voice_ss: float,
    duration: float,
    out_path: Path,
    *,
    music: Path | None = None,
    music_gain: float = 0.25,
    voice_gain: float = 1.0,
    srt_slice_path: Path | None = None,
    title_lines_path: Path | None = None,
) -> None:
    """Preview: video + voice (+ music) + optional burned subs + title; re-encodes when overlays are used."""
    d = max(0.12, float(duration))
    v_ss = max(0.0, float(video_ss))
    vo_ss = max(0.0, float(voice_ss))
    mus = Path(music) if music and Path(music).is_file() else None
    g = max(0.0, min(1.5, float(music_gain)))
    vg = max(0.0, min(2.0, float(voice_gain)))
    ff = get_ffmpeg_executable()
    has_sv = srt_slice_path is not None and Path(srt_slice_path).is_file() and Path(srt_slice_path).stat().st_size > 4
    has_title = title_lines_path is not None and Path(title_lines_path).is_file() and Path(title_lines_path).stat().st_size > 0
    need_encode = mus is not None or has_sv or has_title

    if not need_encode:
        cmd = [
            ff,
            "-y",
            "-ss",
            f"{v_ss:.4f}",
            "-i",
            str(video),
            "-ss",
            f"{vo_ss:.4f}",
            "-i",
            str(voice),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{d:.4f}",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=_SUBPROCESS_FLAGS)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "")[-800:]
            raise RuntimeError(f"FFmpeg preview mux failed:\n{err}")
        return

    cmd = [ff, "-y", "-ss", f"{v_ss:.4f}", "-i", str(video), "-ss", f"{vo_ss:.4f}", "-t", f"{d:.4f}", "-i", str(voice)]
    if mus is not None:
        cmd += ["-ss", f"{vo_ss:.4f}", "-t", f"{d:.4f}", "-i", str(mus)]

    if mus is not None:
        ap = f"[1:a]volume={vg:.5f}[a1];[2:a]volume={g:.5f}[a2];[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    else:
        ap = f"[1:a]volume={vg:.5f}[aout]"

    if has_sv:
        sp = str(srt_slice_path.resolve()).replace("\\", "/")
        sp = sp.replace(":", r"\:").replace("'", r"\'")
        vpart = f"[0:v]subtitles='{sp}'[v1]"
    else:
        vpart = "[0:v]format=yuv420p[v1]"

    font = _windows_drawtext_fontfile()
    if has_title:
        tp = _ffmpeg_filter_path_esc(Path(title_lines_path))
        if font is not None:
            fe = _ffmpeg_filter_path_esc(font)
            vpart += (
                f";[v1]drawtext=textfile='{tp}':fontfile='{fe}':fontsize=20:fontcolor=white:"
                f"borderw=2:bordercolor=black@0.75:x=(w-text_w)/2:y=32:line_spacing=4[vout]"
            )
        else:
            vpart += (
                f";[v1]drawtext=textfile='{tp}':fontsize=20:fontcolor=white:"
                f"borderw=2:bordercolor=black@0.75:x=(w-text_w)/2:y=32:line_spacing=4[vout]"
            )
    else:
        vpart += ";[v1]format=yuv420p[vout]"

    fc = f"{vpart};{ap}"
    cmd += [
        "-filter_complex",
        fc,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "22",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, creationflags=_SUBPROCESS_FLAGS)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-1200:]
        raise RuntimeError(f"FFmpeg preview (overlays/music) failed:\n{err}")


class ClipEditorWindow(ctk.CTkToplevel):
    # ── timeline geometry (matches Ghost Editor reference proportions) ─────
    TRACK_LABEL_W    = 96   # left gutter width  (ref: LEFT_GUTTER = 96)
    RULER_H          = 44   # ruler strip height — tall enough to click reliably
    TRACK_GAP        = 8    # dark separator between tracks
    VIDEO_TRACK_H    = 60   # video lane height   (ref: TRACK_HEIGHT = 56)
    NARRATION_TRACK_H = 52  # voice lane
    MUSIC_TRACK_H    = 44   # music lane
    SUBTITLE_TRACK_H = 34   # subtitle lane
    TIMELINE_BOTTOM_PAD = 8
    PREVIEW_W = 520
    PREVIEW_H = 292
    _TL_MAX_BARS = 480   # max waveform bar columns per track

    # ── timeline colour palette (Ghost Editor reference) ──────────────────
    _TL_BG       = "#0E0E12"   # scene background
    _TL_PANEL    = "#16161C"   # ruler / lane fill
    _TL_PANEL_ALT= "#1C1C25"   # gutter / label area fill
    _TL_BORDER   = "#262631"   # separator / tick minor
    _TL_TEXT     = "#E6E6EC"   # label text
    _TL_MUTED    = "#8A8A96"   # ruler time labels
    _TL_VID      = "#7C5CFF"   # video accent (purple)
    _TL_VOICE    = "#5EE6D0"   # voice accent (teal)
    _TL_MUSIC    = "#E87CFF"   # music accent (pink-purple)
    _TL_SUBS     = "#FFB65E"   # subs accent (orange)
    _TL_PLAYHEAD = "#FF5E7A"   # playhead line (pink-red)
    _TL_TICK_MAJ = "#5EE6D0"   # major ruler tick colour

    def __init__(
        self,
        parent,
        clips: list[ClipInfo],
        audio_path: Path,
        srt_entries: list[SrtEntry],
        script_segments: list[dict],
        run_dir: Path,
        aspect_ratio: str,
        on_done=None,
    ):
        super().__init__(parent)
        self.title("✂️ Ghost Editor")
        self.geometry("1460x960")
        self.minsize(1100, 740)
        self.configure(fg_color=BG_MAIN)
        self.grab_set()

        if clips and (clips[0] is None or not isinstance(clips[0], ClipInfo)):
            self.clips = load_clips(list(clips), script_segments)
        else:
            self.clips = list(clips) if clips else []
        self.audio_path = Path(audio_path)
        self.srt_entries = list(srt_entries) if srt_entries else []
        self.script_segments = list(script_segments) if script_segments else []
        self.run_dir = Path(run_dir)
        self.aspect_ratio = aspect_ratio
        self.on_done = on_done

        self.bg_music_path  = None
        self.bg_volume      = 0.3   # music mix  0.0–1.5
        self._voice_volume  = 1.0   # voice volume 0.0–1.0
        self.selected_clip_idx = -1
        self.is_assembling = False

        self._tl_focus_track = "video"  # video | voice | music | subs
        self._ruler_ptr: dict = {}
        self._tl_zoom = 1.0
        self._tl_view_start = 0.0
        self._tl_ruler_hover_x: int | None = None
        self._preview_title = ""

        self._vlc_instance = None
        self._vlc_player = None
        self._tl_blocks: list[tuple[int, int, int]] = []
        self._srt_blocks: list[tuple[int, int, int]] = []   # (x0, x1, srt_idx)
        self._drag_tl: dict = {"idx": None}
        self._vlc_module = None
        self._playhead_sec = 0.0
        self._narration_env: list[float] | None = None
        self._music_env: list[float] | None = None
        self._preview_mux_path = self.run_dir / "_ghost_editor_preview_mux.mp4"
        self._wave_gen = 0

        # ── redraw throttle ───────────────────────────────────────────────
        self._redraw_pending = False

        # ── undo / redo ───────────────────────────────────────────────────
        import copy as _copy_mod
        self._copy = _copy_mod
        from collections import deque as _deque
        self._undo_stack: _deque = _deque(maxlen=30)
        self._redo_stack: _deque = _deque(maxlen=30)

        # ── audio / subtitle split points ────────────────────────────────
        self._voice_splits: list[float] = []    # seconds into narration timeline
        self._music_splits: list[float] = []    # seconds into music timeline
        self._srt_selected_idx: int = -1
        self._selected_voice_seg: int = -1      # index of selected voice split-segment
        self._selected_music_seg: int = -1      # index of selected music split-segment
        self._voice_seg_blocks: list[tuple[int, int, int]] = []  # (x0, x1, seg_idx)
        self._music_seg_blocks: list[tuple[int, int, int]] = []  # (x0, x1, seg_idx)
        # ── per-clip playback speeds (idx → float, default 1.0) ──────────
        self._clip_speeds: dict[int, float] = {}

        # ── continuous playback ───────────────────────────────────────────
        self._vlc_poll_active = False
        self._preview_clip_idx = 0
        self._preview_clip_tl_start = 0.0       # global timeline sec at clip start

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._load_preview_meta_title()
        self._ensure_segments_match_clips()
        self._build_ui()
        self.bind("<Delete>", self._on_delete_key)
        self.bind("<BackSpace>", self._on_delete_key)
        # Keyboard shortcuts
        self.bind("<Control-z>", self._undo)
        self.bind("<Control-Z>", self._redo)    # Ctrl+Shift+Z
        self.bind("<space>",     self._kbd_play_pause)
        self.bind("<Control-b>", self._kbd_split)
        self._refresh_clip_list()
        self._start_waveform_build()

    def _load_preview_meta_title(self) -> None:
        self._preview_title = ""
        meta = self.run_dir / "metadata.json"
        if not meta.is_file():
            return
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            t = str(data.get("title") or "").strip()
            if t:
                self._preview_title = t[:240]
        except Exception:
            pass

    def _release_vlc(self) -> None:
        if self._vlc_player:
            try:
                self._vlc_player.stop()
                self._vlc_player.release()
            except Exception:
                pass
            self._vlc_player = None
        if self._vlc_instance:
            try:
                self._vlc_instance.release()
            except Exception:
                pass
            self._vlc_instance = None

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0, border_width=1, border_color=ACCENT_DOC)
        hdr.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(hdr, text="[ GHOST EDITOR ]", font=("Orbitron", 18, "bold"), text_color=ACCENT_DOC).pack(
            side="left", padx=15, pady=10
        )
        self.lbl_stats = ctk.CTkLabel(hdr, text="Clips: 0  |  Duration: 0.0s", font=("Share Tech Mono", 14), text_color=TEXT_SEC)
        self.lbl_stats.pack(side="right", padx=15)

        # All internal form widgets live in a hidden frame (logic unchanged)
        self._create_hidden_widgets()

        # Content row: preview (left) + ASSETS panel (right)
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="x", padx=10, pady=(5, 0))
        self._build_preview_row(content)
        self._build_assets_panel(content)

        # Timeline (full-width)
        tl_wrap = ctk.CTkFrame(self, fg_color=self._TL_BG, corner_radius=0,
                               border_width=1, border_color=self._TL_BORDER)
        tl_wrap.pack(fill="x", padx=10, pady=(4, 0))
        tl_top = ctk.CTkFrame(tl_wrap, fg_color="transparent")
        tl_top.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(tl_top, text="TIMELINE", font=("Orbitron", 11, "bold"), text_color=ACCENT_DOC).pack(side="left")
        ctk.CTkLabel(
            tl_top,
            text=(
                "  Ruler drag → scrub playhead  ·  Ctrl+drag ruler → zoom  ·  Ruler tap → split  ·  "
                "Ctrl+wheel → zoom  ·  Wheel → pan  ·  Right-click clip / track → options"
            ),
            font=("Share Tech Mono", 9),
            text_color=TEXT_HINT,
        ).pack(side="left")
        _tl_h = (
            self.RULER_H
            + self.VIDEO_TRACK_H    + self.TRACK_GAP
            + self.NARRATION_TRACK_H + self.TRACK_GAP
            + self.MUSIC_TRACK_H    + self.TRACK_GAP
            + self.SUBTITLE_TRACK_H
            + self.TIMELINE_BOTTOM_PAD
        )
        self._timeline_canvas = tk.Canvas(
            tl_wrap, height=_tl_h,
            bg=self._TL_BG, highlightthickness=0,
        )
        self._timeline_canvas.pack(fill="x", padx=4, pady=(0, 8))
        self._timeline_canvas.bind("<ButtonPress-1>", self._tl_press)
        self._timeline_canvas.bind("<B1-Motion>", self._tl_motion)
        self._timeline_canvas.bind("<ButtonRelease-1>", self._tl_release)
        self._timeline_canvas.bind("<Double-Button-1>", self._tl_double_click)
        self._timeline_canvas.bind("<Motion>", self._tl_motion_hover)
        self._timeline_canvas.bind("<Button-3>", self._tl_right_press)
        self._timeline_canvas.bind("<MouseWheel>", self._tl_wheel)
        self._timeline_canvas.bind("<Configure>", lambda _e: self._timeline_redraw_schedule())

        # Footer
        footer = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0, border_width=1, border_color=BORDER)
        footer.pack(fill="x", padx=10, pady=(5, 10))

        self.btn_assemble = ctk.CTkButton(
            footer,
            text="🎬 RE-ASSEMBLE",
            font=("Orbitron", 14, "bold"),
            fg_color="#330044",
            hover_color=ACCENT_DOC,
            border_color=ACCENT_DOC,
            border_width=1,
            command=self._do_assemble,
        )
        self.btn_assemble.pack(side="left", padx=15, pady=12)

        self.prog_bar = ctk.CTkProgressBar(footer, width=200, progress_color=ACCENT_DOC)
        self.prog_bar.set(0)
        self.prog_bar.pack(side="left", padx=8)
        self.lbl_status = ctk.CTkLabel(footer, text="Ready", font=("Share Tech Mono", 12), text_color=TEXT_HINT)
        self.lbl_status.pack(side="left")

        self.btn_done = ctk.CTkButton(
            footer,
            text="✅ DONE / UPLOAD",
            font=("Orbitron", 14, "bold"),
            fg_color=ACCENT_GRN,
            hover_color="#009944",
            text_color="#000000",
            command=self._on_done_clicked,
        )
        self.btn_done.pack(side="right", padx=15, pady=12)

        # Quick-access buttons in footer
        for _txt, _cmd in [
            ("🖼 Logo", self._show_logo_dialog),
            ("📝 Subtitles", self._show_subtitles_dialog),
        ]:
            ctk.CTkButton(
                footer,
                text=_txt,
                font=("Share Tech Mono", 11),
                fg_color="transparent",
                border_width=1,
                border_color=TEXT_HINT,
                width=90,
                height=30,
                command=_cmd,
            ).pack(side="right", padx=4, pady=12)

    # ── hidden internal widgets ──────────────────────────────────────────────

    def _create_hidden_widgets(self) -> None:
        """Build all tab form-widgets in a hidden frame so existing logic keeps working."""
        _hf = ctk.CTkFrame(self, fg_color="transparent")  # intentionally NOT packed
        self._hidden_frame = _hf
        self._build_voice_tab(_hf)
        self._build_trim_tab(_hf)
        self._build_split_tab(_hf)
        self._build_srt_tab(_hf)
        self._build_music_tab(_hf)
        # Logo: init instance-vars then create hidden widgets
        self._logo_apply = bool(config.get("documentary.logo_enabled", False))
        self._logo_pos = str(config.get("documentary.logo_position", "bottom_right") or "bottom_right")
        self._logo_scale = float(config.get("documentary.logo_scale", 0.15))
        self._logo_margin = int(config.get("documentary.logo_margin", 24))
        self._logo_opacity = float(config.get("documentary.logo_opacity", 1.0))
        self._build_logo_tab(_hf)  # sets self._logo_apply_var etc. (used by _sync_logo_path_hint)

    def _build_preview_row(self, parent=None):
        container = parent if parent is not None else self
        row = ctk.CTkFrame(container, fg_color=BG_CARD, corner_radius=0, border_width=1, border_color=BORDER)
        row.pack(side="left", fill="y", padx=(0, 5), pady=(0, 5))

        self.preview_tk = tk.Frame(row, width=self.PREVIEW_W, height=self.PREVIEW_H, bg="#000000")
        self.preview_tk.pack(side="left", padx=10, pady=10)
        self.preview_tk.pack_propagate(False)

        ctrl = ctk.CTkFrame(row, fg_color="transparent")
        ctrl.pack(side="left", fill="y", padx=10, pady=10)

        self.lbl_preview_msg = ctk.CTkLabel(
            ctrl,
            text="",
            font=("Share Tech Mono", 11),
            text_color=TEXT_HINT,
            wraplength=340,
            justify="left",
        )
        self.lbl_preview_msg.pack(anchor="w", pady=(0, 6))

        self.lbl_preview_tc = ctk.CTkLabel(
            ctrl,
            text="00:00  /  00:00",
            font=("Consolas", 13, "bold"),
            text_color=ACCENT_SEC,
        )
        self.lbl_preview_tc.pack(anchor="w", pady=(0, 8))

        ctk.CTkButton(ctrl, text="▶ Play clip + voice", command=self._preview_play, width=168).pack(anchor="w", pady=2)
        ctk.CTkButton(ctrl, text="▶ Play from playhead", command=self._preview_from_playhead, width=168).pack(anchor="w", pady=2)
        ctk.CTkButton(ctrl, text="⏸ Pause", command=self._preview_pause, width=168).pack(anchor="w", pady=2)
        ctk.CTkButton(ctrl, text="⏹ Stop", command=self._preview_stop, width=168).pack(anchor="w", pady=2)

        inst, reason = get_vlc_instance()
        if inst is not None:
            try:
                import vlc  # type: ignore

                self._vlc_module = vlc
                self._vlc_instance = inst
                self._vlc_player = inst.media_player_new()
                self.update_idletasks()
                if hasattr(self._vlc_player, "set_hwnd"):
                    self._vlc_player.set_hwnd(int(self.preview_tk.winfo_id()))
                elif hasattr(self._vlc_player, "set_xwindow"):
                    self._vlc_player.set_xwindow(int(self.preview_tk.winfo_id()))
                self.lbl_preview_msg.configure(
                    text=(
                        "VLC preview: title (from run metadata) + burned subtitles for this segment, "
                        "voice + optional background music (mix level from Music tab / right‑click MUSIC row)."
                    )
                )
            except Exception as exc:
                self.lbl_preview_msg.configure(
                    text=(
                        f"VLC preview unavailable ({exc}).\n"
                        "Install VLC 64-bit and: pip install python-vlc\n"
                        "Editing and assembly still work."
                    )
                )
                self._release_vlc()
        else:
            msg = reason or "VLC preview unavailable."
            self.lbl_preview_msg.configure(text=msg)

    # ── ASSETS panel ────────────────────────────────────────────────────────

    def _build_assets_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=self._TL_PANEL_ALT,
                             corner_radius=0, border_width=1, border_color=self._TL_BORDER)
        panel.pack(side="left", fill="both", expand=True, pady=(0, 5))

        # Header
        hdr = ctk.CTkFrame(panel, fg_color=self._TL_PANEL, corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="IMPORT MEDIA", font=("Segoe UI", 11, "bold"),
                     text_color=self._TL_TEXT).pack(side="left", padx=12, pady=6)

        # Import buttons row — Video / Audio / SRT  (like Filmora)
        btn_bar = ctk.CTkFrame(panel, fg_color="transparent")
        btn_bar.pack(fill="x", padx=6, pady=(5, 2))
        for _txt, _col, _cmd in [
            ("+ Video",  self._TL_VID,   self._add_clip_dialog),
            ("+ Audio",  self._TL_MUSIC, self._browse_music),
            ("+ Voice",  self._TL_VOICE, self._replace_voiceover),
            ("+ SRT",    self._TL_SUBS,  self._import_srt_file),
        ]:
            ctk.CTkButton(
                btn_bar, text=_txt, width=64, height=24,
                font=("Segoe UI", 10, "bold"),
                fg_color=_col, text_color="#000000" if _col == self._TL_VOICE else "#FFFFFF",
                command=_cmd,
            ).pack(side="left", padx=2)

        # Section: VIDEO CLIPS
        sec_vid = ctk.CTkFrame(panel, fg_color=self._TL_PANEL, corner_radius=0)
        sec_vid.pack(fill="x", padx=4, pady=(4, 0))
        ctk.CTkLabel(sec_vid, text="VIDEO CLIPS",
                     font=("Segoe UI", 9, "bold"), text_color=self._TL_VID).pack(
            side="left", padx=8, pady=3)

        self.clip_list_frame = ctk.CTkScrollableFrame(
            panel, fg_color="transparent", height=220)
        self.clip_list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    # ── context dialogs ──────────────────────────────────────────────────────

    def _show_trim_dialog(self, clip_idx: int | None = None) -> None:
        idx = clip_idx if clip_idx is not None else self.selected_clip_idx
        if not (0 <= idx < len(self.clips)):
            messagebox.showwarning("Trim", "Select a clip first.")
            return
        clip = self.clips[idx]
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Trim Clip {idx + 1}")
        dlg.geometry("400x210")
        dlg.grab_set()
        dlg.configure(fg_color=BG_MAIN)
        ctk.CTkLabel(dlg, text=f"{Path(clip.path).name[:36]}", font=("Share Tech Mono", 11), text_color=TEXT_PRI).pack(
            anchor="w", padx=16, pady=(14, 2)
        )
        ctk.CTkLabel(dlg, text=f"Duration: {clip.duration:.2f}s", font=("Share Tech Mono", 10), text_color=TEXT_HINT).pack(
            anchor="w", padx=16
        )
        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(pady=12, padx=16, fill="x")
        ctk.CTkLabel(row, text="Start (s):").pack(side="left", padx=4)
        ent_s = ctk.CTkEntry(row, width=80)
        ent_s.insert(0, "0.0")
        ent_s.pack(side="left", padx=4)
        ctk.CTkLabel(row, text="End (s):").pack(side="left", padx=8)
        ent_e = ctk.CTkEntry(row, width=80)
        ent_e.insert(0, f"{clip.duration:.1f}")
        ent_e.pack(side="left", padx=4)
        chk = ctk.CTkCheckBox(dlg, text="Re-encode (accurate)", fg_color=ACCENT_DOC)
        chk.select()
        chk.pack(anchor="w", padx=16, pady=4)

        def _do():
            try:
                new_c = trim_clip(self.clips[idx], float(ent_s.get()), float(ent_e.get()), self.run_dir, chk.get())
                self.clips[idx] = new_c
                self._refresh_clip_list()
                self.lbl_status.configure(text=f"Clip {idx + 1} trimmed.", text_color=ACCENT_GRN)
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Trim", str(ex), parent=dlg)

        ctk.CTkButton(dlg, text="APPLY TRIM", fg_color=ACCENT_DOC, command=_do).pack(pady=8)

    def _show_split_dialog(self, clip_idx: int | None = None) -> None:
        idx = clip_idx if clip_idx is not None else self.selected_clip_idx
        if not (0 <= idx < len(self.clips)):
            messagebox.showwarning("Split", "Select a clip first.")
            return
        clip = self.clips[idx]
        clip_start = self._voice_start_for_clip(idx)
        local_t = float(self._playhead_sec) - clip_start
        if not (0.08 < local_t < clip.duration - 0.08):
            local_t = clip.duration / 2.0
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Split Clip {idx + 1}")
        dlg.geometry("360x170")
        dlg.grab_set()
        dlg.configure(fg_color=BG_MAIN)
        ctk.CTkLabel(dlg, text=f"{Path(clip.path).name[:36]}", font=("Share Tech Mono", 11), text_color=TEXT_PRI).pack(
            anchor="w", padx=16, pady=(14, 4)
        )
        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(pady=8, padx=16, fill="x")
        ctk.CTkLabel(row, text="Split at (s):").pack(side="left", padx=4)
        ent = ctk.CTkEntry(row, width=90)
        ent.insert(0, f"{local_t:.2f}")
        ent.pack(side="left", padx=4)

        def _do():
            try:
                sp = float(ent.get())
                if sp <= 0.08 or sp >= clip.duration - 0.08:
                    messagebox.showwarning("Split", "Too close to edge.", parent=dlg)
                    return
                self._ensure_segments_match_clips()
                ratio = max(0.05, min(0.95, sp / max(0.01, clip.duration)))
                s1, s2 = self._split_segment_dict(self.script_segments[idx], ratio)
                c1, c2 = split_clip(clip, sp, self.run_dir, self.chk_reencode.get())
                self.clips.pop(idx)
                self.clips.insert(idx, c2)
                self.clips.insert(idx, c1)
                self.script_segments.pop(idx)
                self.script_segments.insert(idx, s2)
                self.script_segments.insert(idx, s1)
                self._regen_srt_from_voice()
                self.selected_clip_idx = idx + 1
                self._refresh_clip_list()
                self._start_waveform_build()
                self.lbl_status.configure(text="Split done.", text_color=ACCENT_GRN)
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Split", str(ex), parent=dlg)

        ctk.CTkButton(dlg, text="SPLIT CLIP", fg_color=ACCENT_DOC, command=_do).pack(pady=10)

    def _show_voice_dialog(self) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("Voiceover Settings")
        dlg.geometry("420x230")
        dlg.grab_set()
        dlg.configure(fg_color=BG_MAIN)
        ctk.CTkButton(dlg, text="📂 Replace voiceover (MP3/WAV)…", fg_color=ACCENT_DOC, command=self._replace_voiceover).pack(
            pady=(18, 8), padx=20, fill="x"
        )
        ctk.CTkLabel(dlg, text="Trim voice (seconds from file start)", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(
            pady=(8, 4)
        )
        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(pady=4)
        ctk.CTkLabel(row, text="Start:").pack(side="left", padx=4)
        ent_s = ctk.CTkEntry(row, width=70)
        ent_s.insert(0, "0")
        ent_s.pack(side="left", padx=4)
        ctk.CTkLabel(row, text="End (empty=EOF):").pack(side="left", padx=4)
        ent_e = ctk.CTkEntry(row, width=70)
        ent_e.pack(side="left", padx=4)

        def _do():
            try:
                start = float(ent_s.get() or 0)
                end_s = ent_e.get().strip()
                end = float(end_s) if end_s else None
                out = self.run_dir / "voiceover_trimmed.mp3"
                trim_audio(self.audio_path, out, start, end, reencode=True)
                self.audio_path = out
                self._regen_srt_from_voice()
                self._refresh_clip_list()
                self._start_waveform_build()
                self.lbl_status.configure(text="Voice trimmed.", text_color=ACCENT_GRN)
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Voice trim", str(ex), parent=dlg)

        ctk.CTkButton(dlg, text="Apply voice trim", fg_color=ACCENT_PRI, command=_do).pack(pady=8)

    def _show_subtitles_dialog(self) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("Subtitles / SRT Editor")
        dlg.geometry("740x520")
        dlg.configure(fg_color=BG_MAIN)
        dlg.grab_set()
        sf = ctk.CTkFrame(dlg, fg_color=BG_SEC)
        sf.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(sf, text="Color:").pack(side="left", padx=5)
        _c_opts = list(self.colors_map.keys())
        opt_c = ctk.CTkOptionMenu(sf, values=_c_opts, width=90, command=lambda c: self.color_var.set(self.colors_map[c]))
        opt_c.set({v: k for k, v in self.colors_map.items()}.get(self.color_var.get(), "White"))
        opt_c.pack(side="left", padx=5)
        ctk.CTkLabel(sf, text="Bg:").pack(side="left", padx=5)
        _b_opts = list(self.bg_map.keys())
        opt_bg = ctk.CTkOptionMenu(sf, values=_b_opts, width=110, command=lambda c: self.bg_color_var.set(self.bg_map[c]))
        opt_bg.set({v: k for k, v in self.bg_map.items()}.get(self.bg_color_var.get(), "Semi-Black"))
        opt_bg.pack(side="left", padx=5)
        ctk.CTkCheckBox(sf, text="Bold", variable=self.var_bold, width=60).pack(side="left", padx=5)
        ctk.CTkCheckBox(sf, text="Italic", variable=self.var_italic, width=60).pack(side="left", padx=5)
        scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=4)
        dlg_widgets: list[tuple] = []

        def _refresh():
            for w in scroll.winfo_children():
                w.destroy()
            dlg_widgets.clear()
            for i, cue in enumerate(self.srt_entries):
                r = ctk.CTkFrame(scroll, fg_color=BG_SEC)
                r.pack(fill="x", pady=2)
                ctk.CTkLabel(r, text=f"{i + 1}", width=24).pack(side="left", padx=5)
                e_s = ctk.CTkEntry(r, width=72, font=("Consolas", 10))
                e_s.insert(0, cue.start)
                e_s.pack(side="left", padx=2)
                e_e = ctk.CTkEntry(r, width=72, font=("Consolas", 10))
                e_e.insert(0, cue.end)
                e_e.pack(side="left", padx=2)
                e_t = ctk.CTkEntry(r, font=("Consolas", 11))
                e_t.insert(0, cue.text)
                e_t.pack(side="left", fill="x", expand=True, padx=2)

                def _del(ii=i):
                    self.srt_entries.pop(ii)
                    _refresh()

                ctk.CTkButton(r, text="✕", width=26, fg_color="transparent", text_color=ACCENT_RED, command=_del).pack(
                    side="right"
                )
                dlg_widgets.append((e_s, e_e, e_t))

        _refresh()
        br = ctk.CTkFrame(dlg, fg_color="transparent")
        br.pack(fill="x", padx=8, pady=8)

        def _add():
            self.srt_entries.append(SrtEntry(len(self.srt_entries) + 1, "00:00:00,000", "00:00:05,000", "New Cue"))
            _refresh()

        def _save():
            new_srt = [SrtEntry(i + 1, es.get(), ee.get(), et.get()) for i, (es, ee, et) in enumerate(dlg_widgets)]
            self.srt_entries = new_srt
            out_p = self.run_dir / "edited_subtitles.srt"
            export_srt_file(self.srt_entries, out_p)
            self.lbl_status.configure(text=f"SRT saved → {out_p.name}")
            dlg.destroy()

        ctk.CTkButton(br, text="+ ADD CUE", command=_add, fg_color=ACCENT_PRI, width=110).pack(side="left", padx=5)
        ctk.CTkButton(br, text="💾 SAVE & CLOSE", command=_save, fg_color=ACCENT_DOC, width=140).pack(side="left", padx=5)

    def _show_logo_dialog(self) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("Logo Overlay Settings")
        dlg.geometry("500x400")
        dlg.configure(fg_color=BG_MAIN)
        dlg.grab_set()
        p = (config.get("documentary.logo_path") or "").strip()
        hint = f"Using: {Path(p).name}" if p and Path(p).is_file() else "No logo set — configure in Settings tab"
        ctk.CTkLabel(dlg, text=hint, font=("Share Tech Mono", 11), text_color=TEXT_HINT if p else ACCENT_WARN).pack(
            anchor="w", padx=16, pady=(14, 4)
        )
        apply_var = ctk.BooleanVar(value=self._logo_apply)
        ctk.CTkCheckBox(dlg, text="Apply logo on this render", variable=apply_var, fg_color=ACCENT_DOC).pack(
            anchor="w", padx=16, pady=8
        )
        pos_vals = list(_LOGO_LABEL_TO_POS.keys())
        _cur_label = _LOGO_POS_TO_LABEL.get(self._logo_pos, "Bottom-right")
        row_p = ctk.CTkFrame(dlg, fg_color="transparent")
        row_p.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_p, text="Corner:", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(side="left")
        pos_menu = ctk.CTkOptionMenu(row_p, values=pos_vals, width=170)
        pos_menu.set(_cur_label if _cur_label in pos_vals else pos_vals[0])
        pos_menu.pack(side="left", padx=10)
        row_sc = ctk.CTkFrame(dlg, fg_color="transparent")
        row_sc.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_sc, text="Scale (% width):", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(side="left")
        scale_sl = ctk.CTkSlider(row_sc, from_=0.06, to=0.35, number_of_steps=29)
        scale_sl.set(self._logo_scale)
        scale_lbl = ctk.CTkLabel(row_sc, text=f"{self._logo_scale * 100:.0f}%", width=40)
        scale_sl.configure(command=lambda v: scale_lbl.configure(text=f"{float(v) * 100:.0f}%"))
        scale_sl.pack(side="left", fill="x", expand=True, padx=8)
        scale_lbl.pack(side="left")
        row_mg = ctk.CTkFrame(dlg, fg_color="transparent")
        row_mg.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_mg, text="Margin (px):", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(side="left")
        margin_ed = ctk.CTkEntry(row_mg, width=56)
        margin_ed.insert(0, str(self._logo_margin))
        margin_ed.pack(side="left", padx=8)
        row_op = ctk.CTkFrame(dlg, fg_color="transparent")
        row_op.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_op, text="Opacity:", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(side="left")
        opac_sl = ctk.CTkSlider(row_op, from_=0.25, to=1.0, number_of_steps=15)
        opac_sl.set(self._logo_opacity)
        opac_lbl = ctk.CTkLabel(row_op, text=f"{self._logo_opacity * 100:.0f}%", width=40)
        opac_sl.configure(command=lambda v: opac_lbl.configure(text=f"{float(v) * 100:.0f}%"))
        opac_sl.pack(side="left", fill="x", expand=True, padx=8)
        opac_lbl.pack(side="left")

        def _save():
            self._logo_apply = bool(apply_var.get())
            self._logo_pos = _LOGO_LABEL_TO_POS.get(pos_menu.get(), "bottom_right")
            self._logo_scale = float(scale_sl.get())
            try:
                self._logo_margin = max(0, min(120, int(margin_ed.get().strip() or "24")))
            except ValueError:
                self._logo_margin = 24
            self._logo_opacity = float(opac_sl.get())
            dlg.destroy()

        ctk.CTkButton(dlg, text="✅ Save & Close", fg_color=ACCENT_GRN, text_color="#000000", command=_save).pack(pady=14)

    # ────────────────────────────────────────────────────────────────────────

    def _regen_srt_from_voice(self) -> None:
        ad = _audio_duration_sec(self.audio_path)
        self.srt_entries = generate_srt_from_segments(self.script_segments, ad)

    def _ensure_segments_match_clips(self) -> None:
        """Keep script_segments length aligned with clips for assembly."""
        n_c = len(self.clips)
        n_s = len(self.script_segments)
        if n_c == n_s:
            return
        if n_s < n_c:
            base = dict(self.script_segments[-1]) if self.script_segments else {"voiceover": "", "video_query": ""}
            for _k in ("voiceover", "video_query"):
                base.setdefault(_k, "")
            while len(self.script_segments) < n_c:
                self.script_segments.append(dict(base))
        elif n_s > n_c:
            self.script_segments = self.script_segments[:n_c]

    @staticmethod
    def _split_segment_dict(seg: dict, ratio: float) -> tuple[dict, dict]:
        """Split segment voiceover by ratio in (0,1) for first / second clip."""
        ratio = max(0.05, min(0.95, float(ratio)))
        vo = str(seg.get("voiceover", "")).strip()
        q = str(seg.get("video_query", ""))
        d = {k: v for k, v in seg.items() if k not in ("voiceover", "video_query")}
        if not vo:
            a = {**d, "voiceover": "", "video_query": q}
            b = {**d, "voiceover": "", "video_query": q}
            return a, b
        words = vo.split()
        n = len(words)
        if n < 2:
            return (
                {**d, "voiceover": vo, "video_query": q},
                {**d, "voiceover": "", "video_query": q},
            )
        cut = max(1, min(n - 1, int(round(n * ratio))))
        w1 = " ".join(words[:cut])
        w2 = " ".join(words[cut:])
        return ({**d, "voiceover": w1, "video_query": q}, {**d, "voiceover": w2, "video_query": q})

    def _split_timeline_at_global_time(self, t: float) -> None:
        """Filmora-style split at timeline seconds (updates video + script voiceover split)."""
        if not self.clips:
            return
        if self._tl_focus_track == "music":
            self._push_undo()
            self._music_splits.append(float(t))
            self._music_splits.sort()
            self._timeline_redraw_schedule()
            self.lbl_status.configure(text=f"Music split marker at {t:.2f}s.", text_color=ACCENT_GRN)
            return
        if self._tl_focus_track == "voice":
            self._push_undo()
            self._voice_splits.append(float(t))
            self._voice_splits.sort()
            self._timeline_redraw_schedule()
            self.lbl_status.configure(text=f"Voice split marker at {t:.2f}s.", text_color=ACCENT_GRN)
            return
        total = self._timeline_total_duration()
        t = max(0.0, min(total, float(t)))
        idx, local_off, _rem = self._clip_and_offset_at_time(t)
        clip = self.clips[idx]
        if local_off < 0.08 or local_off > clip.duration - 0.08:
            self.lbl_status.configure(text="Split too close to clip edge — move playhead.", text_color=ACCENT_WARN)
            return
        self._ensure_segments_match_clips()
        if idx >= len(self.script_segments):
            return
        ratio = local_off / max(0.01, clip.duration)
        s1, s2 = self._split_segment_dict(self.script_segments[idx], ratio)
        reenc = self.chk_reencode.get() if hasattr(self, "chk_reencode") else True
        self._push_undo()
        try:
            c1, c2 = split_clip(clip, local_off, self.run_dir, reenc)
        except Exception as ex:
            messagebox.showerror("Split", str(ex))
            return
        self.clips.pop(idx)
        self.clips.insert(idx, c2)
        self.clips.insert(idx, c1)
        self.script_segments.pop(idx)
        self.script_segments.insert(idx, s2)
        self.script_segments.insert(idx, s1)
        self._regen_srt_from_voice()
        self.selected_clip_idx = idx + 1
        self._playhead_sec = t
        self._refresh_clip_list()
        self._start_waveform_build()
        self.lbl_status.configure(text="Split: new clip + narration text split.", text_color=ACCENT_GRN)

    def _on_delete_key(self, _event=None) -> None:
        if self.selected_clip_idx >= 0:
            self._remove_clip(self.selected_clip_idx)

    # ── undo / redo ───────────────────────────────────────────────────────
    def _push_undo(self) -> None:
        """Snapshot the mutable editing state before a destructive action."""
        state = {
            "clips":          self._copy.deepcopy(self.clips),
            "srt_entries":    self._copy.deepcopy(self.srt_entries),
            "script_segments": self._copy.deepcopy(self.script_segments),
            "voice_splits":   list(self._voice_splits),
            "music_splits":   list(self._music_splits),
            "clip_speeds":    dict(self._clip_speeds),
            "selected":       self.selected_clip_idx,
            "playhead":       self._playhead_sec,
        }
        self._undo_stack.append(state)
        self._redo_stack.clear()

    def _undo(self, _event=None) -> None:
        if not self._undo_stack:
            self.lbl_status.configure(text="Nothing to undo.", text_color=TEXT_HINT)
            return
        # save current to redo
        state = {
            "clips":          self._copy.deepcopy(self.clips),
            "srt_entries":    self._copy.deepcopy(self.srt_entries),
            "script_segments": self._copy.deepcopy(self.script_segments),
            "voice_splits":   list(self._voice_splits),
            "music_splits":   list(self._music_splits),
            "selected":       self.selected_clip_idx,
            "playhead":       self._playhead_sec,
        }
        self._redo_stack.append(state)
        prev = self._undo_stack.pop()
        self._restore_state(prev)
        self.lbl_status.configure(text="Undo.", text_color=ACCENT_GRN)

    def _redo(self, _event=None) -> None:
        if not self._redo_stack:
            self.lbl_status.configure(text="Nothing to redo.", text_color=TEXT_HINT)
            return
        state = {
            "clips":          self._copy.deepcopy(self.clips),
            "srt_entries":    self._copy.deepcopy(self.srt_entries),
            "script_segments": self._copy.deepcopy(self.script_segments),
            "voice_splits":   list(self._voice_splits),
            "music_splits":   list(self._music_splits),
            "selected":       self.selected_clip_idx,
            "playhead":       self._playhead_sec,
        }
        self._undo_stack.append(state)
        nxt = self._redo_stack.pop()
        self._restore_state(nxt)
        self.lbl_status.configure(text="Redo.", text_color=ACCENT_GRN)

    def _restore_state(self, state: dict) -> None:
        self.clips             = state["clips"]
        self.srt_entries       = state["srt_entries"]
        self.script_segments   = state["script_segments"]
        self._voice_splits     = state["voice_splits"]
        self._music_splits     = state["music_splits"]
        self._clip_speeds      = state.get("clip_speeds", {})
        self.selected_clip_idx = state["selected"]
        self._playhead_sec     = state["playhead"]
        self._refresh_clip_list()
        self._start_waveform_build()

    # ── keyboard shortcuts ────────────────────────────────────────────────
    def _kbd_play_pause(self, event=None) -> None:
        # Don't steal space from Entry/Text widgets
        if event and isinstance(event.widget, (tk.Entry, tk.Text, ctk.CTkEntry, ctk.CTkTextbox)):
            return
        if self._vlc_player and self._vlc_module:
            try:
                state = self._vlc_player.get_state()
                if state == self._vlc_module.State.Playing:
                    self._preview_pause()
                    self._vlc_poll_active = False
                    return
                if state == self._vlc_module.State.Paused:
                    self._vlc_player.play()
                    self._vlc_poll_active = True
                    self.after(80, self._vlc_tick)
                    return
            except Exception:
                pass
        # Start continuous playback from playhead
        self._continuous_play_from_playhead()

    def _kbd_split(self, _event=None) -> None:
        """Ctrl+B: split the focused track at the playhead."""
        t = float(self._playhead_sec)
        ft = self._tl_focus_track
        if ft == "video":
            self._push_undo()
            self._split_timeline_at_global_time(t)
        elif ft == "voice":
            self._push_undo()
            self._voice_splits.append(t)
            self._voice_splits.sort()
            self._timeline_redraw_schedule()
            self.lbl_status.configure(text=f"Voice split marker at {t:.2f}s.", text_color=ACCENT_GRN)
        elif ft == "music":
            self._push_undo()
            self._music_splits.append(t)
            self._music_splits.sort()
            self._timeline_redraw_schedule()
            self.lbl_status.configure(text=f"Music split marker at {t:.2f}s.", text_color=ACCENT_GRN)
        elif ft == "subs":
            self._srt_add_at_playhead()

    def _add_clip_dialog(self) -> None:
        p = filedialog.askopenfilename(title="Add video clip", filetypes=[("Video", "*.mp4 *.mov *.webm *.mkv")])
        if not p:
            return
        ins = self.selected_clip_idx + 1 if self.selected_clip_idx >= 0 else len(self.clips)
        self._push_undo()
        self.clips = add_clip(self.clips, Path(p), at_index=ins)
        self.script_segments.insert(ins, {"voiceover": "", "video_query": "custom"})
        self._ensure_segments_match_clips()
        self._regen_srt_from_voice()
        self.selected_clip_idx = ins
        self._refresh_clip_list()
        self._start_waveform_build()
        self.lbl_status.configure(text="Clip added.", text_color=ACCENT_GRN)

    def _tl_y_track(self, y: int) -> str:
        rh  = self.RULER_H
        vh  = self.VIDEO_TRACK_H
        nh  = self.NARRATION_TRACK_H
        mh  = self.MUSIC_TRACK_H
        sh  = self.SUBTITLE_TRACK_H
        gap = self.TRACK_GAP
        if y < rh:
            return "ruler"
        y0 = rh
        if y0 <= y < y0 + vh:
            return "video"
        y0 += vh + gap
        if y0 <= y < y0 + nh:
            return "voice"
        y0 += nh + gap
        if y0 <= y < y0 + mh:
            return "music"
        y0 += mh + gap
        if y0 <= y < y0 + sh:
            return "subs"
        return "none"

    def _build_voice_tab(self, parent):
        ctk.CTkLabel(parent, text="Voiceover", font=("Orbitron", 14, "bold"), text_color=ACCENT_DOC).pack(pady=10)
        ctk.CTkButton(parent, text="📂 Replace voiceover (MP3/WAV…)…", fg_color=ACCENT_DOC, command=self._replace_voiceover).pack(
            pady=8
        )
        ctk.CTkLabel(parent, text="Trim voice (seconds from file start)", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(
            pady=(12, 4)
        )
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=6)
        ctk.CTkLabel(row, text="Start:").pack(side="left", padx=4)
        self.ent_voice_start = ctk.CTkEntry(row, width=70)
        self.ent_voice_start.pack(side="left", padx=4)
        self.ent_voice_start.insert(0, "0")
        ctk.CTkLabel(row, text="End (empty = EOF):").pack(side="left", padx=4)
        self.ent_voice_end = ctk.CTkEntry(row, width=70)
        self.ent_voice_end.pack(side="left", padx=4)
        ctk.CTkButton(parent, text="Apply voice trim", fg_color=ACCENT_PRI, command=self._apply_voice_trim).pack(pady=10)

    def _replace_voiceover(self):
        p = filedialog.askopenfilename(title="Replace voiceover", filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac")])
        if not p:
            return
        dest = self.run_dir / "voiceover_editor.mp3"
        try:
            shutil.copy2(p, dest)
            self.audio_path = dest
            self._regen_srt_from_voice()
            self._refresh_clip_list()
            self._start_waveform_build()
            self.lbl_status.configure(text="Voiceover replaced.", text_color=ACCENT_GRN)
        except Exception as exc:
            messagebox.showerror("Voice", str(exc))

    def _import_srt_file(self) -> None:
        """Import an external .srt file into the subtitle track."""
        p = filedialog.askopenfilename(
            title="Import SRT file",
            filetypes=[("SRT subtitles", "*.srt"), ("All files", "*.*")],
        )
        if not p:
            return
        try:
            from core.clip_manager import load_srt
            loaded = load_srt(Path(p))
        except Exception:
            # Fallback: parse manually
            loaded = []
            try:
                raw = Path(p).read_text(encoding="utf-8", errors="ignore")
                import re as _re
                blocks = _re.split(r"\n\n+", raw.strip())
                for block in blocks:
                    lines = block.strip().splitlines()
                    if len(lines) >= 3:
                        try:
                            idx_n = int(lines[0].strip())
                            times = lines[1].split("-->")
                            start = times[0].strip().replace(".", ",")
                            end   = times[1].strip().replace(".", ",")
                            text  = " ".join(ln.strip() for ln in lines[2:])
                            loaded.append(SrtEntry(idx_n, start, end, text))
                        except Exception:
                            pass
            except Exception as exc2:
                messagebox.showerror("Import SRT", str(exc2))
                return
        if not loaded:
            messagebox.showwarning("Import SRT", "No subtitle entries found in the file.")
            return
        self._push_undo()
        self.srt_entries = loaded
        self._timeline_redraw()
        self.lbl_status.configure(
            text=f"Imported {len(loaded)} subtitle cues from {Path(p).name}",
            text_color=ACCENT_GRN,
        )

    def _apply_voice_trim(self):
        try:
            start = float(self.ent_voice_start.get() or 0)
        except ValueError:
            messagebox.showerror("Voice", "Invalid start time.")
            return
        end_s = self.ent_voice_end.get().strip()
        end = float(end_s) if end_s else None
        out = self.run_dir / "voiceover_trimmed.mp3"
        try:
            trim_audio(self.audio_path, out, start, end, reencode=True)
            self.audio_path = out
            self._regen_srt_from_voice()
            self._refresh_clip_list()
            self._start_waveform_build()
            self.lbl_status.configure(text="Voice trimmed.", text_color=ACCENT_GRN)
        except Exception as exc:
            messagebox.showerror("Voice trim", str(exc))

    def _build_music_tab(self, parent):
        ctk.CTkLabel(parent, text="Background Music", font=("Orbitron", 14, "bold"), text_color=ACCENT_DOC).pack(pady=10)
        row1 = ctk.CTkFrame(parent, fg_color="transparent")
        row1.pack(fill="x", pady=5, padx=20)
        self.ent_music_path = ctk.CTkEntry(row1)
        self.ent_music_path.pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(row1, text="BROWSE", width=80, command=self._browse_music, fg_color=ACCENT_PRI).pack(side="left", padx=5)

        ctk.CTkLabel(parent, text="Trim bed (optional)", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(pady=(10, 4))
        row_t = ctk.CTkFrame(parent, fg_color="transparent")
        row_t.pack(pady=4)
        ctk.CTkLabel(row_t, text="Start:").pack(side="left", padx=4)
        self.ent_music_start = ctk.CTkEntry(row_t, width=70)
        self.ent_music_start.pack(side="left", padx=4)
        self.ent_music_start.insert(0, "0")
        ctk.CTkLabel(row_t, text="End (empty = EOF):").pack(side="left", padx=4)
        self.ent_music_end = ctk.CTkEntry(row_t, width=70)
        self.ent_music_end.pack(side="left", padx=4)
        ctk.CTkButton(parent, text="Apply music trim", fg_color=ACCENT_PRI, command=self._apply_music_trim).pack(pady=8)

        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", pady=15, padx=20)
        ctk.CTkLabel(row2, text="Mix volume:").pack(side="left", padx=5)
        self.music_slider = ctk.CTkSlider(
            row2, from_=0, to=1.0, command=self._on_music_vol_change, progress_color=ACCENT_DOC
        )
        self.music_slider.set(self.bg_volume)
        self.music_slider.pack(side="left", fill="x", expand=True, padx=5)
        self.lbl_music_vol = ctk.CTkLabel(row2, text=f"{int(self.bg_volume * 100)}%")
        self.lbl_music_vol.pack(side="left", padx=5)

    def _build_logo_tab(self, parent):
        ctk.CTkLabel(
            parent,
            text="Logo overlay",
            font=("Orbitron", 14, "bold"),
            text_color=ACCENT_DOC,
        ).pack(pady=(10, 4))
        self._logo_hint = ctk.CTkLabel(
            parent,
            text="",
            font=("Share Tech Mono", 11),
            text_color=TEXT_HINT,
            wraplength=420,
            justify="left",
        )
        self._logo_hint.pack(anchor="w", padx=16, pady=4)
        self._sync_logo_path_hint()

        row_on = ctk.CTkFrame(parent, fg_color="transparent")
        row_on.pack(fill="x", padx=16, pady=8)
        self._logo_apply_var = ctk.BooleanVar(value=bool(config.get("documentary.logo_enabled", False)))
        ctk.CTkCheckBox(
            row_on,
            text="Apply logo on this render",
            variable=self._logo_apply_var,
            fg_color=ACCENT_DOC,
        ).pack(anchor="w")

        row_pos = ctk.CTkFrame(parent, fg_color="transparent")
        row_pos.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_pos, text="Corner:", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(side="left")
        pos_vals = list(_LOGO_LABEL_TO_POS.keys())
        _pk = str(config.get("documentary.logo_position", "bottom_right") or "bottom_right")
        _pl = _LOGO_POS_TO_LABEL.get(_pk, "Bottom-right")
        self._logo_pos_menu = ctk.CTkOptionMenu(row_pos, values=pos_vals, width=170)
        self._logo_pos_menu.set(_pl if _pl in pos_vals else pos_vals[0])
        self._logo_pos_menu.pack(side="left", padx=10)

        row_sc = ctk.CTkFrame(parent, fg_color="transparent")
        row_sc.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_sc, text="Size (% width):", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(side="left")
        self._logo_scale_slider = ctk.CTkSlider(row_sc, from_=0.06, to=0.35, number_of_steps=29)
        self._logo_scale_slider.set(float(config.get("documentary.logo_scale", 0.15)))
        self._logo_scale_slider.pack(side="left", fill="x", expand=True, padx=8)
        self._logo_scale_ed_lbl = ctk.CTkLabel(row_sc, text="", width=40, font=("Share Tech Mono", 11), text_color=TEXT_HINT)
        self._logo_scale_ed_lbl.pack(side="left")
        self._logo_scale_slider.configure(command=lambda v: self._logo_scale_ed_lbl.configure(text=f"{float(v)*100:.0f}%"))
        self._logo_scale_ed_lbl.configure(text=f"{float(self._logo_scale_slider.get())*100:.0f}%")

        row_mg = ctk.CTkFrame(parent, fg_color="transparent")
        row_mg.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_mg, text="Margin (px):", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(side="left")
        self._logo_margin_ed = ctk.CTkEntry(row_mg, width=56)
        self._logo_margin_ed.pack(side="left", padx=8)
        self._logo_margin_ed.insert(0, str(int(config.get("documentary.logo_margin", 24))))

        row_op = ctk.CTkFrame(parent, fg_color="transparent")
        row_op.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_op, text="Opacity:", font=("Share Tech Mono", 12), text_color=TEXT_SEC).pack(side="left")
        self._logo_opacity_slider = ctk.CTkSlider(row_op, from_=0.25, to=1.0, number_of_steps=15)
        self._logo_opacity_slider.set(float(config.get("documentary.logo_opacity", 1.0)))
        self._logo_opacity_slider.pack(side="left", fill="x", expand=True, padx=8)
        self._logo_opac_ed_lbl = ctk.CTkLabel(row_op, text="", width=40, font=("Share Tech Mono", 11), text_color=TEXT_HINT)
        self._logo_opac_ed_lbl.pack(side="left")
        self._logo_opacity_slider.configure(command=lambda v: self._logo_opac_ed_lbl.configure(text=f"{float(v)*100:.0f}%"))
        self._logo_opac_ed_lbl.configure(text=f"{float(self._logo_opacity_slider.get())*100:.0f}%")

        ctk.CTkLabel(
            parent,
            text="Image file: Settings → Core Parameters → LOGO WATERMARK (Browse + Save Config).",
            font=("Share Tech Mono", 10),
            text_color=TEXT_HINT,
            wraplength=440,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(12, 8))

    def _sync_logo_path_hint(self) -> None:
        p = (config.get("documentary.logo_path") or "").strip()
        if p and Path(p).is_file():
            self._logo_hint.configure(text=f"Using: {Path(p).name}")
        elif p:
            self._logo_hint.configure(text="Saved path missing on disk — pick again in Settings.", text_color=ACCENT_WARN)
        else:
            self._logo_hint.configure(text="No logo file saved yet — set it in Settings.", text_color=ACCENT_WARN)

    def _logo_spec_for_export(self) -> dict:
        if not getattr(self, "_logo_apply", False):
            return {"enabled": False}
        path_s = (config.get("documentary.logo_path") or "").strip()
        if not path_s or not Path(path_s).is_file():
            return {"enabled": False}
        return {
            "enabled": True,
            "path": Path(path_s),
            "position": getattr(self, "_logo_pos", "bottom_right"),
            "scale": getattr(self, "_logo_scale", 0.15),
            "margin": getattr(self, "_logo_margin", 24),
            "opacity": getattr(self, "_logo_opacity", 1.0),
        }

    def _browse_music(self):
        p = filedialog.askopenfilename(title="Select Background Music", filetypes=[("Audio", "*.mp3 *.wav *.m4a")])
        if p:
            self.ent_music_path.delete(0, "end")
            self.ent_music_path.insert(0, p)
            self.bg_music_path = p
            self._start_waveform_build()

    def _apply_music_trim(self):
        raw = self.ent_music_path.get().strip()
        if not raw:
            messagebox.showwarning("Music", "Choose a music file first.")
            return
        src = Path(raw)
        if not src.is_file():
            messagebox.showerror("Music", "Music file not found.")
            return
        try:
            start = float(self.ent_music_start.get() or 0)
        except ValueError:
            messagebox.showerror("Music", "Invalid start time.")
            return
        end_s = self.ent_music_end.get().strip()
        end = float(end_s) if end_s else None
        out = self.run_dir / "background_music_trimmed.m4a"
        try:
            trim_background_music(src, out, start, end)
            self.ent_music_path.delete(0, "end")
            self.ent_music_path.insert(0, str(out))
            self.bg_music_path = str(out)
            self._start_waveform_build()
            self.lbl_status.configure(text="Music trimmed.", text_color=ACCENT_GRN)
        except Exception as exc:
            messagebox.showerror("Music trim", str(exc))

    def _on_music_vol_change(self, val):
        self.bg_volume = float(val)
        self.lbl_music_vol.configure(text=f"{int(self.bg_volume * 100)}%")

    @staticmethod
    def _format_tc(sec: float) -> str:
        sec = max(0.0, float(sec))
        m = int(sec // 60)
        s = int(round(sec % 60))
        if s >= 60:
            m += 1
            s = 0
        return f"{m:02d}:{s:02d}"

    def _timeline_total_duration(self) -> float:
        return sum(max(0.01, c.duration) for c in self.clips)

    def _voice_start_for_clip(self, idx: int) -> float:
        t = 0.0
        for i in range(max(0, idx)):
            if i < len(self.clips):
                t += max(0.01, self.clips[i].duration)
        return t

    def _clip_and_offset_at_time(self, t: float) -> tuple[int, float, float]:
        """Return (clip_index, offset_into_clip_sec, remaining_sec_in_clip)."""
        t = max(0.0, t)
        acc = 0.0
        if not self.clips:
            return 0, 0.0, 0.0
        for i, cl in enumerate(self.clips):
            d = max(0.01, cl.duration)
            if t < acc + d:
                return i, t - acc, acc + d - t
            acc += d
        last = len(self.clips) - 1
        ld = max(0.01, self.clips[last].duration)
        return last, ld, 0.0

    def _timeline_layout(self, canvas_w: int) -> tuple[float, float, int, int]:
        """total_sec, pixels_per_sec, x_content_start, content_width (usable). Clamps _tl_view_start."""
        total = max(0.01, self._timeline_total_duration())
        margin = 8
        usable = max(80, canvas_w - self.TRACK_LABEL_W - 2 * margin)
        base_pps = usable / total
        zoom = max(0.2, min(40.0, float(getattr(self, "_tl_zoom", 1.0))))
        pps = base_pps * zoom
        vis_sec = usable / max(0.0001, pps)
        vmax = max(0.0, total - vis_sec)
        vs = float(getattr(self, "_tl_view_start", 0.0))
        self._tl_view_start = max(0.0, min(vs, vmax))
        x0 = self.TRACK_LABEL_W + margin
        return total, pps, x0, usable

    def _time_from_canvas_x(self, x: int) -> float:
        try:
            w = int(self._timeline_canvas.winfo_width())
        except tk.TclError:
            w = 700
        total, pps, x0, _usable = self._timeline_layout(max(40, w))
        t = self._tl_view_start + (x - x0) / max(0.001, pps)
        return max(0.0, min(total, t))

    def _active_music_path(self) -> Path | None:
        raw = ""
        if hasattr(self, "ent_music_path"):
            raw = self.ent_music_path.get().strip()
        if not raw and self.bg_music_path:
            raw = str(self.bg_music_path)
        p = Path(raw) if raw else None
        if p and p.is_file():
            return p
        return None

    def _update_preview_tc(self) -> None:
        if not hasattr(self, "lbl_preview_tc"):
            return
        vd = self._timeline_total_duration()
        try:
            ad = _audio_duration_sec(self.audio_path)
        except Exception:
            ad = 0.0
        ph = float(getattr(self, "_playhead_sec", 0.0))
        self.lbl_preview_tc.configure(
            text=(
                f"Playhead {self._format_tc(ph)}  •  Project {self._format_tc(vd)}"
                f"  •  Voice track {self._format_tc(ad)}"
            )
        )

    def _start_waveform_build(self) -> None:
        self._wave_gen += 1
        gen = self._wave_gen
        ap = Path(self.audio_path)
        mp = self._active_music_path()

        def work():
            n_env: list[float] = []
            m_env: list[float] = []
            try:
                try:
                    w = max(200, int(self._timeline_canvas.winfo_width()) * 2)
                except Exception:
                    w = 1200
                n_env = _compute_waveform_envelope(ap, min(2400, max(400, w)))
                if mp is not None:
                    m_env = _compute_waveform_envelope(mp, min(2400, max(400, w)))
            except Exception:
                pass
            self.after(0, lambda g=gen, ne=n_env, me=m_env: self._on_waveforms_ready(g, ne, me))

        threading.Thread(target=work, daemon=True).start()

    def _on_waveforms_ready(self, gen: int, narration: list[float], music: list[float]) -> None:
        if gen != self._wave_gen:
            return
        self._narration_env = narration or None
        self._music_env = music or None
        self._timeline_redraw()

    # ── debounced redraw ─────────────────────────────────────────────────
    def _timeline_redraw_schedule(self, ghost_x: int | None = None) -> None:
        """Schedule a redraw; coalesces multiple calls within 14 ms."""
        self._pending_ghost_x = ghost_x
        if not self._redraw_pending:
            self._redraw_pending = True
            self.after(14, self._timeline_redraw_fire)

    def _timeline_redraw_fire(self) -> None:
        self._redraw_pending = False
        gx = getattr(self, "_pending_ghost_x", None)
        self._pending_ghost_x = None
        self._timeline_redraw(ghost_x=gx)

    def _timeline_redraw(self, ghost_x: int | None = None) -> None:  # noqa: C901
        c = self._timeline_canvas
        if not c.winfo_exists():
            return
        c.delete("all")
        try:
            w = int(c.winfo_width())
        except tk.TclError:
            return
        if w < 40:
            w = 700

        # ── colour aliases ─────────────────────────────────────────────────
        TL_BG        = self._TL_BG
        TL_PANEL     = self._TL_PANEL
        TL_PANEL_ALT = self._TL_PANEL_ALT
        TL_BORDER    = self._TL_BORDER
        TL_TEXT      = self._TL_TEXT
        TL_MUTED     = self._TL_MUTED
        C_VID        = self._TL_VID
        C_VOICE      = self._TL_VOICE
        C_MUSIC      = self._TL_MUSIC
        C_SUBS       = self._TL_SUBS
        C_PH         = self._TL_PLAYHEAD
        TICK_MAJ     = self._TL_TICK_MAJ

        # ── geometry ────────────────────────────────────────────────────────
        rh  = self.RULER_H
        vh  = self.VIDEO_TRACK_H
        nh  = self.NARRATION_TRACK_H
        mh  = self.MUSIC_TRACK_H
        sh  = self.SUBTITLE_TRACK_H
        gap = self.TRACK_GAP
        LW  = self.TRACK_LABEL_W

        y_vid0 = rh
        y_vid1 = y_vid0 + vh
        y_n0   = y_vid1 + gap
        y_n1   = y_n0 + nh
        y_m0   = y_n1 + gap
        y_m1   = y_m0 + mh
        y_s0   = y_m1 + gap
        y_s1   = y_s0 + sh
        total_h = y_s1 + self.TIMELINE_BOTTOM_PAD

        # ── full background ─────────────────────────────────────────────────
        c.create_rectangle(0, 0, w, total_h, fill=TL_BG, outline="")

        # ── track gaps (dark separators between tracks) ─────────────────────
        for gap_y in (y_vid1, y_n1, y_m1, y_s1):
            c.create_rectangle(0, gap_y, w, gap_y + gap, fill=TL_BG, outline="")

        # ── left gutter (label area) ─────────────────────────────────────────
        c.create_rectangle(0, 0, LW, total_h, fill=TL_PANEL_ALT, outline="")
        c.create_line(LW, 0, LW, total_h, fill=TL_BORDER, width=1)

        def _draw_track_label(y0, y1, text, accent_col):
            c.create_rectangle(0, y0, LW, y1, fill=TL_PANEL_ALT, outline="")
            # 4 px accent bar on far left (like the reference)
            c.create_rectangle(0, y0, 4, y1, fill=accent_col, outline="")
            mid = (y0 + y1) // 2
            c.create_text(14, mid, text=text, anchor="w",
                          fill=TL_TEXT, font=("Segoe UI", 9, "bold"))

        # Ruler gutter
        c.create_rectangle(0, 0, LW, rh, fill=TL_PANEL_ALT, outline="")
        c.create_text(LW // 2, rh // 2, text="TIME", anchor="center",
                      fill=TL_MUTED, font=("Segoe UI", 8))

        _draw_track_label(y_vid0, y_vid1, "VIDEO", C_VID)
        _draw_track_label(y_n0,   y_n1,   "VOICE", C_VOICE)
        _draw_track_label(y_m0,   y_m1,   "MUSIC", C_MUSIC)
        _draw_track_label(y_s0,   y_s1,   "SUBS",  C_SUBS)

        # ── track lane backgrounds ───────────────────────────────────────────
        nclips = len(self.clips)
        if nclips == 0:
            for y0, y1 in ((y_vid0, y_vid1), (y_n0, y_n1), (y_m0, y_m1), (y_s0, y_s1)):
                c.create_rectangle(LW, y0, w, y1, fill=TL_PANEL, outline="")
            self._tl_blocks = []
            c.create_text(w // 2, (y_vid0 + y_vid1) // 2,
                          text="No clips — click + Video in ASSETS",
                          fill=TL_MUTED, font=("Segoe UI", 10))
            self._update_preview_tc()
            return

        for y0, y1 in ((y_vid0, y_vid1), (y_n0, y_n1), (y_m0, y_m1), (y_s0, y_s1)):
            c.create_rectangle(LW, y0, w, y1, fill=TL_PANEL, outline="")

        total_d, pps, x0, usable = self._timeline_layout(w)
        vis_sec = usable / max(0.0001, pps)
        vs = self._tl_view_start

        # ── ruler ────────────────────────────────────────────────────────────
        # Single unified ruler strip — no dual-zone confusion
        RULER_MID  = rh // 2       # vertical midpoint for labels / ticks
        RULER_TICK = rh - 4        # bottom of major tick

        # Ruler background
        c.create_rectangle(LW, 0, LW + usable, rh, fill="#111820", outline="")
        # Gutter background
        c.create_rectangle(0, 0, LW, rh, fill=TL_PANEL_ALT, outline="")
        # Bottom border
        c.create_line(0, rh - 1, w, rh - 1, fill=TL_BORDER, width=1)

        # Gutter hint labels
        c.create_text(LW // 2, rh // 3,
                      text="drag", anchor="center", fill=TL_MUTED, font=("Segoe UI", 7))
        c.create_text(LW // 2, 2 * rh // 3,
                      text="scrub", anchor="center", fill=TL_MUTED, font=("Segoe UI", 7))

        def _fmt_t(t: float) -> str:
            t = max(0.0, t)
            m = int(t // 60)
            s = int(t) % 60
            return f"{m:02d}:{s:02d}"

        # Choose tick spacing: target ~8 major ticks visible
        for cand in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600):
            if vis_sec / cand <= 10:
                step_maj = cand
                break
        else:
            step_maj = max(1, int(vis_sec / 8))
        step_min = step_maj / 5.0

        t = math.floor(vs / step_min) * step_min
        while t <= vs + vis_sec + step_maj:
            rx = x0 + (t - vs) * pps
            if x0 - 1 <= rx <= x0 + usable + 1:
                is_major = abs(round(t / step_maj) * step_maj - t) < step_min * 0.1
                if is_major:
                    c.create_line(rx, RULER_MID, rx, RULER_TICK, fill=TICK_MAJ, width=1)
                    c.create_text(rx + 3, 3, text=_fmt_t(t), anchor="nw",
                                  fill=TL_MUTED, font=("Consolas", 9))
                else:
                    c.create_line(rx, RULER_TICK - 4, rx, RULER_TICK, fill=TL_BORDER, width=1)
            t += step_min

        # ── Scissor icon tracks the playhead on the ruler ────────────────────
        _ph_x = x0 + (self._playhead_sec - vs) * pps
        if x0 <= _ph_x <= x0 + usable:
            # Small glow behind scissor so it's visible over any background
            c.create_oval(_ph_x - 9, rh // 2 - 9, _ph_x + 9, rh // 2 + 9,
                          fill="#1a2535", outline=C_SUBS, width=1)
            c.create_text(_ph_x, rh // 2, text="✂",
                          anchor="center", fill=C_SUBS,
                          font=("Segoe UI Symbol", 13, "bold"))

        # Hover cursor on ruler
        hx = getattr(self, "_tl_ruler_hover_x", None)
        if hx is not None and x0 <= hx <= x0 + usable:
            c.create_line(hx, RULER_MID, hx, RULER_TICK, fill="#FFFFFF", width=1, dash=(3, 2))

        # Zoom indicator badge
        if self._tl_zoom > 1.05:
            c.create_text(x0 + usable - 4, 2, anchor="ne",
                          text=f"×{self._tl_zoom:.1f}",
                          fill=TICK_MAJ, font=("Consolas", 8))

        # ── helper: draw a centred waveform bar ──────────────────────────────
        def _draw_waveform(env, y0, y1, audio_dur, bar_col, split_pts):
            if not env or len(env) < 2 or audio_dur < 0.1:
                return False
            n = len(env)
            mid_y = (y0 + y1) // 2
            half_h = max(2.0, (y1 - y0) * 0.40)
            bars = min(int(usable), self._TL_MAX_BARS)
            step_px = usable / max(1, bars)
            bar_w = max(1, int(step_px))
            for bi in range(bars):
                t_s = vs + bi * step_px / max(0.001, pps)
                t_ratio = max(0.0, min(1.0, t_s / audio_dur))
                amp = env[min(n - 1, int(t_ratio * (n - 1)))]
                h = max(2, int(amp * half_h))
                px = int(x0 + bi * step_px)
                c.create_rectangle(px, mid_y - h, px + bar_w, mid_y + h,
                                   fill=bar_col, outline="")
            # split dividers
            for sp_t in split_pts:
                sx = x0 + (sp_t - vs) * pps
                if x0 <= sx <= x0 + usable:
                    c.create_line(int(sx), y0 + 2, int(sx), y1 - 2,
                                  fill="#FFAA00", width=2)
                    c.create_text(int(sx) + 2, y0 + 4, text="✂",
                                  fill="#FFAA00", font=("Segoe UI Symbol", 7))
            return True

        # ── video clip blocks ────────────────────────────────────────────────
        acc = 0.0
        self._tl_blocks = []
        for i, clip in enumerate(self.clips):
            dur = max(0.05, clip.duration)
            left  = x0 + (acc - vs) * pps
            bw    = max(3.0, dur * pps)
            right = left + bw
            acc  += dur
            self._tl_blocks.append((int(left), int(right), i))

            if right < x0 or left > x0 + usable:
                continue

            lx  = max(x0,          int(left))
            rxr = min(x0 + usable, int(right) - 1)
            if rxr <= lx + 1:
                continue

            sel   = (i == self.selected_clip_idx)
            speed = self._clip_speeds.get(i, 1.0)
            if sel:
                body_top = "#A080FF"
                body_bot = "#3A1880"
                accent_l = "#C0A0FF"
                border_c = "#FFFFFF"    # bright white for selected
                txt_c    = "#FFFFFF"
                bw_sel   = 2
            else:
                body_top = "#6040CC"
                body_bot = "#281060"
                accent_l = "#7C5CFF"
                border_c = "#5030AA"
                txt_c    = "#D0C0FF"
                bw_sel   = 1

            block_h = y_vid1 - y_vid0
            third   = block_h // 3
            c.create_rectangle(lx, y_vid0,           rxr, y_vid0 + third,    fill=body_top, outline="")
            c.create_rectangle(lx, y_vid0 + third,   rxr, y_vid0 + 2*third,  fill=accent_l, outline="")
            c.create_rectangle(lx, y_vid0 + 2*third, rxr, y_vid1,            fill=body_bot, outline="")
            # Left 4 px accent strip
            c.create_rectangle(lx, y_vid0, lx + 4, y_vid1, fill="#C0A0FF", outline="")
            # Border (white + wider when selected)
            c.create_rectangle(lx, y_vid0, rxr, y_vid1,
                               fill="", outline=border_c, width=bw_sel)

            block_w = rxr - lx
            mid_y   = (y_vid0 + y_vid1) // 2
            if block_w > 12:
                c.create_text(lx + 8, y_vid0 + 4, text=f"#{i+1}",
                              anchor="nw", fill=txt_c, font=("Segoe UI", 8, "bold"))
            if block_w > 60 and clip.search_query:
                q = clip.search_query[:24] + ("…" if len(clip.search_query) > 24 else "")
                c.create_text((lx + rxr) // 2, mid_y,
                              text=q, fill=txt_c, font=("Segoe UI", 8), anchor="center")
            if block_w > 44:
                c.create_text(rxr - 4, y_vid1 - 4,
                              text=f"{dur:.1f}s", anchor="se",
                              fill=TL_MUTED, font=("Consolas", 8))
            # Speed badge (shown when ≠ 1.0x)
            if speed != 1.0 and block_w > 28:
                spd_txt = f"{speed:.1f}×"
                c.create_text(lx + 8, y_vid1 - 4, text=spd_txt, anchor="sw",
                              fill="#FFE066", font=("Consolas", 8, "bold"))

            # Clip-boundary tick on ruler (downward triangle)
            if i > 0 and x0 <= int(left) <= x0 + usable:
                sx = int(left)
                c.create_line(sx, y_vid0, sx, y_s1, fill=TL_BORDER, width=1, dash=(3, 3))
                c.create_polygon(sx - 4, rh - 1, sx + 4, rh - 1, sx, rh - 7,
                                 fill=TICK_MAJ, outline="")

        # ── helper: build segment block list from split points ───────────────
        def _seg_blocks_for(dur: float, splits: list, y0: int, y1: int) -> list:
            """Returns list of (canvas_x0, canvas_x1, seg_idx) for each segment."""
            pts = [0.0] + sorted(splits) + [dur]
            blocks = []
            for si in range(len(pts) - 1):
                t0, t1 = pts[si], pts[si + 1]
                bx0 = int(x0 + (t0 - vs) * pps)
                bx1 = int(x0 + (t1 - vs) * pps)
                bx0 = max(x0, bx0)
                bx1 = min(x0 + usable, bx1)
                if bx1 > bx0:
                    blocks.append((bx0, bx1, si))
            return blocks

        # ── voice waveform ───────────────────────────────────────────────────
        try:
            ad = _audio_duration_sec(self.audio_path)
        except Exception:
            ad = total_d
        self._voice_seg_blocks = _seg_blocks_for(ad, self._voice_splits, y_n0, y_n1)
        if not _draw_waveform(self._narration_env, y_n0, y_n1, ad,
                              "#3ABFA0", self._voice_splits):
            msg = "Building waveform…" if self._narration_env is None else "No voice data"
            c.create_text(x0 + usable // 2, (y_n0 + y_n1) // 2,
                          text=msg, fill=TL_MUTED, font=("Segoe UI", 9))
        # Draw selection outline around the selected voice segment
        for bx0s, bx1s, si in self._voice_seg_blocks:
            if si == self._selected_voice_seg and self._tl_focus_track == "voice":
                c.create_rectangle(bx0s, y_n0 + 1, bx1s, y_n1 - 1,
                                   fill="", outline="#FFFFFF", width=2)

        # ── music waveform ───────────────────────────────────────────────────
        mus = self._active_music_path()
        try:
            mdur = _audio_duration_sec(mus) if mus else 0.0
        except Exception:
            mdur = 0.0
        self._music_seg_blocks = _seg_blocks_for(mdur or total_d, self._music_splits, y_m0, y_m1)
        if not _draw_waveform(self._music_env if mus else None,
                              y_m0, y_m1, mdur, "#B060CC", self._music_splits):
            msg = (f"{mus.name[:32]}" if mus else "No music — right-click to add")
            c.create_text(x0 + usable // 2, (y_m0 + y_m1) // 2,
                          text=msg, fill=TL_MUTED, font=("Segoe UI", 9))
        # Draw selection outline around the selected music segment
        for bx0s, bx1s, si in self._music_seg_blocks:
            if si == self._selected_music_seg and self._tl_focus_track == "music":
                c.create_rectangle(bx0s, y_m0 + 1, bx1s, y_m1 - 1,
                                   fill="", outline="#FFFFFF", width=2)

        # ── subtitle cue track ───────────────────────────────────────────────
        self._srt_blocks = []
        pad_y = 4
        for si, entry in enumerate(self.srt_entries):
            s_sec = _srt_time_to_sec(entry.start)
            e_sec = _srt_time_to_sec(entry.end)
            bx0 = int(x0 + (s_sec - vs) * pps)
            bx1 = int(x0 + (e_sec - vs) * pps)
            if bx1 < x0 or bx0 > x0 + usable:
                continue
            bx0 = max(x0, bx0)
            bx1 = min(x0 + usable, bx1)
            if bx1 - bx0 < 3:
                bx1 = bx0 + 3
            sel_s    = (si == self._srt_selected_idx)
            fill_s   = "#5A3800" if not sel_s else "#9A6000"
            border_s = C_SUBS if not sel_s else "#FFDD88"
            c.create_rectangle(bx0, y_s0 + pad_y, bx1, y_s1 - pad_y,
                               fill=fill_s, outline=border_s, width=1)
            self._srt_blocks.append((bx0, bx1, si))
            if bx1 - bx0 > 18:
                txt_s = (entry.text if hasattr(entry, "text") else "")[:26]
                c.create_text((bx0 + bx1) // 2, (y_s0 + y_s1) // 2,
                              text=txt_s, fill="#FFE0A0",
                              font=("Segoe UI", 8), anchor="center")

        # ── playhead ─────────────────────────────────────────────────────────
        ph  = max(0.0, min(total_d, float(self._playhead_sec)))
        phx = x0 + (ph - vs) * pps
        if x0 - 2 <= phx <= x0 + usable + 2:
            c.create_line(phx, 0, phx, total_h, fill=C_PH, width=2)
            # Triangle knob at ruler top (pointing down)
            c.create_polygon(phx - 5, 0, phx + 5, 0, phx, 8,
                             fill=C_PH, outline="")

        # ── drag ghost ───────────────────────────────────────────────────────
        if ghost_x is not None and self._drag_tl.get("idx") is not None:
            c.create_line(ghost_x, y_vid0, ghost_x, y_vid1,
                          fill=TL_TEXT, width=2, dash=(4, 3))

        # ── focus track highlight: left-edge accent bar only ─────────────────
        ft = self._tl_focus_track
        ft_map = {
            "video": (y_vid0, y_vid1, C_VID),
            "voice": (y_n0, y_n1, C_VOICE),
            "music": (y_m0, y_m1, C_MUSIC),
            "subs":  (y_s0, y_s1, C_SUBS),
        }
        if ft in ft_map:
            fy0, fy1, fc = ft_map[ft]
            # Bright left-edge accent bar marks the active track
            c.create_rectangle(LW, fy0, LW + 5, fy1, fill=fc, outline="")

        self._update_preview_tc()

    def _tl_index_at(self, x: int, y: int | None = None) -> int | None:
        if y is not None:
            yv0 = self.RULER_H + 2
            yv1 = yv0 + self.VIDEO_TRACK_H - 4
            if y < yv0 or y > yv1:
                return None
        for x0, x1, idx in self._tl_blocks:
            if x0 <= x <= x1:
                return idx
        if not self._tl_blocks or not self.clips:
            return None
        # fallback by proportional x
        try:
            w = int(self._timeline_canvas.winfo_width())
        except tk.TclError:
            w = 700
        total_d, pps, x0b, usable = self._timeline_layout(max(40, w))
        if x < x0b or x > x0b + usable:
            return None
        t = self._time_from_canvas_x(x)
        return self._clip_and_offset_at_time(t)[0]

    def _tl_motion_hover(self, e):
        if self._ruler_ptr.get("active"):
            return
        in_ruler = (e.y < self.RULER_H and self._tl_y_track(e.y) == "ruler")
        new_hx = e.x if in_ruler else None
        self._tl_ruler_hover_y = e.y
        if new_hx != self._tl_ruler_hover_x:
            self._tl_ruler_hover_x = new_hx
            self._timeline_redraw_schedule()

    def _tl_wheel(self, e):
        if self._tl_y_track(e.y) == "none":
            return
        try:
            cw = int(self._timeline_canvas.winfo_width())
        except tk.TclError:
            return
        total, pps, _x0, usable = self._timeline_layout(max(40, cw))
        vis = usable / max(0.0001, pps)
        delta = int(getattr(e, "delta", 0))
        ctrl = bool(e.state & 0x0004)
        if ctrl:
            # Ctrl+wheel → zoom in / out
            factor = 1.0 + (delta / 120.0) * 0.18
            self._tl_zoom = max(0.2, min(40.0, self._tl_zoom * factor))
        else:
            # Plain wheel → pan left / right
            step = -(delta / 120.0) * vis * 0.15
            self._tl_view_start = max(0.0, min(max(0.0, total - vis), self._tl_view_start + step))
        self._timeline_redraw_schedule()

    def _music_vol_delta(self, d: float) -> None:
        self.bg_volume = max(0.0, min(1.5, self.bg_volume + float(d)))
        if hasattr(self, "music_slider"):
            self.music_slider.set(min(1.0, self.bg_volume))
        if hasattr(self, "lbl_music_vol"):
            self.lbl_music_vol.configure(text=f"{int(self.bg_volume * 100)}%")
        self.lbl_status.configure(text=f"Music mix: {int(self.bg_volume * 100)}%", text_color=ACCENT_GRN)

    def _music_vol_reset(self) -> None:
        self.bg_volume = 0.3
        if hasattr(self, "music_slider"):
            self.music_slider.set(self.bg_volume)
        if hasattr(self, "lbl_music_vol"):
            self.lbl_music_vol.configure(text=f"{int(self.bg_volume * 100)}%")

    # ── volume dialog (voice & music) ─────────────────────────────────────
    def _show_volume_dialog(self, track: str) -> None:
        """Popup slider to set voice or music volume 0–100%."""
        if track == "voice":
            cur_pct = int(self._voice_volume * 100)
            title   = "Voice Volume"
        else:
            cur_pct = int(self.bg_volume * 100)
            title   = "Music Volume"

        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.configure(fg_color="#1A1A2E")

        # centre over editor
        self.update_idletasks()
        ex, ey = self.winfo_x(), self.winfo_y()
        ew, eh = self.winfo_width(), self.winfo_height()
        dlg.geometry(f"300x180+{ex + ew//2 - 150}+{ey + eh//2 - 90}")

        ctk.CTkLabel(dlg, text=title, font=("Segoe UI", 13, "bold"),
                     text_color="#FFFFFF").pack(pady=(16, 4))

        pct_var = tk.IntVar(value=cur_pct)
        lbl_val = ctk.CTkLabel(dlg, text=f"{cur_pct}%",
                               font=("Consolas", 20, "bold"), text_color="#A0E0FF")
        lbl_val.pack()

        def _on_slide(v):
            pct_var.set(int(float(v)))
            lbl_val.configure(text=f"{int(float(v))}%")

        slider = ctk.CTkSlider(dlg, from_=0, to=100, number_of_steps=100,
                               variable=pct_var, command=_on_slide,
                               width=240, button_color="#5090FF",
                               progress_color="#3060CC")
        slider.set(cur_pct)
        slider.pack(pady=8)

        def _apply():
            val = pct_var.get() / 100.0
            if track == "voice":
                self._voice_volume = float(val)
                self.lbl_status.configure(
                    text=f"Voice volume: {pct_var.get()}%", text_color=ACCENT_GRN)
            else:
                self.bg_volume = float(val)
                if hasattr(self, "music_slider"):
                    self.music_slider.set(min(1.0, self.bg_volume))
                if hasattr(self, "lbl_music_vol"):
                    self.lbl_music_vol.configure(text=f"{pct_var.get()}%")
                self.lbl_status.configure(
                    text=f"Music volume: {pct_var.get()}%", text_color=ACCENT_GRN)
            dlg.destroy()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(pady=(4, 12))
        ctk.CTkButton(btn_row, text="Apply", width=100, fg_color="#2060CC",
                      command=_apply).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cancel", width=80, fg_color="#333355",
                      command=dlg.destroy).pack(side="left", padx=6)

    # ── clip / voice speed ────────────────────────────────────────────────
    def _set_clip_speed(self, clip_idx: int, speed: float) -> None:
        """Set playback speed for a video clip. Stored; applied at assemble time."""
        self._push_undo()
        if speed == 1.0:
            self._clip_speeds.pop(clip_idx, None)
        else:
            self._clip_speeds[clip_idx] = float(speed)
        self._timeline_redraw()
        self.lbl_status.configure(
            text=f"Clip {clip_idx + 1} speed set to {speed}×.", text_color=ACCENT_GRN)

    def _set_voice_speed(self, speed: float) -> None:
        """Set playback speed for the voice track."""
        self._push_undo()
        if speed == 1.0:
            self._clip_speeds.pop(-1, None)
        else:
            self._clip_speeds[-1] = float(speed)
        self._timeline_redraw()
        self.lbl_status.configure(
            text=f"Voice speed set to {speed}×.", text_color=ACCENT_GRN)

    def _tl_right_press(self, e):
        tr = self._tl_y_track(e.y)
        menu = tk.Menu(self, tearoff=0)

        if tr == "video":
            self._tl_focus_track = "video"
            idx = self._tl_index_at(e.x, e.y)
            if idx is not None:
                self._select_clip(idx)
                clip = self.clips[idx]
                name_short = Path(clip.path).name[:28]
                menu.add_command(label=f"Clip {idx + 1}: {name_short}", state="disabled")
                menu.add_separator()
                menu.add_command(label="Preview this clip", command=self._preview_play)
                menu.add_separator()
                menu.add_command(label="Trim clip…", command=lambda: self._show_trim_dialog(idx))
                menu.add_command(label="Split at playhead…", command=lambda: self._show_split_dialog(idx))
                menu.add_command(label="Replace video…", command=lambda: self._replace_clip(idx))
                menu.add_separator()
                # Speed sub-menu: 0.5 → 2.0 with fine steps
                spd_menu = tk.Menu(menu, tearoff=0)
                cur_spd = self._clip_speeds.get(idx, 1.0)
                _SPEED_OPTS = [0.5, 0.75, 0.9, 0.95,
                               1.0, 1.05, 1.10, 1.15, 1.20, 1.25,
                               1.5, 1.75, 2.0]
                for spd in _SPEED_OPTS:
                    lbl = f"{'>' if abs(spd - cur_spd) < 0.001 else ' '} {spd}×"
                    spd_menu.add_command(
                        label=lbl,
                        command=lambda s=spd, ii=idx: self._set_clip_speed(ii, s),
                    )
                menu.add_cascade(label=f"Speed  ({cur_spd}×)", menu=spd_menu)
                menu.add_separator()
                menu.add_command(label="Move up", command=lambda: self._move_clip(idx, -1))
                menu.add_command(label="Move down", command=lambda: self._move_clip(idx, 1))
                menu.add_separator()
                menu.add_command(label="Remove clip", command=lambda: self._remove_clip(idx))
            else:
                return

        elif tr == "voice":
            self._tl_focus_track = "voice"
            _cur_vvol = int(self._voice_volume * 100)
            menu.add_command(label=f"VOICE TRACK  •  {_cur_vvol}%", state="disabled")
            menu.add_separator()
            menu.add_command(label="🔊 Set Volume (0–100%)…",
                             command=lambda: self._show_volume_dialog("voice"))
            menu.add_separator()
            menu.add_command(label="Replace voiceover…", command=self._replace_voiceover)
            menu.add_command(label="Trim voiceover…", command=self._show_voice_dialog)
            menu.add_separator()
            # Speed sub-menu for voice: 0.5 → 2.0 fine steps
            vspd_menu = tk.Menu(menu, tearoff=0)
            cur_vspd = self._clip_speeds.get(-1, 1.0)  # -1 = voice track speed
            _SPEED_OPTS = [0.5, 0.75, 0.9, 0.95,
                           1.0, 1.05, 1.10, 1.15, 1.20, 1.25,
                           1.5, 1.75, 2.0]
            for spd in _SPEED_OPTS:
                lbl = f"{'>' if abs(spd - cur_vspd) < 0.001 else ' '} {spd}×"
                vspd_menu.add_command(
                    label=lbl,
                    command=lambda s=spd: self._set_voice_speed(s),
                )
            menu.add_cascade(label=f"Voice Speed  ({cur_vspd}×)", menu=vspd_menu)

        elif tr == "music":
            self._tl_focus_track = "music"
            _cur_mvol = int(self.bg_volume * 100)
            menu.add_command(label=f"MUSIC TRACK  •  {_cur_mvol}%", state="disabled")
            menu.add_separator()
            menu.add_command(label="🔊 Set Volume (0–100%)…",
                             command=lambda: self._show_volume_dialog("music"))
            menu.add_separator()
            menu.add_command(label="Browse music file…", command=self._browse_music)
            menu.add_separator()
            menu.add_command(label="Louder (+10%)", command=lambda: self._music_vol_delta(0.10))
            menu.add_command(label="Quieter (-10%)", command=lambda: self._music_vol_delta(-0.10))
            menu.add_command(label="Reset to 30%", command=self._music_vol_reset)

        elif tr == "subs":
            self._tl_focus_track = "subs"
            # find the SRT cue under click
            si = None
            for bx0, bx1, idx in self._srt_blocks:
                if bx0 <= e.x <= bx1:
                    si = idx
                    break
            menu.add_command(label="SUBTITLE TRACK", state="disabled")
            menu.add_separator()
            menu.add_command(label="+ Add cue at playhead", command=self._srt_add_at_playhead)
            if si is not None:
                self._srt_selected_idx = si
                menu.add_command(label=f"Edit cue {si + 1}…", command=lambda i=si: self._srt_edit_inline(i))
                menu.add_command(label=f"Delete cue {si + 1}", command=lambda i=si: self._srt_delete_cue(i))
            menu.add_separator()
            menu.add_command(label="Edit all subtitles…", command=self._show_subtitles_dialog)
        else:
            return

        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _tl_double_click(self, e):
        tr = self._tl_y_track(e.y)
        if tr == "subs":
            for bx0, bx1, si in self._srt_blocks:
                if bx0 <= e.x <= bx1:
                    self._srt_edit_inline(si)
                    return

    # ── subtitle track helpers ────────────────────────────────────────────
    def _srt_add_at_playhead(self):
        """Insert a new SRT cue at the current playhead position."""
        t = float(self._playhead_sec)
        end_t = t + 3.0
        new_entry = SrtEntry(
            len(self.srt_entries) + 1,
            _sec_to_srt_time(t),
            _sec_to_srt_time(end_t),
            "New subtitle",
        )
        # insert in time order
        idx = len(self.srt_entries)
        for i, e in enumerate(self.srt_entries):
            es = e.start_sec if hasattr(e, "start_sec") else _srt_time_to_sec(e.start)
            if es > t:
                idx = i
                break
        self._push_undo()
        self.srt_entries.insert(idx, new_entry)
        # renumber
        for i, e in enumerate(self.srt_entries):
            self.srt_entries[i] = SrtEntry(i + 1, e.start, e.end, e.text)
        self._srt_selected_idx = idx
        self._timeline_redraw_schedule()
        self.lbl_status.configure(text="Subtitle cue added.", text_color=ACCENT_GRN)

    def _srt_delete_cue(self, idx: int):
        if not (0 <= idx < len(self.srt_entries)):
            return
        self._push_undo()
        self.srt_entries.pop(idx)
        for i, e in enumerate(self.srt_entries):
            self.srt_entries[i] = SrtEntry(i + 1, e.start, e.end, e.text)
        self._srt_selected_idx = -1
        self._timeline_redraw_schedule()
        self.lbl_status.configure(text="Subtitle cue deleted.", text_color=ACCENT_WARN)

    def _srt_edit_inline(self, idx: int):
        """Small popup to edit a single SRT cue's text and timing."""
        if not (0 <= idx < len(self.srt_entries)):
            return
        entry = self.srt_entries[idx]
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Edit Cue {idx + 1}")
        dlg.geometry("460x260")
        dlg.grab_set()
        dlg.configure(fg_color=BG_MAIN)
        ctk.CTkLabel(dlg, text=f"Cue {idx + 1}", font=("Orbitron", 13, "bold"), text_color=ACCENT_DOC).pack(pady=8)
        rows_f = ctk.CTkFrame(dlg, fg_color="transparent")
        rows_f.pack(fill="x", padx=16)
        r1 = ctk.CTkFrame(rows_f, fg_color="transparent"); r1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1, text="Start (s):", width=70, anchor="e").pack(side="left", padx=4)
        ent_s = ctk.CTkEntry(r1, width=120); ent_s.pack(side="left")
        ent_s.insert(0, str(round(_srt_time_to_sec(entry.start), 3)))
        r2 = ctk.CTkFrame(rows_f, fg_color="transparent"); r2.pack(fill="x", pady=2)
        ctk.CTkLabel(r2, text="End (s):", width=70, anchor="e").pack(side="left", padx=4)
        ent_e = ctk.CTkEntry(r2, width=120); ent_e.pack(side="left")
        ent_e.insert(0, str(round(_srt_time_to_sec(entry.end), 3)))
        ctk.CTkLabel(dlg, text="Text:", anchor="w").pack(fill="x", padx=16)
        txt_box = ctk.CTkTextbox(dlg, height=60, fg_color=BG_SEC); txt_box.pack(fill="x", padx=16, pady=4)
        txt_box.insert("1.0", entry.text)

        def _save():
            try:
                ns = float(ent_s.get())
                ne = float(ent_e.get())
            except ValueError:
                messagebox.showerror("Edit Cue", "Start/End must be numbers.", parent=dlg)
                return
            new_txt = txt_box.get("1.0", "end").strip()
            self._push_undo()
            self.srt_entries[idx] = SrtEntry(idx + 1, _sec_to_srt_time(ns), _sec_to_srt_time(ne), new_txt)
            self._timeline_redraw_schedule()
            dlg.destroy()

        ctk.CTkButton(dlg, text="SAVE", command=_save, fg_color=ACCENT_DOC).pack(pady=8)

    # ── ruler zone helpers ────────────────────────────────────────────────
    # Top 45% of ruler → zoom zone (drag = zoom in/out like Filmora)
    # Bottom 55%       → scrub zone (drag = move playhead; tap = split)
    def _tl_press(self, e):
        tr = self._tl_y_track(e.y)
        if tr == "ruler":
            # Always update playhead on press so user gets instant visual feedback
            self._playhead_sec = self._time_from_canvas_x(e.x)
            self._ruler_ptr = {
                "active": True,
                "x0": e.x,
                "y0": e.y,
                "moved": False,
                "tr": "ruler",
                # Ctrl held → zoom mode; otherwise scrub
                "mode": "zoom" if (e.state & 0x0004) else "scrub",
                "zlx": e.x,
            }
            self._timeline_redraw()
            self._drag_tl["idx"] = None
            return
        if tr == "music":
            self._tl_focus_track = "music"
            self._playhead_sec = self._time_from_canvas_x(e.x)
            # Find which music segment was clicked
            self._selected_music_seg = -1
            for bx0, bx1, si in self._music_seg_blocks:
                if bx0 <= e.x <= bx1:
                    self._selected_music_seg = si
                    break
            self._timeline_redraw()
            self._drag_tl["idx"] = None
            return
        if tr == "voice":
            self._tl_focus_track = "voice"
            self._playhead_sec = self._time_from_canvas_x(e.x)
            # Find which voice segment was clicked
            self._selected_voice_seg = -1
            for bx0, bx1, si in self._voice_seg_blocks:
                if bx0 <= e.x <= bx1:
                    self._selected_voice_seg = si
                    break
            self._timeline_redraw()
            self._drag_tl["idx"] = None
            return
        if tr == "subs":
            self._tl_focus_track = "subs"
            for bx0, bx1, si in self._srt_blocks:
                if bx0 <= e.x <= bx1:
                    self._srt_selected_idx = si
                    break
            self._timeline_redraw()
            self._drag_tl["idx"] = None
            return
        if tr == "video":
            self._tl_focus_track = "video"
            idx = self._tl_index_at(e.x, e.y)
            if idx is not None:
                self._drag_tl["idx"] = idx
                self._select_clip(idx)
            else:
                self._drag_tl["idx"] = None
                self._playhead_sec = self._time_from_canvas_x(e.x)
                self._timeline_redraw()
            return
        self._drag_tl["idx"] = None

    def _tl_motion(self, e):
        rp = self._ruler_ptr
        if rp.get("active") and rp.get("tr") == "ruler":
            dx = e.x - int(rp.get("x0", 0))
            if abs(dx) > 3:
                rp["moved"] = True

            mode = rp.get("mode", "scrub")
            if mode == "zoom":
                # Ctrl+drag: left drag = zoom out, right drag = zoom in
                zlx = int(rp.get("zlx", e.x))
                delta = (e.x - zlx) * 0.007
                self._tl_zoom = max(0.2, min(40.0, self._tl_zoom * (1.0 + delta)))
                rp["zlx"] = e.x
                self._timeline_redraw()
                return

            # Scrub mode: move playhead as user drags
            self._playhead_sec = self._time_from_canvas_x(e.x)
            self._timeline_redraw()
            return

        if self._drag_tl["idx"] is None:
            return
        yv0 = self.RULER_H
        yv1 = yv0 + self.VIDEO_TRACK_H
        if e.y < yv0 or e.y > yv1:
            return
        self._timeline_redraw(ghost_x=e.x)

    def _tl_release(self, e):
        rp = self._ruler_ptr
        if rp.get("active") and rp.get("tr") == "ruler":
            mode    = rp.get("mode", "scrub")
            moved   = bool(rp.get("moved"))
            press_x = int(rp.get("x0", e.x))
            self._ruler_ptr = {}
            # Tap (no drag) in scrub mode = split at playhead
            if mode == "scrub" and not moved:
                t = self._time_from_canvas_x(press_x)
                self._split_timeline_at_global_time(t)
            self._timeline_redraw()
            return
        i0 = self._drag_tl["idx"]
        self._drag_tl["idx"] = None
        self._timeline_redraw()
        if i0 is None:
            return
        if e.y < self.RULER_H:
            return
        yv0 = self.RULER_H + 2
        yv1 = yv0 + self.VIDEO_TRACK_H - 4
        if e.y < yv0 or e.y > yv1:
            return
        i1 = self._tl_index_at(e.x, e.y)
        if i1 is None or i1 == i0:
            return
        self.clips = move_clip(self.clips, i0, i1)
        if len(self.script_segments) == len(self.clips):
            si = self.script_segments.pop(i0)
            self.script_segments.insert(i1, si)
        else:
            self._ensure_segments_match_clips()
        self.selected_clip_idx = i1
        self._regen_srt_from_voice()
        self._refresh_clip_list()

    def _build_mux_and_play(self, clip_idx: int, video_ss: float, audio_ss: float, duration: float) -> None:
        if not self._vlc_player or not self._vlc_instance:
            self.lbl_status.configure(text="Preview needs VLC — see message above.", text_color=ACCENT_WARN)
            return
        if not (0 <= clip_idx < len(self.clips)):
            return
        vp = self.clips[clip_idx].path
        ap = Path(self.audio_path)
        if not vp.is_file() or not ap.is_file():
            messagebox.showerror("Preview", "Video or voice file missing.")
            return
        try:
            out = self._preview_mux_path
            voice_slice = _slice_srt_for_preview(self.srt_entries, float(audio_ss), float(duration))
            srt_p = self.run_dir / "_ghost_preview_window.srt"
            spath: Path | None = srt_p if voice_slice else None
            if voice_slice:
                write_srt(voice_slice, srt_p)
            tpath: Path | None = None
            if self._preview_title.strip():
                tp = self.run_dir / "_ghost_preview_title.txt"
                tp.write_text(self._preview_title.strip()[:240] + "\n", encoding="utf-8")
                tpath = tp
            mus = self._active_music_path()
            try:
                _ffmpeg_mux_preview(
                    vp,
                    ap,
                    float(video_ss),
                    float(audio_ss),
                    float(duration),
                    out,
                    music=mus,
                    music_gain=float(self.bg_volume),
                    voice_gain=float(self._voice_volume),
                    srt_slice_path=spath,
                    title_lines_path=tpath,
                )
            except Exception:
                _ffmpeg_mux_preview(
                    vp,
                    ap,
                    float(video_ss),
                    float(audio_ss),
                    float(duration),
                    out,
                    music=mus,
                    music_gain=float(self.bg_volume),
                    voice_gain=float(self._voice_volume),
                )
            m = self._vlc_instance.media_new(str(out.resolve()))
            self._vlc_player.set_media(m)
            self._vlc_player.play()
            self.lbl_status.configure(
                text=f"Preview: clip {clip_idx + 1} + voice + subs/title"
                + (" + music" if mus else ""),
                text_color=ACCENT_GRN,
            )
        except Exception as exc:
            messagebox.showerror("Preview", str(exc))

    def _preview_play(self):
        if not (0 <= self.selected_clip_idx < len(self.clips)):
            self.lbl_status.configure(text="Select a clip in the list or timeline.", text_color=ACCENT_WARN)
            return
        idx = self.selected_clip_idx
        dur = max(0.12, self.clips[idx].duration)
        ass = self._voice_start_for_clip(idx)
        self._build_mux_and_play(idx, 0.0, ass, dur)

    def _preview_from_playhead(self):
        """Start continuous playback from the current playhead position."""
        self._continuous_play_from_playhead()

    def _preview_pause(self):
        if self._vlc_player:
            self._vlc_player.pause()
        self._vlc_poll_active = False

    def _preview_stop(self):
        if self._vlc_player:
            self._vlc_player.stop()
        self._vlc_poll_active = False

    # ── continuous playback ───────────────────────────────────────────────
    def _continuous_play_from_playhead(self):
        """Build a mux for all remaining clips from playhead and play through them."""
        if not self.clips:
            return
        if not self._vlc_player or not self._vlc_instance:
            self.lbl_status.configure(text="Preview needs VLC.", text_color=ACCENT_WARN)
            return
        t = float(self._playhead_sec)
        idx, vss, _rem = self._clip_and_offset_at_time(t)
        self._preview_clip_idx = idx
        self._preview_clip_tl_start = t - vss  # global seconds at start of this clip
        self._vlc_poll_active = True
        # Build mux for this clip
        dur = max(0.12, self.clips[idx].duration - vss)
        self._build_mux_and_play(idx, vss, t, dur)
        # Start poll ticker
        self.after(80, self._vlc_tick)

    def _vlc_tick(self):
        """Poll VLC every 80ms: update playhead, auto-advance to next clip."""
        if not self._vlc_poll_active:
            return
        if not self._vlc_player or not self._vlc_module:
            return
        try:
            state = self._vlc_player.get_state()
            vlc_playing = self._vlc_module.State.Playing
            vlc_ended   = self._vlc_module.State.Ended
            vlc_paused  = self._vlc_module.State.Paused
            vlc_stopped = self._vlc_module.State.Stopped

            if state in (vlc_paused, vlc_stopped):
                self._vlc_poll_active = False
                return

            # Update playhead from VLC position
            length_ms = self._vlc_player.get_length()
            pos_ms = self._vlc_player.get_time()
            if length_ms > 0 and pos_ms >= 0:
                frac = pos_ms / length_ms
                clip_dur = self.clips[self._preview_clip_idx].duration if self._preview_clip_idx < len(self.clips) else 0
                self._playhead_sec = self._preview_clip_tl_start + frac * clip_dur
                self._timeline_redraw_schedule()

            if state == vlc_ended:
                # Advance to next clip
                nxt = self._preview_clip_idx + 1
                if nxt < len(self.clips):
                    nxt_tl_start = self._preview_clip_tl_start + max(0.0, self.clips[self._preview_clip_idx].duration)
                    self._preview_clip_idx = nxt
                    self._preview_clip_tl_start = nxt_tl_start
                    self._playhead_sec = nxt_tl_start
                    ass = self._voice_start_for_clip(nxt)
                    dur = max(0.12, self.clips[nxt].duration)
                    self._build_mux_and_play(nxt, 0.0, ass, dur)
                else:
                    self._vlc_poll_active = False
                    return
        except Exception:
            pass
        self.after(80, self._vlc_tick)

    def _build_trim_tab(self, parent):
        ctk.CTkLabel(parent, text="Trim Selected Clip", font=("Orbitron", 14, "bold"), text_color=ACCENT_DOC).pack(pady=10)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=10)
        ctk.CTkLabel(row, text="Start (s):").pack(side="left", padx=5)
        self.ent_trim_start = ctk.CTkEntry(row, width=80)
        self.ent_trim_start.pack(side="left", padx=5)
        self.ent_trim_start.insert(0, "0.0")
        ctk.CTkLabel(row, text="End (s):").pack(side="left", padx=5)
        self.ent_trim_end = ctk.CTkEntry(row, width=80)
        self.ent_trim_end.pack(side="left", padx=5)
        self.chk_reencode = ctk.CTkCheckBox(parent, text="Re-encode (Accurate)", fg_color=ACCENT_DOC)
        self.chk_reencode.pack(pady=10)
        self.chk_reencode.select()
        ctk.CTkButton(parent, text="APPLY TRIM", command=self._apply_trim, fg_color=ACCENT_DOC).pack(pady=10)

    def _build_split_tab(self, parent):
        ctk.CTkLabel(parent, text="Split Selected Clip", font=("Orbitron", 14, "bold"), text_color=ACCENT_DOC).pack(pady=10)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=10)
        ctk.CTkLabel(row, text="Split at (s):").pack(side="left", padx=5)
        self.ent_split = ctk.CTkEntry(row, width=80)
        self.ent_split.pack(side="left", padx=5)
        ctk.CTkButton(parent, text="SPLIT CLIP", command=self._apply_split, fg_color=ACCENT_DOC).pack(pady=10)

    def _build_srt_tab(self, parent):
        style_frame = ctk.CTkFrame(parent, fg_color=BG_SEC)
        style_frame.pack(fill="x", pady=5)
        self.color_var = ctk.StringVar(value="#FFFFFF")
        self.colors_map = {"White": "#FFFFFF", "Yellow": "#FFCC00", "Green": "#00FF00", "Red": "#FF0000", "Cyan": "#00FFFF"}
        ctk.CTkLabel(style_frame, text="Color:").pack(side="left", padx=5)
        self.opt_color = ctk.CTkOptionMenu(
            style_frame,
            values=list(self.colors_map.keys()),
            width=90,
            command=lambda c: self.color_var.set(self.colors_map[c]),
        )
        self.opt_color.pack(side="left", padx=5)
        self.bg_color_var = ctk.StringVar(value="&H80000000")
        self.bg_map = {"Semi-Black": "&H80000000", "Solid-Black": "&H00000000", "Transparent": "&HFF000000"}
        ctk.CTkLabel(style_frame, text="Bg:").pack(side="left", padx=5)
        self.opt_bg_color = ctk.CTkOptionMenu(
            style_frame, values=list(self.bg_map.keys()), width=110, command=lambda c: self.bg_color_var.set(self.bg_map[c])
        )
        self.opt_bg_color.pack(side="left", padx=5)
        self.var_bold = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(style_frame, text="Bold", variable=self.var_bold, width=60).pack(side="left", padx=5)
        self.var_italic = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(style_frame, text="Italic", variable=self.var_italic, width=60).pack(side="left", padx=5)
        self.srt_list_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.srt_list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", pady=5)
        ctk.CTkButton(btn_row, text="+ ADD CUE", command=self._add_srt_cue, fg_color=ACCENT_PRI, width=100).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="💾 SAVE SRT", command=self._save_srt, fg_color=ACCENT_DOC, width=100).pack(side="left", padx=5)

    def _refresh_clip_list(self):
        for widget in self.clip_list_frame.winfo_children():
            widget.destroy()
        total_dur = 0.0
        for i, clip in enumerate(self.clips):
            total_dur += clip.duration
            row = ctk.CTkFrame(
                self.clip_list_frame,
                fg_color=BG_SEC if i != self.selected_clip_idx else "#1A0033",
                corner_radius=0,
                border_width=1,
                border_color=ACCENT_DOC if i == self.selected_clip_idx else BORDER,
            )
            row.pack(fill="x", pady=2, padx=2)
            row.bind("<Button-1>", lambda e, idx=i: self._select_clip(idx))
            lbl = ctk.CTkLabel(
                row,
                text=(
                    f"{i+1}. {Path(clip.path).name[:22]}… | {clip.duration:.1f}s"
                    + (f" | ~{clip.target_duration_sec:.1f}s" if clip.target_duration_sec > 0.05 else "")
                ),
                font=("Share Tech Mono", 12),
                text_color=TEXT_PRI,
            )
            lbl.pack(side="left", padx=10, pady=8)
            lbl.bind("<Button-1>", lambda e, idx=i: self._select_clip(idx))
            ctk.CTkButton(row, text="▲", width=28, height=22, fg_color="transparent", border_width=1, command=lambda idx=i: self._move_clip(idx, -1)).pack(
                side="right", padx=2
            )
            ctk.CTkButton(row, text="▼", width=28, height=22, fg_color="transparent", border_width=1, command=lambda idx=i: self._move_clip(idx, 1)).pack(
                side="right", padx=2
            )
            ctk.CTkButton(
                row,
                text="✕",
                width=28,
                height=22,
                fg_color="transparent",
                text_color=ACCENT_RED,
                border_color=ACCENT_RED,
                border_width=1,
                command=lambda idx=i: self._remove_clip(idx),
            ).pack(side="right", padx=2)
            ctk.CTkButton(row, text="🔄", width=28, height=22, fg_color="transparent", border_width=1, command=lambda idx=i: self._replace_clip(idx)).pack(
                side="right", padx=2
            )
        self.lbl_stats.configure(
            text=f"Assets: {len(self.clips)}  |  Σ clips: {total_dur:.1f}s  |  Voice: {_audio_duration_sec(self.audio_path):.1f}s"
        )
        self._refresh_srt_list()
        self._timeline_redraw()

    def _select_clip(self, idx):
        self.selected_clip_idx = idx
        self._tl_focus_track = "video"
        if 0 <= idx < len(self.clips):
            self._playhead_sec = self._voice_start_for_clip(idx)
        self._refresh_clip_list()
        if 0 <= idx < len(self.clips):
            clip = self.clips[idx]
            self.ent_trim_start.delete(0, "end")
            self.ent_trim_start.insert(0, "0.0")
            self.ent_trim_end.delete(0, "end")
            self.ent_trim_end.insert(0, f"{clip.duration:.1f}")
            self.ent_split.delete(0, "end")
            self.ent_split.insert(0, f"{clip.duration / 2:.1f}")

    def _move_clip(self, idx, direction):
        nidx = idx + direction
        if 0 <= nidx < len(self.clips):
            self._push_undo()
            self.clips = move_clip(self.clips, idx, nidx)
            if len(self.script_segments) == len(self.clips):
                seg = self.script_segments.pop(idx)
                self.script_segments.insert(nidx, seg)
            else:
                self._ensure_segments_match_clips()
            self._regen_srt_from_voice()
            self.selected_clip_idx = nidx if self.selected_clip_idx == idx else self.selected_clip_idx
            self._refresh_clip_list()

    def _remove_clip(self, idx):
        self._push_undo()
        if 0 <= idx < len(self.script_segments):
            self.script_segments.pop(idx)
        self.clips = remove_clip(self.clips, idx)
        if self.selected_clip_idx == idx:
            self.selected_clip_idx = -1
        elif self.selected_clip_idx > idx:
            self.selected_clip_idx -= 1
        self._ensure_segments_match_clips()
        self._regen_srt_from_voice()
        self._refresh_clip_list()
        self._start_waveform_build()

    def _replace_clip(self, idx):
        p = filedialog.askopenfilename(title="Replace Clip", filetypes=[("Video", "*.mp4 *.mov *.webm")])
        if p:
            self._push_undo()
            self.clips = replace_clip(self.clips, idx, Path(p))
            self._refresh_clip_list()

    def _apply_trim(self):
        if self.selected_clip_idx < 0:
            return
        try:
            s = float(self.ent_trim_start.get())
            e = float(self.ent_trim_end.get())
            clip = self.clips[self.selected_clip_idx]
            self._push_undo()
            new_c = trim_clip(clip, s, e, self.run_dir, self.chk_reencode.get())
            self.clips[self.selected_clip_idx] = new_c
            self._refresh_clip_list()
            self.lbl_status.configure(text="Clip trimmed.")
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    def _apply_split(self):
        if self.selected_clip_idx < 0:
            return
        try:
            sp = float(self.ent_split.get())
            clip = self.clips[self.selected_clip_idx]
            idx = self.selected_clip_idx
            self._ensure_segments_match_clips()
            if idx >= len(self.script_segments):
                return
            ratio = sp / max(0.01, clip.duration)
            ratio = max(0.05, min(0.95, ratio))
            s1, s2 = self._split_segment_dict(self.script_segments[idx], ratio)
            self._push_undo()
            c1, c2 = split_clip(clip, sp, self.run_dir, self.chk_reencode.get())
            self.clips.pop(idx)
            self.clips.insert(idx, c2)
            self.clips.insert(idx, c1)
            self.script_segments.pop(idx)
            self.script_segments.insert(idx, s2)
            self.script_segments.insert(idx, s1)
            self._regen_srt_from_voice()
            self.selected_clip_idx = idx + 1
            self._refresh_clip_list()
            self._start_waveform_build()
            self.lbl_status.configure(text="Clip split (video + script).")
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    def _refresh_srt_list(self):
        for w in self.srt_list_frame.winfo_children():
            w.destroy()
        self.srt_widgets = []
        for i, cue in enumerate(self.srt_entries):
            r = ctk.CTkFrame(self.srt_list_frame, fg_color=BG_SEC)
            r.pack(fill="x", pady=2)
            ctk.CTkLabel(r, text=f"{i+1}").pack(side="left", padx=5)
            e_s = ctk.CTkEntry(r, width=70, font=("Consolas", 10))
            e_s.insert(0, cue.start)
            e_s.pack(side="left", padx=2)
            e_e = ctk.CTkEntry(r, width=70, font=("Consolas", 10))
            e_e.insert(0, cue.end)
            e_e.pack(side="left", padx=2)
            e_t = ctk.CTkEntry(r, font=("Consolas", 11))
            e_t.insert(0, cue.text)
            e_t.pack(side="left", fill="x", expand=True, padx=2)
            ctk.CTkButton(r, text="✕", width=24, fg_color="transparent", text_color=ACCENT_RED, command=lambda idx=i: self._remove_srt_cue(idx)).pack(
                side="right"
            )
            self.srt_widgets.append((e_s, e_e, e_t))

    def _add_srt_cue(self):
        self.srt_entries.append(SrtEntry(len(self.srt_entries) + 1, "00:00:00,000", "00:00:05,000", "New Cue"))
        self._refresh_srt_list()

    def _remove_srt_cue(self, idx):
        if 0 <= idx < len(self.srt_entries):
            self.srt_entries.pop(idx)
            self._refresh_srt_list()

    def _save_srt(self):
        new_srt = []
        for i, (es, ee, et) in enumerate(self.srt_widgets):
            new_srt.append(SrtEntry(i + 1, es.get(), ee.get(), et.get()))
        self.srt_entries = new_srt
        out_p = self.run_dir / "edited_subtitles.srt"
        export_srt_file(self.srt_entries, out_p)
        self.lbl_status.configure(text=f"SRT saved to {out_p.name}")

    def _get_subtitle_style(self) -> dict:
        return {
            "color": self.color_var.get(),
            "bg_color": self.bg_color_var.get(),
            "bold": self.var_bold.get(),
            "italic": self.var_italic.get(),
        }

    def _do_assemble(self):
        if self.is_assembling:
            return
        self.is_assembling = True
        self.btn_assemble.configure(state="disabled")
        self.btn_done.configure(state="disabled")
        self.lbl_status.configure(text="Assembling video…", text_color=ACCENT_SEC)
        self.prog_bar.set(0)
        mp = self.ent_music_path.get().strip() if hasattr(self, "ent_music_path") else ""
        self.bg_music_path = mp or None

        def run():
            try:
                import datetime

                from core.config_manager import config

                out_name = f"documentary_edited_{datetime.datetime.now().strftime('%H%M%S')}.mp4"
                _pb_speed = float(config.get("documentary.playback_speed", 1.0))
                _burn = wants_burned_subtitles(config)

                def prog(msg):
                    self.after(0, lambda m=msg: self.lbl_status.configure(text=m[:56]))

                logo_wm = self._logo_spec_for_export()
                vp = assemble_documentary(
                    clips=self.clips,
                    audio_path=self.audio_path,
                    segments=self.script_segments,
                    output_dir=self.run_dir,
                    output_filename=out_name,
                    aspect_ratio=self.aspect_ratio,
                    progress_callback=prog,
                    playback_speed=_pb_speed,
                    burn_subtitles=_burn,
                    subtitle_style=self._get_subtitle_style(),
                    bg_music_path=self.bg_music_path,
                    bg_music_volume=float(self.bg_volume),
                    narration_volume=float(self._voice_volume),
                    logo_watermark=logo_wm,
                )
                self.after(0, self._on_assemble_done, vp)
            except Exception as e:
                self.after(0, self._on_assemble_error, str(e))

        threading.Thread(target=run, daemon=True).start()

    def _on_assemble_done(self, vp):
        self.is_assembling = False
        self.btn_assemble.configure(state="normal")
        self.btn_done.configure(state="normal")
        self.prog_bar.set(1.0)
        self.lbl_status.configure(text=f"Done: {vp.name}", text_color=ACCENT_GRN)
        self.last_vp = vp

    def _on_assemble_error(self, err):
        self.is_assembling = False
        self.btn_assemble.configure(state="normal")
        self.btn_done.configure(state="normal")
        self.lbl_status.configure(text=f"Error: {err}", text_color=ACCENT_RED)

    def _on_done_clicked(self):
        # Export current SRT entries (subtitle dialog already updated self.srt_entries)
        if self.srt_entries:
            out_p = self.run_dir / "edited_subtitles.srt"
            try:
                export_srt_file(self.srt_entries, out_p)
            except Exception:
                pass
        mp = self.ent_music_path.get().strip() if hasattr(self, "ent_music_path") else ""
        self.bg_music_path = mp or None
        if self.on_done:
            self.on_done(
                self.clips,
                self.srt_entries,
                self.bg_music_path,
                self.bg_volume,
                self._get_subtitle_style(),
                self.audio_path,
                self._logo_spec_for_export(),
                list(self.script_segments),
            )
        self._release_vlc()
        self.destroy()

    def _on_close(self):
        self._release_vlc()
        self.destroy()

