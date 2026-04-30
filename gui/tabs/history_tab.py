"""
gui/tabs/history_tab.py — Run History Tab
==========================================
Scans the configured output folder for completed documentary run subfolders,
each of which contains a metadata.json written by the pipeline.
Displays them as rich scrollable cards sorted newest-first.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import customtkinter as ctk

from core.config_manager import config

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
        self._count_lbl.configure(text=f"{len(runs)} run{'s' if len(runs) != 1 else ''}")

        if not runs:
            self._empty_lbl.pack(expand=True, pady=80)
            return

        for run in runs:
            card = self._make_card(run)
            card.pack(fill="x", pady=(0, 8))
            self._cards.append(card)

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

        runs: list[dict] = []
        if not base.exists():
            return runs

        for folder in sorted(base.iterdir(), reverse=True):
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

            # Read history_entry.json if present (has topic, timestamp, video_path)
            hist: dict = {}
            if hist_file.exists():
                try:
                    hist = json.loads(hist_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # Derive timestamp from folder name (Safe_Title_YYYYMMDD_HHMMSS)
            ts_str = ""
            parts = folder.name.rsplit("_", 2)
            if len(parts) >= 2:
                try:
                    ts = datetime.strptime(f"{parts[-2]}_{parts[-1]}", "%Y%m%d_%H%M%S")
                    ts_str = ts.strftime("%d %b %Y  %H:%M")
                except ValueError:
                    ts_str = folder.name[-15:]

            # Find mp4
            mp4s = list(folder.glob("*.mp4"))
            video_path = str(mp4s[0]) if mp4s else ""

            runs.append({
                "folder":      str(folder),
                "title":       meta.get("title") or hist.get("title") or folder.name,
                "description": meta.get("description", "")[:300],
                "tags":        meta.get("tags", [])[:8],
                "topic":       hist.get("topic", ""),
                "timestamp":   ts_str or hist.get("timestamp", ""),
                "duration":    hist.get("duration", ""),
                "video_path":  video_path or hist.get("video_path", ""),
            })
        return runs

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

        folder_path = run["folder"]
        ctk.CTkButton(
            btn_row, text="📂  Open Folder",
            font=("Share Tech Mono", 11, "bold"),
            text_color=ACCENT_PRI, fg_color="transparent",
            hover_color=BG_SEC, border_color=ACCENT_PRI, border_width=1,
            corner_radius=0, width=130,
            command=lambda p=folder_path: subprocess.Popen(["explorer", p]),
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
