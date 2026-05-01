"""
gui/tabs/settings_tab.py — Settings Tab Cyberpunk
"""

import tempfile
import threading
import shutil

import customtkinter as ctk
from pathlib import Path
from tkinter import filedialog

from config import APP_VERSION
from core.config_manager import config

# === BLUE AI PALETTE ===
BG_MAIN     = "#050A10"
BG_SEC      = "#0A121A"
BG_CARD     = "#0F1A24"
BORDER      = "#1A2B3D"
ACCENT_PRI  = "#0088FF"
ACCENT_SEC  = "#00BFFF"
ACCENT_RED  = "#FF4444"
ACCENT_WARN = "#FFB800"
ACCENT_GRN  = "#00CC66"
TEXT_PRI    = "#E6F0FF"
TEXT_SEC    = "#88AADD"
TEXT_HINT   = "#4A6080"

# ── Per-backend beginner descriptions ─────────────────────────────────────────
TTS_DESCRIPTIONS = {
    "omnivoice": (
        "🎙️ OmniVoice — local voice cloning. GPU strongly recommended (CPU = 2–5 hrs/video).\n"
        "   Hindi/all Indian languages ✅. run.bat (server) ya pip. Details: neeche 'OmniVoice' fold."
    ),
    "edge_tts": (
        "✅ Edge TTS — free cloud, no API key. Hindi/English/regional Indian voices.\n"
        "   Internet required. Fast & reliable — best choice for CPU users with Indian languages."
    ),
    "elevenlabs": (
        "⭐ ElevenLabs — API key chahiye; paid cloud, best quality. Details: neeche fold mein."
    ),
}

# ── API key helper info ────────────────────────────────────────────────────────

API_KEY_INFO = {
    "api_keys.gemini":      ("REQUIRED", ACCENT_GRN,  "Documentary script (Gemini)  •  Free at: aistudio.google.com/app/apikey"),
    "api_keys.elevenlabs":  ("OPTIONAL", TEXT_HINT,   "Sirf ElevenLabs TTS use karne par chahiye  •  elevenlabs.io"),
    "api_keys.pexels":      ("OPTIONAL", TEXT_HINT,   "Documentary footage ke liye stock video  •  pexels.com/api (free)"),
}

OMNIVOICE_STYLE_OPTIONS = {
    "Default - neutral": "default",
    "Narrator - calm documentary": "narrator",
    "Storyteller - warm": "storyteller",
    "Excited / energetic": "excited",
    "News / formal reader": "news",
    "Whisper / soft": "whisper",
    "Casual conversation": "casual",
}
OMNIVOICE_STYLE_REV = {v: k for k, v in OMNIVOICE_STYLE_OPTIONS.items()}

OMNIVOICE_QUALITY_OPTIONS = {
    "Faster preview": "fast",
    "Balanced": "balanced",
    "Higher quality (slower)": "high",
}
OMNIVOICE_QUALITY_REV = {v: k for k, v in OMNIVOICE_QUALITY_OPTIONS.items()}

OMNIVOICE_VOICE_OPTIONS = {
    "Custom - use style + tags": "custom",
    "Female - warm & clear": "vf_warm",
    "Female - soft storyteller": "vf_story",
    "Male - news / formal": "vm_news",
    "Male - deep narrator": "vm_narrator",
    "Male - young energetic": "vm_young",
    "Neutral - model picks voice": "neutral_auto",
}
OMNIVOICE_VOICE_REV = {v: k for k, v in OMNIVOICE_VOICE_OPTIONS.items()}

OMNIVOICE_GENDER_OPTIONS = {
    "Unspecified": "",
    "Male": "male",
    "Female": "female",
}
OMNIVOICE_GENDER_REV = {v: k for k, v in OMNIVOICE_GENDER_OPTIONS.items()}

OMNIVOICE_MODE_OPTIONS = {
    "Voice Cloning": "clone",
    "Sound Design": "design",
}
OMNIVOICE_MODE_REV = {v: k for k, v in OMNIVOICE_MODE_OPTIONS.items()}

_LOGO_POS_TO_LABEL = {
    "bottom_right": "Bottom-right",
    "bottom_left": "Bottom-left",
    "top_right": "Top-right",
    "top_left": "Top-left",
}
_LOGO_LABEL_TO_POS = {v: k for k, v in _LOGO_POS_TO_LABEL.items()}


class SettingsTab(ctk.CTkFrame):
    def __init__(self, master, app_ref, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app_ref = app_ref

        self._key_entries = {}
        self._key_visible = {}

        # State variables
        self._tts_val = config.get("tts.backend", "omnivoice")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)

        self._build_beginner_banner(scroll)
        self._build_api_keys_section(scroll)
        self._build_tts_section(scroll)
        self._build_video_format_section(scroll)
        self._build_pipeline_section(scroll)
        self._build_license_section(scroll)

        # Save button
        save_frame = ctk.CTkFrame(self, fg_color="transparent")
        save_frame.pack(fill="x", padx=20, pady=(10, 5))

        self._save_btn = ctk.CTkButton(
            save_frame,
            text="[ SAVE CONFIG ]",
            font=("Orbitron", 18, "bold"),
            text_color=ACCENT_PRI,
            fg_color="transparent",
            hover_color=BG_SEC,
            border_color=ACCENT_PRI,
            border_width=2,
            corner_radius=0,
            height=55,
            command=self._save,
        )
        self._save_btn.pack(fill="x")

        # .env.local quick-access bar
        env_frame = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0,
                                 border_width=1, border_color=BORDER)
        env_frame.pack(fill="x", padx=20, pady=(5, 20))

        ctk.CTkLabel(
            env_frame,
            text="⚡ .ENV.LOCAL →",
            font=("Share Tech Mono", 12, "bold"),
            text_color=ACCENT_WARN,
        ).pack(side="left", padx=(12, 6), pady=10)

        self._env_path_label = ctk.CTkLabel(
            env_frame,
            text=str(config.env_local_path),
            font=("Share Tech Mono", 11),
            text_color=TEXT_SEC,
            anchor="w",
        )
        self._env_path_label.pack(side="left", padx=0, pady=10, expand=True, fill="x")

        ctk.CTkButton(
            env_frame,
            text="[ OPEN IN EDITOR ]",
            font=("Share Tech Mono", 12, "bold"),
            text_color=ACCENT_WARN,
            fg_color="transparent",
            hover_color=BG_CARD,
            border_color=ACCENT_WARN,
            border_width=1,
            corner_radius=0,
            height=32,
            command=self._open_env_local,
        ).pack(side="right", padx=12, pady=8)

    # ── Beginner Banner ───────────────────────────────────────────────────
    def _build_beginner_banner(self, parent):
        inner = self._add_foldable(
            parent, "🚀  Quick start (first run — 5 steps)", start_open=False
        )
        ctk.CTkLabel(
            inner,
            text=(
                "1) API Keys → GEMINI  (aistudio.google.com)  ·  2) Audio → EDGE TTS  (free)  ·  "
                "3) Core → language hi/en/…  ·  4) [ SAVE ] → Documentary tab → ROLL FILM"
            ),
            font=("Share Tech Mono", 12),
            text_color="#88CCAA",
            justify="left",
            anchor="w",
            wraplength=800,
        ).pack(anchor="w", padx=10, pady=(2, 8))

    # ── Section 1: API Keys ───────────────────────────────────────────────
    def _build_api_keys_section(self, parent):
        section = self._section(parent, ">> [ API KEYS ]",
                                "Yahan apni API keys daalo. Sirf Gemini key REQUIRED hai — baaki sab optional hain.")

        keys = [
            ("Gemini API Key",              "api_keys.gemini"),
            ("ElevenLabs API Key",          "api_keys.elevenlabs"),
            ("Pexels API Key",              "api_keys.pexels"),
        ]

        more_keys_frame: ctk.CTkFrame | None = None
        for idx, (label_text, key_path) in enumerate(keys):
            if idx == 0:
                key_parent: ctk.CTkFrame = section
            else:
                if more_keys_frame is None:
                    more_keys_frame = self._add_foldable(
                        section, "More API keys (optional)", start_open=False
                    )
                key_parent = more_keys_frame
            badge_text, badge_color, hint_text = API_KEY_INFO.get(
                key_path, ("OPTIONAL", TEXT_HINT, "")
            )

            # Container card
            card = ctk.CTkFrame(key_parent, fg_color=BG_CARD, corner_radius=0,
                                border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=4)

            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=(8, 2))

            # Badge [REQUIRED] / [OPTIONAL]
            badge = ctk.CTkFrame(row, fg_color="transparent")
            badge.pack(side="left")
            ctk.CTkLabel(badge, text=f"[{badge_text}]",
                         font=("Share Tech Mono", 10, "bold"),
                         text_color=badge_color, width=80, anchor="w").pack()
            ctk.CTkLabel(badge, text=label_text.upper(),
                         font=("Share Tech Mono", 12, "bold"),
                         text_color=TEXT_SEC, width=230, anchor="w").pack()

            entry = ctk.CTkEntry(row, show="●", width=370,
                                 font=("Share Tech Mono", 13),
                                 fg_color=BG_MAIN, border_color=BORDER,
                                 text_color=TEXT_PRI, corner_radius=0)
            entry.pack(side="left", padx=8)
            entry.insert(0, config.get(key_path, "") or "")
            self._key_entries[key_path] = entry
            self._key_visible[key_path] = False

            entry.bind("<FocusIn>",  lambda e, en=entry: en.configure(border_width=2, border_color=ACCENT_PRI))
            entry.bind("<FocusOut>", lambda e, en=entry: en.configure(border_width=1, border_color=BORDER))

            ctk.CTkButton(
                row, text="[👁]", width=40, height=28,
                font=("Share Tech Mono", 14), text_color=ACCENT_PRI,
                fg_color="transparent", hover_color=BG_CARD, corner_radius=0,
                command=lambda kp=key_path: self._toggle_key(kp),
            ).pack(side="left")

            # Hint line
            if hint_text:
                ctk.CTkLabel(card, text=f"   ↳  {hint_text}",
                             font=("Share Tech Mono", 11),
                             text_color=TEXT_HINT, anchor="w").pack(
                    anchor="w", padx=10, pady=(0, 8))

    def _toggle_key(self, key_path: str):
        entry = self._key_entries[key_path]
        self._key_visible[key_path] = not self._key_visible[key_path]
        entry.configure(show="" if self._key_visible[key_path] else "●")

    def _add_foldable(
        self, parent, title: str, *, start_open: bool = True
    ) -> ctk.CTkFrame:
        """Header row (toggle) + inner frame. Pack children on the returned inner frame."""
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(fill="x", pady=(2, 0))
        state = {"open": start_open}
        head = ctk.CTkFrame(box, fg_color=BG_CARD, corner_radius=0, border_width=1, border_color=BORDER)
        head.pack(fill="x")
        inner = ctk.CTkFrame(box, fg_color="transparent")

        def toggle() -> None:
            state["open"] = not state["open"]
            if state["open"]:
                inner.pack(fill="x", pady=(2, 4))
                btn.configure(text=f"  ▼  {title}")
            else:
                inner.pack_forget()
                btn.configure(text=f"  ▶  {title}")

        btn = ctk.CTkButton(
            head,
            text=f"  {'▼' if start_open else '▶'}  {title}",
            command=toggle,
            anchor="w",
            height=30,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_PRI,
            fg_color="transparent",
            hover_color=BG_SEC,
        )
        btn.pack(fill="x", padx=1, pady=1)
        if start_open:
            inner.pack(fill="x", pady=(2, 4))
        return inner

    # ── Section 2: TTS Backend ────────────────────────────────────────────
    def _build_tts_section(self, parent):
        section = self._section(
            parent, ">> [ AUDIO SUBROUTINE ]",
            "Video ki awaaz (voiceover) kaun generate karega. "
            "👉 Beginner? → EDGE TTS chuno (free, koi setup nahi)."
        )

        options = [
            ("omnivoice",  "OMNIVOICE ⭐"),
            ("edge_tts",   "EDGE TTS ✅"),
            ("elevenlabs", "ELEVENLABS"),
        ]

        btn_frame = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(5, 8))

        self._tts_btns = {}
        for val, label in options:
            btn = ctk.CTkButton(
                btn_frame, text=label, font=("Share Tech Mono", 12, "bold"),
                fg_color="transparent", text_color=TEXT_SEC,
                border_color=BORDER, border_width=1, corner_radius=0,
                command=lambda v=val: self._select_tts(v)
            )
            btn.pack(side="left", padx=4, expand=True, fill="x")
            btn.bind("<Enter>", lambda e, b=btn: b.configure(border_color=ACCENT_PRI) if b.cget("fg_color") == "transparent" else None)
            btn.bind("<Leave>", lambda e, b=btn: b.configure(border_color=BORDER)     if b.cget("fg_color") == "transparent" else None)
            self._tts_btns[val] = btn

        # Dynamic description box
        self._tts_desc = ctk.CTkLabel(
            section,
            text="",
            font=("Share Tech Mono", 11),
            text_color="#88CCAA",
            justify="left",
            anchor="w",
            wraplength=760,
            fg_color="#071510",
            corner_radius=0,
        )
        self._tts_desc.pack(fill="x", padx=0, pady=(0, 6), ipadx=10, ipady=6)

        self._select_tts(self._tts_val)

        # TTS config sub-section
        tts_config = ctk.CTkFrame(section, fg_color=BG_MAIN, corner_radius=0,
                                  border_color=BORDER, border_width=1)
        tts_config.pack(fill="x", pady=(0, 5), ipadx=10, ipady=10)

        omni_inner = self._add_foldable(
            tts_config, "OmniVoice — run.bat, mode, reference, design, quality", start_open=True
        )

        # ── OmniVoice (collapsed header above) ────────────────────────────
        ctk.CTkLabel(
            omni_inner, text="OMNIVOICE SERVER:",
            font=("Share Tech Mono", 12, "bold"), text_color=ACCENT_PRI,
        ).pack(anchor="w", padx=10, pady=(10, 0))

        om_mode_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_mode_row.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(om_mode_row, text="OMNIVOICE MODE:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        current_mode = config.get("tts.omnivoice_mode", "clone")
        mode_display = OMNIVOICE_MODE_REV.get(current_mode, "Voice Cloning")
        self._omnivoice_mode = ctk.CTkSegmentedButton(
            om_mode_row,
            values=["Voice Cloning", "Sound Design"],
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_PRI,
            fg_color=BG_SEC,
            selected_color=ACCENT_PRI,
            selected_hover_color=ACCENT_SEC,
            unselected_color=BG_CARD,
            unselected_hover_color=BORDER,
            corner_radius=0,
        )
        self._omnivoice_mode.set(mode_display)
        self._omnivoice_mode.pack(side="left", padx=5)
        self._hint(omni_inner, "Voice Cloning = reference WAV + transcript  |  Sound Design = bina reference audio ke generated voice")

        ov_path_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        ov_path_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(ov_path_row, text="SERVER PATH (run.bat):", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        self._omnivoice_server_path = ctk.CTkEntry(
            ov_path_row, width=310, font=("Share Tech Mono", 12),
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT_PRI, corner_radius=0,
        )
        self._omnivoice_server_path.insert(0, config.get("tts.omnivoice_server_path", ""))
        self._omnivoice_server_path.pack(side="left", padx=5)
        self._omnivoice_server_path.bind(
            "<FocusIn>",  lambda e: self._omnivoice_server_path.configure(border_width=2, border_color=ACCENT_PRI))
        self._omnivoice_server_path.bind(
            "<FocusOut>", lambda e: self._omnivoice_server_path.configure(border_width=1, border_color=BORDER))
        ctk.CTkButton(
            ov_path_row, text="[ BROWSE ]", width=80,
            font=("Share Tech Mono", 13, "bold"), text_color=ACCENT_PRI,
            fg_color="transparent", hover_color=BG_CARD,
            border_color=BORDER, border_width=1, corner_radius=0,
            command=self._browse_omnivoice_server,
        ).pack(side="left", padx=5)

        self._omnivoice_autostart_var = ctk.BooleanVar(
            value=bool(config.get("tts.omnivoice_autostart", True))
        )
        ctk.CTkCheckBox(
            omni_inner,
            text="Auto-start OmniVoice server before each documentary run",
            variable=self._omnivoice_autostart_var,
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC,
            fg_color=BG_MAIN, border_color=BORDER,
            hover_color=BG_CARD, checkmark_color=ACCENT_PRI, corner_radius=0,
        ).pack(anchor="w", padx=10, pady=(4, 2))
        self._hint(
            omni_inner,
            "run.bat ka path daalo (e.g. D:/omnivoice/OmniVoice/run.bat). "
            "Auto-start ON → app khud server start karega. "
            "OFF → manually start karo pehle.",
        )

        # Voice clone reference audio
        cb_ref_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        cb_ref_row.pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(cb_ref_row, text="VOICE CLONE REF (.wav):", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        self._ref_audio = ctk.CTkEntry(cb_ref_row, width=280, font=("Share Tech Mono", 13),
                                       fg_color=BG_MAIN, border_color=BORDER,
                                       text_color=TEXT_PRI, corner_radius=0)
        self._ref_audio.insert(0, config.get("tts.reference_audio", "my_voice_reference.wav"))
        self._ref_audio.pack(side="left", padx=5)
        self._ref_audio.bind("<FocusIn>",  lambda e: self._ref_audio.configure(border_width=2, border_color=ACCENT_PRI))
        self._ref_audio.bind("<FocusOut>", lambda e: self._ref_audio.configure(border_width=1, border_color=BORDER))
        ctk.CTkButton(cb_ref_row, text="[ BROWSE ]", width=80,
                      font=("Share Tech Mono", 13, "bold"), text_color=ACCENT_PRI,
                      fg_color="transparent", hover_color=BG_CARD,
                      border_color=BORDER, border_width=1, corner_radius=0,
                      command=self._browse_ref_audio).pack(side="left", padx=5)
        self._hint(
            omni_inner,
            "Chhota clear WAV (max ~15s, WebUI jaisa) — jis voice ko clone karna hai. "
            "Transcript neeche zaroori (WebUI ne Whisper hata diya).",
        )

        om_vn_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_vn_row.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(om_vn_row, text="REF VOICE NAME (opt):", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        self._omnivoice_ref_voice_name = ctk.CTkEntry(om_vn_row, width=400, font=("Share Tech Mono", 12),
                                                       fg_color=BG_MAIN, border_color=BORDER,
                                                       text_color=TEXT_PRI, corner_radius=0)
        self._omnivoice_ref_voice_name.insert(0, config.get("tts.omnivoice_ref_voice_name", ""))
        self._omnivoice_ref_voice_name.pack(side="left", padx=5, fill="x", expand=True)
        self._omnivoice_ref_voice_name.bind(
            "<FocusIn>", lambda e: self._omnivoice_ref_voice_name.configure(border_width=2, border_color=ACCENT_PRI)
        )
        self._omnivoice_ref_voice_name.bind(
            "<FocusOut>", lambda e: self._omnivoice_ref_voice_name.configure(border_width=1, border_color=BORDER)
        )
        self._hint(
            omni_inner,
            "Optional — WebUI `reference_voices.json` ke liye (jaise mom, narrator_h1). "
            "Khali = WAV filename se match.",
        )

        om_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_row.pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(om_row, text="REF TRANSCRIPT:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        self._omnivoice_transcript = ctk.CTkEntry(om_row, width=400, font=("Share Tech Mono", 12),
                                                    fg_color=BG_MAIN, border_color=BORDER,
                                                    text_color=TEXT_PRI, corner_radius=0)
        self._omnivoice_transcript.insert(0, config.get("tts.omnivoice_ref_transcript", ""))
        self._omnivoice_transcript.pack(side="left", padx=5, fill="x", expand=True)
        self._omnivoice_transcript.bind("<FocusIn>",  lambda e: self._omnivoice_transcript.configure(border_width=2, border_color=ACCENT_PRI))
        self._omnivoice_transcript.bind("<FocusOut>", lambda e: self._omnivoice_transcript.configure(border_width=1, border_color=BORDER))
        self._hint(
            omni_inner,
            "Zaroori: reference WAV mein jo bole gaye hon wahi exact text (OmniVoice WebUI jaisa).",
        )

        om_model_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_model_row.pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(om_model_row, text="OMNIVOICE MODEL ID:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        self._omnivoice_model = ctk.CTkEntry(om_model_row, width=400, font=("Share Tech Mono", 12),
                                             fg_color=BG_MAIN, border_color=BORDER,
                                             text_color=TEXT_PRI, corner_radius=0)
        self._omnivoice_model.insert(0, config.get("tts.omnivoice_model_id", "k2-fsa/OmniVoice"))
        self._omnivoice_model.pack(side="left", padx=5, fill="x", expand=True)
        self._omnivoice_model.bind("<FocusIn>",  lambda e: self._omnivoice_model.configure(border_width=2, border_color=ACCENT_PRI))
        self._omnivoice_model.bind("<FocusOut>", lambda e: self._omnivoice_model.configure(border_width=1, border_color=BORDER))
        self._hint(omni_inner, "OmniVoice Hugging Face model id (default: k2-fsa/OmniVoice)")

        ctk.CTkLabel(omni_inner, text="OMNIVOICE VOICE DESIGN:",
                     font=("Share Tech Mono", 12, "bold"),
                     text_color=ACCENT_PRI).pack(anchor="w", padx=10, pady=(10, 0))

        om_voice_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_voice_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(om_voice_row, text="VOICE CHARACTER:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        cur_voice = config.get("tts.omnivoice_design_voice", "custom")
        self._omnivoice_voice = ctk.CTkOptionMenu(
            om_voice_row,
            values=list(OMNIVOICE_VOICE_OPTIONS.keys()),
            font=("Share Tech Mono", 12), text_color=TEXT_PRI,
            fg_color=BG_SEC, button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI, corner_radius=0,
            width=320,
        )
        self._omnivoice_voice.set(OMNIVOICE_VOICE_REV.get(cur_voice, "Custom - use style + tags"))
        self._omnivoice_voice.pack(side="left", padx=5)

        om_style_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_style_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(om_style_row, text="SPEAKING STYLE:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        cur_style = config.get("tts.omnivoice_speaking_style", "default")
        self._omnivoice_style = ctk.CTkOptionMenu(
            om_style_row,
            values=list(OMNIVOICE_STYLE_OPTIONS.keys()),
            font=("Share Tech Mono", 12), text_color=TEXT_PRI,
            fg_color=BG_SEC, button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI, corner_radius=0,
            width=320,
        )
        self._omnivoice_style.set(OMNIVOICE_STYLE_REV.get(cur_style, "Default - neutral"))
        self._omnivoice_style.pack(side="left", padx=5)

        om_quality_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_quality_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(om_quality_row, text="QUALITY PRESET:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        cur_quality = config.get("tts.omnivoice_quality_preset", "balanced")
        self._omnivoice_quality = ctk.CTkOptionMenu(
            om_quality_row,
            values=list(OMNIVOICE_QUALITY_OPTIONS.keys()),
            font=("Share Tech Mono", 12), text_color=TEXT_PRI,
            fg_color=BG_SEC, button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI, corner_radius=0,
            width=320,
        )
        self._omnivoice_quality.set(OMNIVOICE_QUALITY_REV.get(cur_quality, "Balanced"))
        self._omnivoice_quality.pack(side="left", padx=5)

        om_gender_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_gender_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(om_gender_row, text="VOICE GENDER:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        cur_gender = config.get("tts.omnivoice_voice_gender", "")
        self._omnivoice_gender = ctk.CTkOptionMenu(
            om_gender_row,
            values=list(OMNIVOICE_GENDER_OPTIONS.keys()),
            font=("Share Tech Mono", 12), text_color=TEXT_PRI,
            fg_color=BG_SEC, button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI, corner_radius=0,
            width=180,
        )
        self._omnivoice_gender.set(OMNIVOICE_GENDER_REV.get(cur_gender, "Unspecified"))
        self._omnivoice_gender.pack(side="left", padx=5)

        om_instr_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_instr_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(om_instr_row, text="EXTRA VOICE TAGS:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        self._omnivoice_instruct = ctk.CTkEntry(om_instr_row, width=400, font=("Share Tech Mono", 12),
                                                fg_color=BG_MAIN, border_color=BORDER,
                                                text_color=TEXT_PRI, corner_radius=0)
        self._omnivoice_instruct.insert(0, config.get("tts.omnivoice_extra_instruct", ""))
        self._omnivoice_instruct.pack(side="left", padx=5, fill="x", expand=True)
        self._omnivoice_instruct.bind("<FocusIn>",  lambda e: self._omnivoice_instruct.configure(border_width=2, border_color=ACCENT_PRI))
        self._omnivoice_instruct.bind("<FocusOut>", lambda e: self._omnivoice_instruct.configure(border_width=1, border_color=BORDER))

        om_lang_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_lang_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(om_lang_row, text="LANGUAGE HINT:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        self._omnivoice_language = ctk.CTkEntry(om_lang_row, width=240, font=("Share Tech Mono", 12),
                                                fg_color=BG_MAIN, border_color=BORDER,
                                                text_color=TEXT_PRI, corner_radius=0)
        self._omnivoice_language.insert(0, config.get("tts.omnivoice_language_hint", ""))
        self._omnivoice_language.pack(side="left", padx=5)
        self._omnivoice_language.bind("<FocusIn>",  lambda e: self._omnivoice_language.configure(border_width=2, border_color=ACCENT_PRI))
        self._omnivoice_language.bind("<FocusOut>", lambda e: self._omnivoice_language.configure(border_width=1, border_color=BORDER))
        self._hint(omni_inner, "WebUI: profile + style + quality. Pipeline language maps to OmniVoice (Odia→ory, Telugu te, Tamil ta). Optional LANGUAGE HINT overrides when set.")

        alt_tts = self._add_foldable(
            tts_config, "Edge TTS & ElevenLabs", start_open=False
        )
        ctk.CTkLabel(alt_tts, text="EDGE TTS VOICE:",
                     font=("Share Tech Mono", 12, "bold"),
                     text_color=TEXT_SEC).pack(anchor="w", padx=10, pady=(10, 0))
        self._edge_voice = ctk.CTkOptionMenu(
            alt_tts,
            values=["hi-IN-MadhurNeural", "hi-IN-SwaraNeural",
                    "en-US-GuyNeural", "en-US-JennyNeural"],
            font=("Share Tech Mono", 13), text_color=TEXT_PRI,
            fg_color=BG_SEC, button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI, corner_radius=0
        )
        self._edge_voice.set(config.get("tts.edge_tts_voice", "hi-IN-MadhurNeural"))
        self._edge_voice.pack(anchor="w", padx=10, pady=(2, 2))
        self._hint(alt_tts, "Hindi: MadhurNeural (male) / SwaraNeural (female)  |  English: GuyNeural / JennyNeural")

        ctk.CTkLabel(alt_tts, text="ELEVENLABS VOICE ID:",
                     font=("Share Tech Mono", 12, "bold"),
                     text_color=TEXT_SEC).pack(anchor="w", padx=10, pady=(10, 0))
        self._eleven_voice = ctk.CTkEntry(alt_tts, width=350, font=("Share Tech Mono", 13),
                                          fg_color=BG_MAIN, border_color=BORDER,
                                          text_color=TEXT_PRI, corner_radius=0)
        self._eleven_voice.insert(0, config.get("tts.elevenlabs_voice_id", "") or "")
        self._eleven_voice.pack(anchor="w", padx=10, pady=(2, 2))
        self._eleven_voice.bind("<FocusIn>",  lambda e: self._eleven_voice.configure(border_width=2, border_color=ACCENT_PRI))
        self._eleven_voice.bind("<FocusOut>", lambda e: self._eleven_voice.configure(border_width=1, border_color=BORDER))
        self._hint(alt_tts, "ElevenLabs.io → Voice Lab → apni voice pe click karo → Voice ID copy karo")

        # ElevenLabs realism knobs
        eleven_knobs_row = ctk.CTkFrame(alt_tts, fg_color="transparent")
        eleven_knobs_row.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(eleven_knobs_row, text="ELEVENLABS VOICE SETTINGS (Realism Tuning):",
                     font=("Share Tech Mono", 11, "bold"), text_color=TEXT_SEC,
                     anchor="w").pack(anchor="w", padx=10, pady=(6, 2))

        knob_inner = ctk.CTkFrame(alt_tts, fg_color=BG_CARD, corner_radius=0,
                                  border_width=1, border_color=BORDER)
        knob_inner.pack(fill="x", padx=10, pady=(0, 4))

        def _knob_row(parent, label, key, default, hint_text):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(r, text=label, width=200, anchor="w",
                         font=("Share Tech Mono", 11, "bold"), text_color=TEXT_SEC).pack(side="left")
            e = ctk.CTkEntry(r, width=90, font=("Share Tech Mono", 12),
                             fg_color=BG_MAIN, border_color=BORDER,
                             text_color=TEXT_PRI, corner_radius=0)
            e.insert(0, str(config.get(key, default)))
            e.pack(side="left", padx=6)
            e.bind("<FocusIn>",  lambda ev, w=e: w.configure(border_width=2, border_color=ACCENT_PRI))
            e.bind("<FocusOut>", lambda ev, w=e: w.configure(border_width=1, border_color=BORDER))
            ctk.CTkLabel(r, text=hint_text, font=("Share Tech Mono", 10),
                         text_color=TEXT_HINT, anchor="w").pack(side="left", padx=6)
            return e

        self._eleven_stability = _knob_row(
            knob_inner, "Stability (0.0–1.0):", "tts.elevenlabs_stability", 0.30,
            "Lower = more expressive  |  Recommended: 0.25–0.40"
        )
        self._eleven_similarity = _knob_row(
            knob_inner, "Similarity Boost:", "tts.elevenlabs_similarity_boost", 0.85,
            "Higher = truer to voice  |  Recommended: 0.80–0.90"
        )
        self._eleven_style = _knob_row(
            knob_inner, "Style Exaggeration:", "tts.elevenlabs_style", 0.45,
            "Higher = more dramatic  |  Recommended: 0.35–0.55"
        )
        self._hint(alt_tts, "Speaker Boost is always ON — gives cleaner, more present voice output")

    def _select_tts(self, val):
        self._tts_val = val
        for v, btn in self._tts_btns.items():
            if v == val:
                btn.configure(fg_color=ACCENT_PRI, text_color=BG_MAIN, border_color=ACCENT_PRI)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SEC, border_color=BORDER)
        if hasattr(self, "_tts_desc"):
            self._tts_desc.configure(text=TTS_DESCRIPTIONS.get(val, ""))

    # ── Section: Run Behavior ─────────────────────────────────────────────
    def _build_video_format_section(self, parent):
        section = self._section(
            parent, ">> [ RUN BEHAVIOR ]",
            "Pipeline controls, language, model, and output — all in one compact table."
        )

        # ── Table grid (3 columns, fully responsive) ──────────────────────
        tbl = ctk.CTkFrame(section, fg_color="transparent")
        tbl.pack(fill="x", pady=(4, 8))
        for c in range(3):
            tbl.columnconfigure(c, weight=1, uniform="rb")

        # ── Helper: build one table cell ──────────────────────────────────
        def _cell(row, col, colspan=1, *, rowspan=1):
            f = ctk.CTkFrame(
                tbl, fg_color=BG_CARD, corner_radius=0,
                border_width=1, border_color=BORDER,
            )
            f.grid(row=row, column=col, columnspan=colspan, rowspan=rowspan,
                   sticky="nsew", padx=3, pady=3)
            return f

        def _cell_lbl(cell, text):
            ctk.CTkLabel(
                cell, text=text,
                font=("Share Tech Mono", 10, "bold"),
                text_color=ACCENT_PRI, anchor="w",
            ).pack(anchor="w", padx=10, pady=(6, 2))

        def _hint_lbl(cell, text):
            ctk.CTkLabel(
                cell, text=f"  ↳  {text}",
                font=("Share Tech Mono", 10),
                text_color=TEXT_HINT, anchor="w", wraplength=0,
            ).pack(anchor="w", padx=10, pady=(0, 6))

        # ════════════════════ ROW 0 ════════════════════════════════════════

        # [0,0] Pipeline pause toggles
        c00 = _cell(0, 0)
        _cell_lbl(c00, "PIPELINE BEHAVIOR")
        self._script_review_var = ctk.BooleanVar(
            value=bool(config.get("script_review_enabled", True))
        )
        self._chk_script_review = ctk.CTkCheckBox(
            c00,
            text="Pause for script review",
            variable=self._script_review_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
            fg_color=BG_MAIN, border_color=BORDER,
            hover_color=BG_CARD, checkmark_color=ACCENT_PRI, corner_radius=0,
        )
        self._chk_script_review.pack(anchor="w", padx=10, pady=(2, 1))
        _hint_lbl(c00, "Uncheck for fully automated / unattended runs")

        self._video_preview_var = ctk.BooleanVar(
            value=bool(config.get("video_preview_enabled", True))
        )
        self._chk_video_preview = ctk.CTkCheckBox(
            c00,
            text="Pause for Ghost Editor (before assembly)",
            variable=self._video_preview_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
            fg_color=BG_MAIN, border_color=BORDER,
            hover_color=BG_CARD, checkmark_color=ACCENT_PRI, corner_radius=0,
        )
        self._chk_video_preview.pack(anchor="w", padx=10, pady=(2, 1))
        _hint_lbl(c00, "Opens Ghost Editor after downloads so you can trim clips before the final render")

        # [0,1] Language picker
        c01 = _cell(0, 1)
        _cell_lbl(c01, "NARRATION LANGUAGE")
        _langs = [
            ("hi",       "🇮🇳 Hindi"),
            ("hinglish", "🔀 Hinglish"),
            ("en",       "🇬🇧 English"),
            ("mr",       "🟠 Marathi"),
            ("bn",       "🔵 Bengali"),
            ("gu",       "🟢 Gujarati"),
            ("ta",       "🔴 Tamil"),
            ("te",       "🟣 Telugu"),
            ("or",       "🟤 Odia (Odisha)"),
        ]
        cur_lang = config.get("pipeline.language", "hi")
        # Dropdown fits all options and is responsive
        self._lang = ctk.CTkOptionMenu(
            c01,
            values=[lbl for _, lbl in _langs],
            font=("Share Tech Mono", 12),
            text_color=TEXT_PRI, fg_color=BG_SEC,
            button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI,
            corner_radius=0,
        )
        self._lang_label_to_code = {lbl: code for code, lbl in _langs}
        self._lang_code_to_label = {code: lbl for code, lbl in _langs}
        self._lang.set(self._lang_code_to_label.get(cur_lang, _langs[0][1]))
        self._lang.pack(anchor="w", padx=10, pady=(2, 2), fill="x")
        _hint_lbl(c01, "Script + voiceover isi language mein generate hoga")

        # [0,2] Output folder
        c02 = _cell(0, 2)
        _cell_lbl(c02, "OUTPUT FOLDER")
        of_row = ctk.CTkFrame(c02, fg_color="transparent")
        of_row.pack(fill="x", padx=8, pady=(2, 2))
        self._output_dir = ctk.CTkEntry(
            of_row, font=("Share Tech Mono", 12),
            fg_color=BG_MAIN, border_color=BORDER,
            text_color=TEXT_PRI, corner_radius=0,
        )
        self._output_dir.insert(0, config.get("pipeline.output_folder", "output"))
        self._output_dir.pack(side="left", fill="x", expand=True)
        self._output_dir.bind("<FocusIn>",  lambda e: self._output_dir.configure(border_width=2, border_color=ACCENT_PRI))
        self._output_dir.bind("<FocusOut>", lambda e: self._output_dir.configure(border_width=1, border_color=BORDER))
        ctk.CTkButton(
            of_row, text="…", width=30,
            font=("Share Tech Mono", 13, "bold"), text_color=ACCENT_PRI,
            fg_color="transparent", hover_color=BG_CARD,
            border_color=BORDER, border_width=1, corner_radius=0,
            command=self._browse_output,
        ).pack(side="left", padx=(4, 0))
        _hint_lbl(c02, "Relative (e.g. 'output') or full path — folder created automatically")

        # ════════════════════ ROW 1 ════════════════════════════════════════

        # [1,0] Upload settings
        c10 = _cell(1, 0)
        _cell_lbl(c10, "YOUTUBE UPLOAD")
        self._upload_enabled_var = ctk.BooleanVar(
            value=bool(config.get("pipeline.upload_enabled", True))
        )
        self._chk_upload_enabled = ctk.CTkCheckBox(
            c10,
            text="Enable YouTube upload after render",
            variable=self._upload_enabled_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
            fg_color=BG_MAIN, border_color=BORDER,
            hover_color=BG_CARD, checkmark_color=ACCENT_PRI, corner_radius=0,
            command=self._sync_upload_controls,
        )
        self._chk_upload_enabled.pack(anchor="w", padx=10, pady=(2, 4))
        upload_row = ctk.CTkFrame(c10, fg_color="transparent")
        upload_row.pack(fill="x", padx=8, pady=(0, 2))
        ctk.CTkLabel(
            upload_row, text="Mode:",
            font=("Share Tech Mono", 11), text_color=TEXT_SEC,
        ).pack(side="left")
        self._upload = ctk.CTkOptionMenu(
            upload_row,
            values=["unlisted", "public", "draft"],
            font=("Share Tech Mono", 12), text_color=TEXT_PRI,
            fg_color=BG_SEC, button_color=BORDER,
            button_hover_color=ACCENT_PRI, corner_radius=0, width=130,
        )
        self._upload.set(config.get("pipeline.upload_mode", "unlisted"))
        self._upload.pack(side="left", padx=(6, 0))
        _hint_lbl(c10, "unlisted = link-only  |  public = all  |  draft = save only")
        self._sync_upload_controls()

        # [1,1] Script provider + Gemini model
        c11 = _cell(1, 1)
        _cell_lbl(c11, "AI SCRIPT PROVIDER")
        cur_prov = config.get("script_provider", "gemini")
        self._provider_var = ctk.StringVar(
            value="Gemini" if cur_prov == "gemini" else "Ollama"
        )
        self._provider_seg = ctk.CTkSegmentedButton(
            c11,
            values=["Gemini", "Ollama"],
            variable=self._provider_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_PRI,
            fg_color=BG_MAIN,
            selected_color=ACCENT_PRI,
            selected_hover_color=ACCENT_SEC,
            unselected_color=BG_CARD,
            unselected_hover_color=BORDER,
            corner_radius=0,
            command=self._on_provider_switch,
        )
        self._provider_seg.pack(anchor="w", padx=10, pady=(2, 6), fill="x")

        # Ollama status inline (small)
        self._ollama_status_lbl = ctk.CTkLabel(
            c11, text="⬤ checking…",
            font=("Share Tech Mono", 10), text_color=TEXT_HINT,
        )
        self._ollama_status_lbl.pack(anchor="w", padx=10)
        threading.Thread(target=self._probe_ollama_async, daemon=True).start()

        # ── Gemini frame (shown when Gemini selected) ──────────────────────
        self._gemini_frame = ctk.CTkFrame(c11, fg_color="transparent")
        GEMINI_MODELS = [
            "gemini-2.5-flash       · 5rpm/20rpd  · Free ✅",
            "gemini-2.5-flash-lite  · 10rpm/20rpd · Free ✅",
            "gemini-3-flash         · 5rpm/20rpd  · Free ✅",
            "gemini-3.1-flash-lite  · 15rpm/500rpd· Free ✅ BEST",
            "gemini-2.5-pro         · Paid 💰 · Best Quality",
            "gemini-3.1-pro         · Paid 💰 · Pro Quality",
        ]
        GEMINI_MODEL_MAP = {
            "gemini-2.5-flash       · 5rpm/20rpd  · Free ✅":      "gemini-2.5-flash",
            "gemini-2.5-flash-lite  · 10rpm/20rpd · Free ✅":       "gemini-2.5-flash-lite",
            "gemini-3-flash         · 5rpm/20rpd  · Free ✅":       "gemini-3-flash",
            "gemini-3.1-flash-lite  · 15rpm/500rpd· Free ✅ BEST":  "gemini-3.1-flash-lite",
            "gemini-2.5-pro         · Paid 💰 · Best Quality":      "gemini-2.5-pro",
            "gemini-3.1-pro         · Paid 💰 · Pro Quality":       "gemini-3.1-pro",
        }
        GEMINI_MODEL_REV = {v: k for k, v in GEMINI_MODEL_MAP.items()}
        self._gemini_model_map = GEMINI_MODEL_MAP
        cur_gem = config.get("gemini_model", "gemini-2.5-flash")
        self._gemini_model_var = ctk.StringVar(
            value=GEMINI_MODEL_REV.get(cur_gem, GEMINI_MODELS[0])
        )
        self._gemini_model_dropdown = ctk.CTkOptionMenu(
            self._gemini_frame,
            values=GEMINI_MODELS,
            variable=self._gemini_model_var,
            font=("Share Tech Mono", 11),
            text_color=TEXT_PRI, fg_color=BG_SEC,
            button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI,
            corner_radius=0,
        )
        self._gemini_model_dropdown.pack(anchor="w", padx=10, pady=(2, 6), fill="x")

        # ── Ollama frame (shown when Ollama selected) ──────────────────────
        self._ollama_frame = ctk.CTkFrame(c11, fg_color="transparent")
        self._ollama_detail_lbl = ctk.CTkLabel(
            self._ollama_frame,
            text="Status: checking…",
            font=("Share Tech Mono", 10, "bold"),
            text_color=TEXT_HINT, anchor="w", wraplength=0,
        )
        self._ollama_detail_lbl.pack(anchor="w", padx=10, pady=(0, 2))

        url_r = ctk.CTkFrame(self._ollama_frame, fg_color="transparent")
        url_r.pack(fill="x", padx=8, pady=(2, 2))
        ctk.CTkLabel(url_r, text="URL:", font=("Share Tech Mono", 11), text_color=TEXT_SEC).pack(side="left")
        self._ollama_url_entry = ctk.CTkEntry(
            url_r, font=("Share Tech Mono", 11),
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT_PRI, corner_radius=0,
        )
        self._ollama_url_entry.insert(0, config.get("ollama_url", "http://localhost:11434"))
        self._ollama_url_entry.pack(side="left", fill="x", expand=True, padx=(6, 4))
        self._ollama_url_entry.bind("<FocusIn>",  lambda e: self._ollama_url_entry.configure(border_width=2, border_color=ACCENT_PRI))
        self._ollama_url_entry.bind("<FocusOut>", lambda e: self._ollama_url_entry.configure(border_width=1, border_color=BORDER))
        ctk.CTkButton(
            url_r, text="TEST", width=50,
            font=("Share Tech Mono", 11, "bold"),
            text_color=ACCENT_GRN, fg_color="transparent",
            hover_color=BG_CARD, border_color=ACCENT_GRN, border_width=1, corner_radius=0,
            command=self._test_ollama_connection,
        ).pack(side="left")

        mod_r = ctk.CTkFrame(self._ollama_frame, fg_color="transparent")
        mod_r.pack(fill="x", padx=8, pady=(2, 4))
        ctk.CTkLabel(mod_r, text="Model:", font=("Share Tech Mono", 11), text_color=TEXT_SEC).pack(side="left")
        self._ollama_model_entry = ctk.CTkEntry(
            mod_r, font=("Share Tech Mono", 11),
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT_PRI, corner_radius=0,
        )
        self._ollama_model_entry.insert(0, config.get("ollama_model", "llama3"))
        self._ollama_model_entry.pack(side="left", fill="x", expand=True, padx=(6, 4))
        self._ollama_model_entry.bind("<FocusIn>",  lambda e: self._ollama_model_entry.configure(border_width=2, border_color=ACCENT_PRI))
        self._ollama_model_entry.bind("<FocusOut>", lambda e: self._ollama_model_entry.configure(border_width=1, border_color=BORDER))
        ctk.CTkButton(
            mod_r, text="↻", width=36,
            font=("Share Tech Mono", 13, "bold"),
            text_color=ACCENT_PRI, fg_color="transparent",
            hover_color=BG_CARD, border_color=ACCENT_PRI, border_width=1, corner_radius=0,
            command=self._refresh_ollama_models,
        ).pack(side="left")
        self._ollama_model_hint = ctk.CTkLabel(
            self._ollama_frame,
            text="   ↳  Detected models will appear above",
            font=("Share Tech Mono", 10), text_color=TEXT_HINT, anchor="w",
        )
        self._ollama_model_hint.pack(anchor="w", padx=8, pady=(0, 4))

        # Show correct frame on init
        self._on_provider_switch(self._provider_var.get())

        # [1,2] Quick links / notes cell
        c12 = _cell(1, 2)
        _cell_lbl(c12, "PIPELINE NOTES")
        notes = (
            "• Script review pause → edit narration before footage download\n"
            "• Video preview pause → watch final video before upload\n"
            "• Uncheck both for fully automated overnight runs\n"
            "• Language applies to script + voiceover (Edge TTS + OmniVoice)\n"
            "• Output folder is relative to project root unless full path given"
        )
        ctk.CTkLabel(
            c12, text=notes,
            font=("Share Tech Mono", 11),
            text_color=TEXT_HINT, anchor="w",
            justify="left", wraplength=0,
        ).pack(anchor="w", padx=10, pady=(2, 8))



    def _sync_upload_controls(self):
        """Disable upload visibility mode when YouTube upload is turned off."""
        if not hasattr(self, "_upload"):
            return
        if self._upload_enabled_var.get():
            self._upload.configure(state="normal")
        else:
            self._upload.configure(state="disabled")

    # _build_script_generation_section removed — functionality merged into
    # the "AI SCRIPT PROVIDER" cell in _build_video_format_section (quick grid).

    def _on_provider_switch(self, value: str):
        self._gemini_frame.pack_forget()
        self._ollama_frame.pack_forget()
        if value == "Ollama":
            self._ollama_frame.pack(fill="x")
        else:
            self._gemini_frame.pack(fill="x")

    # ── (legacy placeholder — kept for grep-ability) ──────────────────────
    def _build_script_generation_section_REMOVED(self, parent):
        # Model IDs verified from Google AI Studio Rate Limit page (Mar 2026)
        # Format: "Display · RPM/RPD · Cost"
        GEMINI_MODELS = [
            "gemini-2.5-flash       · 5rpm/20rpd  · Free ✅",
            "gemini-2.5-flash-lite  · 10rpm/20rpd · Free ✅",
            "gemini-3-flash         · 5rpm/20rpd  · Free ✅",
            "gemini-3.1-flash-lite  · 15rpm/500rpd· Free ✅ BEST",
            "gemini-2.5-pro         · Paid 💰 · Best Quality",
            "gemini-3.1-pro         · Paid 💰 · Pro Quality",
        ]
        GEMINI_MODEL_MAP = {
            "gemini-2.5-flash       · 5rpm/20rpd  · Free ✅":       "gemini-2.5-flash",
            "gemini-2.5-flash-lite  · 10rpm/20rpd · Free ✅":        "gemini-2.5-flash-lite",
            "gemini-3-flash         · 5rpm/20rpd  · Free ✅":        "gemini-3-flash",
            "gemini-3.1-flash-lite  · 15rpm/500rpd· Free ✅ BEST":   "gemini-3.1-flash-lite",
            "gemini-2.5-pro         · Paid 💰 · Best Quality":       "gemini-2.5-pro",
            "gemini-3.1-pro         · Paid 💰 · Pro Quality":        "gemini-3.1-pro",
        }
        GEMINI_MODEL_REV = {v: k for k, v in GEMINI_MODEL_MAP.items()}

        self._gemini_model_map = GEMINI_MODEL_MAP

        section = self._section(
            parent, ">> [ SCRIPT GENERATION ]",
            "AI provider aur model choose karo — Gemini free hai, Ollama local/free"
        )

        # ── AI Provider toggle ──────────────────────────────────────────────
        prov_row = ctk.CTkFrame(section, fg_color="transparent")
        prov_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(
            prov_row, text="AI PROVIDER:",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC, width=260, anchor="w"
        ).pack(side="left", padx=5)

        current_provider = config.get("script_provider", "gemini")
        _prov_display = {"gemini": "Gemini", "ollama": "Ollama"}
        self._provider_var = ctk.StringVar(value=_prov_display.get(current_provider, "Gemini"))
        self._provider_seg = ctk.CTkSegmentedButton(
            prov_row,
            values=["Gemini", "Ollama"],
            variable=self._provider_var,
            font=("Share Tech Mono", 13, "bold"),
            text_color=TEXT_PRI,
            fg_color=BG_MAIN,
            selected_color=ACCENT_PRI,
            selected_hover_color=ACCENT_SEC,
            unselected_color=BG_CARD,
            unselected_hover_color=BORDER,
            corner_radius=0,
            command=self._on_provider_switch,
        )
        self._provider_seg.pack(side="left", padx=10)

        # ── Ollama status badge (shown inline next to segment) ──────────────
        self._ollama_status_lbl = ctk.CTkLabel(
            prov_row, text="⬤ checking…",
            font=("Share Tech Mono", 11), text_color=TEXT_HINT,
        )
        self._ollama_status_lbl.pack(side="left", padx=(6, 0))
        threading.Thread(target=self._probe_ollama_async, daemon=True).start()

        # ── Gemini frame ────────────────────────────────────────────────────
        self._gemini_frame = ctk.CTkFrame(section, fg_color="transparent")

        gem_row = ctk.CTkFrame(self._gemini_frame, fg_color="transparent")
        gem_row.pack(fill="x", pady=4)
        ctk.CTkLabel(
            gem_row, text="GEMINI MODEL:",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC, width=260, anchor="w"
        ).pack(side="left", padx=5)

        cur_gem = config.get("gemini_model", "gemini-2.5-flash")
        cur_gem_display = GEMINI_MODEL_REV.get(cur_gem, GEMINI_MODELS[0])
        self._gemini_model_var = ctk.StringVar(value=cur_gem_display)
        self._gemini_model_dropdown = ctk.CTkOptionMenu(
            gem_row,
            values=GEMINI_MODELS,
            variable=self._gemini_model_var,
            font=("Share Tech Mono", 13),
            text_color=TEXT_PRI, fg_color=BG_SEC,
            button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI,
            corner_radius=0, width=280,
        )
        self._gemini_model_dropdown.pack(side="left", padx=10)

        # ── Ollama frame ─────────────────────────────────────────────────────
        self._ollama_frame = ctk.CTkFrame(section, fg_color="transparent")

        # Ollama status info card
        ollama_info_card = ctk.CTkFrame(
            self._ollama_frame, fg_color=BG_CARD, corner_radius=0,
            border_width=1, border_color=BORDER,
        )
        ollama_info_card.pack(fill="x", padx=5, pady=(4, 6))
        ctk.CTkLabel(
            ollama_info_card,
            text="🦙  OLLAMA  —  Free local LLM (llama3, mistral, phi3, gemma2 …)",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_PRI, anchor="w",
        ).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            ollama_info_card,
            text=(
                "   • ollama.com se download karo → install karo → `ollama serve` chalao\n"
                "   • Model download: `ollama pull llama3`  (ya neeche PULL button se)\n"
                "   • No internet needed after install  |  Free  |  Runs on CPU/GPU"
            ),
            font=("Share Tech Mono", 11), text_color=TEXT_SEC, anchor="w", justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        self._ollama_detail_lbl = ctk.CTkLabel(
            ollama_info_card, text="Status: checking…",
            font=("Share Tech Mono", 11, "bold"), text_color=TEXT_HINT, anchor="w",
        )
        self._ollama_detail_lbl.pack(anchor="w", padx=10, pady=(0, 8))

        # URL row
        url_row = ctk.CTkFrame(self._ollama_frame, fg_color="transparent")
        url_row.pack(fill="x", pady=4)
        lbl_url = ctk.CTkFrame(url_row, fg_color="transparent", width=260)
        lbl_url.pack(side="left")
        lbl_url.pack_propagate(False)
        ctk.CTkLabel(lbl_url, text="OLLAMA URL:", anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=5)
        ctk.CTkLabel(lbl_url, text="default: http://localhost:11434", anchor="w",
                     font=("Share Tech Mono", 10), text_color=TEXT_HINT).pack(anchor="w", padx=5)
        self._ollama_url_entry = ctk.CTkEntry(
            url_row, width=300, font=("Share Tech Mono", 13),
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT_PRI, corner_radius=0,
        )
        self._ollama_url_entry.insert(0, config.get("ollama_url", "http://localhost:11434"))
        self._ollama_url_entry.pack(side="left", padx=10)
        self._ollama_url_entry.bind("<FocusIn>",  lambda e: self._ollama_url_entry.configure(border_width=2, border_color=ACCENT_PRI))
        self._ollama_url_entry.bind("<FocusOut>", lambda e: self._ollama_url_entry.configure(border_width=1, border_color=BORDER))

        ctk.CTkButton(
            url_row, text="TEST", width=60,
            font=("Share Tech Mono", 12, "bold"),
            text_color=ACCENT_GRN, fg_color="transparent",
            hover_color=BG_CARD, border_color=ACCENT_GRN, border_width=1, corner_radius=0,
            command=self._test_ollama_connection,
        ).pack(side="left", padx=4)

        # Model row
        model_row = ctk.CTkFrame(self._ollama_frame, fg_color="transparent")
        model_row.pack(fill="x", pady=4)
        lbl_mod = ctk.CTkFrame(model_row, fg_color="transparent", width=260)
        lbl_mod.pack(side="left")
        lbl_mod.pack_propagate(False)
        ctk.CTkLabel(lbl_mod, text="OLLAMA MODEL:", anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=5)
        ctk.CTkLabel(lbl_mod, text="e.g. llama3, mistral, phi3, gemma2", anchor="w",
                     font=("Share Tech Mono", 10), text_color=TEXT_HINT).pack(anchor="w", padx=5)
        self._ollama_model_entry = ctk.CTkEntry(
            model_row, width=220, font=("Share Tech Mono", 13),
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT_PRI, corner_radius=0,
        )
        self._ollama_model_entry.insert(0, config.get("ollama_model", "llama3"))
        self._ollama_model_entry.pack(side="left", padx=10)
        self._ollama_model_entry.bind("<FocusIn>",  lambda e: self._ollama_model_entry.configure(border_width=2, border_color=ACCENT_PRI))
        self._ollama_model_entry.bind("<FocusOut>", lambda e: self._ollama_model_entry.configure(border_width=1, border_color=BORDER))

        ctk.CTkButton(
            model_row, text="↻ DETECT MODELS", width=140,
            font=("Share Tech Mono", 12, "bold"),
            text_color=ACCENT_PRI, fg_color="transparent",
            hover_color=BG_CARD, border_color=ACCENT_PRI, border_width=1, corner_radius=0,
            command=self._refresh_ollama_models,
        ).pack(side="left", padx=4)

        self._ollama_model_hint = ctk.CTkLabel(
            self._ollama_frame,
            text="   ↳  Detected models will appear above — type model name manually if not listed",
            font=("Share Tech Mono", 11), text_color=TEXT_HINT, anchor="w",
        )
        self._ollama_model_hint.pack(anchor="w", padx=10, pady=(0, 4))

        # ── Language Warning Card ─────────────────────────────────────────────
        lang_warn_card = ctk.CTkFrame(
            self._ollama_frame, fg_color="#1A0A00", corner_radius=0,
            border_width=2, border_color=ACCENT_WARN,
        )
        lang_warn_card.pack(fill="x", padx=5, pady=(6, 4))

        ctk.CTkLabel(
            lang_warn_card,
            text="⚠️  LANGUAGE SUPPORT WARNING",
            font=("Share Tech Mono", 12, "bold"), text_color=ACCENT_WARN, anchor="w",
        ).pack(anchor="w", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            lang_warn_card,
            text=(
                "Zyaadatar Ollama models sirf ENGLISH mein output dete hain.\n"
                "Hindi (Devanagari), Marathi, Bengali, Gujarati, Tamil, Telugu, Odia script\n"
                "produce nahi kar sakte — script English mein hi aayegi."
            ),
            font=("Share Tech Mono", 12), text_color="#FFCC66",
            anchor="w", justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 4))

        ctk.CTkLabel(
            lang_warn_card,
            text=(
                "✅  Multilingual models jo thoda better kaam karte hain:\n"
                "     • qwen2.5   →  `ollama pull qwen2.5`   (best non-English)\n"
                "     • aya-expanse  →  `ollama pull aya-expanse`  (101 languages)\n"
                "     • llama3.1   →  `ollama pull llama3.1`  (partial support)\n"
                "\n"
                "💡  Sahi Hindi/regional script ke liye Gemini use karo."
            ),
            font=("Share Tech Mono", 11), text_color=TEXT_SEC,
            anchor="w", justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 10))

        # Show correct frame on init
        self._on_provider_switch(self._provider_var.get())

    # ── Ollama helpers ────────────────────────────────────────────────────
    def _probe_ollama_async(self):
        """Background thread: probe Ollama and update status labels."""
        try:
            from modules.scripter import check_ollama_status
            installed, running, models = check_ollama_status()
        except Exception:
            installed, running, models = False, False, []

        def _update():
            if running:
                badge = f"⬤ Running  ({len(models)} model{'s' if len(models) != 1 else ''} installed)"
                color = ACCENT_GRN
                detail = (
                    f"✅ Ollama is running at {config.get('ollama_url', 'http://localhost:11434')}\n"
                    f"   Installed models: {', '.join(models) if models else '(none pulled yet)'}"
                )
                detail_color = ACCENT_GRN
            elif installed:
                badge = "⬤ Installed (not running)"
                color = ACCENT_WARN
                detail = (
                    "⚠️  Ollama is installed but server is not running.\n"
                    "   Run: `ollama serve`  in a terminal to start it."
                )
                detail_color = ACCENT_WARN
            else:
                badge = "⬤ Not found"
                color = ACCENT_RED
                detail = (
                    "❌  Ollama not found.\n"
                    "   Download from: https://ollama.com  then run `ollama serve`."
                )
                detail_color = ACCENT_RED

            try:
                self._ollama_status_lbl.configure(text=badge, text_color=color)
                if hasattr(self, "_ollama_detail_lbl"):
                    self._ollama_detail_lbl.configure(text=detail, text_color=detail_color)
                if running and models and hasattr(self, "_ollama_model_entry"):
                    current_val = self._ollama_model_entry.get().strip()
                    if not current_val or current_val == "llama3":
                        self._ollama_model_entry.delete(0, "end")
                        self._ollama_model_entry.insert(0, models[0])
                if running and models and hasattr(self, "_ollama_model_hint"):
                    self._ollama_model_hint.configure(
                        text=f"   ↳  Detected: {' | '.join(models[:6])}{'…' if len(models) > 6 else ''}"
                    )
            except Exception:
                pass

        try:
            self.after(0, _update)
        except Exception:
            pass

    def _test_ollama_connection(self):
        """Test the currently entered Ollama URL."""
        url = self._ollama_url_entry.get().strip()
        if not url:
            return
        import requests as _req
        try:
            r = _req.get(f"{url.rstrip('/')}/api/tags", timeout=5)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                msg = f"✅ Connected!  {len(models)} model(s): {', '.join(models[:4]) or '(none pulled)'}"
                self._ollama_detail_lbl.configure(text=msg, text_color=ACCENT_GRN)
                self._ollama_status_lbl.configure(
                    text=f"⬤ Running ({len(models)} models)", text_color=ACCENT_GRN
                )
                if models and hasattr(self, "_ollama_model_hint"):
                    self._ollama_model_hint.configure(
                        text=f"   ↳  Detected: {' | '.join(models[:6])}{'…' if len(models) > 6 else ''}"
                    )
            else:
                self._ollama_detail_lbl.configure(
                    text=f"❌ Server returned HTTP {r.status_code}", text_color=ACCENT_RED
                )
        except Exception as exc:
            self._ollama_detail_lbl.configure(
                text=f"❌ Cannot connect: {exc}", text_color=ACCENT_RED
            )

    def _refresh_ollama_models(self):
        """Re-probe Ollama in background and refresh model list."""
        self._ollama_detail_lbl.configure(text="⟳ Refreshing…", text_color=TEXT_HINT)
        threading.Thread(target=self._probe_ollama_async, daemon=True).start()

    # ── Section 4: Pipeline Settings ──────────────────────────────────────
    def _build_pipeline_section(self, parent):
        section = self._section(
            parent, ">> [ CORE PARAMETERS ]",
            "Documentary + upload ke liye language aur Chrome profiles."
        )

        # Chrome Profiles
        ctk.CTkFrame(section, fg_color=ACCENT_PRI, height=1).pack(fill="x", pady=(18, 5), padx=5)
        ctk.CTkLabel(section, text=">> [ CHROME PROFILES ]",
                     font=("Orbitron", 14, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=10)

        # Chrome profiles info box
        chrome_info = ctk.CTkFrame(section, fg_color="#0A0F1A", corner_radius=0,
                                   border_width=1, border_color=BORDER)
        chrome_info.pack(fill="x", pady=(5, 10), padx=5)
        ctk.CTkLabel(
            chrome_info,
            text=(
                "🌐  YouTube Auto-Upload ke liye Chrome Profile setup karo:\n"
                "   1.  Google Chrome mein apne YouTube channel account mein login karo\n"
                "   2.  Neeche  [ + SETUP NEW PROFILE ]  dabao → ek naam do (e.g. 'Tech Channel')\n"
                "   3.  Jo Chrome window khule usme YouTube Studio tak jao — profile save ho jaayega\n"
                "   ℹ️   Ek baar setup ke baad dobara login nahi karna — session save rehta hai"
            ),
            font=("Share Tech Mono", 11),
            text_color="#8899BB",
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=12, pady=10)

        profile_row = ctk.CTkFrame(section, fg_color="transparent")
        profile_row.pack(fill="x", pady=5, padx=10)
        self._profile_menu = ctk.CTkOptionMenu(
            profile_row, values=["No Profiles Configured"], width=220,
            font=("Share Tech Mono", 13), text_color=TEXT_PRI,
            fg_color=BG_SEC, button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI, corner_radius=0,
            command=self._on_profile_select
        )
        self._profile_menu.pack(side="left")

        btn_row = ctk.CTkFrame(section, fg_color="transparent")
        btn_row.pack(fill="x", pady=5, padx=10)
        ctk.CTkButton(btn_row, text="[ + SETUP NEW PROFILE ]",
                      font=("Share Tech Mono", 12, "bold"),
                      text_color=ACCENT_PRI, fg_color="transparent",
                      hover_color=BG_CARD, border_color=ACCENT_PRI,
                      border_width=1, corner_radius=0,
                      command=self._setup_new_profile).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_row, text="[ 🗑 REMOVE ]",
                      font=("Share Tech Mono", 12, "bold"),
                      text_color=ACCENT_RED, fg_color="transparent",
                      hover_color=BG_CARD, border_color=ACCENT_RED,
                      border_width=1, corner_radius=0,
                      command=self._remove_profile).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="[ BROWSE EXISTING ]",
                      font=("Share Tech Mono", 12, "bold"),
                      text_color=TEXT_SEC, fg_color="transparent",
                      hover_color=BG_CARD, border_color=BORDER,
                      border_width=1, corner_radius=0,
                      command=self._browse_existing_profile).pack(side="left", padx=5)

        self._refresh_profile_menu()

        # ── After Run: Video Editor ───────────────────────────────────────
        ctk.CTkFrame(section, fg_color=ACCENT_PRI, height=1).pack(fill="x", pady=(18, 5), padx=5)
        ctk.CTkLabel(section, text=">> [ PRE-UPLOAD VIDEO EDITOR ]",
                     font=("Orbitron", 14, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=10)

        editor_info = ctk.CTkFrame(section, fg_color="#0A0F1A", corner_radius=0,
                                   border_width=1, border_color=BORDER)
        editor_info.pack(fill="x", pady=(5, 10), padx=5)
        ctk.CTkLabel(
            editor_info,
            text=(
                "🎬  When enabled, opens a timeline editor BEFORE uploading to YouTube.\n"
                "   • Trim, split, remove, replace, or add video clips\n"
                "   • Edit subtitle text and timing (SRT)\n"
                "   • Add background music with custom volume\n"
                "   • Export clips, audio, or subtitles separately"
            ),
            font=("Share Tech Mono", 11), text_color="#8899BB",
            justify="left", anchor="w",
        ).pack(anchor="w", padx=12, pady=10)

        editor_row = ctk.CTkFrame(section, fg_color="transparent")
        editor_row.pack(fill="x", pady=5, padx=10)
        ctk.CTkLabel(editor_row, text="Enable Pre-Upload Editor:",
                     font=("Share Tech Mono", 12), text_color=TEXT_PRI).pack(side="left")
        self._editor_enabled_var = ctk.BooleanVar(value=bool(config.get("editor.enabled", False)))
        self._editor_sw = ctk.CTkSwitch(
            editor_row,
            text="", variable=self._editor_enabled_var,
            fg_color=BORDER, progress_color=ACCENT_PRI,
            button_color=TEXT_PRI,
        )
        self._editor_sw.pack(side="left", padx=10)
        self._editor_state_lbl = ctk.CTkLabel(
            editor_row,
            text="ON — editor opens after assembly" if self._editor_enabled_var.get() else "OFF — skip directly to upload",
            font=("Share Tech Mono", 11),
            text_color=ACCENT_PRI if self._editor_enabled_var.get() else TEXT_HINT,
        )
        self._editor_state_lbl.pack(side="left", padx=5)
        self._editor_enabled_var.trace_add("write", self._on_editor_toggle)

        self._build_logo_watermark_section(section)

    def _build_logo_watermark_section(self, section):
        ctk.CTkFrame(section, fg_color=ACCENT_PRI, height=1).pack(fill="x", pady=(18, 5), padx=5)
        ctk.CTkLabel(
            section, text=">> [ LOGO WATERMARK ]",
            font=("Orbitron", 14, "bold"), text_color=TEXT_SEC,
        ).pack(anchor="w", padx=10)

        hint = ctk.CTkFrame(section, fg_color="#0A0F1A", corner_radius=0, border_width=1, border_color=BORDER)
        hint.pack(fill="x", pady=(5, 10), padx=5)
        ctk.CTkLabel(
            hint,
            text=(
                "🖼  Choose a PNG or JPG once — saved path is reused for every export.\n"
                "   In Ghost Editor you can turn the overlay on/off per render and set corner + size."
            ),
            font=("Share Tech Mono", 11), text_color="#8899BB",
            justify="left", anchor="w",
        ).pack(anchor="w", padx=12, pady=10)

        row_on = ctk.CTkFrame(section, fg_color="transparent")
        row_on.pack(fill="x", pady=4, padx=10)
        self._logo_enabled_var = ctk.BooleanVar(value=bool(config.get("documentary.logo_enabled", False)))
        ctk.CTkLabel(row_on, text="Enable logo on exports (default):", font=("Share Tech Mono", 12), text_color=TEXT_PRI).pack(side="left")
        ctk.CTkSwitch(
            row_on, text="", variable=self._logo_enabled_var,
            fg_color=BORDER, progress_color=ACCENT_PRI, button_color=TEXT_PRI,
        ).pack(side="left", padx=10)

        row_p = ctk.CTkFrame(section, fg_color="transparent")
        row_p.pack(fill="x", pady=6, padx=10)
        self._logo_path_entry = ctk.CTkEntry(row_p, placeholder_text="No image selected…")
        self._logo_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        lp = (config.get("documentary.logo_path") or "").strip()
        if lp:
            self._logo_path_entry.insert(0, lp)
        ctk.CTkButton(
            row_p, text="BROWSE…", width=100, corner_radius=0,
            command=self._browse_logo_watermark,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            row_p, text="CLEAR", width=72, corner_radius=0, fg_color="transparent",
            border_width=1, border_color=BORDER,
            command=lambda: self._logo_path_entry.delete(0, "end"),
        ).pack(side="left", padx=4)

        row_pos = ctk.CTkFrame(section, fg_color="transparent")
        row_pos.pack(fill="x", pady=6, padx=10)
        ctk.CTkLabel(row_pos, text="Default corner:", font=("Share Tech Mono", 12), text_color=TEXT_PRI).pack(side="left")
        pos_vals = list(_LOGO_LABEL_TO_POS.keys())
        _pkey = str(config.get("documentary.logo_position", "bottom_right") or "bottom_right")
        _plab = _LOGO_POS_TO_LABEL.get(_pkey, "Bottom-right")
        self._logo_position_menu = ctk.CTkOptionMenu(row_pos, values=pos_vals, width=160)
        self._logo_position_menu.set(_plab if _plab in pos_vals else pos_vals[0])
        self._logo_position_menu.pack(side="left", padx=10)

        row_sc = ctk.CTkFrame(section, fg_color="transparent")
        row_sc.pack(fill="x", pady=6, padx=10)
        ctk.CTkLabel(row_sc, text="Size (% of video width):", font=("Share Tech Mono", 12), text_color=TEXT_PRI).pack(side="left")
        self._logo_scale_slider = ctk.CTkSlider(row_sc, from_=0.06, to=0.35, number_of_steps=29)
        self._logo_scale_slider.set(float(config.get("documentary.logo_scale", 0.15)))
        self._logo_scale_slider.pack(side="left", fill="x", expand=True, padx=10)
        self._logo_scale_lbl = ctk.CTkLabel(row_sc, text="", width=44, font=("Share Tech Mono", 11), text_color=TEXT_HINT)
        self._logo_scale_lbl.pack(side="left")
        self._logo_scale_slider.configure(command=self._on_logo_scale_slide)
        self._on_logo_scale_slide(self._logo_scale_slider.get())

        row_mg = ctk.CTkFrame(section, fg_color="transparent")
        row_mg.pack(fill="x", pady=6, padx=10)
        ctk.CTkLabel(row_mg, text="Edge margin (px):", font=("Share Tech Mono", 12), text_color=TEXT_PRI).pack(side="left")
        self._logo_margin_entry = ctk.CTkEntry(row_mg, width=56)
        self._logo_margin_entry.pack(side="left", padx=10)
        self._logo_margin_entry.insert(0, str(int(config.get("documentary.logo_margin", 24))))

        row_op = ctk.CTkFrame(section, fg_color="transparent")
        row_op.pack(fill="x", pady=(6, 12), padx=10)
        ctk.CTkLabel(row_op, text="Opacity:", font=("Share Tech Mono", 12), text_color=TEXT_PRI).pack(side="left")
        self._logo_opacity_slider = ctk.CTkSlider(row_op, from_=0.25, to=1.0, number_of_steps=15)
        self._logo_opacity_slider.set(float(config.get("documentary.logo_opacity", 1.0)))
        self._logo_opacity_slider.pack(side="left", fill="x", expand=True, padx=10)
        self._logo_opacity_lbl = ctk.CTkLabel(row_op, text="", width=36, font=("Share Tech Mono", 11), text_color=TEXT_HINT)
        self._logo_opacity_lbl.pack(side="left")
        self._logo_opacity_slider.configure(command=self._on_logo_opacity_slide)
        self._on_logo_opacity_slide(self._logo_opacity_slider.get())

    def _on_logo_scale_slide(self, val):
        try:
            self._logo_scale_lbl.configure(text=f"{float(val)*100:.0f}%")
        except Exception:
            pass

    def _on_logo_opacity_slide(self, val):
        try:
            self._logo_opacity_lbl.configure(text=f"{float(val)*100:.0f}%")
        except Exception:
            pass

    def _browse_logo_watermark(self):
        from tkinter import messagebox
        p = filedialog.askopenfilename(
            title="Logo image (PNG or JPEG)",
            filetypes=[
                ("PNG / JPEG", "*.png *.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
            ],
        )
        if not p:
            return
        src = Path(p)
        ext = src.suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg"):
            messagebox.showerror("Logo", "Choose a PNG or JPG file.")
            return
        dest_dir = config.path.parent / "watermark_assets"
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"user_logo{ext}"
            shutil.copy2(src, dest)
        except OSError as exc:
            messagebox.showerror("Logo", str(exc))
            return
        self._logo_path_entry.delete(0, "end")
        self._logo_path_entry.insert(0, str(dest.resolve()))

    def _on_editor_toggle(self, *_):
        val = self._editor_enabled_var.get()
        self._editor_state_lbl.configure(
            text="ON — editor opens after assembly" if val else "OFF — skip directly to upload",
            text_color=ACCENT_PRI if val else TEXT_HINT,
        )


    def _browse_ref_audio(self):
        path = filedialog.askopenfilename(
            title="Locate Reference Audio File",
            filetypes=[("Audio Files", "*.wav *.mp3 *.m4a"), ("All Files", "*.*")],
        )
        if path:
            self._ref_audio.delete(0, "end")
            self._ref_audio.insert(0, path)

    def _browse_omnivoice_server(self):
        path = filedialog.askopenfilename(
            title="Locate OmniVoice run.bat",
            filetypes=[("Batch Files", "*.bat"), ("All Files", "*.*")],
        )
        if path:
            self._omnivoice_server_path.delete(0, "end")
            self._omnivoice_server_path.insert(0, path)

    def _browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self._output_dir.delete(0, "end")
            self._output_dir.insert(0, path)

    # ── Profile helpers ───────────────────────────────────────────────────
    def _refresh_profile_menu(self):
        config.load()
        profiles = config.get("pipeline.chrome_profiles", [])
        idx = config.get("pipeline.active_profile_index", 0)
        if not profiles:
            self._profile_menu.configure(values=["No Profiles Configured"])
            self._profile_menu.set("No Profiles Configured")
            if hasattr(self.app_ref, "documentary_tab"):
                self.app_ref.documentary_tab.update_uplink_status("No Profile")
        else:
            names = [p["name"] for p in profiles]
            self._profile_menu.configure(values=names)
            if 0 <= idx < len(names):
                self._profile_menu.set(names[idx])
                if hasattr(self.app_ref, "documentary_tab"):
                    self.app_ref.documentary_tab.update_uplink_status(names[idx])
            else:
                self._profile_menu.set(names[0])
                config.set("pipeline.active_profile_index", 0)
                config.save()
                if hasattr(self.app_ref, "documentary_tab"):
                    self.app_ref.documentary_tab.update_uplink_status(names[0])

    def _on_profile_select(self, value):
        profiles = config.get("pipeline.chrome_profiles", [])
        for i, p in enumerate(profiles):
            if p["name"] == value:
                config.set("pipeline.active_profile_index", i)
                config.save()
                if hasattr(self.app_ref, "documentary_tab"):
                    self.app_ref.documentary_tab.update_uplink_status(value)
                break

    def _setup_new_profile(self):
        dialog = ctk.CTkInputDialog(
            text="Profile ka naam daalo (e.g. 'Tech Channel'):",
            title="New Chrome Profile"
        )
        name = dialog.get_input()
        if name:
            import threading, asyncio
            from setup_chrome_profile import _run_with_name

            def run_setup():
                asyncio.run(_run_with_name(name))
                self.after(0, self._refresh_profile_menu)

            threading.Thread(target=run_setup, daemon=True).start()

    def _remove_profile(self):
        profiles = config.get("pipeline.chrome_profiles", [])
        idx = config.get("pipeline.active_profile_index", 0)
        if profiles and 0 <= idx < len(profiles):
            profiles.pop(idx)
            config.set("pipeline.chrome_profiles", profiles)
            config.set("pipeline.active_profile_index", 0)
            config.save()
            self._refresh_profile_menu()

    def _browse_existing_profile(self):
        path = filedialog.askdirectory(title="Locate 'User Data' folder of Chrome")
        if path:
            dialog = ctk.CTkInputDialog(
                text="Profile ka naam daalo (e.g. 'Tech Channel'):",
                title="New Chrome Profile"
            )
            name = dialog.get_input()
            if name:
                profiles = config.get("pipeline.chrome_profiles", [])
                profiles.append({
                    "name": name,
                    "path": path.replace("\\", "/"),
                    "profile_name": "Default"
                })
                config.set("pipeline.chrome_profiles", profiles)
                config.set("pipeline.active_profile_index", len(profiles) - 1)
                config.save()
                self._refresh_profile_menu()

    # ── Save Action ───────────────────────────────────────────────────────
    def _save(self):
        self._save_btn.configure(fg_color=ACCENT_GRN, text_color=BG_MAIN, text="[ SAVED ✓ ]")

        for key_path, entry in self._key_entries.items():
            config.set(key_path, entry.get().strip())

        config.set("tts.backend",          self._tts_val)
        config.set("tts.reference_audio",  self._ref_audio.get().strip())
        if hasattr(self, "_omnivoice_server_path"):
            config.set("tts.omnivoice_server_path", self._omnivoice_server_path.get().strip())
        if hasattr(self, "_omnivoice_autostart_var"):
            config.set("tts.omnivoice_autostart", bool(self._omnivoice_autostart_var.get()))
        if hasattr(self, "_omnivoice_mode"):
            config.set("tts.omnivoice_mode", OMNIVOICE_MODE_OPTIONS.get(self._omnivoice_mode.get(), "clone"))
        if hasattr(self, "_omnivoice_ref_voice_name"):
            config.set("tts.omnivoice_ref_voice_name", self._omnivoice_ref_voice_name.get().strip()[:120])
        if hasattr(self, "_omnivoice_transcript"):
            config.set("tts.omnivoice_ref_transcript", self._omnivoice_transcript.get().strip())
        if hasattr(self, "_omnivoice_model"):
            config.set("tts.omnivoice_model_id", self._omnivoice_model.get().strip() or "k2-fsa/OmniVoice")
        if hasattr(self, "_omnivoice_voice"):
            config.set("tts.omnivoice_design_voice", OMNIVOICE_VOICE_OPTIONS.get(self._omnivoice_voice.get(), "custom"))
        if hasattr(self, "_omnivoice_style"):
            config.set("tts.omnivoice_speaking_style", OMNIVOICE_STYLE_OPTIONS.get(self._omnivoice_style.get(), "default"))
        if hasattr(self, "_omnivoice_quality"):
            config.set("tts.omnivoice_quality_preset", OMNIVOICE_QUALITY_OPTIONS.get(self._omnivoice_quality.get(), "balanced"))
        if hasattr(self, "_omnivoice_gender"):
            config.set("tts.omnivoice_voice_gender", OMNIVOICE_GENDER_OPTIONS.get(self._omnivoice_gender.get(), ""))
        if hasattr(self, "_omnivoice_instruct"):
            config.set("tts.omnivoice_extra_instruct", self._omnivoice_instruct.get().strip())
        if hasattr(self, "_omnivoice_language"):
            config.set("tts.omnivoice_language_hint", self._omnivoice_language.get().strip())
        config.set("tts.edge_tts_voice",             self._edge_voice.get())
        config.set("tts.elevenlabs_voice_id",        self._eleven_voice.get().strip())

        # ElevenLabs realism tuning (entry-based)
        def _safe_float(entry, default):
            try:
                return max(0.0, min(1.0, float(entry.get().strip())))
            except (ValueError, AttributeError):
                return default
        if hasattr(self, "_eleven_stability"):
            config.set("tts.elevenlabs_stability",        _safe_float(self._eleven_stability, 0.30))
            config.set("tts.elevenlabs_similarity_boost", _safe_float(self._eleven_similarity, 0.85))
            config.set("tts.elevenlabs_style",            _safe_float(self._eleven_style, 0.45))

        if hasattr(self, "_script_review_var"):
            config.set("script_review_enabled", bool(self._script_review_var.get()))

        if hasattr(self, "_video_preview_var"):
            config.set("video_preview_enabled", bool(self._video_preview_var.get()))

        if hasattr(self, "_editor_enabled_var"):
            config.set("editor.enabled", bool(self._editor_enabled_var.get()))

        if hasattr(self, "_provider_var"):
            _prov_map = {"Gemini": "gemini", "Ollama": "ollama"}
            provider = _prov_map.get(self._provider_var.get(), "gemini")
            config.set("script_provider", provider)
            config.set("gemini_model", self._gemini_model_map.get(self._gemini_model_var.get(), "gemini-2.0-flash"))
            if hasattr(self, "_ollama_url_entry"):
                config.set("ollama_url", self._ollama_url_entry.get().strip() or "http://localhost:11434")
            if hasattr(self, "_ollama_model_entry"):
                config.set("ollama_model", self._ollama_model_entry.get().strip() or "llama3")

        _lang_raw = self._lang.get()
        _lang_code = getattr(self, "_lang_label_to_code", {}).get(_lang_raw, _lang_raw)
        config.set("pipeline.language", _lang_code)
        config.set("pipeline.upload_enabled",       bool(self._upload_enabled_var.get()))
        config.set("pipeline.upload_mode",           self._upload.get())
        config.set("pipeline.output_folder",         self._output_dir.get().strip())

        if hasattr(self, "_logo_enabled_var"):
            config.set("documentary.logo_enabled", bool(self._logo_enabled_var.get()))
            config.set("documentary.logo_path", self._logo_path_entry.get().strip())
            config.set(
                "documentary.logo_position",
                _LOGO_LABEL_TO_POS.get(self._logo_position_menu.get(), "bottom_right"),
            )
            config.set("documentary.logo_scale", float(self._logo_scale_slider.get()))
            try:
                config.set("documentary.logo_margin", int(self._logo_margin_entry.get().strip() or "24"))
            except ValueError:
                config.set("documentary.logo_margin", 24)
            config.set("documentary.logo_opacity", float(self._logo_opacity_slider.get()))

        config.save()
        self.app_ref.update_backend_labels()

        self.after(2000, lambda: self._save_btn.configure(
            fg_color="transparent", text_color=ACCENT_PRI, text="[ SAVE CONFIG ]"
        ))

    def _open_env_local(self):
        config.open_env_local()

    # ── Section: License ──────────────────────────────────────────────────
    def _build_license_section(self, parent):
        section = self._section(
            parent, ">> [ LICENSE ]",
            "Ghost Creator AI activation status for this device."
        )

        # Status card
        self._lic_card = ctk.CTkFrame(
            section, fg_color=BG_CARD, corner_radius=0,
            border_width=1, border_color=BORDER,
        )
        self._lic_card.pack(fill="x", pady=(4, 10))

        row1 = ctk.CTkFrame(self._lic_card, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(
            row1, text="STATUS:",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC, width=80, anchor="w",
        ).pack(side="left")
        self._lic_status_lbl = ctk.CTkLabel(
            row1, text="⟳  checking…",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_HINT, anchor="w",
        )
        self._lic_status_lbl.pack(side="left", padx=6)

        row_v = ctk.CTkFrame(self._lic_card, fg_color="transparent")
        row_v.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(
            row_v, text="VERSION:",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC, width=80, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            row_v, text=f"v{APP_VERSION}",
            font=("Share Tech Mono", 12), text_color=ACCENT_SEC, anchor="w",
        ).pack(side="left", padx=6)

        row2 = ctk.CTkFrame(self._lic_card, fg_color="transparent")
        row2.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkLabel(
            row2, text="DEVICE:",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC, width=80, anchor="w",
        ).pack(side="left")
        import platform as _platform
        ctk.CTkLabel(
            row2, text=_platform.node() or "This PC",
            font=("Share Tech Mono", 12), text_color=TEXT_SEC, anchor="w",
        ).pack(side="left", padx=6)

        # Buttons row
        btn_row = ctk.CTkFrame(section, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            btn_row,
            text="🔄  Re-check License",
            font=("Share Tech Mono", 12, "bold"),
            text_color=ACCENT_PRI, fg_color="transparent",
            hover_color=BG_CARD, border_color=ACCENT_PRI, border_width=1, corner_radius=0,
            command=self._recheck_license,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="❌  Deactivate",
            font=("Share Tech Mono", 12, "bold"),
            text_color=ACCENT_RED, fg_color="transparent",
            hover_color=BG_CARD, border_color=ACCENT_RED, border_width=1, corner_radius=0,
            command=self._deactivate_license,
        ).pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="⬆  Check for updates",
            font=("Share Tech Mono", 12, "bold"),
            text_color=ACCENT_SEC, fg_color="transparent",
            hover_color=BG_CARD, border_color=ACCENT_SEC, border_width=1, corner_radius=0,
            command=self._check_for_updates,
        ).pack(side="left", padx=(16, 0))

        # Load status immediately
        self._recheck_license()

    def _check_for_updates(self) -> None:
        threading.Thread(target=self._do_check_updates, daemon=True).start()

    def _do_check_updates(self) -> None:
        try:
            from core.update_checker import post_update_check

            data = post_update_check()
        except Exception as exc:
            data = {"success": False, "error": "exception", "message": str(exc)}
        try:
            self.winfo_toplevel().after(0, lambda: self._handle_update_check_response(data))
        except Exception:
            pass

    def _handle_update_check_response(self, data: dict) -> None:
        from tkinter import messagebox

        if not data.get("success"):
            messagebox.showerror(
                "Update check",
                data.get("message")
                or data.get("error")
                or "Could not check for updates.",
            )
            return

        if not data.get("update_available"):
            lv = data.get("latest_version", "?")
            msg = (data.get("message") or "").strip()
            if msg:
                messagebox.showinfo("Updates", msg)
            else:
                messagebox.showinfo(
                    "Up to date",
                    f"You have the latest release (app v{APP_VERSION}; server latest v{lv}).",
                )
            return

        token = data.get("download_token")
        if not token:
            messagebox.showerror(
                "Update",
                "Server reported a new version but did not provide a download. Try again later.",
            )
            return

        notes = (data.get("release_notes") or "").strip()
        latest = data.get("latest_version", "?")
        intro = f"Version {latest} is available (you have v{APP_VERSION})."
        if not messagebox.askyesno(
            "Update available",
            f"{intro}\n\n{notes}\n\nDownload and install now? The app will close when setup runs.",
        ):
            return

        self._run_update_download_dialog(data, token)

    def _run_update_download_dialog(self, data: dict, token: str) -> None:
        from tkinter import messagebox

        import tkinter as tk

        dlg = ctk.CTkToplevel(self)
        dlg.title("Downloading update")
        dlg.geometry("480x180")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.configure(fg_color=BG_MAIN)
        lbl = ctk.CTkLabel(
            dlg,
            text="Preparing download…",
            font=("Share Tech Mono", 12),
            text_color=TEXT_PRI,
        )
        lbl.pack(padx=24, pady=(16, 8))
        pbar = ctk.CTkProgressBar(
            dlg,
            width=400,
            height=14,
            corner_radius=4,
            fg_color=BORDER,
            progress_color=ACCENT_PRI,
        )
        pbar.set(0)
        pbar.pack(padx=24, pady=(0, 16))

        latest = str(data.get("latest_version", "setup")).replace("/", "-")
        safe_name = f"GhostCreator_update_{latest}.exe"
        dest = Path(tempfile.gettempdir()) / safe_name
        sha = data.get("installer_sha256") or None
        if isinstance(sha, str) and not sha.strip():
            sha = None

        def tick() -> None:
            dlg.update_idletasks()
            try:
                self.winfo_toplevel().update_idletasks()
            except tk.TclError:
                pass

        def work() -> None:
            try:
                from core.update_checker import download_installer, launch_installer

                def prog_msg(t: str) -> None:
                    dlg.after(0, lambda x=t: lbl.configure(text=x))

                def prog_r(r: float) -> None:
                    dlg.after(0, lambda u=r: pbar.set(max(0.0, min(1.0, u))))

                download_installer(
                    token,
                    dest,
                    progress=prog_msg,
                    progress_ratio=prog_r,
                    ui_tick=tick,
                    sha256_expected=sha,
                )
                dlg.after(0, lambda: _done_ok())
            except Exception as exc:
                dlg.after(0, lambda: _done_err(exc))

        def _done_ok() -> None:
            try:
                dlg.grab_release()
            except tk.TclError:
                pass
            try:
                dlg.destroy()
            except tk.TclError:
                pass
            try:
                from core.update_checker import launch_installer

                launch_installer(dest)
            except Exception as exc:
                messagebox.showerror("Update", str(exc))
                return
            import os

            os._exit(0)

        def _done_err(exc: BaseException) -> None:
            try:
                dlg.grab_release()
            except tk.TclError:
                pass
            try:
                dlg.destroy()
            except tk.TclError:
                pass
            messagebox.showerror("Download failed", str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _recheck_license(self):
        self._lic_status_lbl.configure(text="⟳  checking…", text_color=TEXT_HINT)
        threading.Thread(target=self._do_recheck, daemon=True).start()

    def _do_recheck(self):
        try:
            from core.license import is_licensed
            valid, message = is_licensed()
        except Exception as exc:
            valid, message = False, str(exc)
        try:
            self.winfo_toplevel().after(0, self._update_lic_status, valid, message)
        except Exception:
            pass


    def _update_lic_status(self, valid: bool, message: str):
        if valid:
            self._lic_status_lbl.configure(text=f"✅  Activated  ({message})", text_color=ACCENT_GRN)
        else:
            self._lic_status_lbl.configure(text=f"❌  {message}", text_color=ACCENT_RED)

    def _deactivate_license(self):
        dialog = ctk.CTkInputDialog(
            text=(
                "Are you sure you want to deactivate Ghost Creator on this device?\n\n"
                "Type  DEACTIVATE  to confirm:"
            ),
            title="Deactivate License",
        )
        answer = dialog.get_input()
        if answer and answer.strip().upper() == "DEACTIVATE":
            from core.license import _revoke_local_license
            _revoke_local_license()
            import sys as _sys
            _sys.exit(0)

    # ── Widget helpers ────────────────────────────────────────────────────
    def _hint(self, parent, text: str):
        """Small dimmed hint line."""
        ctk.CTkLabel(
            parent,
            text=f"   ↳  {text}",
            font=("Share Tech Mono", 11),
            text_color=TEXT_HINT,
            anchor="w",
        ).pack(anchor="w", padx=10, pady=(0, 6))

    def _section(self, parent, title: str, subtitle: str = "") -> ctk.CTkFrame:
        div = ctk.CTkFrame(parent, fg_color=ACCENT_PRI, height=1)
        div.pack(fill="x", pady=(28, 0), padx=5)

        ctk.CTkLabel(
            parent, text=title,
            font=("Orbitron", 18, "bold"), text_color=ACCENT_PRI,
        ).pack(anchor="w", padx=10, pady=(6, 2))

        if subtitle:
            ctk.CTkLabel(
                parent, text=subtitle,
                font=("Share Tech Mono", 12), text_color="#5577AA",
                anchor="w", justify="left",
            ).pack(anchor="w", padx=14, pady=(0, 8))

        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.pack(fill="x", padx=10, pady=(0, 5))
        return content
