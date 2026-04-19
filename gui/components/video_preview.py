"""
gui/components/video_preview.py — Video preview modal before upload.
Pause point between Step 5 (video assembly) and Step 6 (upload).
"""

import os
import subprocess
import sys
from pathlib import Path

import customtkinter as ctk

BG_MAIN    = "#050A10"
BG_SEC     = "#0A121A"
BG_CARD    = "#0F1A24"
BORDER     = "#1A2B3D"
ACCENT_PRI = "#0088FF"
ACCENT_SEC = "#00BFFF"
ACCENT_GRN = "#00CC66"
ACCENT_RED = "#FF4444"
TEXT_PRI   = "#E6F0FF"
TEXT_SEC   = "#88AADD"
TEXT_HINT  = "#4A6080"


def _open_in_player(path: str) -> None:
    """Open the video in the OS default media player."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class VideoPreviewWindow(ctk.CTkToplevel):
    """
    Shows after video assembly completes.
    User can play the video in their media player, then approve or cancel.

    Callbacks
    ---------
    on_approve : callable — user clicked "Approve & Continue"
    on_cancel  : callable — user clicked "Cancel Pipeline"
    """

    def __init__(self, parent, video_path: str, on_approve, on_cancel):
        super().__init__(parent)
        self._video_path = video_path
        self._on_approve = on_approve
        self._on_cancel  = on_cancel

        self.title("🎬 Video Preview — Step 5 of 6")
        self.geometry("640x380")
        self.minsize(560, 340)
        self.configure(fg_color=BG_MAIN)
        self.resizable(True, False)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.protocol("WM_DELETE_WINDOW", self._do_cancel)

        self._build_ui()

        # Auto-open the video so user doesn't have to click
        self.after(200, lambda: _open_in_player(self._video_path))

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0,
                           border_width=1, border_color=ACCENT_PRI)
        hdr.pack(fill="x", padx=20, pady=(20, 0))

        ctk.CTkLabel(
            hdr, text="[ VIDEO PREVIEW ]",
            font=("Orbitron", 16, "bold"), text_color=ACCENT_PRI,
        ).pack(pady=(14, 2))
        ctk.CTkLabel(
            hdr,
            text="Review your video in the media player, then approve or cancel.",
            font=("Share Tech Mono", 11), text_color=TEXT_SEC,
        ).pack(pady=(0, 14))

        # ── File info card ────────────────────────────────────────────────
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=20, pady=12)

        p = Path(self._video_path)
        size_mb = ""
        try:
            size_mb = f"  ·  {p.stat().st_size / 1_048_576:.1f} MB"
        except OSError:
            pass

        ctk.CTkLabel(
            card, text=p.name,
            font=("Share Tech Mono", 13, "bold"), text_color=ACCENT_SEC,
            wraplength=560, justify="left",
        ).pack(anchor="w", padx=16, pady=(10, 2))

        ctk.CTkLabel(
            card, text=str(p.parent) + size_mb,
            font=("Share Tech Mono", 10), text_color=TEXT_HINT,
            wraplength=560, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # ── Play button ───────────────────────────────────────────────────
        ctk.CTkButton(
            self,
            text="▶  PLAY VIDEO",
            font=("Orbitron", 12, "bold"),
            fg_color=BG_CARD,
            hover_color=BG_SEC,
            border_color=ACCENT_SEC,
            border_width=1,
            text_color=ACCENT_SEC,
            height=38,
            command=lambda: _open_in_player(self._video_path),
        ).pack(fill="x", padx=20, pady=(0, 4))

        # ── Action buttons ────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(8, 20))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_row,
            text="✗  CANCEL PIPELINE",
            font=("Orbitron", 11, "bold"),
            fg_color=BG_CARD,
            hover_color="#2A0A0A",
            border_color=ACCENT_RED,
            border_width=1,
            text_color=ACCENT_RED,
            height=42,
            command=self._do_cancel,
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            btn_row,
            text="✓  APPROVE & CONTINUE",
            font=("Orbitron", 11, "bold"),
            fg_color=ACCENT_GRN,
            hover_color="#009944",
            text_color="#000000",
            height=42,
            command=self._do_approve,
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    # ── Actions ───────────────────────────────────────────────────────────

    def _do_approve(self):
        self.destroy()
        self._on_approve()

    def _do_cancel(self):
        self.destroy()
        self._on_cancel()
