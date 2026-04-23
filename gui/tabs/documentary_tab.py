"""
gui/tabs/documentary_tab.py — Documentary Engine Tab
======================================================
Standalone documentary pipeline: OmniVoice narration + YouTube footage + FFmpeg.
No AI image generation.  Two sub-modes: SHORT (≤60s) and LONG (10-40 min).
"""
from __future__ import annotations

import math
import os
import queue
import subprocess
import tkinter as tk
from datetime import datetime
from pathlib import Path

import customtkinter as ctk

from core.config_manager import config

# ── Palette (same as main app) ────────────────────────────────────────────────
BG_MAIN     = "#050A10"
BG_SEC      = "#0A121A"
BG_CARD     = "#0F1A24"
BORDER      = "#1A2B3D"
ACCENT_PRI  = "#0088FF"
ACCENT_SEC  = "#00BFFF"
ACCENT_RED  = "#FF4444"
ACCENT_WARN = "#FFB800"
ACCENT_GOLD = "#FFD700"
TEXT_PRI    = "#E6F0FF"
TEXT_SEC    = "#88AADD"

# Documentary-specific accent
ACCENT_DOC  = "#B060FF"   # purple-ish — distinct from normal pipeline blue

# Step labels for documentary mode
DOC_STEPS = ["Research", "Script", "Voice", "Footage", "Assembly", "Upload"]


def _poll_queue_wrapper(tab: "DocumentaryTab") -> None:
    tab._poll_queue()


class DocumentaryTab(ctk.CTkFrame):
    """Full documentary pipeline tab — mirrors PipelineTab but for footage-based docs."""

    def __init__(self, master, progress_queue: queue.Queue, app_ref, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.progress_queue = progress_queue
        self.app_ref        = app_ref
        self.runner         = None
        self.pipeline_running = False

        self._step_states   = ["pending"] * 6
        self._current_step_idx = -1
        self._progress_val  = 0.0
        self._doc_mode      = config.get("documentary.length_mode", "short")  # "short" | "long"
        self._pipeline_run_id = 0

        # Bottom uplink label (fixed)
        self._uplink_lbl = ctk.CTkLabel(
            self, text="UPLINK: [No Profile]",
            font=("Orbitron", 12, "bold"), text_color=ACCENT_DOC,
        )
        self._uplink_lbl.pack(side="bottom", anchor="se", padx=20, pady=10)

        # Scrollable body
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT_DOC,
        )
        self._scroll.pack(fill="both", expand=True)
        self._body = self._scroll

        self._build_header()
        self._build_mode_cards()
        self._build_topic_row()
        self._build_duration_row()
        self._build_language_row()
        self._build_voice_engine_row()
        self._build_footage_settings()
        self._build_control_row()
        self._build_progress_section()
        self._build_log_section()
        self._build_output_preview()

        self._poll_queue()
        self._apply_mode(self._doc_mode, save=False)

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self._body, fg_color=BG_CARD, corner_radius=0,
                           border_width=1, border_color=ACCENT_DOC)
        hdr.pack(fill="x", padx=20, pady=(20, 10))

        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=14)

        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left")

        ctk.CTkLabel(
            left, text="🎬  DOCUMENTARY ENGINE",
            font=("Orbitron", 18, "bold"), text_color=ACCENT_DOC,
        ).pack(anchor="w")
        ctk.CTkLabel(
            left,
            text="OmniVoice narration  ·  YouTube footage  ·  FFmpeg assembly  ·  No AI images",
            font=("Share Tech Mono", 11), text_color=TEXT_SEC,
        ).pack(anchor="w", pady=(4, 0))

        badge = ctk.CTkFrame(inner, fg_color="#1A0A2E", corner_radius=0,
                             border_width=1, border_color=ACCENT_DOC)
        badge.pack(side="right")
        ctk.CTkLabel(badge, text="CINEMATIC MODE",
                     font=("Orbitron", 11, "bold"), text_color=ACCENT_DOC,
                     ).pack(padx=12, pady=6)

    # ── Mode Cards ────────────────────────────────────────────────────────────
    def _build_mode_cards(self):
        outer = ctk.CTkFrame(self._body, fg_color="transparent")
        outer.pack(fill="x", padx=20, pady=(0, 10))

        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)

        # SHORT card
        self._short_card = ctk.CTkFrame(
            outer, fg_color=BG_CARD, corner_radius=0,
            border_width=2, border_color=ACCENT_DOC,
        )
        self._short_card.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        self._short_card.bind("<Button-1>", lambda e: self._apply_mode("short"))

        si = ctk.CTkFrame(self._short_card, fg_color="transparent")
        si.pack(padx=18, pady=16, fill="x")
        si.bind("<Button-1>", lambda e: self._apply_mode("short"))

        ctk.CTkLabel(si, text="⚡  SHORT FORM",
                     font=("Orbitron", 15, "bold"), text_color=ACCENT_DOC,
                     ).pack(anchor="w")
        ctk.CTkLabel(si, text="30 – 60 seconds",
                     font=("Share Tech Mono", 13, "bold"), text_color=ACCENT_GOLD,
                     ).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(si,
                     text="• Quick 30–60s; output size: Settings → Video format (9:16 or 16:9)\n"
                          "• Auto: several short clips / cuts\n"
                          "• Fast narration, punchy cuts",
                     font=("Share Tech Mono", 11), text_color=TEXT_SEC, justify="left",
                     ).pack(anchor="w", pady=(8, 0))

        # LONG card
        self._long_card = ctk.CTkFrame(
            outer, fg_color=BG_CARD, corner_radius=0,
            border_width=1, border_color=BORDER,
        )
        self._long_card.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        self._long_card.bind("<Button-1>", lambda e: self._apply_mode("long"))

        li = ctk.CTkFrame(self._long_card, fg_color="transparent")
        li.pack(padx=18, pady=16, fill="x")
        li.bind("<Button-1>", lambda e: self._apply_mode("long"))

        ctk.CTkLabel(li, text="🎞  LONG FORM",
                     font=("Orbitron", 15, "bold"), text_color=TEXT_SEC,
                     ).pack(anchor="w")
        ctk.CTkLabel(li, text="3 – 40 minutes",
                     font=("Share Tech Mono", 13, "bold"), text_color=TEXT_SEC,
                     ).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(li,
                     text="• Full feature documentary\n"
                          "• More clips on longer runs (auto), up to 100\n"
                          "• Deep narration, chapter-style flow",
                     font=("Share Tech Mono", 11), text_color=TEXT_SEC, justify="left",
                     ).pack(anchor="w", pady=(8, 0))

    def _apply_mode(self, mode: str, save: bool = True) -> None:
        self._doc_mode = mode
        if save:
            config.set("documentary.length_mode", mode)

        if mode == "short":
            self._short_card.configure(border_width=2, border_color=ACCENT_DOC, fg_color="#100820")
            self._long_card.configure(border_width=1, border_color=BORDER, fg_color=BG_CARD)
            # Reconfigure slider for 30–60 s
            if hasattr(self, "_dur_slider"):
                self._dur_slider.configure(from_=30, to=60, number_of_steps=30)
                saved = int(config.get("documentary.short_duration", 60))
                self._dur_var.set(float(max(30, min(saved, 60))))
                self._on_dur_slider()
            if hasattr(self, "_dur_range_lbl"):
                self._dur_range_lbl.configure(text="30 – 60 sec")
        else:
            self._short_card.configure(border_width=1, border_color=BORDER, fg_color=BG_CARD)
            self._long_card.configure(border_width=2, border_color=ACCENT_DOC, fg_color="#100820")
            # Reconfigure slider for 180–2400 s (3–40 min)
            if hasattr(self, "_dur_slider"):
                self._dur_slider.configure(from_=180, to=2400, number_of_steps=222)
                saved = int(config.get("documentary.long_duration", 600))
                self._dur_var.set(float(max(180, min(saved, 2400))))
                self._on_dur_slider()
            if hasattr(self, "_dur_range_lbl"):
                self._dur_range_lbl.configure(text="3 – 40 min")

    # ── Topic ─────────────────────────────────────────────────────────────────
    def _build_topic_row(self):
        frame = ctk.CTkFrame(self._body, fg_color=BG_SEC, corner_radius=0,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=(0, 10))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=14)

        ctk.CTkLabel(inner, text="📡  DOCUMENTARY SUBJECT:",
                     font=("Share Tech Mono", 14), text_color=ACCENT_DOC,
                     ).pack(side="left")

        self._topic_entry = ctk.CTkEntry(
            inner,
            placeholder_text="Enter topic  — or leave blank for auto-trending",
            width=480, font=("Share Tech Mono", 13),
            fg_color=BG_MAIN, border_color=ACCENT_DOC,
            text_color=TEXT_PRI, corner_radius=0, border_width=1,
        )
        self._topic_entry.pack(side="left", padx=15)
        self._topic_entry.bind("<FocusIn>",  lambda e: self._topic_entry.configure(border_width=2))
        self._topic_entry.bind("<FocusOut>", lambda e: self._topic_entry.configure(border_width=1))

        self._auto_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            inner, text="AUTO-SELECT",
            variable=self._auto_var,
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC,
            fg_color=BG_MAIN, border_color=ACCENT_DOC,
            hover_color=BG_CARD, checkmark_color=ACCENT_DOC, corner_radius=0,
            command=self._toggle_auto,
        ).pack(side="left", padx=10)

    def _toggle_auto(self):
        if self._auto_var.get():
            self._topic_entry.configure(state="disabled")
        else:
            self._topic_entry.configure(state="normal")

    # ── Duration ──────────────────────────────────────────────────────────────
    def _build_duration_row(self):
        frame = ctk.CTkFrame(self._body, fg_color=BG_SEC, corner_radius=0,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=(0, 10))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(inner, text="⏱  DURATION:",
                     font=("Share Tech Mono", 14), text_color=ACCENT_DOC,
                     ).pack(side="left")

        self._dur_range_lbl = ctk.CTkLabel(
            inner, text="30 – 60 sec",
            font=("Share Tech Mono", 11), text_color=TEXT_SEC, width=90,
        )
        self._dur_range_lbl.pack(side="left", padx=(8, 0))

        self._dur_var = tk.DoubleVar(value=60.0)
        self._dur_slider = ctk.CTkSlider(
            inner, from_=30, to=60, number_of_steps=30,
            variable=self._dur_var, width=400,
            fg_color=BORDER, progress_color=ACCENT_DOC,
            button_color=ACCENT_DOC, button_hover_color=ACCENT_PRI,
            command=self._on_dur_slider,
        )
        self._dur_slider.pack(side="left", padx=12, fill="x", expand=True)

        self._dur_lbl = ctk.CTkLabel(
            inner, text="60s", width=72,
            font=("Share Tech Mono", 13, "bold"), text_color=ACCENT_DOC,
        )
        self._dur_lbl.pack(side="left")

    def _on_dur_slider(self, _=None):
        v = int(self._dur_var.get())
        if self._doc_mode == "short":
            config.set("documentary.short_duration", v)
            self._dur_lbl.configure(text=f"{v}s")
        else:
            mins = v // 60
            secs = v % 60
            config.set("documentary.long_duration", v)
            label = f"{mins}m" if secs == 0 else f"{mins}m {secs}s"
            self._dur_lbl.configure(text=label)

    # ── Language ──────────────────────────────────────────────────────────────
    def _build_language_row(self):
        frame = ctk.CTkFrame(self._body, fg_color=BG_SEC, corner_radius=0,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=(0, 10))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(inner, text="🌐  NARRATION LANGUAGE:",
                     font=("Share Tech Mono", 14), text_color=ACCENT_DOC,
                     ).pack(side="left")

        self._lang_btns: dict[str, ctk.CTkButton] = {}
        _langs = [
            ("hi",       "🇮🇳 Hindi"),
            ("hinglish", "🔀 Hinglish"),
            ("en",       "🇬🇧 English"),
            ("mr",       "🟠 Marathi"),
        ]
        cur_lang = config.get("pipeline.language", "hi")
        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(side="left", padx=12)
        for code, label in _langs:
            sel = (code == cur_lang)
            btn = ctk.CTkButton(
                btn_row, text=label, width=110,
                font=("Share Tech Mono", 11, "bold"),
                fg_color=ACCENT_DOC if sel else "transparent",
                text_color=BG_MAIN if sel else TEXT_SEC,
                border_color=ACCENT_DOC if sel else BORDER,
                border_width=1, corner_radius=0,
                command=lambda c=code: self._select_lang(c),
            )
            btn.pack(side="left", padx=3)
            self._lang_btns[code] = btn

    def _select_lang(self, code: str) -> None:
        config.set("pipeline.language", code)
        for c, btn in self._lang_btns.items():
            if c == code:
                btn.configure(fg_color=ACCENT_DOC, text_color=BG_MAIN, border_color=ACCENT_DOC)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SEC, border_color=BORDER)

    # ── Voice Engine ──────────────────────────────────────────────────────────
    def _build_voice_engine_row(self):
        frame = ctk.CTkFrame(self._body, fg_color=BG_SEC, corner_radius=0,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=(0, 10))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(inner, text="🎙  VOICE ENGINE:",
                     font=("Share Tech Mono", 14), text_color=ACCENT_DOC,
                     ).pack(side="left")

        _engines = [
            ("omnivoice",  "🔊 OmniVoice",  "Local AI — zero-shot voice clone/design"),
            ("elevenlabs", "⚡ ElevenLabs",  "Cloud — ultra-realistic (API key required)"),
            ("edge_tts",   "🆓 Edge TTS",    "Free Microsoft neural TTS"),
        ]
        cur = config.get("documentary.voice_backend",
                         config.get("tts.backend", "omnivoice"))

        self._voice_btns: dict[str, ctk.CTkButton] = {}
        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(side="left", padx=12)

        for code, label, _ in _engines:
            sel = (code == cur)
            btn = ctk.CTkButton(
                btn_row, text=label, width=130,
                font=("Share Tech Mono", 11, "bold"),
                fg_color=ACCENT_DOC if sel else "transparent",
                text_color=BG_MAIN if sel else TEXT_SEC,
                border_color=ACCENT_DOC if sel else BORDER,
                border_width=1, corner_radius=0,
                command=lambda c=code: self._select_voice(c),
            )
            btn.pack(side="left", padx=3)
            self._voice_btns[code] = btn

        self._voice_hint = ctk.CTkLabel(
            inner,
            text=next((h for c, _, h in _engines if c == cur), ""),
            font=("Share Tech Mono", 11), text_color=TEXT_SEC,
        )
        self._voice_hint.pack(side="left", padx=12)

        self._voice_hints = {c: h for c, _, h in _engines}

    def _select_voice(self, code: str) -> None:
        config.set("documentary.voice_backend", code)
        for c, btn in self._voice_btns.items():
            if c == code:
                btn.configure(fg_color=ACCENT_DOC, text_color=BG_MAIN, border_color=ACCENT_DOC)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SEC, border_color=BORDER)
        self._voice_hint.configure(text=self._voice_hints.get(code, ""))

    # ── Footage Settings ──────────────────────────────────────────────────────
    def _build_footage_settings(self):
        frame = ctk.CTkFrame(self._body, fg_color=BG_SEC, corner_radius=0,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=(0, 10))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(inner, text="🎥  FOOTAGE SETTINGS:",
                     font=("Share Tech Mono", 14, "bold"), text_color=ACCENT_DOC,
                     ).pack(anchor="w")

        row1 = ctk.CTkFrame(inner, fg_color="transparent")
        row1.pack(fill="x", pady=(8, 0))

        # Clip count (number of segments)
        ctk.CTkLabel(row1, text="Clips:",
                     font=("Share Tech Mono", 12), text_color=TEXT_SEC,
                     ).pack(side="left")

        saved_segs = int(config.get("documentary.segments", 0) or 0)
        self._seg_var = tk.StringVar(
            value=str(saved_segs) if saved_segs > 0 else "Auto"
        )
        ctk.CTkOptionMenu(
            row1,
            values=[
                "Auto", "3", "5", "7", "10", "15", "20", "25", "30", "40", "50",
                "60", "70", "80", "90", "100",
            ],
            variable=self._seg_var,
            width=80,
            font=("Share Tech Mono", 12),
            fg_color=BG_MAIN, button_color=ACCENT_DOC,
            button_hover_color=ACCENT_PRI, text_color=TEXT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI,
            dropdown_hover_color=BG_MAIN, corner_radius=0,
            command=self._save_segments,
        ).pack(side="left", padx=(8, 20))

        # Max clip duration
        ctk.CTkLabel(row1, text="Max clip dur:",
                     font=("Share Tech Mono", 12), text_color=TEXT_SEC,
                     ).pack(side="left")

        self._clip_dur_var = tk.StringVar(
            value=str(int(config.get("documentary.max_clip_duration", 120)))
        )
        ctk.CTkOptionMenu(
            row1,
            values=["30", "60", "90", "120", "180", "300"],
            variable=self._clip_dur_var,
            width=90,
            font=("Share Tech Mono", 12),
            fg_color=BG_MAIN, button_color=ACCENT_DOC,
            button_hover_color=ACCENT_PRI, text_color=TEXT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI,
            dropdown_hover_color=BG_MAIN, corner_radius=0,
            command=self._save_clip_dur,
        ).pack(side="left", padx=(8, 20))
        ctk.CTkLabel(row1, text="s",
                     font=("Share Tech Mono", 11), text_color=TEXT_SEC,
                     ).pack(side="left")

        row2 = ctk.CTkFrame(inner, fg_color="transparent")
        row2.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(
            row2,
            text="Output aspect: change in Settings → [ Video format & effects ] — "
            "Pexels uses portrait (9:16) or landscape (16:9) to match. Current:",
            font=("Share Tech Mono", 11), text_color=TEXT_SEC, justify="left", anchor="w",
            wraplength=900,
        ).pack(anchor="w")
        self._doc_aspect_lbl = ctk.CTkLabel(
            row2,
            text="",
            font=("Share Tech Mono", 12, "bold"), text_color=ACCENT_DOC, anchor="w",
        )
        self._doc_aspect_lbl.pack(anchor="w", pady=(2, 0))
        self._refresh_doc_aspect_lbl()

    def _save_segments(self, val: str) -> None:
        try:
            config.set("documentary.segments", 0 if val == "Auto" else int(val))
        except ValueError:
            pass

    def _save_clip_dur(self, val: str) -> None:
        try:
            config.set("documentary.max_clip_duration", int(val))
        except ValueError:
            pass

    def _refresh_doc_aspect_lbl(self) -> None:
        if not hasattr(self, "_doc_aspect_lbl"):
            return
        ar = str(config.get("aspect_ratio", "9:16"))
        orient = "portrait" if ar == "9:16" else "landscape"
        self._doc_aspect_lbl.configure(
            text=f"  →  {ar}  (Pexels: {orient})"
        )

    # ── Controls ──────────────────────────────────────────────────────────────
    def _build_control_row(self):
        frame = ctk.CTkFrame(self._body, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=10)

        self._run_btn = ctk.CTkButton(
            frame, text="▶  ROLL FILM",
            font=("Orbitron", 14, "bold"), text_color=ACCENT_DOC,
            fg_color="#100820", hover_color=ACCENT_DOC,
            border_color=ACCENT_DOC, border_width=1, corner_radius=0,
            height=50, width=220,
            command=self._on_run,
        )
        self._run_btn.pack(side="left")

        self._stop_btn = ctk.CTkButton(
            frame, text="✂  CUT",
            font=("Orbitron", 14, "bold"), text_color=ACCENT_RED,
            fg_color="#330000", hover_color=ACCENT_RED,
            border_color=ACCENT_RED, border_width=1, corner_radius=0,
            height=50, width=150, state="disabled",
            command=self._on_stop,
        )
        self._stop_btn.pack(side="left", padx=15)

        self._status_lbl = ctk.CTkLabel(
            frame, text="",
            font=("Share Tech Mono", 12), text_color=TEXT_SEC,
        )
        self._status_lbl.pack(side="left", padx=15)

    # ── Progress ──────────────────────────────────────────────────────────────
    def _build_progress_section(self):
        frame = ctk.CTkFrame(self._body, fg_color=BG_SEC, corner_radius=0,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=10)

        self.steps_canvas = tk.Canvas(frame, bg=BG_SEC, height=80, highlightthickness=0)
        self.steps_canvas.pack(fill="x", padx=20, pady=(20, 0))

        bar_frame = ctk.CTkFrame(frame, fg_color="transparent")
        bar_frame.pack(fill="x", padx=20, pady=(10, 20))

        self.prog_canvas = tk.Canvas(
            bar_frame, bg=BG_MAIN, height=16,
            highlightthickness=1, highlightbackground=ACCENT_DOC,
        )
        self.prog_canvas.pack(side="left", fill="x", expand=True, padx=(0, 15))

        self._progress_pct = ctk.CTkLabel(
            bar_frame, text="0%",
            font=("Orbitron", 16, "bold"), text_color=ACCENT_DOC, width=50,
        )
        self._progress_pct.pack(side="right")

        self.bind("<Configure>", self._redraw_steps_and_bar)

    def _draw_hexagon(self, canvas, x, y, r, outline, fill="", tags=""):
        pts = []
        for i in range(6):
            ang = math.pi / 180 * (60 * i - 30)
            pts += [x + r * math.cos(ang), y + r * math.sin(ang)]
        return canvas.create_polygon(pts, outline=outline, fill=fill, width=2, tags=tags)

    def _redraw_steps_and_bar(self, event=None):
        w = self.steps_canvas.winfo_width()
        if w < 50:
            return
        self.steps_canvas.delete("all")

        n = len(DOC_STEPS)
        spacing = w / n
        r = 16
        self._hex_centers = []

        for i in range(n):
            cx = spacing * i + spacing / 2
            cy = 30
            self._hex_centers.append((cx, cy))
            state = self._step_states[i]

            if state == "pending":
                self._draw_hexagon(self.steps_canvas, cx, cy, r, BORDER, BG_MAIN)
            elif state == "active":
                self._draw_hexagon(self.steps_canvas, cx, cy, r, ACCENT_DOC, BG_MAIN)
            elif state == "done":
                self._draw_hexagon(self.steps_canvas, cx, cy, r, ACCENT_DOC, ACCENT_DOC)
                self.steps_canvas.create_text(cx, cy, text="✓", fill=BG_MAIN,
                                              font=("Courier New", 12, "bold"))
            elif state == "error":
                self._draw_hexagon(self.steps_canvas, cx, cy, r, ACCENT_RED, ACCENT_RED)
                self.steps_canvas.create_text(cx, cy, text="✗", fill=BG_MAIN,
                                              font=("Courier New", 12, "bold"))

            col = ACCENT_DOC if state != "pending" else TEXT_SEC
            self.steps_canvas.create_text(
                cx, cy + 30, text=DOC_STEPS[i].upper(), fill=col,
                font=("Share Tech Mono", 10, "bold"),
            )
            if i < n - 1:
                nx = spacing * (i + 1) + spacing / 2
                dc = ACCENT_DOC if state in ("done", "active") else BORDER
                self.steps_canvas.create_line(
                    cx + r + 5, cy, nx - r - 5, cy,
                    fill=dc, width=2, dash=(4, 4),
                )

        self._redraw_progress_bar()

    def _redraw_progress_bar(self):
        w = self.prog_canvas.winfo_width()
        h = self.prog_canvas.winfo_height()
        if w < 10:
            return
        self.prog_canvas.delete("bar")
        fw = w * self._progress_val
        if fw > 0:
            segs = 20
            sw = fw / segs
            for i in range(segs):
                ratio = i / (segs - 1) if segs > 1 else 0
                # Purple → Blue gradient
                r_ = int(0xB0 * (1 - ratio) + 0x00 * ratio)
                g_ = int(0x60 * (1 - ratio) + 0x88 * ratio)
                b_ = int(0xFF * 1)
                col = f"#{r_:02x}{g_:02x}{b_:02x}"
                self.prog_canvas.create_rectangle(
                    i * sw, 0, (i + 1) * sw, h, fill=col, outline="", tags="bar",
                )

    # ── Log ───────────────────────────────────────────────────────────────────
    def _build_log_section(self):
        frame = ctk.CTkFrame(self._body, fg_color=BG_SEC, corner_radius=0,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(frame, text="[ CINEMA TERMINAL ] ▋",
                     font=("Share Tech Mono", 14, "bold"), text_color=ACCENT_DOC,
                     ).pack(anchor="w", padx=20, pady=(15, 5))

        self._log_box = ctk.CTkTextbox(
            frame, font=("Consolas", 12),
            fg_color="#020608", border_color=BORDER, border_width=1,
            corner_radius=0, state="disabled", height=240,
        )
        self._log_box.pack(fill="x", padx=15, pady=(0, 15))
        self._log_box.tag_config("INFO",    foreground=TEXT_SEC)
        self._log_box.tag_config("SUCCESS", foreground=ACCENT_DOC)
        self._log_box.tag_config("ERROR",   foreground=ACCENT_RED)
        self._log_box.tag_config("WARNING", foreground=ACCENT_WARN)

    # ── Output preview ────────────────────────────────────────────────────────
    def _build_output_preview(self):
        self._output_frame = ctk.CTkFrame(
            self._body, fg_color=BG_CARD, corner_radius=0,
            border_color=ACCENT_DOC, border_width=1,
        )
        self._output_label = ctk.CTkLabel(
            self._output_frame, text="",
            font=("Share Tech Mono", 14, "bold"), text_color=ACCENT_DOC,
        )
        self._output_label.pack(padx=20, pady=(15, 5))
        ctk.CTkButton(
            self._output_frame, text="▶▶  OPEN OUTPUT FOLDER",
            font=("Orbitron", 12, "bold"), text_color=BG_MAIN,
            fg_color=ACCENT_DOC, hover_color=ACCENT_PRI, corner_radius=0,
            command=self._open_output_folder,
        ).pack(padx=20, pady=(5, 15))

    def _open_output_folder(self):
        out_dir = config.get("pipeline.output_folder", "output")
        full_path = Path(config.path).parent / out_dir
        if full_path.exists():
            subprocess.Popen(["explorer", str(full_path)])

    # ── Run / Stop ────────────────────────────────────────────────────────────
    def _on_run(self):
        if self.pipeline_running:
            return
        self._refresh_doc_aspect_lbl()

        topic = self._topic_entry.get().strip() if not self._auto_var.get() else None

        # Set documentary config
        config.set("pipeline_mode", "documentary")
        config.set("documentary.length_mode", self._doc_mode)

        dur = int(self._dur_var.get())
        config.set("target_duration", dur)

        # Apply selected voice backend for this run
        voice_backend = config.get("documentary.voice_backend",
                                   config.get("tts.backend", "omnivoice"))
        config.set("tts.backend", voice_backend)

        self._reset_steps()
        ar = str(config.get("aspect_ratio", "9:16"))
        self._append_log(
            f"🎬 Documentary pipeline started — mode={self._doc_mode}, "
            f"duration={dur}s, aspect={ar}",
            "INFO",
        )

        self.pipeline_running = True
        self._pipeline_run_id += 1
        self._run_btn.configure(state="disabled", text="⏳  FILMING…")
        self._stop_btn.configure(state="normal")
        self._status_lbl.configure(text="● FILMING", text_color=ACCENT_DOC)
        if self.app_ref:
            self.app_ref.set_system_state("PROCESSING")

        from core.pipeline_runner import PipelineRunner
        self.runner = PipelineRunner(self.progress_queue, run_id=self._pipeline_run_id)
        self.runner.start(topic=topic)

        # Start polling loops for interactive review windows
        self.after(500, self._check_for_script_review)
        self.after(500, self._check_for_video_preview)

    def _on_stop(self):
        if self.runner:
            self.runner.stop()
        self.pipeline_running = False
        self._run_btn.configure(state="normal", text="▶  ROLL FILM")
        self._stop_btn.configure(state="disabled")
        self._status_lbl.configure(text="ABORTED", text_color=ACCENT_RED)
        if self.app_ref:
            self.app_ref.set_system_state("READY")
        self._append_log("Pipeline stopped by user.", "WARNING")

    # ── Script Review ─────────────────────────────────────────────────────────
    def _check_for_script_review(self):
        if not self.pipeline_running:
            return
        if self.runner and getattr(self.runner, "waiting_for_script_review", False):
            self._show_script_review_window()
            return
        self.after(500, self._check_for_script_review)

    def _show_script_review_window(self):
        from gui.components.script_review import ScriptReviewWindow

        script_data = self.runner.pending_script_data
        if not script_data:
            self.after(500, self._check_for_script_review)
            return

        def on_approve(approved_data):
            self.runner.approve_script(approved_data)
            self._append_log("[OK] Script approved ✓ — continuing documentary …", "SUCCESS")
            self.after(500, self._check_for_script_review)

        def on_regenerate():
            self.runner.cancel_pipeline_from_review()
            self._append_log("[INFO] Regenerating script …", "INFO")
            # Re-run with same topic (cleared from entry)
            self.after(400, self._on_run)

        def on_cancel():
            self.runner.cancel_pipeline_from_review()
            self._on_stop()

        ScriptReviewWindow(self.winfo_toplevel(), script_data, on_approve, on_regenerate, on_cancel)

    # ── Video Preview ─────────────────────────────────────────────────────────
    def _check_for_video_preview(self):
        if not self.pipeline_running:
            return
        if self.runner and getattr(self.runner, "waiting_for_video_preview", False):
            self._show_video_preview_window()
            return
        self.after(500, self._check_for_video_preview)

    def _show_video_preview_window(self):
        from gui.components.video_preview import VideoPreviewWindow

        video_path = self.runner.pending_video_path
        if not video_path:
            self.runner.approve_video_preview()
            return

        def on_approve():
            self.runner.approve_video_preview()
            self._append_log("[OK] Video approved ✓ — continuing …", "SUCCESS")
            self.after(500, self._check_for_video_preview)

        def on_cancel():
            self.runner.cancel_from_video_preview()
            self._on_stop()

        VideoPreviewWindow(self.winfo_toplevel(), video_path, on_approve, on_cancel)

    # ── Queue polling ─────────────────────────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                msg = self.progress_queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.after(100, _poll_queue_wrapper, self)

    def _handle_message(self, msg: dict):
        rid = msg.get("run_id")
        if rid is not None and rid != self._pipeline_run_id:
            return

        step    = msg.get("step", 0)
        message = msg.get("message", "")
        level   = msg.get("level", "INFO")
        done    = msg.get("done", False)
        output  = msg.get("output_path", "")

        prefix = {"SUCCESS": "[OK] ", "ERROR": "[ERR] ", "WARNING": "[WARN] "}.get(level, "")
        self._append_log(prefix + message, level)

        if 1 <= step <= 6:
            for i in range(step - 1):
                self._step_states[i] = "done"
            if level == "ERROR":
                self._step_states[step - 1] = "error"
            elif level == "SUCCESS":
                self._step_states[step - 1] = "done"
            else:
                self._step_states[step - 1] = "active"
            self._progress_val = (step - 1 + 0.5) / 6
            self._progress_pct.configure(text=f"{int(self._progress_val * 100)}%")
            self._redraw_steps_and_bar()

        if done:
            self._on_pipeline_done(level, message, output)

    def _on_pipeline_done(self, level: str, message: str, output: str):
        self.pipeline_running = False
        self._run_btn.configure(state="normal", text="▶  ROLL FILM")
        self._stop_btn.configure(state="disabled")

        if level == "SUCCESS":
            for i in range(6):
                self._step_states[i] = "done"
            self._progress_val = 1.0
            self._progress_pct.configure(text="100%")
            self._status_lbl.configure(text="COMPLETE ✓", text_color=ACCENT_DOC)
            if output:
                self._output_label.configure(
                    text=f"🎬 Documentary: {Path(output).name}"
                )
                self._output_frame.pack(fill="x", padx=20, pady=10)
            if self.app_ref:
                self.app_ref.set_system_state("READY")
        else:
            self._status_lbl.configure(text="ERROR ✗", text_color=ACCENT_RED)
            if self.app_ref:
                self.app_ref.set_system_state("ERROR")

        self._redraw_steps_and_bar()

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _reset_steps(self):
        self._step_states = ["pending"] * 6
        self._progress_val = 0.0
        self._progress_pct.configure(text="0%")
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self._output_frame.pack_forget()
        self._redraw_steps_and_bar()

    def _append_log(self, text: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}\n"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line, level)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def update_uplink_status(self, name: str):
        self._uplink_lbl.configure(text=f"UPLINK: [{name}]")
