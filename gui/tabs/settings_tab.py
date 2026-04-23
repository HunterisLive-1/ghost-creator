"""
gui/tabs/settings_tab.py — Settings Tab Cyberpunk
"""

import threading

import customtkinter as ctk
from pathlib import Path
from tkinter import filedialog

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
        "🎙️ OmniVoice — local clone/design. run.bat (server) ya pip. Reference .wav, GPU help.\n"
        "   Details: neeche fold \"OmniVoice\" mein."
    ),
    "edge_tts": (
        "✅ Edge TTS — free cloud, no key. Hindi/English voices neeche \"Edge TTS & ElevenLabs\" fold mein."
    ),
    "elevenlabs": (
        "⭐ ElevenLabs — API key chahiye; neeche Voice ID + tuning fold mein (paid, best quality)."
    ),
    "google_tts": (
        "☁️ Google Cloud TTS — service-account JSON path API Keys + advanced setup (paid)."
    ),
}

IMG_DESCRIPTIONS = {
    "gemini_imagen": (
        "✅ Imagen-3 — sirf Gemini key, cloud, no GPU. Best default.\n"
        "   Fal/Replicate/Comfy = neeche ComfyUI fold + API keys."
    ),
    "pollinations": (
        "🆓 Pollinations — free, no key; model dropdown image section mein. Basic quality."
    ),
    "comfyui": (
        "⚡ ComfyUI — local, GPU, URL neeche \"ComfyUI URL\" fold mein. ~8188."
    ),
    "fal_ai": (
        "🚀 Fal — fast cloud; API key. Pay-per-image."
    ),
    "stable_horde": (
        "🌐 Stable Horde — free community GPU; key 000… ; slow queue possible."
    ),
    "replicate": (
        "🔧 Replicate — hosted models, API key; many models, pay-per-use."
    ),
    "grok_imagine": (
        "⭐ Grok Imagine — xAI key; Standard/Pro model neeche jab select ho. $0.02–0.07/img."
    ),
}

# ── API key helper info ────────────────────────────────────────────────────────
# Video format GUI labels ↔ config values
_ASPECT_LABEL_FOR_RATIO = {"9:16": "9:16 Shorts", "16:9": "16:9 YouTube"}
_TRANSITION_STYLE_TO_CONFIG = {
    "Cinematic Mix": "cinematic_mix",
    "Fade Only": "fade_only",
    "Zoom Only": "zoom_only",
    "Minimal": "minimal",
}
_TRANSITION_CONFIG_TO_STYLE = {v: k for k, v in _TRANSITION_STYLE_TO_CONFIG.items()}

API_KEY_INFO = {
    "api_keys.gemini":      ("REQUIRED", ACCENT_GRN,  "Script + Image generation  •  Free at: aistudio.google.com/app/apikey"),
    "api_keys.elevenlabs":  ("OPTIONAL", TEXT_HINT,   "Sirf ElevenLabs TTS use karne par chahiye  •  elevenlabs.io"),
    "api_keys.google_tts":  ("OPTIONAL", TEXT_HINT,   "Google Cloud TTS ka service-account JSON file ka PATH daalo"),
    "api_keys.fal_ai":      ("OPTIONAL", TEXT_HINT,   "Sirf Fal.ai image backend use karne par chahiye  •  fal.ai/dashboard"),
    "api_keys.replicate":   ("OPTIONAL", TEXT_HINT,   "Sirf Replicate image backend use karne par chahiye  •  replicate.com"),
    "api_keys.stable_horde":("OPTIONAL", TEXT_HINT,   "Free use ke liye '0000000000' daalo  •  stablehorde.net"),
    "api_keys.pexels":      ("OPTIONAL", TEXT_HINT,   "Documentary footage ke liye real stock videos  •  pexels.com/api (free)"),
    "xai_api_key":          ("OPTIONAL", TEXT_HINT,   "Grok Imagine images + Grok Video clips ke liye  •  console.x.ai"),
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


class SettingsTab(ctk.CTkFrame):
    def __init__(self, master, app_ref, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app_ref = app_ref

        self._key_entries = {}
        self._key_visible = {}

        # State variables
        self._tts_val = config.get("tts.backend", "omnivoice")
        self._img_val = config.get("image.backend", "comfyui")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)

        self._build_beginner_banner(scroll)
        self._build_api_keys_section(scroll)
        self._build_tts_section(scroll)
        self._build_image_section(scroll)
        self._build_video_format_section(scroll)
        self._build_script_generation_section(scroll)
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
                "3) Vision → IMAGEN-3  ·  4) Core → language hi/en/…  ·  5) [ SAVE ] → Pipeline → RUN"
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
            ("Google Cloud TTS (JSON path)","api_keys.google_tts"),
            ("Fal.ai API Key",              "api_keys.fal_ai"),
            ("Replicate API Key",           "api_keys.replicate"),
            ("Stable Horde API Key",        "api_keys.stable_horde"),
            ("Pexels API Key",              "api_keys.pexels"),
            ("xAI API Key",                 "xai_api_key"),
        ]

        more_keys_frame: ctk.CTkFrame | None = None
        for idx, (label_text, key_path) in enumerate(keys):
            if idx == 0:
                key_parent: ctk.CTkFrame = section
            else:
                if more_keys_frame is None:
                    more_keys_frame = self._add_foldable(
                        section, "More API keys (optional — 7 fields)", start_open=False
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
            ("google_tts", "GOOGLE CLOUD"),
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

        _vpe = config.get("tts.voice_post_process", 1)
        if isinstance(_vpe, bool):
            _vpost_on = _vpe
        else:
            try:
                _vpost_on = int(_vpe) != 0
            except (TypeError, ValueError):
                _vpost_on = True
        self._voice_post_var = ctk.BooleanVar(value=_vpost_on)
        ctk.CTkCheckBox(
            tts_config,
            text="Post-process voiceover: FFmpeg cleanup (80 Hz high-pass + loudness normalize) — all TTS",
            variable=self._voice_post_var,
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC,
            fg_color=BG_MAIN, border_color=BORDER,
            hover_color=BG_CARD, checkmark_color=ACCENT_PRI, corner_radius=0,
        ).pack(anchor="w", padx=10, pady=(10, 2))
        self._hint(
            tts_config,
            "Bina manual touch: TTS ke baad level consistent + halka rumble hata. "
            "FFmpeg chahiye. Target LUFS: config / .env  `tts.voice_post_target_lufs` (default -16).",
        )

        _vst = config.get("tts.voice_post_silence_trim", 1)
        if isinstance(_vst, bool):
            _vst_on = _vst
        else:
            try:
                _vst_on = int(_vst) != 0
            except (TypeError, ValueError):
                _vst_on = True
        self._voice_post_silence_var = ctk.BooleanVar(value=_vst_on)
        ctk.CTkCheckBox(
            tts_config,
            text="+ Smart silence: lambi chup kam, chhote word/sentence gaps bane rahen (FFmpeg silenceremove)",
            variable=self._voice_post_silence_var,
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC,
            fg_color=BG_MAIN, border_color=BORDER,
            hover_color=BG_CARD, checkmark_color=ACCENT_PRI, corner_radius=0,
        ).pack(anchor="w", padx=10, pady=(2, 2))
        self._hint(
            tts_config,
            "Fine-tune: `tts.voice_post_silence_min_internal` (sec, lamba dead-air) · "
            "`tts.voice_post_silence_keep` (replaced gap) · `tts.voice_post_silence_threshold_db` — default 0.42 / 0.22 / -46.",
        )
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
            text="Auto-start OmniVoice server before each pipeline run",
            variable=self._omnivoice_autostart_var,
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC,
            fg_color=BG_MAIN, border_color=BORDER,
            hover_color=BG_CARD, checkmark_color=ACCENT_PRI, corner_radius=0,
        ).pack(anchor="w", padx=10, pady=(4, 2))
        self._hint(
            omni_inner,
            "run.bat ka path daalo (e.g. D:/omnivoice/OmniVoice/run.bat). "
            "Auto-start ON → pipeline khud server start karega. "
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
        self._hint(omni_inner, "Chhota clear WAV — jis voice ko clone karna hai (project root ya full path)")

        _auto_raw = config.get("tts.omnivoice_auto_transcribe_ref", 1)
        if isinstance(_auto_raw, bool):
            _auto_on = _auto_raw
        else:
            try:
                _auto_on = bool(int(_auto_raw))
            except (TypeError, ValueError):
                _auto_on = True
        self._omnivoice_auto_ref_var = ctk.BooleanVar(value=_auto_on)
        ctk.CTkCheckBox(
            omni_inner,
            text="Auto-transcribe reference (Whisper — OmniVoice WebUI default, recommended)",
            variable=self._omnivoice_auto_ref_var,
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC,
            fg_color=BG_MAIN, border_color=BORDER,
            hover_color=BG_CARD, checkmark_color=ACCENT_PRI, corner_radius=0,
        ).pack(anchor="w", padx=10, pady=(6, 2))
        self._hint(
            omni_inner,
            "ON = reference clip ka exact text model khud nikaalega (WebUI jaisa). "
            "OFF = neeche manual transcript (exact words) zaroori.",
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
        self._hint(omni_inner, "Sirf jab 'Auto-transcribe' band ho: reference WAV ke exact shabd likho. Khali rehne par auto-ON use karo.")

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

        om_chunk_row = ctk.CTkFrame(omni_inner, fg_color="transparent")
        om_chunk_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(om_chunk_row, text="TEXT CHUNK (chars):", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        _chunk_menu_vals = ["280", "360", "400", "480", "520", "640", "800"]
        try:
            _cur_chunk = int(config.get("tts.omnivoice_text_chunk_chars", 800))
        except (TypeError, ValueError):
            _cur_chunk = 800
        _cur_chunk = max(120, min(800, _cur_chunk))
        if str(_cur_chunk) not in _chunk_menu_vals:
            _cur_chunk = min(_chunk_menu_vals, key=lambda s: abs(int(s) - _cur_chunk))
        self._omnivoice_text_chunk = ctk.CTkOptionMenu(
            om_chunk_row,
            values=_chunk_menu_vals,
            font=("Share Tech Mono", 12), text_color=TEXT_PRI,
            fg_color=BG_SEC, button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI, corner_radius=0,
            width=120,
        )
        self._omnivoice_text_chunk.set(str(_cur_chunk))
        self._omnivoice_text_chunk.pack(side="left", padx=5)
        self._hint(
            omni_inner,
            "TEXT CHUNK: pehle `।.!?` se sentences, phir comma/colon pe pause, phir char limit — alag-alag tone kam. Read timeout: Settings → 5h default (lamba generate).",
        )

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
        self._hint(omni_inner, "WebUI style controls: profile + style + quality + tags. Language hint optional (hi/en etc).")

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

    # ── Section 3: Image Backend ──────────────────────────────────────────
    def _build_image_section(self, parent):
        section = self._section(
            parent, ">> [ VISION MATRIX ]",
            "Video ke liye AI images kaun generate karega. "
            "👉 Beginner? → IMAGEN-3 chuno (sirf Gemini key chahiye, koi setup nahi)."
        )

        options = [
            ("comfyui",       "COMFYUI"),
            ("pollinations",  "POLLINATIONS 🆓"),
            ("gemini_imagen", "IMAGEN-3 ✅"),
            ("fal_ai",        "FAL.AI"),
            ("stable_horde",  "STABLE HORDE"),
            ("replicate",     "REPLICATE"),
            ("grok_imagine",  "GROK IMAGINE ⭐"),
        ]

        btn_frame1 = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame1.pack(fill="x", pady=(5, 3))
        btn_frame2 = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame2.pack(fill="x", pady=(0, 8))

        self._img_btns = {}
        for i, (val, label) in enumerate(options):
            b_frame = btn_frame1 if i < 4 else btn_frame2
            btn = ctk.CTkButton(
                b_frame, text=label, font=("Share Tech Mono", 12, "bold"),
                fg_color="transparent", text_color=TEXT_SEC,
                border_color=BORDER, border_width=1, corner_radius=0,
                command=lambda v=val: self._select_img(v)
            )
            btn.pack(side="left", padx=4, expand=True, fill="x")
            btn.bind("<Enter>", lambda e, b=btn: b.configure(border_color=ACCENT_PRI) if b.cget("fg_color") == "transparent" else None)
            btn.bind("<Leave>", lambda e, b=btn: b.configure(border_color=BORDER)     if b.cget("fg_color") == "transparent" else None)
            self._img_btns[val] = btn

        # Dynamic description box
        self._img_desc = ctk.CTkLabel(
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
        self._img_desc.pack(fill="x", padx=0, pady=(0, 6), ipadx=10, ipady=6)

        # Grok model sub-panel (shown only when Grok Imagine is selected)
        GROK_MODEL_OPTIONS = {
            "Standard · $0.02/img": "grok-2-image-1212",
            "Pro · $0.07/img": "grok-2-image",
        }
        GROK_MODEL_REV = {v: k for k, v in GROK_MODEL_OPTIONS.items()}
        self._grok_model_options = GROK_MODEL_OPTIONS

        self._grok_panel = ctk.CTkFrame(section, fg_color=BG_CARD, corner_radius=0,
                                        border_color=BORDER, border_width=1)
        grok_inner = ctk.CTkFrame(self._grok_panel, fg_color="transparent")
        grok_inner.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(grok_inner, text="GROK MODEL:",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left")
        cur_grok_model = config.get("grok_image_model", "grok-2-image-1212")
        self._grok_model_var = ctk.StringVar(value=GROK_MODEL_REV.get(cur_grok_model, "Standard · $0.02/img"))
        ctk.CTkOptionMenu(
            grok_inner,
            values=list(GROK_MODEL_OPTIONS.keys()),
            variable=self._grok_model_var,
            font=("Share Tech Mono", 13),
            text_color=TEXT_PRI, fg_color=BG_SEC,
            button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI,
            corner_radius=0, width=220,
        ).pack(side="left", padx=10)
        self._hint(self._grok_panel, "Requires xAI API key (set in API Keys section above)")

        self._select_img(self._img_val)

        # ComfyUI URL (fold — Imagen / Grok users skip)
        _comfy_fold = self._add_foldable(
            section, "ComfyUI URL (local SD — if using ComfyUI backend)",
            start_open=False,
        )
        inner_img = ctk.CTkFrame(_comfy_fold, fg_color=BG_MAIN, corner_radius=0,
                                 border_color=BORDER, border_width=1)
        inner_img.pack(fill="x", pady=(0, 4), ipadx=10, ipady=8)

        ctk.CTkLabel(inner_img, text="COMFYUI NODE URL:",
                     font=("Share Tech Mono", 12, "bold"),
                     text_color=TEXT_SEC).pack(anchor="w", padx=10, pady=(8, 0))
        self._comfyui_url = ctk.CTkEntry(inner_img, width=400, font=("Share Tech Mono", 13),
                                         fg_color=BG_MAIN, border_color=BORDER,
                                         text_color=TEXT_PRI, corner_radius=0)
        self._comfyui_url.insert(0, config.get("image.comfyui_url", "http://127.0.0.1:8188"))
        self._comfyui_url.pack(anchor="w", padx=10, pady=(2, 2))
        self._comfyui_url.bind("<FocusIn>",  lambda e: self._comfyui_url.configure(border_width=2, border_color=ACCENT_PRI))
        self._comfyui_url.bind("<FocusOut>", lambda e: self._comfyui_url.configure(border_width=1, border_color=BORDER))
        self._hint(inner_img, "ComfyUI backend only. Default :8188 — server start karo pehle.")

    def _select_img(self, val):
        self._img_val = val
        for v, btn in self._img_btns.items():
            if v == val:
                btn.configure(fg_color=ACCENT_PRI, text_color=BG_MAIN, border_color=ACCENT_PRI)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SEC, border_color=BORDER)
        if hasattr(self, "_img_desc"):
            self._img_desc.configure(text=IMG_DESCRIPTIONS.get(val, ""))
        if hasattr(self, "_grok_panel"):
            if val == "grok_imagine":
                self._grok_panel.pack(fill="x", pady=(0, 8))
            else:
                self._grok_panel.pack_forget()

    # ── Section: Video Format & Effects ───────────────────────────────────
    def _build_video_format_section(self, parent):
        section = self._section(
            parent, ">> [ VIDEO FORMAT & EFFECTS ]",
            "Final MP4 ka aspect ratio aur FFmpeg cinematic intro / scene transitions."
        )

        ctk.CTkLabel(
            section, text="ASPECT RATIO:",
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
        ).pack(anchor="w", padx=10, pady=(4, 2))

        ar_cfg = config.get("aspect_ratio", "9:16")
        if ar_cfg not in _ASPECT_LABEL_FOR_RATIO:
            ar_cfg = "9:16"
        aspect_default = _ASPECT_LABEL_FOR_RATIO[ar_cfg]

        self._aspect_seg = ctk.CTkSegmentedButton(
            section,
            values=["9:16 Shorts", "16:9 YouTube"],
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_PRI,
            fg_color=BG_SEC,
            selected_color=ACCENT_PRI,
            selected_hover_color=ACCENT_SEC,
            unselected_color=BG_CARD,
            unselected_hover_color=BORDER,
            corner_radius=0,
            command=self._on_aspect_segment_change,
        )
        self._aspect_seg.set(aspect_default)
        self._aspect_seg.pack(anchor="w", padx=10, pady=(0, 6), fill="x")
        self._hint(
            section,
            "9:16 = vertical Shorts  |  16:9 = landscape. Change = turant apply + disk save — "
            "[ SAVE CONFIG ] ab optional hai is ke liye.",
        )

        ce = config.get("cinematic_effects", {})
        intro_on = bool(ce.get("intro", True))
        trans_on = bool(ce.get("transitions", True))

        self._ce_intro_var = ctk.BooleanVar(value=intro_on)
        self._ce_trans_var = ctk.BooleanVar(value=trans_on)

        self._video_format_chk_row = ctk.CTkFrame(section, fg_color="transparent")
        self._video_format_chk_row.pack(fill="x", pady=(8, 4), padx=5)

        self._chk_intro = ctk.CTkCheckBox(
            self._video_format_chk_row,
            text="Cinematic Intro",
            variable=self._ce_intro_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
            fg_color=BG_MAIN,
            border_color=BORDER,
            hover_color=BG_CARD,
            checkmark_color=ACCENT_PRI,
            corner_radius=0,
        )
        self._chk_intro.pack(side="left", padx=(5, 24))

        self._chk_trans = ctk.CTkCheckBox(
            self._video_format_chk_row,
            text="Scene Transitions",
            variable=self._ce_trans_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
            fg_color=BG_MAIN,
            border_color=BORDER,
            hover_color=BG_CARD,
            checkmark_color=ACCENT_PRI,
            corner_radius=0,
            command=self._sync_transition_style_visibility,
        )
        self._chk_trans.pack(side="left", padx=(0, 5))

        self._transition_style_row = ctk.CTkFrame(section, fg_color="transparent")
        ctk.CTkLabel(
            self._transition_style_row,
            text="TRANSITION STYLE:",
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
        ).pack(anchor="w", padx=10, pady=(4, 2))
        ts_cfg = ce.get("transition_style", "cinematic_mix")
        ts_label = _TRANSITION_CONFIG_TO_STYLE.get(ts_cfg, "Cinematic Mix")
        self._trans_style = ctk.CTkOptionMenu(
            self._transition_style_row,
            values=["Cinematic Mix", "Fade Only", "Zoom Only", "Minimal"],
            font=("Share Tech Mono", 13),
            text_color=TEXT_PRI,
            fg_color=BG_SEC,
            button_color=BORDER,
            button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD,
            dropdown_text_color=TEXT_PRI,
            corner_radius=0,
            width=200,
        )
        self._trans_style.set(ts_label)
        self._trans_style.pack(anchor="w", padx=10, pady=(0, 4))
        self._hint(self._transition_style_row, "xfade transition pool — sirf tab use hota hai jab Scene Transitions ON ho")

        self._sync_transition_style_visibility()

        ctk.CTkLabel(
            section,
            text="─── Pipeline Behavior ───────────────────────────────────",
            font=("Share Tech Mono", 11),
            text_color=TEXT_HINT,
        ).pack(anchor="w", padx=10, pady=(18, 4))

        self._script_review_var = ctk.BooleanVar(value=bool(config.get("script_review_enabled", True)))
        self._chk_script_review = ctk.CTkCheckBox(
            section,
            text="Pause for script review before generating images",
            variable=self._script_review_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
            fg_color=BG_MAIN,
            border_color=BORDER,
            hover_color=BG_CARD,
            checkmark_color=ACCENT_PRI,
            corner_radius=0,
        )
        self._chk_script_review.pack(anchor="w", padx=10, pady=(2, 2))
        ctk.CTkLabel(
            section,
            text="   ↳  Uncheck for fully automated / unattended runs",
            font=("Share Tech Mono", 11),
            text_color=TEXT_HINT,
            anchor="w",
        ).pack(anchor="w", padx=10, pady=(0, 2))
        self._hint(
            section,
            "When enabled, pipeline pauses after script generation so you can review and edit before images are created.",
        )

        self._video_preview_var = ctk.BooleanVar(value=bool(config.get("video_preview_enabled", True)))
        self._chk_video_preview = ctk.CTkCheckBox(
            section,
            text="Pause for video preview before uploading",
            variable=self._video_preview_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
            fg_color=BG_MAIN,
            border_color=BORDER,
            hover_color=BG_CARD,
            checkmark_color=ACCENT_PRI,
            corner_radius=0,
        )
        self._chk_video_preview.pack(anchor="w", padx=10, pady=(2, 2))
        ctk.CTkLabel(
            section,
            text="   ↳  Opens your media player so you can watch the final video before it uploads",
            font=("Share Tech Mono", 11),
            text_color=TEXT_HINT,
            anchor="w",
        ).pack(anchor="w", padx=10, pady=(0, 2))
        self._hint(
            section,
            "When enabled, pipeline pauses after video assembly so you can preview the result, then approve or cancel the upload.",
        )

    def _sync_transition_style_visibility(self):
        """Show transition style row only when Scene Transitions is checked."""
        if not hasattr(self, "_transition_style_row"):
            return
        if self._ce_trans_var.get():
            self._transition_style_row.pack(
                fill="x", pady=(4, 0), after=self._video_format_chk_row
            )
        else:
            self._transition_style_row.pack_forget()

    def _sync_upload_controls(self):
        """Disable upload visibility mode when YouTube upload is turned off."""
        if not hasattr(self, "_upload"):
            return
        if self._upload_enabled_var.get():
            self._upload.configure(state="normal")
        else:
            self._upload.configure(state="disabled")

    # ── Section: Script Generation ────────────────────────────────────────
    def _build_script_generation_section(self, parent):
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

        OPENAI_MODELS = [
            "gpt-4o (Best · ~$0.01/script)",
            "gpt-4o-mini (Cheap · ~$0.001/script)",
        ]
        OPENAI_MODEL_MAP = {
            "gpt-4o (Best · ~$0.01/script)": "gpt-4o",
            "gpt-4o-mini (Cheap · ~$0.001/script)": "gpt-4o-mini",
        }
        OPENAI_MODEL_REV = {v: k for k, v in OPENAI_MODEL_MAP.items()}

        IMG2VIDEO_OPTIONS = {
            "AnimateDiff · $0.005/clip (Fal)": "animatediff",
            "Stable Video · $0.05/clip (Fal)": "stable_video",
            "Kling Standard · $0.14/clip (Fal)": "kling_standard",
            "Kling Pro · $0.28/clip (Fal)": "kling_pro",
            "Grok Video 5s · $0.25/clip (xAI)": "grok_video_5s",
            "Grok Video 10s · $0.50/clip (xAI)": "grok_video_10s",
        }
        IMG2VIDEO_REV = {v: k for k, v in IMG2VIDEO_OPTIONS.items()}

        self._gemini_model_map = GEMINI_MODEL_MAP
        self._openai_model_map = OPENAI_MODEL_MAP
        self._img2video_map = IMG2VIDEO_OPTIONS

        section = self._section(
            parent, ">> [ SCRIPT GENERATION ]",
            "AI provider aur model choose karo — Gemini free hai, OpenAI paid, Ollama local/free"
        )

        # ── AI Provider toggle ──────────────────────────────────────────────
        prov_row = ctk.CTkFrame(section, fg_color="transparent")
        prov_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(
            prov_row, text="AI PROVIDER:",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC, width=260, anchor="w"
        ).pack(side="left", padx=5)

        current_provider = config.get("script_provider", "gemini")
        _prov_display = {"gemini": "Gemini", "openai": "OpenAI", "ollama": "Ollama"}
        self._provider_var = ctk.StringVar(value=_prov_display.get(current_provider, "Gemini"))
        self._provider_seg = ctk.CTkSegmentedButton(
            prov_row,
            values=["Gemini", "OpenAI", "Ollama"],
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

        # ── OpenAI frame ────────────────────────────────────────────────────
        self._openai_frame = ctk.CTkFrame(section, fg_color="transparent")

        oai_row = ctk.CTkFrame(self._openai_frame, fg_color="transparent")
        oai_row.pack(fill="x", pady=4)
        ctk.CTkLabel(
            oai_row, text="OPENAI MODEL:",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC, width=260, anchor="w"
        ).pack(side="left", padx=5)

        cur_oai = config.get("openai_model", "gpt-4o")
        cur_oai_display = OPENAI_MODEL_REV.get(cur_oai, OPENAI_MODELS[0])
        self._openai_model_var = ctk.StringVar(value=cur_oai_display)
        self._openai_model_dropdown = ctk.CTkOptionMenu(
            oai_row,
            values=OPENAI_MODELS,
            variable=self._openai_model_var,
            font=("Share Tech Mono", 13),
            text_color=TEXT_PRI, fg_color=BG_SEC,
            button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI,
            corner_radius=0, width=280,
        )
        self._openai_model_dropdown.pack(side="left", padx=10)

        key_row = ctk.CTkFrame(self._openai_frame, fg_color="transparent")
        key_row.pack(fill="x", pady=4)
        lbl_k = ctk.CTkFrame(key_row, fg_color="transparent", width=260)
        lbl_k.pack(side="left")
        lbl_k.pack_propagate(False)
        ctk.CTkLabel(lbl_k, text="OPENAI API KEY:", anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=5)
        ctk.CTkLabel(lbl_k, text="platform.openai.com/api-keys", anchor="w",
                     font=("Share Tech Mono", 10), text_color=TEXT_HINT).pack(anchor="w", padx=5)
        self._openai_key_entry = ctk.CTkEntry(
            key_row, width=340, show="•",
            font=("Share Tech Mono", 13),
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT_PRI, corner_radius=0,
        )
        self._openai_key_entry.insert(0, config.get("openai_api_key", ""))
        self._openai_key_entry.pack(side="left", padx=10)
        self._openai_key_entry.bind("<FocusIn>",  lambda e: self._openai_key_entry.configure(border_width=2, border_color=ACCENT_PRI))
        self._openai_key_entry.bind("<FocusOut>", lambda e: self._openai_key_entry.configure(border_width=1, border_color=BORDER))

        ctk.CTkButton(
            key_row, text="👁", width=36,
            font=("Share Tech Mono", 13),
            text_color=TEXT_SEC, fg_color="transparent",
            hover_color=BG_CARD, border_color=BORDER, border_width=1, corner_radius=0,
            command=self._toggle_openai_key_visibility,
        ).pack(side="left")

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
                "Hindi (Devanagari), Marathi, Bengali, Gujarati, Tamil script\n"
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
                "💡  Sahi Hindi/regional script ke liye Gemini ya OpenAI use karo."
            ),
            font=("Share Tech Mono", 11), text_color=TEXT_SEC,
            anchor="w", justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 10))

        # ── Image-to-Video Backend ──────────────────────────────────────────
        ctk.CTkFrame(section, fg_color=BORDER, height=1).pack(fill="x", pady=(16, 6), padx=5)
        ctk.CTkLabel(
            section, text=">> [ IMAGE-TO-VIDEO BACKEND ]",
            font=("Orbitron", 13, "bold"), text_color=TEXT_SEC,
        ).pack(anchor="w", padx=10, pady=(0, 4))

        i2v_row = ctk.CTkFrame(section, fg_color="transparent")
        i2v_row.pack(fill="x", pady=4)
        ctk.CTkLabel(
            i2v_row, text="IMG2VIDEO BACKEND:",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC, width=260, anchor="w"
        ).pack(side="left", padx=5)
        cur_i2v = config.get("img2video_backend", "kling_standard")
        cur_i2v_display = IMG2VIDEO_REV.get(cur_i2v, list(IMG2VIDEO_OPTIONS.keys())[2])
        self._img2video_var = ctk.StringVar(value=cur_i2v_display)
        ctk.CTkOptionMenu(
            i2v_row,
            values=list(IMG2VIDEO_OPTIONS.keys()),
            variable=self._img2video_var,
            font=("Share Tech Mono", 13),
            text_color=TEXT_PRI, fg_color=BG_SEC,
            button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI,
            corner_radius=0, width=280,
        ).pack(side="left", padx=10)

        dur_row = ctk.CTkFrame(section, fg_color="transparent")
        dur_row.pack(fill="x", pady=4)
        ctk.CTkLabel(
            dur_row, text="CLIP DURATION:",
            font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC, width=260, anchor="w"
        ).pack(side="left", padx=5)
        cur_dur = config.get("img2video_duration", "5") + "s"
        self._clip_duration_var = ctk.StringVar(value=cur_dur)
        ctk.CTkOptionMenu(
            dur_row,
            values=["5s", "10s"],
            variable=self._clip_duration_var,
            font=("Share Tech Mono", 13),
            text_color=TEXT_PRI, fg_color=BG_SEC,
            button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI,
            corner_radius=0, width=120,
        ).pack(side="left", padx=10)
        self._hint(section, "Fal.ai backends → Fal API key  •  Grok backends → xAI API key  |  Used in Image Review step when 'Make Video' is toggled ON")

        # Show correct frame on init
        self._on_provider_switch(self._provider_var.get())

    def _on_provider_switch(self, value: str):
        self._gemini_frame.pack_forget()
        self._openai_frame.pack_forget()
        self._ollama_frame.pack_forget()
        if value == "OpenAI":
            self._openai_frame.pack(fill="x")
        elif value == "Ollama":
            self._ollama_frame.pack(fill="x")
        else:
            self._gemini_frame.pack(fill="x")

    def _toggle_openai_key_visibility(self):
        current = self._openai_key_entry.cget("show")
        self._openai_key_entry.configure(show="" if current == "•" else "•")

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
            "Video banane ke general settings. Language aur upload mode zaroor check karo."
        )

        def _make_row(label_text, hint, widget_class, **kwargs):
            row = ctk.CTkFrame(section, fg_color="transparent")
            row.pack(fill="x", pady=4)
            lbl_col = ctk.CTkFrame(row, fg_color="transparent", width=260)
            lbl_col.pack(side="left")
            lbl_col.pack_propagate(False)
            ctk.CTkLabel(lbl_col, text=label_text, anchor="w",
                         font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=5)
            ctk.CTkLabel(lbl_col, text=hint, anchor="w",
                         font=("Share Tech Mono", 10), text_color=TEXT_HINT).pack(anchor="w", padx=5)
            w = widget_class(row, **kwargs)
            w.pack(side="left", padx=10)
            return row, w

        _, self._lang = _make_row(
            "LANGUAGE:", "Script + voice kis language mein",
            ctk.CTkOptionMenu,
            values=["hi", "en", "mr", "bn", "gu", "ta"],
            width=160,
            font=("Share Tech Mono", 13),
            text_color=TEXT_PRI, fg_color=BG_SEC, button_color=BORDER,
            button_hover_color=ACCENT_PRI, corner_radius=0
        )
        self._lang.set(config.get("pipeline.language", "hi"))
        self._hint(
            section,
            "hi Hindi  |  en English  |  mr Marathi  |  bn Bengali  |  gu Gujarati  |  ta Tamil  "
            "— script + voiceover isi language mein",
        )

        _, self._img_count = _make_row(
            "IMAGE COUNT:", "Script + video mein kitni scenes / images",
            ctk.CTkOptionMenu,
            values=["4", "6", "8", "10", "12", "14", "16", "18", "20", "24", "28", "32", "36", "40"],
            width=160,
            font=("Share Tech Mono", 13),
            text_color=TEXT_PRI, fg_color=BG_SEC, button_color=BORDER,
            button_hover_color=ACCENT_PRI, corner_radius=0
        )
        self._img_count.set(str(config.get("image.image_count", 6)))
        self._hint(section, "Zyada scenes = lamba render  |  4–40 (Gemini script + utni hi images)")

        row_td = ctk.CTkFrame(section, fg_color="transparent")
        row_td.pack(fill="x", pady=4)
        lbl_td = ctk.CTkFrame(row_td, fg_color="transparent", width=260)
        lbl_td.pack(side="left")
        lbl_td.pack_propagate(False)
        ctk.CTkLabel(lbl_td, text="TARGET DURATION (SEC):", anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=5)
        ctk.CTkLabel(lbl_td, text="Voiceover + video length target", anchor="w",
                     font=("Share Tech Mono", 10), text_color=TEXT_HINT).pack(anchor="w", padx=5)
        self._target_duration = ctk.CTkEntry(
            row_td, width=120, font=("Share Tech Mono", 13),
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT_PRI, corner_radius=0,
        )
        self._target_duration.insert(0, str(int(config.get("target_duration", 60))))
        self._target_duration.pack(side="left", padx=10)
        self._target_duration.bind(
            "<FocusIn>", lambda e: self._target_duration.configure(border_width=2, border_color=ACCENT_PRI)
        )
        self._target_duration.bind(
            "<FocusOut>", lambda e: self._target_duration.configure(border_width=1, border_color=BORDER)
        )
        self._hint(section, "60–600 seconds — script + TTS roughly is duration ke around banega")

        self._upload_enabled_var = ctk.BooleanVar(value=bool(config.get("pipeline.upload_enabled", True)))
        upload_flag_row = ctk.CTkFrame(section, fg_color="transparent")
        upload_flag_row.pack(fill="x", pady=(6, 2), padx=5)
        self._chk_upload_enabled = ctk.CTkCheckBox(
            upload_flag_row,
            text="Enable YouTube upload after render",
            variable=self._upload_enabled_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
            fg_color=BG_MAIN,
            border_color=BORDER,
            hover_color=BG_CARD,
            checkmark_color=ACCENT_PRI,
            corner_radius=0,
            command=self._sync_upload_controls,
        )
        self._chk_upload_enabled.pack(anchor="w", padx=5)
        self._hint(
            section,
            "Off = sirf MP4 local output folder mein save (permanent) — YouTube pe upload nahi hoga",
        )

        _, self._upload = _make_row(
            "UPLOAD MODE:", "YouTube pe kaise upload ho (jab upload ON ho)",
            ctk.CTkOptionMenu,
            values=["unlisted", "public", "draft"], width=150, font=("Share Tech Mono", 13),
            text_color=TEXT_PRI, fg_color=BG_SEC, button_color=BORDER,
            button_hover_color=ACCENT_PRI, corner_radius=0
        )
        self._upload.set(config.get("pipeline.upload_mode", "unlisted"))
        self._hint(section, "unlisted = sirf link wale dekh sakte (testing ke liye)  |  public = sabko dikhega  |  draft = save only")

        # Thumbnail toggle
        self._thumbnail_enabled_var = ctk.BooleanVar(value=bool(config.get("pipeline.thumbnail_enabled", True)))
        thumb_flag_row = ctk.CTkFrame(section, fg_color="transparent")
        thumb_flag_row.pack(fill="x", pady=(6, 2), padx=5)
        ctk.CTkCheckBox(
            thumb_flag_row,
            text="Auto-generate clickbait thumbnail before upload",
            variable=self._thumbnail_enabled_var,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
            fg_color=BG_MAIN,
            border_color=BORDER,
            hover_color=BG_CARD,
            checkmark_color=ACCENT_PRI,
            corner_radius=0,
        ).pack(anchor="w", padx=5)
        self._hint(
            section,
            "AI se 1280×720 thumbnail banega — title text + clickbait overlay — output/thumbnails/ mein save hoga",
        )

        self._sync_upload_controls()

        # Output folder
        row4 = ctk.CTkFrame(section, fg_color="transparent")
        row4.pack(fill="x", pady=4)
        lbl4 = ctk.CTkFrame(row4, fg_color="transparent", width=260)
        lbl4.pack(side="left")
        lbl4.pack_propagate(False)
        ctk.CTkLabel(lbl4, text="OUTPUT FOLDER:", anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=5)
        ctk.CTkLabel(lbl4, text="Videos kahan save honge", anchor="w",
                     font=("Share Tech Mono", 10), text_color=TEXT_HINT).pack(anchor="w", padx=5)
        self._output_dir = ctk.CTkEntry(row4, width=320, font=("Share Tech Mono", 13),
                                        fg_color=BG_MAIN, border_color=BORDER,
                                        text_color=TEXT_PRI, corner_radius=0)
        self._output_dir.insert(0, config.get("pipeline.output_folder", "output"))
        self._output_dir.pack(side="left", padx=10)
        self._output_dir.bind("<FocusIn>",  lambda e: self._output_dir.configure(border_width=2, border_color=ACCENT_PRI))
        self._output_dir.bind("<FocusOut>", lambda e: self._output_dir.configure(border_width=1, border_color=BORDER))
        ctk.CTkButton(row4, text="[ BROWSE ]", width=90,
                      font=("Share Tech Mono", 13, "bold"), text_color=ACCENT_PRI,
                      fg_color="transparent", hover_color=BG_CARD,
                      border_color=BORDER, border_width=1, corner_radius=0,
                      command=self._browse_output).pack(side="left", padx=5)
        self._hint(section, "Relative path (e.g. 'output') ya full path (e.g. D:\\\\Videos\\\\GhostAI)  —  Folder automatically create hoga")

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

    # ── Browse helpers ────────────────────────────────────────────────────
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
            if hasattr(self.app_ref, "pipeline_tab"):
                self.app_ref.pipeline_tab.update_uplink_status("No Profile")
        else:
            names = [p["name"] for p in profiles]
            self._profile_menu.configure(values=names)
            if 0 <= idx < len(names):
                self._profile_menu.set(names[idx])
                if hasattr(self.app_ref, "pipeline_tab"):
                    self.app_ref.pipeline_tab.update_uplink_status(names[idx])
            else:
                self._profile_menu.set(names[0])
                config.set("pipeline.active_profile_index", 0)
                config.save()
                if hasattr(self.app_ref, "pipeline_tab"):
                    self.app_ref.pipeline_tab.update_uplink_status(names[0])

    def _on_profile_select(self, value):
        profiles = config.get("pipeline.chrome_profiles", [])
        for i, p in enumerate(profiles):
            if p["name"] == value:
                config.set("pipeline.active_profile_index", i)
                config.save()
                if hasattr(self.app_ref, "pipeline_tab"):
                    self.app_ref.pipeline_tab.update_uplink_status(value)
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

    def _on_aspect_segment_change(self, value: str) -> None:
        """Apply aspect ratio on tap so pipeline/Documentary see it without a separate [ SAVE CONFIG ] click."""
        aspect_ratio = "16:9" if value == "16:9 YouTube" else "9:16"
        config.set("aspect_ratio", aspect_ratio)
        try:
            config.save()
        except OSError:
            pass

    # ── Save Action ───────────────────────────────────────────────────────
    def _save(self):
        self._save_btn.configure(fg_color=ACCENT_GRN, text_color=BG_MAIN, text="[ SAVED ✓ ]")

        for key_path, entry in self._key_entries.items():
            config.set(key_path, entry.get().strip())

        config.set("tts.backend",          self._tts_val)
        config.set("tts.reference_audio",  self._ref_audio.get().strip())
        if hasattr(self, "_voice_post_var"):
            config.set("tts.voice_post_process", 1 if self._voice_post_var.get() else 0)
        if hasattr(self, "_voice_post_silence_var"):
            config.set("tts.voice_post_silence_trim", 1 if self._voice_post_silence_var.get() else 0)
        if hasattr(self, "_omnivoice_server_path"):
            config.set("tts.omnivoice_server_path", self._omnivoice_server_path.get().strip())
        if hasattr(self, "_omnivoice_autostart_var"):
            config.set("tts.omnivoice_autostart", bool(self._omnivoice_autostart_var.get()))
        if hasattr(self, "_omnivoice_mode"):
            config.set("tts.omnivoice_mode", OMNIVOICE_MODE_OPTIONS.get(self._omnivoice_mode.get(), "clone"))
        if hasattr(self, "_omnivoice_auto_ref_var"):
            config.set("tts.omnivoice_auto_transcribe_ref", 1 if self._omnivoice_auto_ref_var.get() else 0)
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
        if hasattr(self, "_omnivoice_text_chunk"):
            try:
                _cc = int(self._omnivoice_text_chunk.get().strip())
            except (ValueError, AttributeError):
                _cc = 800
            config.set("tts.omnivoice_text_chunk_chars", max(120, min(800, _cc)))
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


        config.set("image.backend",                  self._img_val)
        config.set("image.comfyui_url",              self._comfyui_url.get().strip())
        if hasattr(self, "_grok_model_var") and hasattr(self, "_grok_model_options"):
            config.set("grok_image_model", self._grok_model_options.get(self._grok_model_var.get(), "grok-2-image-1212"))
        try:
            ic = int(self._img_count.get())
        except ValueError:
            ic = 6
        config.set("image.image_count", max(4, min(ic, 40)))

        try:
            td = int(str(self._target_duration.get()).strip())
        except ValueError:
            td = 60
        config.set("target_duration", max(60, min(td, 600)))

        aspect_label = self._aspect_seg.get()
        aspect_ratio = "16:9" if aspect_label == "16:9 YouTube" else "9:16"
        config.set("aspect_ratio", aspect_ratio)

        ce = dict(config.get("cinematic_effects", {}))
        ce["intro"] = bool(self._ce_intro_var.get())
        ce["transitions"] = bool(self._ce_trans_var.get())
        ts_label = self._trans_style.get()
        ce["transition_style"] = _TRANSITION_STYLE_TO_CONFIG.get(ts_label, "cinematic_mix")
        config.set("cinematic_effects", ce)

        if hasattr(self, "_script_review_var"):
            config.set("script_review_enabled", bool(self._script_review_var.get()))

        if hasattr(self, "_video_preview_var"):
            config.set("video_preview_enabled", bool(self._video_preview_var.get()))

        if hasattr(self, "_provider_var"):
            _prov_map = {"Gemini": "gemini", "OpenAI": "openai", "Ollama": "ollama"}
            provider = _prov_map.get(self._provider_var.get(), "gemini")
            config.set("script_provider", provider)
            config.set("gemini_model", self._gemini_model_map.get(self._gemini_model_var.get(), "gemini-2.0-flash"))
            config.set("openai_model", self._openai_model_map.get(self._openai_model_var.get(), "gpt-4o"))
            config.set("openai_api_key", self._openai_key_entry.get().strip())
            config.set("img2video_backend", self._img2video_map.get(self._img2video_var.get(), "kling_standard"))
            config.set("img2video_duration", self._clip_duration_var.get().replace("s", ""))
            if hasattr(self, "_ollama_url_entry"):
                config.set("ollama_url", self._ollama_url_entry.get().strip() or "http://localhost:11434")
            if hasattr(self, "_ollama_model_entry"):
                config.set("ollama_model", self._ollama_model_entry.get().strip() or "llama3")

        config.set("pipeline.language",              self._lang.get())
        config.set("pipeline.upload_enabled",       bool(self._upload_enabled_var.get()))
        config.set("pipeline.upload_mode",           self._upload.get())
        config.set("pipeline.thumbnail_enabled",    bool(self._thumbnail_enabled_var.get()))
        config.set("pipeline.output_folder",         self._output_dir.get().strip())

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

        # Load status immediately
        self._recheck_license()

    def _recheck_license(self):
        self._lic_status_lbl.configure(text="⟳  checking…", text_color=TEXT_HINT)
        threading.Thread(target=self._do_recheck, daemon=True).start()

    def _do_recheck(self):
        try:
            from core.license import is_licensed
            valid, message = is_licensed()
        except Exception as exc:
            valid, message = False, str(exc)
        self.after(0, self._update_lic_status, valid, message)

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
