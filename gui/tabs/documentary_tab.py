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
import re
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
TEXT_HINT   = "#4A6080"

# Documentary-specific accent
ACCENT_DOC  = "#B060FF"   # purple-ish — distinct from normal pipeline blue

# Step labels for documentary mode
DOC_STEPS = ["Research", "Script", "Voice", "Footage", "Assembly", "Upload"]

_WORKSHOP_STYLE_OPTS = ("cinematic", "shocking", "educational", "inspirational", "fun")
_WORKSHOP_TONE_OPTS = ("energetic", "calm", "dramatic", "casual", "authoritative")


def _coerce_workshop_format(s: str) -> str:
    t = (s or "long").lower()
    if re.search(r"\bshort\b", t) or "under 60" in t or "60 second" in t or "60s" in t or "under a minute" in t:
        return "short"
    return "long"


def _coerce_workshop_style(s: str) -> str:
    t = (s or "").lower()
    for o in _WORKSHOP_STYLE_OPTS:
        if o in t:
            return o
    return "cinematic"


def _coerce_workshop_tone(s: str) -> str:
    t = (s or "").lower()
    for o in _WORKSHOP_TONE_OPTS:
        if o in t:
            return o
    return "authoritative"


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
        self._build_idea_workshop()
        self._build_topic_row()
        self._build_duration_row()
        self._build_voice_engine_row()
        self._build_footage_settings()
        self._build_control_row()
        self._build_progress_section()
        self._build_log_section()
        self._build_ai_error_panel()     # ← AI error analyst panel
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
        ctk.CTkLabel(li, text="3 min – 2 hours",
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
            # 30 – 60 s
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
            # 180 – 7200 s  (3 min – 2 hours), steps of 60 s = 117 steps
            if hasattr(self, "_dur_slider"):
                self._dur_slider.configure(from_=180, to=7200, number_of_steps=117)
                saved = int(config.get("documentary.long_duration", 600))
                self._dur_var.set(float(max(180, min(saved, 7200))))
                self._on_dur_slider()
            if hasattr(self, "_dur_range_lbl"):
                self._dur_range_lbl.configure(text="3 min – 2 hrs")
        if hasattr(self, "_refresh_burn_subs_state"):
            self._refresh_burn_subs_state()

    # ── Idea Workshop ─────────────────────────────────────────────────────────
    def _build_idea_workshop(self):
        """Collapsible Ghost AI brainstorm chat — unlimited conversational sessions."""
        self._workshop_open      = False
        self._chat_history: list[dict] = []
        self._workshop_turns     = 0          # total turns this session
        self._workshop_thinking  = False
        self._workshop_dot_cycle = 0

        # ── Outer container ───────────────────────────────────────────────────
        outer = ctk.CTkFrame(
            self._body,
            fg_color="#060C16",
            corner_radius=6,
            border_width=2,
            border_color="#3A1880",
        )
        outer.pack(fill="x", padx=20, pady=(0, 8))

        # ── Toggle header ────────────────────────────────────────────────────
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=8)

        self._workshop_toggle_btn = ctk.CTkButton(
            header,
            text="▶  [ GHOST AI ]  —  Idea Workshop  •  Chat with your AI director",
            font=("Share Tech Mono", 12, "bold"),
            text_color="#C090FF", fg_color="transparent",
            hover_color="#0F0A20", anchor="w",
            corner_radius=4, height=32,
            command=self._toggle_workshop,
        )
        self._workshop_toggle_btn.pack(side="left", fill="x", expand=True)

        # Status badge (right side of header)
        badge_frame = ctk.CTkFrame(header, fg_color="#0A0520", corner_radius=4,
                                   border_width=1, border_color="#5030A0")
        badge_frame.pack(side="right", padx=(8, 0))
        ctk.CTkLabel(badge_frame, text="⬡ GHOST AI", font=("Share Tech Mono", 10, "bold"),
                     text_color="#B080FF").pack(side="left", padx=(8, 4), pady=3)
        self._workshop_status_dot = ctk.CTkLabel(
            badge_frame, text="●", font=("Share Tech Mono", 10), text_color="#00FF88")
        self._workshop_status_dot.pack(side="left", padx=(0, 4), pady=3)
        self._workshop_status_lbl = ctk.CTkLabel(
            badge_frame, text="ONLINE", font=("Share Tech Mono", 9), text_color="#00CC66")
        self._workshop_status_lbl.pack(side="left", padx=(0, 8), pady=3)

        # ── Collapsible body ─────────────────────────────────────────────────
        self._workshop_body = ctk.CTkFrame(outer, fg_color="transparent")

        # Session meta row
        meta_row = ctk.CTkFrame(self._workshop_body, fg_color="transparent")
        meta_row.pack(fill="x", padx=14, pady=(4, 0))
        self._workshop_turns_lbl = ctk.CTkLabel(
            meta_row,
            text="Session: 0 turns  •  ∞ unlimited",
            font=("Share Tech Mono", 9), text_color="#3A3A6A",
        )
        self._workshop_turns_lbl.pack(side="left")
        ctk.CTkLabel(meta_row, text="↵ Enter to send  •  ⚡ to create now",
                     font=("Share Tech Mono", 9), text_color="#3A3A6A").pack(side="right")

        # Chat log
        self._workshop_log = ctk.CTkTextbox(
            self._workshop_body,
            font=("Consolas", 12),
            fg_color="#030811",
            border_color="#2A1060", border_width=1,
            corner_radius=4, state="disabled", height=380,
            wrap="word",
        )
        self._workshop_log.pack(fill="x", padx=14, pady=(6, 0))

        # Text tags for different message types
        self._workshop_log.tag_config("user_hdr",  foreground="#5090FF")
        self._workshop_log.tag_config("user_body", foreground="#B0CCFF")
        self._workshop_log.tag_config("ai_hdr",    foreground="#C090FF")
        self._workshop_log.tag_config("ai_body",   foreground="#DDD0FF")
        self._workshop_log.tag_config("sys_hdr",   foreground="#00CC88")
        self._workshop_log.tag_config("sys_body",  foreground="#88EEC8")
        self._workshop_log.tag_config("plan_hdr",  foreground="#FFD700")
        self._workshop_log.tag_config("plan_body", foreground="#FFE870")
        self._workshop_log.tag_config("sep",       foreground="#1C1040")
        self._workshop_log.tag_config("hint",      foreground="#3A4A6A")

        # Isolate scroll
        def _chat_scroll(event):
            self._workshop_log._textbox.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        self.after(100, lambda: self._workshop_log._textbox.bind("<MouseWheel>", _chat_scroll))

        # Thinking indicator
        self._workshop_thinking_lbl = ctk.CTkLabel(
            self._workshop_body,
            text="",
            font=("Share Tech Mono", 10), text_color="#8040FF", anchor="w",
        )
        self._workshop_thinking_lbl.pack(anchor="w", padx=16, pady=(2, 0))

        # Input row
        input_row = ctk.CTkFrame(self._workshop_body, fg_color="transparent")
        input_row.pack(fill="x", padx=14, pady=(6, 4))

        self._workshop_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="Talk to Ghost AI — describe your idea, ask questions, refine…",
            font=("Share Tech Mono", 12),
            fg_color="#070F1A",
            border_color="#5030A0", border_width=1,
            text_color="#E0D8FF", corner_radius=4,
            height=38,
        )
        self._workshop_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._workshop_entry.bind("<Return>", lambda e: self._workshop_send())

        self._workshop_send_btn = ctk.CTkButton(
            input_row, text="SEND  ↵",
            font=("Share Tech Mono", 12, "bold"),
            text_color="#FFFFFF", fg_color="#4020A0",
            hover_color="#6040C0", corner_radius=4, width=100, height=38,
            command=self._workshop_send,
        )
        self._workshop_send_btn.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            input_row, text="⚡ CREATE NOW",
            font=("Share Tech Mono", 11, "bold"),
            text_color="#050A10", fg_color="#FFB800",
            hover_color="#CC9200", corner_radius=4, width=130, height=38,
            command=self._workshop_generate_now,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            input_row, text="⟳ New",
            font=("Share Tech Mono", 10),
            text_color="#5560A0", fg_color="transparent",
            hover_color="#0F0A20", border_color="#2A1060", border_width=1,
            corner_radius=4, width=58, height=38,
            command=self._workshop_clear,
        ).pack(side="left")

        # "Use topic" row (hidden until AI suggests one)
        self._use_topic_frame = ctk.CTkFrame(
            self._workshop_body, fg_color="#080316",
            border_width=1, border_color="#2A6040", corner_radius=4)
        self._suggested_topic_lbl = ctk.CTkLabel(
            self._use_topic_frame, text="",
            font=("Share Tech Mono", 11, "bold"), text_color="#00FF99", anchor="w",
        )
        self._suggested_topic_lbl.pack(side="left", padx=(12, 10), fill="x", expand=True)
        ctk.CTkButton(
            self._use_topic_frame, text="▶  USE THIS TOPIC",
            font=("Share Tech Mono", 11, "bold"),
            text_color="#050A10", fg_color="#00CC88",
            hover_color="#009966",
            corner_radius=4, width=160, height=32,
            command=self._use_suggested_topic,
        ).pack(side="right", padx=10, pady=6)

        # Initial greeting
        self._workshop_append(
            "ghost_ai",
            "I'm Ghost AI — your personal documentary director.\n\n"
            "Tell me what you want to create. We can have a full conversation: refine the "
            "topic, decide style, tone, and length together. No rush.\n\n"
            "When you're ready to create, just say  go / banao / start / create  — or click "
            "⚡ CREATE NOW anytime.",
            "ai",
        )

    def _toggle_workshop(self):
        if self._workshop_open:
            self._workshop_body.pack_forget()
            self._workshop_open = False
            self._workshop_toggle_btn.configure(
                text="▶  [ GHOST AI ]  —  Idea Workshop  •  Chat with your AI director"
            )
        else:
            self._workshop_body.pack(fill="x")
            self._workshop_open = True
            self._workshop_toggle_btn.configure(
                text="▼  [ GHOST AI ]  —  Idea Workshop  •  Chat with your AI director"
            )
            self._workshop_entry.focus()

    def _workshop_append(self, who: str, text: str, kind: str = "ai"):
        """Append a styled message bubble to the chat log."""
        from datetime import datetime as _dt
        ts = _dt.now().strftime("%H:%M")
        log = self._workshop_log
        log.configure(state="normal")

        if kind == "user":
            hdr  = f"  ╭─── YOU  {ts} ───────────────────────────────────╮\n"
            body = "\n".join(f"  │  {ln}" for ln in text.splitlines()) + "\n"
            foot = "  ╰────────────────────────────────────────────────╯\n\n"
            log.insert("end", hdr,  "user_hdr")
            log.insert("end", body, "user_body")
            log.insert("end", foot, "user_hdr")
        elif kind == "ai":
            hdr  = f"⬡ GHOST AI  {ts} ───────────────────────────────────\n"
            body = "\n".join(f"  {ln}" for ln in text.splitlines()) + "\n"
            foot = "────────────────────────────────────────────────────\n\n"
            log.insert("end", hdr,  "ai_hdr")
            log.insert("end", body, "ai_body")
            log.insert("end", foot, "sep")
        elif kind == "plan":
            hdr  = f"★ PLAN CONFIRMED  {ts} ─────────────────────────────\n"
            body = "\n".join(f"  {ln}" for ln in text.splitlines()) + "\n"
            foot = "════════════════════════════════════════════════════\n\n"
            log.insert("end", hdr,  "plan_hdr")
            log.insert("end", body, "plan_body")
            log.insert("end", foot, "plan_hdr")
        else:  # system / hint
            hdr  = f"◈ SYSTEM  {ts}\n"
            body = "\n".join(f"  {ln}" for ln in text.splitlines()) + "\n\n"
            log.insert("end", hdr,  "sys_hdr")
            log.insert("end", body, "sys_body")

        log.see("end")
        log.configure(state="disabled")

    # ── START-INTENT keywords (any match → smart auto-start) ─────────────────
    _START_PHRASES = (
        "start", "generate", "create", "make it", "make the video",
        "banao", "bana do", "chalo banao", "bhai banao", "lo banao",
        "okay go", "ok go", "let's go", "ab banao", "chalao",
        "shuru karo", "video banao", "go ahead", "create now",
        "begin", "start now", "roll film", "produce it",
    )

    def _user_wants_to_start(self, msg: str) -> bool:
        """Return True if the user's message clearly signals 'start creating'."""
        lower = msg.lower().strip()
        return any(ph in lower for ph in self._START_PHRASES)

    def _workshop_set_thinking(self, thinking: bool):
        self._workshop_thinking = thinking
        if thinking:
            self._workshop_status_dot.configure(text_color="#FFB800")
            self._workshop_status_lbl.configure(text="THINKING", text_color="#FFB800")
            self._workshop_send_btn.configure(state="disabled", text="…")
            self._workshop_thinking_lbl.configure(text="  Ghost AI is thinking  ●")
            self._animate_thinking_dots()
        else:
            self._workshop_status_dot.configure(text_color="#00FF88")
            self._workshop_status_lbl.configure(text="ONLINE", text_color="#00CC66")
            self._workshop_send_btn.configure(state="normal", text="SEND  ↵")
            self._workshop_thinking_lbl.configure(text="")

    def _animate_thinking_dots(self):
        if not self._workshop_thinking:
            return
        dots = ["  ●   ", "  ●●  ", "  ●●● ", "  ●●●●"]
        self._workshop_dot_cycle = (self._workshop_dot_cycle + 1) % len(dots)
        self._workshop_thinking_lbl.configure(
            text=f"  Ghost AI is thinking {dots[self._workshop_dot_cycle]}")
        self.after(400, self._animate_thinking_dots)

    def _workshop_send(self):
        msg = self._workshop_entry.get().strip()
        if not msg:
            return
        # If pipeline is already running, block
        if getattr(self, "pipeline_running", False):
            self._workshop_append("ghost_ai",
                "Pipeline is already running. Please wait for it to finish.", "system")
            return

        # Smart detection: if user explicitly says "start/banao/…" trigger immediately
        if self._user_wants_to_start(msg):
            self._workshop_append("you", msg, "user")
            self._workshop_entry.delete(0, "end")
            self._workshop_append("ghost_ai",
                "Got it! Starting video creation now…", "ai")
            self.after(500, self._workshop_generate_now)
            return

        # Normal chat flow
        self._workshop_append("you", msg, "user")
        self._workshop_entry.delete(0, "end")
        self._workshop_set_thinking(True)
        self._use_topic_frame.pack_forget()

        import threading
        threading.Thread(target=self._workshop_call_gemini, args=(msg,), daemon=True).start()

    def _workshop_call_gemini(self, user_msg: str):
        from modules.scripter import chat_with_consultant, parse_plan_block
        cfg = {
            "api_keys.gemini": config.get("api_keys.gemini", ""),
            "gemini_model":    config.get("gemini_model", "gemini-2.5-flash"),
        }
        # Send only last 30 turns to API for token efficiency, but keep full history
        api_history = self._chat_history[-30:] if len(self._chat_history) > 30 else self._chat_history
        reply = chat_with_consultant(api_history, user_msg, cfg)

        # Append to full history — unlimited, no trimming
        self._chat_history.append({"role": "user",  "text": user_msg})
        self._chat_history.append({"role": "model", "text": reply})

        # Check for finalized <<PLAN_START>>..<<PLAN_END>> block
        plan = parse_plan_block(reply)

        # Schedule GUI update on main thread
        self.after(0, self._workshop_on_reply, reply, plan)

    def _workshop_on_reply(self, reply: str, plan):
        self._workshop_turns += 1
        self._workshop_turns_lbl.configure(
            text=f"Session: {self._workshop_turns} turns  •  ∞ unlimited")

        # Strip raw plan block from display
        clean_reply = reply
        if plan and "<<PLAN_START>>" in reply:
            clean_reply = reply[:reply.index("<<PLAN_START>>")].strip()

        self._workshop_append("ghost_ai", clean_reply, "ai")
        self._workshop_set_thinking(False)

        if plan:
            self._last_plan = plan
            summary = (
                "✅  VIDEO PLAN CONFIRMED — STARTING CREATION\n\n"
                f"  TOPIC   :  {plan.get('topic', '')}\n"
                f"  STYLE   :  {plan.get('style', '')}\n"
                f"  FORMAT  :  {plan.get('format', '')}\n"
                f"  TONE    :  {plan.get('tone', '')}\n"
            )
            if plan.get("title"):
                summary += f"  TITLE   :  {plan['title']}\n"
            if plan.get("tags"):
                summary += f"  TAGS    :  {plan['tags']}"
            self._workshop_append("ghost_ai", summary, "plan")
            self._auto_apply_and_start(plan)

    def _auto_apply_and_start(self, plan: dict):
        """Apply agreed plan params and auto-start ROLL FILM with a 3s countdown."""
        topic  = plan.get("topic", "")
        fmt    = _coerce_workshop_format(plan.get("format", "long"))
        tone   = _coerce_workshop_tone(plan.get("tone", "authoritative"))
        style  = _coerce_workshop_style(plan.get("style", "cinematic"))

        # 1. Fill topic entry
        if topic:
            self._topic_entry.configure(state="normal")
            self._topic_entry.delete(0, "end")
            self._topic_entry.insert(0, topic)
            self._auto_var.set(False)

        # 2. Switch mode card (short/long)
        if fmt in ("short", "long"):
            self._apply_mode(fmt)

        # 3. Persist tone + style + metadata hints
        if tone:  config.set("documentary.voiceover_tone", tone)
        if style: config.set("documentary.video_style", style)
        if plan.get("title"): config.set("documentary.suggested_title", plan["title"])
        if plan.get("tags"):  config.set("documentary.suggested_tags",  plan["tags"])
        try:
            config.save()
        except OSError:
            pass

        # 4. Countdown then fire _on_run
        def _tick(n: int):
            if not self.pipeline_running:
                if n > 0:
                    self._workshop_append(
                        "ghost_ai",
                        f"🎬  Starting in {n}s …  (press ⏹ STOP to cancel)",
                        "plan",
                    )
                    self.after(1000, _tick, n - 1)
                else:
                    if self._workshop_open:
                        self._toggle_workshop()
                    self._on_run()

        _tick(3)

    def _use_suggested_topic(self):
        """Apply the full agreed plan: topic, format, tone, style to the pipeline."""
        plan = getattr(self, "_last_plan", None)

        if not plan:
            topic = getattr(self, "_last_suggested_topic", "")
            if topic:
                self._topic_entry.configure(state="normal")
                self._topic_entry.delete(0, "end")
                self._topic_entry.insert(0, topic)
                self._auto_var.set(False)
                self._workshop_append("ghost_ai", f'Topic set: "{topic}" — click ROLL FILM to begin!', "ai")
                self._use_topic_frame.pack_forget()
            return

        # Delegate to auto-apply (includes countdown + _on_run)
        self._auto_apply_and_start(plan)


    def _workshop_clear(self):
        self._chat_history.clear()
        self._workshop_turns = 0
        self._last_plan = None
        self._workshop_log.configure(state="normal")
        self._workshop_log.delete("1.0", "end")
        self._workshop_log.configure(state="disabled")
        self._use_topic_frame.pack_forget()
        self._workshop_turns_lbl.configure(text="Session: 0 turns  •  ∞ unlimited")
        config.set("documentary.voiceover_tone", "")
        config.set("documentary.video_style", "")
        self._workshop_append(
            "ghost_ai",
            "New session started. What documentary shall we create today?",
            "ai",
        )

    def _workshop_generate_now(self):
        """
        Skip the formal plan flow — extract best topic from chat history and
        start generation immediately with cinematic/long/authoritative defaults.
        Called when user clicks ⚡ GENERATE NOW or types 'banao' , 'create' , 'make' , 'bhai banao', 'chalo banao' , 'lo banao', etc.
        """
        # 1. Prefer a confirmed plan if one exists
        plan = getattr(self, "_last_plan", None)
        if plan:
            self._use_suggested_topic()
            return

        # 2. Try to extract topic from what the user typed
        topic = ""
        # First check the topic entry field
        entry_val = self._topic_entry.get().strip()
        if entry_val:
            topic = entry_val

        # If empty, scan chat history for user messages (skip very short ones)
        if not topic:
            for turn in reversed(self._chat_history):
                if turn.get("role") == "user":
                    txt = turn.get("text", "").strip()
                    if len(txt) > 8:  # skip "ok", "ha", etc
                        topic = txt
                        break

        if not topic:
            self._workshop_append(
                "ghost_ai",
                "Please type a topic first — or describe your idea in the chat.",
                "ai",
            )
            return

        # 3. Apply defaults and fill topic entry
        self._topic_entry.configure(state="normal")
        self._topic_entry.delete(0, "end")
        self._topic_entry.insert(0, topic)
        self._auto_var.set(False)

        # Apply defaults for tone/style (cinematic + authoritative)
        config.set("documentary.voiceover_tone", "authoritative")
        config.set("documentary.video_style", "cinematic")
        try:
            config.save()
        except OSError:
            pass

        self._workshop_append(
            "ghost_ai",
            (
                f"🎬 Creating video now:\n"
                f"  Topic : \"{topic}\"\n"
                f"  Style : cinematic  |  Tone : authoritative\n"
                f"  Mode  : {self._doc_mode}\n"
                f"  → Launching pipeline…"
            ),
            "plan",
        )

        # Collapse workshop and start run
        if self._workshop_open:
            self._toggle_workshop()
        self.after(200, self._on_run)


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

        head = ctk.CTkFrame(inner, fg_color="transparent")
        head.pack(fill="x", anchor="w")
        ctk.CTkLabel(head, text="🌐  NARRATION LANGUAGE:",
                     font=("Share Tech Mono", 14), text_color=ACCENT_DOC,
                     ).pack(side="left")

        langs_wrap = ctk.CTkFrame(inner, fg_color="transparent")
        langs_wrap.pack(fill="x", anchor="w", pady=(6, 0))

        self._lang_btns: dict[str, ctk.CTkButton] = {}
        _lang_rows = [
            [
                ("hi",       "🇮🇳 Hindi"),
                ("hinglish", "🔀 Hinglish"),
                ("en",       "🇬🇧 English"),
                ("mr",       "🟠 Marathi"),
            ],
            [
                ("bn",       "🔵 Bengali"),
                ("gu",       "🟢 Gujarati"),
                ("ta",       "🔴 Tamil"),
                ("te",       "🟣 Telugu"),
                ("or",       "🟤 Odia"),
            ],
        ]
        cur_lang = config.get("pipeline.language", "hi")
        for row_langs in _lang_rows:
            btn_row = ctk.CTkFrame(langs_wrap, fg_color="transparent")
            btn_row.pack(anchor="w", pady=2)
            for code, label in row_langs:
                sel = (code == cur_lang)
                btn = ctk.CTkButton(
                    btn_row, text=label, width=100,
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
            (
                "omnivoice",
                "🔊 OmniVoice",
                "Local AI — zero-shot clone · TTS: पूरी स्क्रिप्ट एक pass में; Settings → HTTP read timeout",
            ),
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

        row3 = ctk.CTkFrame(inner, fg_color="transparent")
        row3.pack(fill="x", pady=(12, 0))
        self._burn_subs_var = ctk.BooleanVar(
            value=bool(config.get("documentary.burn_subtitles", False))
        )
        self._burn_subs_cb = ctk.CTkCheckBox(
            row3,
            text="Subtitles: burn into long output (white, bold, bottom) — Long mode only",
            variable=self._burn_subs_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
            fg_color=BG_MAIN,
            border_color=BORDER,
            hover_color=BG_CARD,
            checkmark_color=ACCENT_DOC,
            corner_radius=0,
            command=self._save_burn_subs,
        )
        self._burn_subs_cb.pack(anchor="w")
        self._refresh_burn_subs_state()

    def _save_burn_subs(self) -> None:
        config.set("documentary.burn_subtitles", bool(self._burn_subs_var.get()))
        try:
            config.save()
        except OSError:
            pass
        st = getattr(self.app_ref, "settings_tab", None)
        if st and hasattr(st, "_doc_burn_subs_var"):
            st._doc_burn_subs_var.set(self._burn_subs_var.get())

    def _refresh_burn_subs_state(self) -> None:
        if not hasattr(self, "_burn_subs_cb"):
            return
        is_long = getattr(self, "_doc_mode", "short") == "long"
        self._burn_subs_cb.configure(state="normal" if is_long else "disabled")

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

    def _save_aspect_ratio(self, val: str) -> None:
        config.set("aspect_ratio", "16:9" if val == "16:9" else "9:16")
        self._refresh_doc_aspect_lbl()
        try:
            config.save()
        except OSError:
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

        self._retry_btn = ctk.CTkButton(
            frame, text="🔄  RETRY STEP",
            font=("Orbitron", 13, "bold"), text_color=ACCENT_WARN,
            fg_color="#221500", hover_color="#FF8C00",
            border_color=ACCENT_WARN, border_width=1, corner_radius=0,
            height=50, width=160,
            command=self._on_retry,
        )
        # Not packed yet — shown only when a step error occurs

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

    # ── AI Error Analyst panel ────────────────────────────────────────────────
    def _build_ai_error_panel(self):
        """Hidden panel that appears below Cinema Terminal on any ERROR."""
        self._error_panel = ctk.CTkFrame(
            self._body, fg_color="#120004", corner_radius=0,
            border_width=1, border_color=ACCENT_RED,
        )
        # Not packed by default — revealed by _on_error_detected()

        # Header row
        hdr = ctk.CTkFrame(self._error_panel, fg_color="transparent")
        hdr.pack(fill="x", padx=15, pady=(12, 6))

        ctk.CTkLabel(
            hdr,
            text="🤖  GHOST AGENT — ERROR ANALYST",
            font=("Orbitron", 13, "bold"), text_color=ACCENT_RED, anchor="w",
        ).pack(side="left")

        self._error_explain_btn = ctk.CTkButton(
            hdr,
            text="🤖 EXPLAIN & FIX  ►",
            font=("Share Tech Mono", 12, "bold"),
            text_color="#120004", fg_color=ACCENT_RED,
            hover_color="#CC0022", corner_radius=0, height=32, width=160,
            command=self._on_explain_error,
        )
        self._error_explain_btn.pack(side="right")

        # Brief error hint label (filled on detection)
        self._error_hint_lbl = ctk.CTkLabel(
            self._error_panel,
            text="An error was detected in the Cinema Terminal.",
            font=("Share Tech Mono", 11), text_color="#FF8888", anchor="w",
        )
        self._error_hint_lbl.pack(anchor="w", padx=15, pady=(0, 8))

        # AI analysis output box (hidden until analysis runs)
        self._error_analysis_box = ctk.CTkTextbox(
            self._error_panel,
            font=("Consolas", 12),
            fg_color="#0A0002", border_color=ACCENT_RED, border_width=1,
            corner_radius=0, state="disabled", height=220, wrap="word",
        )
        # packed on demand

        self._error_dismiss_btn = ctk.CTkButton(
            self._error_panel,
            text="✕  Dismiss",
            font=("Share Tech Mono", 11),
            text_color=TEXT_HINT, fg_color="transparent",
            hover_color=BG_CARD, border_color=BORDER, border_width=1,
            corner_radius=0, height=28, width=90,
            command=self._dismiss_error_panel,
        )
        self._error_dismiss_btn.pack(anchor="e", padx=15, pady=(4, 12))

        # Internal state
        self._last_error_log: str = ""
        self._error_panel_visible = False

    def _on_error_detected(self, error_message: str):
        """Show the AI error panel when an ERROR line appears in the log."""
        # Collect full log text for analysis
        try:
            self._log_box.configure(state="normal")
            self._last_error_log = self._log_box.get("1.0", "end")
            self._log_box.configure(state="disabled")
        except Exception:
            self._last_error_log = error_message

        # Update hint label with a brief excerpt of the error
        short = error_message[:120] + ("…" if len(error_message) > 120 else "")
        self._error_hint_lbl.configure(text=f"⚠️  {short}")

        # Show the panel (idempotent)
        if not self._error_panel_visible:
            self._error_analysis_box.pack_forget()
            self._error_panel.pack(fill="x", padx=20, pady=(0, 10))
            self._error_panel_visible = True

        # Re-enable explain button in case it was disabled
        self._error_explain_btn.configure(state="normal", text="🤖 EXPLAIN & FIX  ►")

    def _on_explain_error(self):
        """Call Gemini in a background thread to analyse the error."""
        self._error_explain_btn.configure(state="disabled", text="🤖 Analysing…")
        self._error_analysis_box.configure(state="normal")
        self._error_analysis_box.delete("1.0", "end")
        self._error_analysis_box.insert(
            "end",
            "Ghost Agent is reading the Cinema Terminal and analysing your error…\n"
            "This usually takes 3–8 seconds.",
        )
        self._error_analysis_box.configure(state="disabled")
        self._error_analysis_box.pack(fill="x", padx=15, pady=(0, 8))

        import threading
        log_snapshot = self._last_error_log  # capture before thread starts
        threading.Thread(
            target=self._run_error_analysis,
            args=(log_snapshot,),
            daemon=True,
        ).start()

    def _run_error_analysis(self, log_snapshot: str):
        """Background thread: call error_analyst and post result to GUI."""
        from modules.error_analyst import analyse_error
        cfg = {
            "api_keys.gemini": config.get("api_keys.gemini", ""),
            "gemini_model":    config.get("gemini_model", "gemini-2.0-flash"),
        }
        result = analyse_error(log_snapshot, cfg)
        self.after(0, self._show_error_analysis, result)

    def _show_error_analysis(self, result: str):
        """Main thread: display Gemini's analysis in the text box."""
        self._error_analysis_box.configure(state="normal")
        self._error_analysis_box.delete("1.0", "end")
        self._error_analysis_box.insert("end", result)
        self._error_analysis_box.configure(state="disabled")
        self._error_explain_btn.configure(state="normal", text="🤖 RE-ANALYSE")
        # Scroll body down so user can read the analysis
        self.after(150, lambda: self._scroll._parent_canvas.yview_moveto(1.0))

    def _dismiss_error_panel(self):
        """Hide the error panel."""
        self._error_panel.pack_forget()
        self._error_panel_visible = False

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
        self._output_label.pack(padx=20, pady=(15, 5))
        
        btn_row = ctk.CTkFrame(self._output_frame, fg_color="transparent")
        btn_row.pack(padx=20, pady=(5, 15))
        
        ctk.CTkButton(
            btn_row, text="▶▶  OPEN OUTPUT FOLDER",
            font=("Orbitron", 12, "bold"), text_color=BG_MAIN,
            fg_color=ACCENT_DOC, hover_color=ACCENT_PRI, corner_radius=0,
            command=self._open_output_folder,
        ).pack(side="left", padx=5)

        self._edit_clips_btn = ctk.CTkButton(
            btn_row, text="✂️  EDIT CLIPS",
            font=("Orbitron", 12, "bold"), text_color="#A020F0",
            fg_color="#330044", hover_color="#4A0066", corner_radius=0,
            command=self._open_standalone_editor,
        )
        self._edit_clips_btn.pack(side="left", padx=5)

    def _open_standalone_editor(self):
        ctx = getattr(self, "_last_run_ctx", None)
        if not ctx:
            self._append_log("[WARN] No completed run found to edit.", "WARNING")
            return
            
        from gui.components.clip_editor import ClipEditorWindow
        
        def on_done(new_clips, new_srt, bg_music, bg_vol, subtitle_style, audio_path=None, logo_watermark=None, script_segments=None):
            self._last_run_ctx["clips"] = new_clips
            self._last_run_ctx["srt"] = new_srt
            self._last_run_ctx["subtitle_style"] = subtitle_style
            self._last_run_ctx["bg_music"] = bg_music
            self._last_run_ctx["bg_vol"] = bg_vol
            self._last_run_ctx["logo_watermark"] = logo_watermark
            if audio_path is not None:
                self._last_run_ctx["audio_path"] = audio_path
            if script_segments is not None:
                if "script" not in self._last_run_ctx or not isinstance(self._last_run_ctx.get("script"), dict):
                    self._last_run_ctx["script"] = {}
                self._last_run_ctx["script"]["segments"] = script_segments
            self._append_log("[OK] Edits saved from standalone editor.", "SUCCESS")
            
        ClipEditorWindow(
            self.winfo_toplevel(),
            clips=ctx.get("clips", []),
            audio_path=ctx.get("audio_path"),
            srt_entries=ctx.get("srt", []),
            script_segments=ctx.get("script", {}).get("segments", []),
            run_dir=ctx.get("run_dir"),
            aspect_ratio=ctx.get("aspect_ratio", "9:16"),
            on_done=on_done
        )

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
        self.after(500, self._check_for_editor)

    def _on_stop(self):
        if self.runner:
            self.runner.stop()
        self.pipeline_running = False
        self._run_btn.configure(state="normal", text="▶  ROLL FILM")
        self._stop_btn.configure(state="disabled")
        self._status_lbl.configure(text="ABORTED", text_color=ACCENT_RED)
        self._retry_btn.pack_forget()
        if self.app_ref:
            self.app_ref.set_system_state("READY")
        self._append_log("Pipeline stopped by user.", "WARNING")

    def _on_retry(self):
        """Called when user clicks the Retry button after a step error."""
        if not self.runner or not self.pipeline_running:
            return
        self._retry_btn.pack_forget()
        self._status_lbl.configure(text="● RETRYING", text_color=ACCENT_WARN)
        self._append_log("🔄 Retry requested — re-attempting step…", "INFO")
        self.runner.request_retry()

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

    # ── Editor Before Assembly ────────────────────────────────────────────────
    def _check_for_editor(self):
        if not self.pipeline_running:
            self._editor_open = False
            return
        if self.runner and getattr(self.runner, "waiting_for_editor", False):
            if not getattr(self, "_editor_open", False):
                self._editor_open = True
                self._show_editor_window()
        else:
            self._editor_open = False
        self.after(500, self._check_for_editor)

    def _show_editor_window(self):
        from gui.components.clip_editor import ClipEditorWindow

        ctx = getattr(self.runner, "_doc_regen_ctx", None)
        if not ctx:
            self.runner.approve_editor()
            return

        def on_done(new_clips, new_srt, bg_music, bg_vol, subtitle_style, audio_path=None, logo_watermark=None, script_segments=None):
            ctx["clips"] = new_clips
            ctx["srt"] = new_srt
            ctx["bg_music"] = bg_music
            ctx["bg_vol"] = bg_vol
            ctx["subtitle_style"] = subtitle_style
            ctx["logo_watermark"] = logo_watermark
            if audio_path is not None:
                ctx["audio_path"] = audio_path
            if script_segments is not None:
                if "script" not in ctx or not isinstance(ctx.get("script"), dict):
                    ctx["script"] = {}
                ctx["script"]["segments"] = script_segments
            self._append_log("[OK] Edits saved ✓ — continuing to final assembly …", "SUCCESS")
            self._editor_open = False
            self.runner.approve_editor()

        ClipEditorWindow(
            self.winfo_toplevel(),
            clips=ctx.get("clips", []),
            audio_path=ctx.get("audio_path"),
            srt_entries=ctx.get("srt", []),
            script_segments=ctx.get("script", {}).get("segments", []),
            run_dir=ctx.get("run_dir"),
            aspect_ratio=ctx.get("aspect_ratio", "9:16"),
            on_done=on_done,
        )

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

        # Auto-show AI error analyst panel on any ERROR message
        if level == "ERROR":
            self.after(200, self._on_error_detected, message)

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
            return

        if msg.get("retry_available"):
            # Show retry button — pipeline is paused waiting for user input
            self._status_lbl.configure(text="● STEP FAILED", text_color=ACCENT_RED)
            self._retry_btn.pack(side="left", padx=(0, 10), after=self._stop_btn)
        else:
            # Any non-retry message hides it (step moved on or a normal progress msg)
            self._retry_btn.pack_forget()

    def _on_pipeline_done(self, level: str, message: str, output: str):
        self.pipeline_running = False
        self._run_btn.configure(state="normal", text="▶  ROLL FILM")
        self._stop_btn.configure(state="disabled")
        self._retry_btn.pack_forget()

        if level == "SUCCESS":
            for i in range(6):
                self._step_states[i] = "done"
            self._progress_val = 1.0
            self._progress_pct.configure(text="100%")
            self._status_lbl.configure(text="COMPLETE ✓", text_color=ACCENT_DOC)
            
            # Save context for standalone editor
            if self.runner and hasattr(self.runner, "_doc_regen_ctx") and self.runner._doc_regen_ctx:
                self._last_run_ctx = dict(self.runner._doc_regen_ctx)
                
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
        # Scroll to bottom so the output panel / error status is visible
        self.after(100, lambda: self._scroll._parent_canvas.yview_moveto(1.0))
        # Refresh history tab if available
        if level == "SUCCESS":
            ht = getattr(self.app_ref, "history_tab", None)
            if ht and hasattr(ht, "refresh"):
                self.after(300, ht.refresh)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _reset_steps(self):
        self._step_states = ["pending"] * 6
        self._progress_val = 0.0
        self._progress_pct.configure(text="0%")
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self._output_frame.pack_forget()
        # Hide error panel on new run
        if hasattr(self, "_error_panel") and self._error_panel_visible:
            self._dismiss_error_panel()
        self._redraw_steps_and_bar()
        # Scroll back to top so the user sees the progress from the beginning
        self.after(50, lambda: self._scroll._parent_canvas.yview_moveto(0.0))

    def _append_log(self, text: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}\n"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line, level)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def update_uplink_status(self, name: str):
        self._uplink_lbl.configure(text=f"UPLINK: [{name}]")
