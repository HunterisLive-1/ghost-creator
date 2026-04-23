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
    on_regen_audio : callable | None — documentary only: re-TTS + remux
    on_regen_video : callable | None — documentary only: re-fetch clips + remux
    on_edit_plan : callable | None — documentary only: open script editor, then regen
    """

    def __init__(
        self,
        parent,
        video_path: str,
        on_approve,
        on_cancel,
        on_regen_audio=None,
        on_regen_video=None,
        on_edit_plan=None,
    ):
        super().__init__(parent)
        self._video_path = video_path
        self._on_approve = on_approve
        self._on_cancel = on_cancel
        self._on_regen_audio = on_regen_audio
        self._on_regen_video = on_regen_video
        self._on_edit_plan = on_edit_plan
        self._has_doc_regen = bool(on_regen_audio and on_regen_video)
        self._has_edit_plan = bool(on_edit_plan)

        self.title("🎬 Video Preview — Step 5 of 6")
        _h = 520 if (self._has_doc_regen and self._has_edit_plan) else (480 if self._has_doc_regen else 380)
        _mh = 440 if (self._has_doc_regen and self._has_edit_plan) else (400 if self._has_doc_regen else 340)
        self.geometry(f"640x{_h}")
        self.minsize(560, _mh)
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
        if self._has_doc_regen and self._has_edit_plan:
            _sub = (
                "Documentary: use Edit plan / narration to change voiceover and scene search terms, "
                "then Regenerate audio and/or Regenerate video. You can also tweak max clip and playback in Settings. "
                "Approve to save or upload — else cancel."
            )
        elif self._has_doc_regen:
            _sub = (
                "Documentary: tweak max clip / playback in Settings, then use regen. "
                "When satisfied, Approve to save or upload — else cancel."
            )
        else:
            _sub = "Review your video in the media player, then approve or cancel."
        ctk.CTkLabel(
            hdr,
            text=_sub,
            font=("Share Tech Mono", 11), text_color=TEXT_SEC,
            wraplength=580,
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

        # ── Documentary: edit plan (then regen) ──────────────────────────
        if self._on_edit_plan:
            ctk.CTkButton(
                self,
                text="📝  EDIT PLAN / NARRATION…",
                font=("Orbitron", 11, "bold"),
                fg_color=BG_SEC,
                hover_color=BG_CARD,
                border_color=ACCENT_PRI,
                border_width=1,
                text_color=ACCENT_PRI,
                height=40,
                command=self._do_edit_plan,
            ).pack(fill="x", padx=20, pady=(0, 4))

        # ── Documentary: regen row (re-reads Settings) ────────────────────
        if self._has_doc_regen:
            regen_row = ctk.CTkFrame(self, fg_color="transparent")
            regen_row.pack(fill="x", padx=20, pady=(4, 4))
            regen_row.columnconfigure(0, weight=1)
            regen_row.columnconfigure(1, weight=1)
            ctk.CTkButton(
                regen_row,
                text="🎙  REGENERATE AUDIO",
                font=("Orbitron", 11, "bold"),
                fg_color=BG_CARD,
                hover_color=BG_SEC,
                border_color=ACCENT_SEC,
                border_width=1,
                text_color=ACCENT_SEC,
                height=40,
                command=self._do_regen_audio,
            ).grid(row=0, column=0, padx=(0, 6), sticky="ew")
            ctk.CTkButton(
                regen_row,
                text="🎥  REGENERATE VIDEO",
                font=("Orbitron", 11, "bold"),
                fg_color=BG_CARD,
                hover_color=BG_SEC,
                border_color=ACCENT_PRI,
                border_width=1,
                text_color=ACCENT_PRI,
                height=40,
                command=self._do_regen_video,
            ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

        # ── Approve / Cancel ──────────────────────────────────────────────
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

    def _do_regen_audio(self):
        if not self._on_regen_audio:
            return
        self.destroy()
        self._on_regen_audio()

    def _do_regen_video(self):
        if not self._on_regen_video:
            return
        self.destroy()
        self._on_regen_video()

    def _do_edit_plan(self):
        if not self._on_edit_plan:
            return
        self.destroy()
        self._on_edit_plan()
