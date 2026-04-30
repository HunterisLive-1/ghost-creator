"""
core/config_manager.py — JSON-based Configuration Manager
==========================================================
Replaces the old .env-based config system.  Reads/writes config.json
with dot-notation access (e.g. "api_keys.gemini", "tts.backend").

On first run, creates .env.local in the same directory as config.json
so users can directly edit settings in a readable format.

Usage:
    from core.config_manager import config
    config.load()
    key = config.get("api_keys.gemini")
    config.set("tts.backend", "edge_tts")
    config.save()
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any




# ── Default configuration — matches PLANNING.md schema exactly ────────────────
DEFAULT_CONFIG: dict = {
    "api_keys": {
        "gemini": "",
        "elevenlabs": "",
        "fal_ai": "",
        "replicate": "",
        "stable_horde": "",
        "pexels": "",
    },
    "xai_api_key": "",
    "grok_image_model": "grok-2-image-1212",
    "tts": {
        "backend": "omnivoice",
        "omnivoice_url": "http://127.0.0.1:8765",
        "omnivoice_mode": "clone",
        # Seconds for one full-script HTTP / package generate (long CPU jobs).
        "omnivoice_http_read_timeout": 18000,
        "reference_audio": "my_voice_reference.wav",
        "omnivoice_model_id": "k2-fsa/OmniVoice",
        "omnivoice_ref_transcript": "",
        # Optional label for OmniVoice WebUI reference_voices.json (same as WebUI voice name).
        "omnivoice_ref_voice_name": "",
        "omnivoice_design_voice": "custom",
        "omnivoice_speaking_style": "default",
        "omnivoice_quality_preset": "balanced",
        "omnivoice_voice_gender": "",
        "omnivoice_extra_instruct": "",
        "omnivoice_language_hint": "",
        "elevenlabs_voice_id": "",
        "elevenlabs_stability": 0.30,
        "elevenlabs_similarity_boost": 0.85,
        "elevenlabs_style": 0.45,
        # FFmpeg: HPF + silenceremove + loudnorm (applies to all TTS after synthesis; no atempo)
        "voice_post_process": 1,
        "voice_post_target_lufs": -16.0,
        # Silence: only gaps longer than stop_duration (sec) are trimmed; stop_silence = gap kept (natural)
        "voice_post_silence_trim": 1,
        "voice_post_silence_min_internal": 0.42,
        "voice_post_silence_keep": 0.22,
        "voice_post_silence_threshold_db": -46.0,
    },
    "image": {
        "backend": "gemini_imagen",
        "gemini_image_model": "nano_banana",
        "fal_model": "fal-ai/fast-sdxl",
        "replicate_model": "stability-ai/sdxl",
        "image_count": 6,
        "width": 1080,
        "height": 1920,
    },
    "aspect_ratio": "9:16",
    "image_source": "ai_generate",
    "custom_image_paths": [],
    "script_review_enabled": True,
    "script_provider": "gemini",
    "gemini_model": "gemini-2.0-flash",
    "openai_model": "gpt-4o",
    "openai_api_key": "",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3",
    "video_features_enabled": True,
    "video_pace": "medium",
    "pipeline_mode": "normal",
    "documentary.max_clip_duration": 120,
    "documentary.length_mode": "short",
    "documentary.voice_backend": "omnivoice",
    "documentary.short_duration": 60,
    "documentary.long_duration": 600,
    "documentary.segments": 0,          # 0 = auto (~1 per 12s, max 100); else fixed clip count
    "documentary.playback_speed": 1.0,  # final doc: 1.0 = normal speed (video + voice in sync)
    "documentary.burn_subtitles": False,  # long-form only: hardcoded white bold subs at bottom
    "img2video_enabled": False,
    "img2video_backend": "kling_standard",
    "img2video_duration": "5",
    "target_duration": 60,
    "cinematic_effects": {
        "enabled": True,
        "intro": True,
        "transitions": True,
        "transition_style": "cinematic_mix",
    },
    "pipeline": {
        "language": "hi",
        "upload_mode": "unlisted",
        "upload_enabled": True,
        "output_folder": "output",
        "gemini_model": "gemini-2.0-flash",
        "chrome_profiles": [],
        "active_profile_index": 0,
        # YouTube uploader: max wait for file transfer 0→100% (ms); do not proceed if exceeded.
        "upload_complete_timeout_ms": 900_000,
        # After successful publish, wait before closing Chrome so Studio can finish requests.
        "post_publish_grace_ms": 12_000,
    },
}


# ── Mapping: .env.local variable name → (config dot-path, python type) ────────
ENV_LOCAL_MAP: dict[str, tuple[str, type]] = {
    # API Keys
    "GEMINI_API_KEY":             ("api_keys.gemini",                    str),
    "ELEVENLABS_API_KEY":         ("api_keys.elevenlabs",                str),
    "FAL_AI_API_KEY":             ("api_keys.fal_ai",                    str),
    "REPLICATE_API_KEY":          ("api_keys.replicate",                 str),
    "STABLE_HORDE_API_KEY":       ("api_keys.stable_horde",              str),
    # TTS
    "TTS_BACKEND":                ("tts.backend",                        str),
    "OMNIVOICE_URL":              ("tts.omnivoice_url",                  str),
    "OMNIVOICE_HTTP_READ_TIMEOUT": ("tts.omnivoice_http_read_timeout",  int),
    "OMNIVOICE_MODE":             ("tts.omnivoice_mode",                 str),
    "REFERENCE_AUDIO":            ("tts.reference_audio",                str),
    "OMNIVOICE_MODEL_ID":         ("tts.omnivoice_model_id",             str),
    "OMNIVOICE_REF_TRANSCRIPT":   ("tts.omnivoice_ref_transcript",       str),
    "OMNIVOICE_DESIGN_VOICE":     ("tts.omnivoice_design_voice",         str),
    "OMNIVOICE_SPEAKING_STYLE":   ("tts.omnivoice_speaking_style",       str),
    "OMNIVOICE_QUALITY_PRESET":   ("tts.omnivoice_quality_preset",       str),
    "OMNIVOICE_VOICE_GENDER":     ("tts.omnivoice_voice_gender",         str),
    "OMNIVOICE_EXTRA_INSTRUCT":   ("tts.omnivoice_extra_instruct",       str),
    "OMNIVOICE_LANGUAGE_HINT":    ("tts.omnivoice_language_hint",        str),
    "ELEVENLABS_VOICE_ID":        ("tts.elevenlabs_voice_id",            str),
    "VOICE_POST_PROCESS":         ("tts.voice_post_process",             int),
    "VOICE_POST_TARGET_LUFS":     ("tts.voice_post_target_lufs",         float),
    "VOICE_POST_SILENCE_TRIM":    ("tts.voice_post_silence_trim",         int),
    "VOICE_POST_SILENCE_MIN":     ("tts.voice_post_silence_min_internal", float),
    "VOICE_POST_SILENCE_KEEP":    ("tts.voice_post_silence_keep",        float),
    "VOICE_POST_SILENCE_THR":     ("tts.voice_post_silence_threshold_db", float),
    # Image
    "IMAGE_BACKEND":              ("image.backend",                      str),
    "GEMINI_IMAGE_MODEL":         ("image.gemini_image_model",           str),
    "FAL_MODEL":                  ("image.fal_model",                    str),
    "REPLICATE_MODEL":            ("image.replicate_model",              str),
    "IMAGE_COUNT":                ("image.image_count",                  int),
    "VIDEO_WIDTH":                ("image.width",                        int),
    "VIDEO_HEIGHT":               ("image.height",                       int),
    # Pipeline
    "LANGUAGE":                   ("pipeline.language",                  str),
    "UPLOAD_MODE":                ("pipeline.upload_mode",               str),
    "UPLOAD_ENABLED":             ("pipeline.upload_enabled",            bool),
    "OUTPUT_FOLDER":              ("pipeline.output_folder",             str),
    "GEMINI_MODEL":               ("pipeline.gemini_model",              str),
}


# ── .env.local template (comments preserved on every save) ────────────────────
_ENV_LOCAL_TEMPLATE = """\
# ================================================================
#   GHOST CREATOR AI v2  ·  LOCAL CONFIGURATION  (.env.local)
# ================================================================
#
#  Yahan seedha apni API keys aur settings set kar sakte ho.
#  GUI (Settings tab) se [ SAVE CONFIG ] karne par yeh file bhi
#  automatically update hoti hai.
#
#  Directly edit karo → app restart karo → changes apply!
#
#  TIP: Agar ek variable empty rakhoge toh GUI wali value use hogi.
#
# ================================================================

# ── API KEYS ─────────────────────────────────────────────────────
# Gemini AI — script generation + image generation (REQUIRED)
# Get key: https://aistudio.google.com/app/apikey
GEMINI_API_KEY={GEMINI_API_KEY}

# ElevenLabs — premium Hindi/English voice synthesis
# Get key: https://elevenlabs.io/app/subscription
ELEVENLABS_API_KEY={ELEVENLABS_API_KEY}

# Fal.ai — fast cloud image generation
# Get key: https://fal.ai/dashboard/keys
FAL_AI_API_KEY={FAL_AI_API_KEY}

# Replicate — hosted model inference
# Get key: https://replicate.com/account/api-tokens
REPLICATE_API_KEY={REPLICATE_API_KEY}

# Stable Horde — community GPU cloud (use "0000000000" for anonymous)
STABLE_HORDE_API_KEY={STABLE_HORDE_API_KEY}

# ── TTS (VOICE) BACKEND ──────────────────────────────────────────
# Options: omnivoice | edge_tts | elevenlabs
TTS_BACKEND={TTS_BACKEND}

# OmniVoice local server URL (when using server mode)
OMNIVOICE_URL={OMNIVOICE_URL}

# Seconds — one full-script OmniVoice HTTP generate may take a long time on CPU
OMNIVOICE_HTTP_READ_TIMEOUT={OMNIVOICE_HTTP_READ_TIMEOUT}

# OmniVoice generation mode: clone | design
OMNIVOICE_MODE={OMNIVOICE_MODE}

# Voice-clone reference WAV path (used by OmniVoice)
REFERENCE_AUDIO={REFERENCE_AUDIO}

# Hugging Face model id for OmniVoice
OMNIVOICE_MODEL_ID={OMNIVOICE_MODEL_ID}

# What is spoken in the reference clip (for zero-shot clone)
OMNIVOICE_REF_TRANSCRIPT={OMNIVOICE_REF_TRANSCRIPT}

# 1 = after TTS, run FFmpeg speech cleanup (loudnorm + high-pass) on voiceover
VOICE_POST_PROCESS={VOICE_POST_PROCESS}
# Target integrated loudness in LUFS (typical speech: -16 to -18)
VOICE_POST_TARGET_LUFS={VOICE_POST_TARGET_LUFS}
# 1 = trim long silences; min_internal sec = only collapse gaps longer than this; keep = gap to leave
VOICE_POST_SILENCE_TRIM={VOICE_POST_SILENCE_TRIM}
VOICE_POST_SILENCE_MIN={VOICE_POST_SILENCE_MIN}
VOICE_POST_SILENCE_KEEP={VOICE_POST_SILENCE_KEEP}
VOICE_POST_SILENCE_THR={VOICE_POST_SILENCE_THR}

# ElevenLabs voice ID (from https://elevenlabs.io/voice-lab)
ELEVENLABS_VOICE_ID={ELEVENLABS_VOICE_ID}

# ── IMAGE BACKEND ────────────────────────────────────────────────
# Thumbnails / image gen: gemini_imagen only (Gemini API key required)
IMAGE_BACKEND={IMAGE_BACKEND}

# Gemini Imagen model: nano_banana | imagen-3
GEMINI_IMAGE_MODEL={GEMINI_IMAGE_MODEL}

# Fal.ai model ID
FAL_MODEL={FAL_MODEL}

# Replicate model ID
REPLICATE_MODEL={REPLICATE_MODEL}

# Number of images per video (recommended: 4 | 6 | 8 | 10)
IMAGE_COUNT={IMAGE_COUNT}

# Output video resolution — vertical short-form default
VIDEO_WIDTH={VIDEO_WIDTH}
VIDEO_HEIGHT={VIDEO_HEIGHT}

# ── PIPELINE SETTINGS ────────────────────────────────────────────
# Script + voiceover language: hi en mr bn gu ta (Hindi, English, Marathi, Bengali, Gujarati, Tamil)
LANGUAGE={LANGUAGE}

# YouTube upload visibility: unlisted | public | draft
UPLOAD_MODE={UPLOAD_MODE}

# Output folder for finished videos (absolute path or relative to app)
OUTPUT_FOLDER={OUTPUT_FOLDER}

# Gemini model for script generation
# Models: gemini-2.0-flash | gemini-1.5-pro | gemini-2.0-flash-lite
GEMINI_MODEL={GEMINI_MODEL}
"""


class ConfigManager:
    """
    Singleton configuration manager backed by config.json + .env.local.

    Supports dot-notation key paths for nested access:
            config.get("tts.backend")         → "omnivoice"
        config.get("api_keys.gemini")     → ""
        config.set("api_keys.gemini", "ABC123")

    On first run, creates .env.local with a human-friendly template so
    users can edit settings directly without touching JSON.
    """

    _instance: "ConfigManager | None" = None
    _config_path: Path
    _data: dict

    def __new__(cls, config_path: str | Path | None = None) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False  # type: ignore[attr-defined]
        return cls._instance

    def __init__(self, config_path: str | Path | None = None) -> None:
        if self._initialised:  # type: ignore[attr-defined]
            return
        if config_path is None:
            if getattr(sys, 'frozen', False):
                # When running as an installed executable (e.g. in Program Files),
                # we don't have write permissions. Save to user's AppData instead.
                app_data = os.getenv('LOCALAPPDATA') or os.path.expanduser('~/.config')
                config_dir = Path(app_data) / "GhostCreatorAI"
                config_dir.mkdir(parents=True, exist_ok=True)
                self._config_path = config_dir / "config.json"
            else:
                # Default for dev: config.json in project root
                self._config_path = Path(__file__).resolve().parent.parent / "config.json"
        else:
            self._config_path = Path(config_path)
        self._data = {}
        self._initialised = True  # type: ignore[attr-defined]
        self.load()

    # ── Core API ──────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load config.json, creating it from defaults if it doesn't exist.
        Then read .env.local (creating it first if missing) and apply overrides."""
        if not self._config_path.exists():
            self._data = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
            self.save()
        else:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            # Merge any new default keys that might have been added in updates
            changed = self._merge_defaults(self._data, DEFAULT_CONFIG)
            if changed:
                self.save()

        # Create .env.local if it doesn't exist, then load it
        env_path = self.env_local_path
        if not env_path.exists():
            self._create_env_local()
        else:
            self._load_env_local()

        if self._validate_v3_fields():
            self.save()

    def save(self) -> None:
        """Write current config to config.json and sync .env.local."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        # Sync .env.local
        env_path = self.env_local_path
        if env_path.exists():
            self._update_env_local()
        else:
            self._create_env_local()

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a value using dot-notation path.

        Examples:
            config.get("api_keys.gemini")   → ""
            config.get("tts.backend")       → "omnivoice"
            config.get("missing.key")       → None
        """
        keys = key_path.split(".")
        node = self._data
        for key in keys:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return default
        return node

    def set(self, key_path: str, value: Any) -> None:
        """
        Set a value using dot-notation path.  Creates intermediate dicts if needed.

        Examples:
            config.set("api_keys.gemini", "MY_KEY")
            config.set("image.image_count", 8)
        """
        keys = key_path.split(".")
        node = self._data
        for key in keys[:-1]:
            if key not in node or not isinstance(node[key], dict):
                node[key] = {}
            node = node[key]
        node[keys[-1]] = value

    @property
    def data(self) -> dict:
        """Direct access to the full config dict (read-only use recommended)."""
        return self._data

    @property
    def path(self) -> Path:
        """Path to the config.json file."""
        return self._config_path

    @property
    def env_local_path(self) -> Path:
        """Path to the .env.local file (same directory as config.json)."""
        return self._config_path.parent / ".env.local"

    def open_env_local(self) -> None:
        """Open .env.local in the system's default text editor."""
        path = self.env_local_path
        if not path.exists():
            self._create_env_local()
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def get_resolution(self) -> tuple[int, int]:
        aspect_ratio = self.get("aspect_ratio", DEFAULT_CONFIG["aspect_ratio"])
        if aspect_ratio == "16:9":
            return (1920, 1080)
        return (1080, 1920)

    # ── .env.local helpers ────────────────────────────────────────────────────

    def _get_current_env_values(self) -> dict[str, str]:
        """Build a dict of {ENV_VAR: current_value_string} from live config."""
        values: dict[str, str] = {}
        for env_var, (cfg_path, typ) in ENV_LOCAL_MAP.items():
            raw = self.get(cfg_path, "")
            if raw is None:
                raw = ""
            values[env_var] = str(raw)
        return values

    def _create_env_local(self) -> None:
        """Create .env.local from the template, populated with current config values."""
        values = self._get_current_env_values()
        content = _ENV_LOCAL_TEMPLATE.format(**values)
        env_path = self.env_local_path
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(content, encoding="utf-8")

    def _load_env_local(self) -> None:
        """Read .env.local and apply non-empty values into the in-memory config."""
        env_path = self.env_local_path
        if not env_path.exists():
            return
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            env_var, _, raw_value = line.partition("=")
            env_var = env_var.strip()
            raw_value = raw_value.strip()
            if env_var not in ENV_LOCAL_MAP or raw_value == "":
                continue
            cfg_path, typ = ENV_LOCAL_MAP[env_var]
            try:
                self.set(cfg_path, typ(raw_value))
            except (ValueError, TypeError):
                pass  # Skip malformed values silently

    def _update_env_local(self) -> None:
        """Update KEY=VALUE lines in the existing .env.local, preserving all comments."""
        env_path = self.env_local_path
        values = self._get_current_env_values()

        lines = env_path.read_text(encoding="utf-8").splitlines()
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                new_lines.append(line)
                continue
            env_var = stripped.split("=", 1)[0].strip()
            if env_var in values:
                new_lines.append(f"{env_var}={values[env_var]}")
            else:
                new_lines.append(line)
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _merge_defaults(target: dict, defaults: dict) -> bool:
        """Recursively add missing keys from defaults into target."""
        changed = False
        for key, value in defaults.items():
            if key not in target:
                target[key] = json.loads(json.dumps(value))  # deep copy
                changed = True
            elif isinstance(value, dict) and isinstance(target[key], dict):
                if ConfigManager._merge_defaults(target[key], value):
                    changed = True
        return changed

    def _validate_v3_fields(self) -> bool:
        changed = False

        if self.get("tts.backend") == "google_tts":
            self.set("tts.backend", "edge_tts")
            changed = True

        _img_backends = ("gemini_imagen",)
        _ib = self.get("image.backend", DEFAULT_CONFIG["image"]["backend"])
        if _ib not in _img_backends:
            self.set("image.backend", "gemini_imagen")
            changed = True

        aspect_ratio = self.get("aspect_ratio", DEFAULT_CONFIG["aspect_ratio"])
        if aspect_ratio not in ("9:16", "16:9"):
            self.set("aspect_ratio", DEFAULT_CONFIG["aspect_ratio"])
            changed = True

        target_duration = self.get("target_duration", DEFAULT_CONFIG["target_duration"])
        try:
            target_duration_int = int(target_duration)
        except (TypeError, ValueError):
            target_duration_int = DEFAULT_CONFIG["target_duration"]

        if target_duration_int < 60:
            target_duration_int = 60
        if target_duration_int > 600:
            target_duration_int = 600

        if target_duration_int != self.get("target_duration"):
            self.set("target_duration", target_duration_int)
            changed = True

        cinematic_effects = self.get("cinematic_effects", {})
        if not isinstance(cinematic_effects, dict):
            cinematic_effects = {}
            changed = True

        defaults = json.loads(json.dumps(DEFAULT_CONFIG["cinematic_effects"]))
        if self._merge_defaults(cinematic_effects, defaults):
            changed = True

        for flag in ("enabled", "intro", "transitions"):
            if not isinstance(cinematic_effects.get(flag), bool):
                cinematic_effects[flag] = defaults[flag]
                changed = True

        if cinematic_effects.get("transition_style") not in (
            "cinematic_mix",
            "fade_only",
            "zoom_only",
            "minimal",
        ):
            cinematic_effects["transition_style"] = defaults["transition_style"]
            changed = True

        if cinematic_effects != self.get("cinematic_effects"):
            self.set("cinematic_effects", cinematic_effects)
            changed = True

        allowed_langs = ("hi", "en", "mr", "bn", "gu", "ta")
        plang = self.get("pipeline.language", DEFAULT_CONFIG["pipeline"]["language"])
        if plang not in allowed_langs:
            self.set("pipeline.language", DEFAULT_CONFIG["pipeline"]["language"])
            changed = True

        pipeline = dict(self.get("pipeline", {}))
        if not isinstance(pipeline.get("upload_enabled"), bool):
            pipeline["upload_enabled"] = DEFAULT_CONFIG["pipeline"]["upload_enabled"]
            self.set("pipeline", pipeline)
            changed = True

        try:
            ic = int(self.get("image.image_count", DEFAULT_CONFIG["image"]["image_count"]))
        except (TypeError, ValueError):
            ic = DEFAULT_CONFIG["image"]["image_count"]
        ic = max(4, min(ic, 40))
        if ic != self.get("image.image_count"):
            self.set("image.image_count", ic)
            changed = True

        return changed

    def __repr__(self) -> str:
        return f"ConfigManager(path={self._config_path}, keys={list(self._data.keys())})"


# ── Singleton instance (import this everywhere) ──────────────────────────────
config = ConfigManager()
