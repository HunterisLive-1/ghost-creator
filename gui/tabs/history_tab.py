"""
gui/tabs/history_tab.py — Run History Tab
==========================================
Scans the configured output folder for completed documentary run subfolders,
each of which contains a metadata.json written by the pipeline.
Displays the **10 most recent** runs as rich scrollable cards (newest-first).
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from config import get_ffmpeg_executable
from core.config_manager import config

_SUBPROC_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

# ── Palette ───────────────────────────────────────────────────────────────────
BG_MAIN    = "#050A10"
BG_SEC     = "#0A121A"
BG_CARD    = "#0F1A24"
BORDER     = "#1A2B3D"
ACCENT_PRI = "#0088FF"
ACCENT_DOC = "#B060FF"
ACCENT_GRN = "#00CC66"
ACCENT_RED = "#FF4444"
TEXT_PRI   = "#E6F0FF"
TEXT_SEC   = "#88AADD"
TEXT_HINT  = "#4A6080"


class HistoryTab(ctk.CTkFrame):
    """Scrollable card list of completed runs."""

    def __init__(self, master, app_ref=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app_ref = app_ref
        self._cards: list[ctk.CTkFrame] = []
        self._build_ui()
        self.refresh()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0,
                               border_width=1, border_color=BORDER)
        toolbar.pack(fill="x", padx=10, pady=(10, 0))

        ctk.CTkLabel(
            toolbar, text="📋  RUN HISTORY",
            font=("Orbitron", 16, "bold"), text_color=ACCENT_DOC,
        ).pack(side="left", padx=16, pady=10)

        ctk.CTkButton(
            toolbar, text="↻  REFRESH",
            font=("Share Tech Mono", 12, "bold"),
            text_color=ACCENT_PRI, fg_color="transparent",
            hover_color=BG_CARD, border_color=ACCENT_PRI, border_width=1,
            corner_radius=0, width=110,
            command=self.refresh,
        ).pack(side="right", padx=12, pady=8)

        # Count label
        self._count_lbl = ctk.CTkLabel(
            toolbar, text="",
            font=("Share Tech Mono", 11), text_color=TEXT_HINT,
        )
        self._count_lbl.pack(side="right", padx=8)

        # Scrollable card area
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT_DOC,
        )
        self._scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Empty state (shown when no runs)
        self._empty_lbl = ctk.CTkLabel(
            self._scroll,
            text=(
                "[ NO RUNS RECORDED ]\n\n"
                "Complete a documentary run in the 🎬 DOCUMENTARY tab\n"
                "and it will appear here automatically."
            ),
            font=("Share Tech Mono", 14),
            text_color=TEXT_HINT,
            justify="center",
        )

    # ── Refresh ───────────────────────────────────────────────────────────────
    def refresh(self):
        """Re-scan the output folder and rebuild cards."""
        # Clear existing cards
        for card in self._cards:
            card.destroy()
        self._cards.clear()
        self._empty_lbl.pack_forget()

        runs = self._collect_runs()
        self._count_lbl.configure(
            text=f"{len(runs)} recent run{'s' if len(runs) != 1 else ''} (newest 10)",
        )

        if not runs:
            self._empty_lbl.pack(expand=True, pady=80)
            return

        for run in runs:
            card = self._make_card(run)
            card.pack(fill="x", pady=(0, 8))
            self._cards.append(card)

    @staticmethod
    def _run_sort_epoch(folder: Path, hist: dict) -> float:
        """Newest-first ordering: folder name date, history hints, else metadata.mtime."""
        parts = folder.name.rsplit("_", 2)
        if len(parts) >= 2:
            try:
                ts = datetime.strptime(f"{parts[-2]}_{parts[-1]}", "%Y%m%d_%H%M%S")
                return ts.timestamp()
            except ValueError:
                pass
        for key in ("completed_at", "finished_at", "updated_at"):
            v = hist.get(key)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str) and v:
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    pass
        try:
            return (folder / "metadata.json").stat().st_mtime
        except OSError:
            return 0.0

    def _collect_runs(self) -> list[dict]:
        """Scan output folder for run subfolders containing metadata.json."""
        out_str = config.get("pipeline.output_folder", "output")
        base = Path(out_str)
        if not base.is_absolute():
            cfg_path = getattr(config, "path", None)
            if cfg_path:
                base = Path(cfg_path).parent / out_str
            else:
                base = Path(out_str)

        scored: list[tuple[float, dict]] = []
        if not base.exists():
            return []

        for folder in base.iterdir():
            if not folder.is_dir():
                continue
            meta_file = folder / "metadata.json"
            hist_file = folder / "history_entry.json"
            if not meta_file.exists():
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            hist: dict = {}
            if hist_file.exists():
                try:
                    hist = json.loads(hist_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            ts_str = ""
            parts = folder.name.rsplit("_", 2)
            if len(parts) >= 2:
                try:
                    ts = datetime.strptime(f"{parts[-2]}_{parts[-1]}", "%Y%m%d_%H%M%S")
                    ts_str = ts.strftime("%d %b %Y  %H:%M")
                except ValueError:
                    ts_str = folder.name[-15:]

            mp4s = list(folder.glob("*.mp4"))
            video_path = str(mp4s[0]) if mp4s else ""

            run = {
                "folder":      str(folder),
                "title":       meta.get("title") or hist.get("title") or folder.name,
                "description": meta.get("description", "")[:300],
                "tags":        meta.get("tags", [])[:8],
                "topic":       hist.get("topic", ""),
                "timestamp":   ts_str or hist.get("timestamp", ""),
                "duration":    hist.get("duration", ""),
                "video_path":  video_path or hist.get("video_path", ""),
            }
            scored.append((self._run_sort_epoch(folder, hist), run))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _epoch, r in scored[:10]]

    @staticmethod
    def _resolve_edit_clip_paths(folder: Path, n_segments: int) -> list[Path]:
        """Prefer clips_for_edit (full-length), then raw clips/, then pre-trimmed."""
        cfe = sorted(folder.glob("clips_for_edit/e_*.mp4"))
        if len(cfe) >= n_segments:
            return cfe[:n_segments]
        raw = sorted(folder.glob("clips/*.mp4"))
        if len(raw) >= n_segments:
            return raw[:n_segments]
        trimmed = sorted(folder.glob("clips_trimmed/t_*.mp4"))
        if len(trimmed) >= n_segments:
            return trimmed[:n_segments]
        merged = sorted(folder.glob("clips_for_edit/*.mp4"))
        if len(merged) >= n_segments:
            return merged[:n_segments]
        return []

    @staticmethod
    def _extract_audio_from_video(video_path: Path, dest_m4a: Path) -> None:
        """Pull the first audio stream from a rendered MP4 for Ghost Editor (narration track)."""
        dest_m4a.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            get_ffmpeg_executable(), "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "aac", "-b:a", "192k",
            str(dest_m4a),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            creationflags=_SUBPROC_FLAGS,
        )
        if result.returncode != 0:
            tail = (result.stderr or "")[-500:]
            raise RuntimeError(tail or "FFmpeg could not extract audio from this video.")

    def _history_run_aspect_ratio(self, folder: Path) -> str:
        snap = folder / "documentary_editor.json"
        if snap.exists():
            try:
                data = json.loads(snap.read_text(encoding="utf-8"))
                if data.get("aspect_ratio"):
                    return str(data["aspect_ratio"])
            except Exception:
                pass
        return str(config.get("aspect_ratio", "9:16"))

    def _open_ghost_editor_for_run(self, run: dict):
        """Prefer multi-clip edit from documentary_editor.json + per-segment files; audio from VO or extracted from final MP4."""
        folder = Path(run["folder"])
        vp_str = (run.get("video_path") or "").strip()
        video_path = Path(vp_str) if vp_str and Path(vp_str).is_file() else None
        snap_p = folder / "documentary_editor.json"

        if snap_p.is_file():
            try:
                data = json.loads(snap_p.read_text(encoding="utf-8"))
            except Exception:
                data = None
            if data:
                segments = data.get("segments") or []
                paths = self._resolve_edit_clip_paths(folder, len(segments)) if segments else []
                if segments and len(paths) == len(segments):
                    audio_path = folder / "voiceover.mp3"
                    if not audio_path.is_file() and video_path is not None:
                        extracted = folder / "_ghost_editor_from_video_audio.m4a"
                        try:
                            self._extract_audio_from_video(video_path, extracted)
                            audio_path = extracted
                        except Exception:
                            audio_path = None
                    if audio_path is not None and audio_path.is_file():
                        self._open_ghost_editor_full_snapshot(run, audio_path_override=audio_path)
                        return

        if video_path is not None:
            self._open_ghost_editor_from_final_video(run, video_path)
            return
        messagebox.showwarning(
            "Ghost Editor",
            "Need documentary_editor.json with matching clips, or a finished MP4 in this run.\n"
            "Open the folder to verify files.",
        )

    def _open_ghost_editor_full_snapshot(self, run: dict, audio_path_override: Path | None = None):
        from gui.components.clip_editor import ClipEditorWindow
        from core.clip_manager import load_clips, generate_srt_from_segments
        from modules.documentary_assembler import (
            _audio_duration_sec,
            _normalized_segment_durations,
            assemble_documentary,
            wants_burned_subtitles,
        )

        folder = Path(run["folder"])
        snap = folder / "documentary_editor.json"
        try:
            data = json.loads(snap.read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror("Ghost Editor", f"Could not read snapshot:\n{exc}")
            return

        segments = data.get("segments") or []
        if not segments:
            messagebox.showerror("Ghost Editor", "Snapshot has no segments.")
            return

        audio_path = Path(audio_path_override) if audio_path_override is not None else (folder / "voiceover.mp3")
        if not audio_path.exists():
            messagebox.showerror("Ghost Editor", "No narration audio (voiceover.mp3 or extracted track).")
            return

        paths = self._resolve_edit_clip_paths(folder, len(segments))
        if len(paths) != len(segments):
            messagebox.showerror(
                "Ghost Editor",
                f"Found {len(paths)} clip file(s) but need {len(segments)}.\n"
                "Expected clips_for_edit/e_*.mp4 or clips/*.mp4.\n\n"
                "Try “Ghost Editor” on the final MP4 if per-segment clips are missing.",
            )
            return

        audio_dur = _audio_duration_sec(audio_path)
        targets = _normalized_segment_durations(segments, audio_dur)
        clip_infos = load_clips(paths, segments, target_durations=targets)
        srt_entries = generate_srt_from_segments(segments, audio_dur)
        ar = str(data.get("aspect_ratio") or config.get("aspect_ratio", "9:16"))

        top = self.winfo_toplevel()
        run_snapshot = dict(run)

        def on_done(new_clips, _new_srt, bg_music, bg_vol, subtitle_style, audio_path_edited=None, logo_watermark=None, script_segments=None):
            ap = Path(audio_path_edited) if audio_path_edited is not None else audio_path
            segs = script_segments if script_segments is not None else segments

            def worker():
                try:
                    _pb = float(config.get("documentary.playback_speed", 1.0))
                    _burn = wants_burned_subtitles(config)
                    out_name = f"documentary_reedit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

                    def prog(_msg: str) -> None:
                        pass

                    vp = assemble_documentary(
                        clips=new_clips,
                        audio_path=ap,
                        segments=segs,
                        output_dir=folder,
                        output_filename=out_name,
                        aspect_ratio=ar,
                        progress_callback=prog,
                        playback_speed=_pb,
                        burn_subtitles=_burn,
                        subtitle_style=subtitle_style,
                        bg_music_path=bg_music,
                        bg_music_volume=float(bg_vol or 0.25),
                        logo_watermark=logo_watermark,
                    )
                    he = folder / "history_entry.json"
                    if he.exists():
                        try:
                            h = json.loads(he.read_text(encoding="utf-8"))
                            h["video_path"] = str(vp)
                            he.write_text(
                                json.dumps(h, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                        except Exception:
                            pass
                    top.after(0, lambda: self._after_ghost_editor_assemble(vp, run_snapshot))
                except Exception as exc:
                    top.after(0, lambda e=str(exc): messagebox.showerror("Assembly failed", e))
                top.after(0, self.refresh)

            threading.Thread(target=worker, daemon=True).start()

        ClipEditorWindow(
            top,
            clips=clip_infos,
            audio_path=audio_path,
            srt_entries=srt_entries,
            script_segments=segments,
            run_dir=folder,
            aspect_ratio=ar,
            on_done=on_done,
        )

    def _open_ghost_editor_from_final_video(self, run: dict, video_path: Path):
        """Single-clip mode: edit the exported documentary MP4 (audio extracted for the VOICE row)."""
        from gui.components.clip_editor import ClipEditorWindow
        from core.clip_manager import load_clips, generate_srt_from_segments
        from modules.documentary_assembler import (
            _audio_duration_sec,
            _normalized_segment_durations,
            assemble_documentary,
            wants_burned_subtitles,
        )

        folder = Path(run["folder"])
        ar = self._history_run_aspect_ratio(folder)
        segments = [{"voiceover": "", "video_query": ""}]
        extracted = folder / "_ghost_editor_from_video_audio.m4a"
        try:
            self._extract_audio_from_video(video_path, extracted)
        except Exception as exc:
            fallback = folder / "voiceover.mp3"
            if fallback.is_file():
                if not messagebox.askyesno(
                    "Ghost Editor",
                    "Could not extract audio from the video file:\n\n"
                    f"{exc}\n\n"
                    "Use voiceover.mp3 from this run instead? (Length may not match the video.)",
                ):
                    return
                extracted = fallback
            else:
                messagebox.showerror(
                    "Ghost Editor",
                    f"Could not extract audio from the video:\n{exc}\n\n"
                    "The file may have no audio stream.",
                )
                return

        audio_path = extracted
        audio_dur = _audio_duration_sec(audio_path)
        if audio_dur <= 0.1:
            messagebox.showerror("Ghost Editor", "Extracted audio has no usable duration.")
            return

        targets = _normalized_segment_durations(segments, audio_dur)
        clip_infos = load_clips([video_path], segments, target_durations=targets)
        srt_entries = generate_srt_from_segments(segments, audio_dur)

        top = self.winfo_toplevel()
        run_snapshot = dict(run)

        def on_done(new_clips, _new_srt, bg_music, bg_vol, subtitle_style, audio_path_edited=None, logo_watermark=None, script_segments=None):
            ap = Path(audio_path_edited) if audio_path_edited is not None else audio_path
            segs = script_segments if script_segments is not None else segments

            def worker():
                try:
                    _pb = float(config.get("documentary.playback_speed", 1.0))
                    _burn = wants_burned_subtitles(config)
                    out_name = f"documentary_reedit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

                    def prog(_msg: str) -> None:
                        pass

                    vp = assemble_documentary(
                        clips=new_clips,
                        audio_path=ap,
                        segments=segs,
                        output_dir=folder,
                        output_filename=out_name,
                        aspect_ratio=ar,
                        progress_callback=prog,
                        playback_speed=_pb,
                        burn_subtitles=_burn,
                        subtitle_style=subtitle_style,
                        bg_music_path=bg_music,
                        bg_music_volume=float(bg_vol or 0.25),
                        logo_watermark=logo_watermark,
                    )
                    he = folder / "history_entry.json"
                    if he.exists():
                        try:
                            h = json.loads(he.read_text(encoding="utf-8"))
                            h["video_path"] = str(vp)
                            he.write_text(
                                json.dumps(h, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                        except Exception:
                            pass
                    top.after(0, lambda: self._after_ghost_editor_assemble(vp, run_snapshot))
                except Exception as exc:
                    top.after(0, lambda e=str(exc): messagebox.showerror("Assembly failed", e))
                top.after(0, self.refresh)

            threading.Thread(target=worker, daemon=True).start()

        ClipEditorWindow(
            top,
            clips=clip_infos,
            audio_path=audio_path,
            srt_entries=srt_entries,
            script_segments=segments,
            run_dir=folder,
            aspect_ratio=ar,
            on_done=on_done,
        )

    def _after_ghost_editor_assemble(self, vp: Path, run: dict) -> None:
        messagebox.showinfo("Ghost Editor", f"Re-rendered:\n{vp.name}")
        app = self.app_ref
        if app is None:
            return
        if messagebox.askyesno(
            "Direct Upload",
            "Open the Direct Upload tab with this video so you can publish to YouTube?",
        ):
            title_hint = (run.get("title") or "")[:100]
            try:
                app.open_direct_upload_with_video(vp, title_hint=title_hint or None)
            except Exception as exc:
                messagebox.showerror("Upload", str(exc))

    # ── Card builder ──────────────────────────────────────────────────────────
    def _make_card(self, run: dict) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self._scroll, fg_color=BG_CARD, corner_radius=0,
            border_width=1, border_color=BORDER,
        )

        # ── Top row: title + timestamp ──────────────────────────────────────
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))

        ctk.CTkLabel(
            top,
            text=run["title"] or "(untitled)",
            font=("Share Tech Mono", 13, "bold"),
            text_color=ACCENT_DOC,
            anchor="w", wraplength=500,
        ).pack(side="left", fill="x", expand=True)

        if run["timestamp"]:
            ctk.CTkLabel(
                top, text=run["timestamp"],
                font=("Share Tech Mono", 10), text_color=TEXT_HINT,
            ).pack(side="right")

        # ── Topic line ─────────────────────────────────────────────────────
        if run["topic"]:
            ctk.CTkLabel(
                card,
                text=f"📡  {run['topic']}",
                font=("Share Tech Mono", 11), text_color=TEXT_SEC,
                anchor="w",
            ).pack(anchor="w", padx=14, pady=(0, 4))

        # ── Description snippet ────────────────────────────────────────────
        if run["description"]:
            snippet = run["description"][:220].replace("\n", " ")
            ctk.CTkLabel(
                card, text=snippet,
                font=("Share Tech Mono", 11), text_color=TEXT_HINT,
                anchor="w", wraplength=680, justify="left",
            ).pack(anchor="w", padx=14, pady=(0, 4))

        # ── Tags ───────────────────────────────────────────────────────────
        if run["tags"]:
            tags_frame = ctk.CTkFrame(card, fg_color="transparent")
            tags_frame.pack(anchor="w", padx=12, pady=(0, 6))
            for tag in run["tags"][:7]:
                ctk.CTkLabel(
                    tags_frame, text=f"#{tag}",
                    font=("Share Tech Mono", 10), text_color=ACCENT_PRI,
                    fg_color=BG_SEC, corner_radius=0,
                ).pack(side="left", padx=(0, 6))

        # ── Buttons row ────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(4, 12))

        folder_path = Path(run["folder"])
        vid_ok = bool(run.get("video_path")) and Path(run["video_path"]).is_file()
        can_multi = False
        dj = folder_path / "documentary_editor.json"
        if dj.is_file():
            try:
                dj_data = json.loads(dj.read_text(encoding="utf-8"))
                segs = dj_data.get("segments") or []
                paths = self._resolve_edit_clip_paths(folder_path, len(segs))
                vo_ok = (folder_path / "voiceover.mp3").is_file()
                can_multi = bool(segs) and len(paths) == len(segs) and (vo_ok or vid_ok)
            except Exception:
                can_multi = False
        ghost_ok = can_multi or vid_ok
        ctk.CTkButton(
            btn_row, text="📂  Open Folder",
            font=("Share Tech Mono", 11, "bold"),
            text_color=ACCENT_PRI, fg_color="transparent",
            hover_color=BG_SEC, border_color=ACCENT_PRI, border_width=1,
            corner_radius=0, width=130,
            command=lambda p=str(folder_path): subprocess.Popen(["explorer", p]),
        ).pack(side="left", padx=(0, 8))

        if ghost_ok:
            label = "✂️  Ghost Editor" if can_multi else "✂️  Ghost (video)"
            ctk.CTkButton(
                btn_row,
                text=label,
                font=("Share Tech Mono", 11, "bold"),
                text_color=ACCENT_DOC,
                fg_color="#330044",
                hover_color="#4A0066",
                border_color=ACCENT_DOC,
                border_width=1,
                corner_radius=0,
                width=148,
                command=lambda r=dict(run): self._open_ghost_editor_for_run(r),
            ).pack(side="left", padx=(0, 8))

        if run["video_path"] and Path(run["video_path"]).exists():
            vp = run["video_path"]
            ctk.CTkButton(
                btn_row, text="▶  Play Video",
                font=("Share Tech Mono", 11, "bold"),
                text_color=ACCENT_GRN, fg_color="transparent",
                hover_color=BG_SEC, border_color=ACCENT_GRN, border_width=1,
                corner_radius=0, width=110,
                command=lambda p=vp: subprocess.Popen(["explorer", p]),
            ).pack(side="left", padx=(0, 8))

        if run["duration"]:
            ctk.CTkLabel(
                btn_row, text=f"⏱ {run['duration']}",
                font=("Share Tech Mono", 11), text_color=TEXT_HINT,
            ).pack(side="right", padx=8)

        return card
