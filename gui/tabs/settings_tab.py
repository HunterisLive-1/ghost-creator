"""
gui/tabs/settings_tab.py — Settings Tab Cyberpunk
"""

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
    "chatterbox": (
        "🎙️  CHATTERBOX  —  Apni khud ki awaaz clone karo!\n"
        "   • Apna ek reference audio (.wav/.mp3) record karo aur neeche path daalo\n"
        "   • Pehle  start-chatterbox.bat  chalao — server start hona chahiye\n"
        "   • Sabse realistic Hindi voice quality milti hai\n"
        "   ⚠️  Local server + GPU recommended  |  No API key needed"
    ),
    "edge_tts": (
        "✅  EDGE TTS  —  Beginners ke liye BEST choice! (Recommended)\n"
        "   • Microsoft ka free cloud voice — zero setup chahiye\n"
        "   • Sirf internet connection chahiye, turant kaam karta hai\n"
        "   • Hindi: MadhurNeural (male) / SwaraNeural (female)\n"
        "   ✔️  Free  |  No API key  |  No local server  |  Works instantly"
    ),
    "elevenlabs": (
        "⭐  ELEVENLABS  —  Sabse realistic professional voice\n"
        "   • ElevenLabs.io pe account banao → Subscription lo\n"
        "   • API Key Settings mein daalo\n"
        "   • Voice Lab se apni pasand ki Voice ka ID copy karo, neeche daalo\n"
        "   💰  Paid plan required  |  Best quality  |  Many Hindi voices available"
    ),
    "google_tts": (
        "☁️  GOOGLE CLOUD TTS  —  Google ka official professional voice\n"
        "   • Google Cloud Console pe project banao\n"
        "   • Text-to-Speech API enable karo\n"
        "   • Service Account JSON file download karo aur path neeche daalo\n"
        "   ⚙️  Advanced setup  |  Paid  |  Very high quality"
    ),
    "kokoro": (
        "🤖  KOKORO TTS  —  Free local AI voice model\n"
        "   • Pehli baar auto-download hoga (~1GB model)\n"
        "   • GPU ho toh fast, CPU pe bhi chalega (thoda slow)\n"
        "   • Model ka folder path neeche daalo (ya empty chodo auto ke liye)\n"
        "   ✔️  Free  |  No internet needed  |  Offline use possible"
    ),
}

IMG_DESCRIPTIONS = {
    "gemini_imagen": (
        "✅  IMAGEN-3  —  Beginners ke liye BEST choice! (Recommended)\n"
        "   • Sirf Gemini API Key chahiye — koi extra setup nahi\n"
        "   • Aistudio.google.com se free API key lo\n"
        "   • Google ka latest image model — achhi quality\n"
        "   ✔️  Free tier available  |  No local GPU  |  Works instantly"
    ),
    "pollinations": (
        "🆓  POLLINATIONS  —  Completely free, no key needed!\n"
        "   • Koi account nahi, koi key nahi — bas select karo aur chalaao\n"
        "   • Model choose karo: dreamshaper / flux / turbo\n"
        "   • Quality thodi basic hogi but zero cost\n"
        "   ✔️  100% Free  |  No signup  |  Beginner friendly"
    ),
    "comfyui": (
        "⚡  COMFYUI  —  Local Stable Diffusion (Powerful)\n"
        "   • Apne PC pe Stable Diffusion run karo — best control\n"
        "   • GPU minimum 6GB VRAM chahiye (RTX/AMD)\n"
        "   • Pehle ComfyUI install karo aur server start karo\n"
        "   • Default URL: http://127.0.0.1:8188\n"
        "   ⚠️  Advanced users  |  GPU required  |  Free after setup"
    ),
    "fal_ai": (
        "🚀  FAL.AI  —  Fastest cloud image generation\n"
        "   • Fal.ai pe account banao → API key lo → Settings mein daalo\n"
        "   • SDXL, Flux, aur many more models available\n"
        "   • Speed + quality dono best hain cloud options mein\n"
        "   💰  Pay-per-use (cheap)  |  Very fast  |  No local GPU"
    ),
    "stable_horde": (
        "🌐  STABLE HORDE  —  Community free GPU cloud\n"
        "   • Bilkul free — anonymous use ke liye '0000000000' key daalo\n"
        "   • Community ke GPU pe queue mein wait karna hoga (slow)\n"
        "   • Account banao toh priority milegi\n"
        "   ✔️  Free  |  Slow (queue)  |  No local GPU needed"
    ),
    "replicate": (
        "🔧  REPLICATE  —  Premium hosted AI models\n"
        "   • Replicate.com pe account banao → API token lo\n"
        "   • Sabse zyada model options available hain\n"
        "   • SDXL, Flux, custom LoRA models sab yahan milte hain\n"
        "   💰  Pay-per-use  |  Most variety  |  No local GPU"
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
}


class SettingsTab(ctk.CTkFrame):
    def __init__(self, master, app_ref, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app_ref = app_ref

        self._key_entries = {}
        self._key_visible = {}

        # State variables
        self._tts_val = config.get("tts.backend", "chatterbox")
        self._img_val = config.get("image.backend", "comfyui")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)

        self._build_beginner_banner(scroll)
        self._build_api_keys_section(scroll)
        self._build_tts_section(scroll)
        self._build_image_section(scroll)
        self._build_video_format_section(scroll)
        self._build_pipeline_section(scroll)

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
        banner = ctk.CTkFrame(parent, fg_color="#0A1A0F", corner_radius=0,
                              border_width=1, border_color=ACCENT_GRN)
        banner.pack(fill="x", pady=(5, 15), padx=5)

        ctk.CTkLabel(
            banner,
            text="🚀  QUICK START — Pehli Baar Setup Kaise Karo",
            font=("Orbitron", 13, "bold"),
            text_color=ACCENT_GRN,
        ).pack(anchor="w", padx=15, pady=(12, 4))

        guide = (
            "  1.  API KEYS section mein sirf  GEMINI API KEY  daalo  (free hai — aistudio.google.com)\n"
            "  2.  AUDIO SUBROUTINE mein  EDGE TTS  select karo  (free, no setup needed)\n"
            "  3.  VISION MATRIX mein  IMAGEN-3  select karo  (sirf Gemini key se kaam karta hai)\n"
            "  4.  CORE PARAMETERS mein Language chuno:  hi / en / mr / bn / gu / ta  (voiceover + script)\n"
            "  5.  Neeche  [ SAVE CONFIG ]  dabao  →  Pipeline tab pe jao  →  RUN!"
        )
        ctk.CTkLabel(
            banner,
            text=guide,
            font=("Share Tech Mono", 12),
            text_color="#88CCAA",
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=15, pady=(0, 12))

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
        ]

        for label_text, key_path in keys:
            badge_text, badge_color, hint_text = API_KEY_INFO.get(
                key_path, ("OPTIONAL", TEXT_HINT, "")
            )

            # Container card
            card = ctk.CTkFrame(section, fg_color=BG_CARD, corner_radius=0,
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

    # ── Section 2: TTS Backend ────────────────────────────────────────────
    def _build_tts_section(self, parent):
        section = self._section(
            parent, ">> [ AUDIO SUBROUTINE ]",
            "Video ki awaaz (voiceover) kaun generate karega. "
            "👉 Beginner? → EDGE TTS chuno (free, koi setup nahi)."
        )

        options = [
            ("chatterbox", "CHATTERBOX"),
            ("edge_tts",   "EDGE TTS ✅"),
            ("elevenlabs", "ELEVENLABS"),
            ("google_tts", "GOOGLE CLOUD"),
            ("kokoro",     "KOKORO TTS"),
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
            font=("Share Tech Mono", 12),
            text_color="#88CCAA",
            justify="left",
            anchor="w",
            wraplength=820,
            fg_color="#071510",
            corner_radius=0,
        )
        self._tts_desc.pack(fill="x", padx=0, pady=(0, 10), ipadx=12, ipady=10)

        self._select_tts(self._tts_val)

        # TTS config sub-section
        tts_config = ctk.CTkFrame(section, fg_color=BG_MAIN, corner_radius=0,
                                  border_color=BORDER, border_width=1)
        tts_config.pack(fill="x", pady=(0, 5), ipadx=10, ipady=10)

        # Chatterbox Server Directory
        cb_row = ctk.CTkFrame(tts_config, fg_color="transparent")
        cb_row.pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(cb_row, text="CHATTERBOX SERVER DIR:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        self._chatterbox_dir = ctk.CTkEntry(cb_row, width=280, font=("Share Tech Mono", 13),
                                            fg_color=BG_MAIN, border_color=BORDER,
                                            text_color=TEXT_PRI, corner_radius=0)
        self._chatterbox_dir.insert(0, config.get("tts.chatterbox_path", ""))
        self._chatterbox_dir.pack(side="left", padx=5)
        self._chatterbox_dir.bind("<FocusIn>",  lambda e: self._chatterbox_dir.configure(border_width=2, border_color=ACCENT_PRI))
        self._chatterbox_dir.bind("<FocusOut>", lambda e: self._chatterbox_dir.configure(border_width=1, border_color=BORDER))
        ctk.CTkButton(cb_row, text="[ BROWSE ]", width=80,
                      font=("Share Tech Mono", 13, "bold"), text_color=ACCENT_PRI,
                      fg_color="transparent", hover_color=BG_CARD,
                      border_color=BORDER, border_width=1, corner_radius=0,
                      command=self._browse_chatterbox).pack(side="left", padx=5)
        self._hint(tts_config, "Chatterbox-TTS-Server folder ka path daalo  |  start-chatterbox.bat pehle chalao")

        # Chatterbox Reference Audio
        cb_ref_row = ctk.CTkFrame(tts_config, fg_color="transparent")
        cb_ref_row.pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(cb_ref_row, text="CHATTERBOX REF AUDIO:", width=200, anchor="w",
                     font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC).pack(side="left", padx=10)
        self._chatterbox_ref = ctk.CTkEntry(cb_ref_row, width=280, font=("Share Tech Mono", 13),
                                            fg_color=BG_MAIN, border_color=BORDER,
                                            text_color=TEXT_PRI, corner_radius=0)
        self._chatterbox_ref.insert(0, config.get("tts.chatterbox_reference_audio", "my_voice_reference.wav"))
        self._chatterbox_ref.pack(side="left", padx=5)
        self._chatterbox_ref.bind("<FocusIn>",  lambda e: self._chatterbox_ref.configure(border_width=2, border_color=ACCENT_PRI))
        self._chatterbox_ref.bind("<FocusOut>", lambda e: self._chatterbox_ref.configure(border_width=1, border_color=BORDER))
        ctk.CTkButton(cb_ref_row, text="[ BROWSE ]", width=80,
                      font=("Share Tech Mono", 13, "bold"), text_color=ACCENT_PRI,
                      fg_color="transparent", hover_color=BG_CARD,
                      border_color=BORDER, border_width=1, corner_radius=0,
                      command=self._browse_chatterbox_ref).pack(side="left", padx=5)
        self._hint(tts_config, "Apni awaaz ka sample audio file (.wav / .mp3) — jis awaaz mein video banani hai")

        ctk.CTkLabel(tts_config, text="EDGE TTS VOICE:",
                     font=("Share Tech Mono", 12, "bold"),
                     text_color=TEXT_SEC).pack(anchor="w", padx=10, pady=(10, 0))
        self._edge_voice = ctk.CTkOptionMenu(
            tts_config,
            values=["hi-IN-MadhurNeural", "hi-IN-SwaraNeural",
                    "en-US-GuyNeural", "en-US-JennyNeural"],
            font=("Share Tech Mono", 13), text_color=TEXT_PRI,
            fg_color=BG_SEC, button_color=BORDER, button_hover_color=ACCENT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_PRI, corner_radius=0
        )
        self._edge_voice.set(config.get("tts.edge_tts_voice", "hi-IN-MadhurNeural"))
        self._edge_voice.pack(anchor="w", padx=10, pady=(2, 2))
        self._hint(tts_config, "Hindi: MadhurNeural (male) / SwaraNeural (female)  |  English: GuyNeural / JennyNeural")

        ctk.CTkLabel(tts_config, text="ELEVENLABS VOICE ID:",
                     font=("Share Tech Mono", 12, "bold"),
                     text_color=TEXT_SEC).pack(anchor="w", padx=10, pady=(10, 0))
        self._eleven_voice = ctk.CTkEntry(tts_config, width=350, font=("Share Tech Mono", 13),
                                          fg_color=BG_MAIN, border_color=BORDER,
                                          text_color=TEXT_PRI, corner_radius=0)
        self._eleven_voice.insert(0, config.get("tts.elevenlabs_voice_id", "") or "")
        self._eleven_voice.pack(anchor="w", padx=10, pady=(2, 2))
        self._eleven_voice.bind("<FocusIn>",  lambda e: self._eleven_voice.configure(border_width=2, border_color=ACCENT_PRI))
        self._eleven_voice.bind("<FocusOut>", lambda e: self._eleven_voice.configure(border_width=1, border_color=BORDER))
        self._hint(tts_config, "ElevenLabs.io → Voice Lab → apni voice pe click karo → Voice ID copy karo")

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
        ]

        btn_frame1 = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame1.pack(fill="x", pady=(5, 3))
        btn_frame2 = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame2.pack(fill="x", pady=(0, 8))

        self._img_btns = {}
        for i, (val, label) in enumerate(options):
            b_frame = btn_frame1 if i < 3 else btn_frame2
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
            font=("Share Tech Mono", 12),
            text_color="#88CCAA",
            justify="left",
            anchor="w",
            wraplength=820,
            fg_color="#071510",
            corner_radius=0,
        )
        self._img_desc.pack(fill="x", padx=0, pady=(0, 10), ipadx=12, ipady=10)

        self._select_img(self._img_val)

        # Image config sub-section
        img_config = ctk.CTkFrame(section, fg_color=BG_MAIN, corner_radius=0,
                                  border_color=BORDER, border_width=1)
        img_config.pack(fill="x", pady=(0, 5), ipadx=10, ipady=10)

        ctk.CTkLabel(img_config, text="COMFYUI NODE URL:",
                     font=("Share Tech Mono", 12, "bold"),
                     text_color=TEXT_SEC).pack(anchor="w", padx=10, pady=(8, 0))
        self._comfyui_url = ctk.CTkEntry(img_config, width=400, font=("Share Tech Mono", 13),
                                         fg_color=BG_MAIN, border_color=BORDER,
                                         text_color=TEXT_PRI, corner_radius=0)
        self._comfyui_url.insert(0, config.get("image.comfyui_url", "http://127.0.0.1:8188"))
        self._comfyui_url.pack(anchor="w", padx=10, pady=(2, 2))
        self._comfyui_url.bind("<FocusIn>",  lambda e: self._comfyui_url.configure(border_width=2, border_color=ACCENT_PRI))
        self._comfyui_url.bind("<FocusOut>", lambda e: self._comfyui_url.configure(border_width=1, border_color=BORDER))
        self._hint(img_config, "Sirf ComfyUI backend ke liye. Default: http://127.0.0.1:8188  |  ComfyUI server pehle start karo")

    def _select_img(self, val):
        self._img_val = val
        for v, btn in self._img_btns.items():
            if v == val:
                btn.configure(fg_color=ACCENT_PRI, text_color=BG_MAIN, border_color=ACCENT_PRI)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SEC, border_color=BORDER)
        if hasattr(self, "_img_desc"):
            self._img_desc.configure(text=IMG_DESCRIPTIONS.get(val, ""))

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
        )
        self._aspect_seg.set(aspect_default)
        self._aspect_seg.pack(anchor="w", padx=10, pady=(0, 6), fill="x")
        self._hint(section, "9:16 = Shorts / Reels  |  16:9 = standard YouTube landscape")

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
    def _browse_chatterbox(self):
        path = filedialog.askdirectory(title="Locate Chatterbox-TTS-Server directory")
        if path:
            self._chatterbox_dir.delete(0, "end")
            self._chatterbox_dir.insert(0, path)

    def _browse_chatterbox_ref(self):
        path = filedialog.askopenfilename(
            title="Locate Reference Audio File",
            filetypes=[("Audio Files", "*.wav *.mp3 *.m4a"), ("All Files", "*.*")]
        )
        if path:
            self._chatterbox_ref.delete(0, "end")
            self._chatterbox_ref.insert(0, path)

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

    # ── Save Action ───────────────────────────────────────────────────────
    def _save(self):
        self._save_btn.configure(fg_color=ACCENT_GRN, text_color=BG_MAIN, text="[ SAVED ✓ ]")

        for key_path, entry in self._key_entries.items():
            config.set(key_path, entry.get().strip())

        config.set("tts.backend",                   self._tts_val)
        config.set("tts.chatterbox_path",            self._chatterbox_dir.get().strip())
        config.set("tts.chatterbox_reference_audio", self._chatterbox_ref.get().strip())
        config.set("tts.edge_tts_voice",             self._edge_voice.get())
        config.set("tts.elevenlabs_voice_id",        self._eleven_voice.get().strip())

        config.set("image.backend",                  self._img_val)
        config.set("image.comfyui_url",              self._comfyui_url.get().strip())
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

        config.set("pipeline.language",              self._lang.get())
        config.set("pipeline.upload_enabled",       bool(self._upload_enabled_var.get()))
        config.set("pipeline.upload_mode",           self._upload.get())
        config.set("pipeline.output_folder",         self._output_dir.get().strip())

        config.save()
        self.app_ref.update_backend_labels()

        self.after(2000, lambda: self._save_btn.configure(
            fg_color="transparent", text_color=ACCENT_PRI, text="[ SAVE CONFIG ]"
        ))

    def _open_env_local(self):
        config.open_env_local()

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
