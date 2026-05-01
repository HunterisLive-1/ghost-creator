"""
modules/tts_lang_support.py
=============================
Pipeline narration language helpers: map ISO/codes to OmniVoice API tags,
and validate that the configured TTS backend can speak the selected language.
"""

from __future__ import annotations

from core.config_manager import config

# Languages exposed in Settings → narration (must match GUI + scripter).
SUPPORTED_PIPELINE_LANGS: frozenset[str] = frozenset({
    "hi",
    "hinglish",
    "en",
    "mr",
    "bn",
    "gu",
    "ta",
    "te",
    "or",
})


def normalize_pipeline_language(code: str | None) -> str:
    return (code or "hi").lower().strip()


def resolve_omnivoice_language_tag(pipeline_lang: str, language_hint: str = "") -> str:
    """
    Map Ghost pipeline language (and optional Settings language hint) to the
    `language` field expected by k2-fsa OmniVoice WebUI / pip API.

    See OmniVoice ``docs/languages.md`` / ``lang_id_name_map.tsv``:
    Odia → ory; Telugu → te; Tamil → ta; etc.
    """
    raw = (language_hint or "").strip()
    if not raw or raw.lower() in ("auto", "none", "default"):
        raw = normalize_pipeline_language(pipeline_lang)
    s = raw.lower().strip()
    if "_" in s:
        s = s.split("_")[0]

    aliases: dict[str, str] = {
        "or": "ory",
        "odia": "ory",
        "oriya": "ory",
        "ory": "ory",
        "odi": "ory",
        "tel": "te",
        "telugu": "te",
        "tam": "ta",
        "tamil": "ta",
        "hinglish": "en",
        "english": "en",
        "hindi": "hi",
        "hin": "hi",
    }
    if s in aliases:
        return aliases[s]
    return raw



# Default Edge voices (India Neural). Hindi follows tts.edge_tts_voice when lang is hi/hinglish.
EDGE_DEFAULT_VOICE_BY_LANG: dict[str, str] = {
    "en": "en-US-GuyNeural",
    "mr": "mr-IN-ManoharNeural",
    "bn": "bn-IN-BashkarNeural",
    "gu": "gu-IN-NiranjanNeural",
    "ta": "ta-IN-ValluvarNeural",
    "te": "te-IN-MohanNeural",
    "or": "or-IN-JagaNeural",
}

# Edge: Hindi/Hinglish use ``tts.edge_tts_voice``; other codes use defaults above.
EDGE_TTS_SUPPORTED_LANGS: frozenset[str] = frozenset(EDGE_DEFAULT_VOICE_BY_LANG.keys()) | {"hi", "hinglish"}


def edge_tts_voice_for_language(language_code: str | None) -> str:
    """Resolve Edge voice short name. Hindi + Hinglish use ``tts.edge_tts_voice``."""
    lang = normalize_pipeline_language(language_code)
    if lang in ("hi", "hindi", "hinglish"):
        return str(config.get("tts.edge_tts_voice", "hi-IN-MadhurNeural"))
    return EDGE_DEFAULT_VOICE_BY_LANG.get(lang, "en-US-GuyNeural")


def assert_tts_backend_supports_language(backend_name: str | None, pipeline_lang: str | None) -> None:
    """
    Raise ValueError with a user-facing message if this backend cannot
    synthesize the pipeline language in Ghost.

    - OmniVoice: multilingual (Telugu/Odia supported; Odia uses tag ``ory``).
    - ElevenLabs: ``eleven_multilingual_v2`` — allowed (choose a multilingual voice).
    - Edge TTS: only languages with a known Neural voice mapping.
    """
    b = (backend_name or "").strip().lower()
    lang = normalize_pipeline_language(pipeline_lang)

    if lang not in SUPPORTED_PIPELINE_LANGS:
        raise ValueError(
            f"Narration language {lang!r} is not supported in Ghost. "
            f"Choose one of: {', '.join(sorted(SUPPORTED_PIPELINE_LANGS))} in Settings."
        )

    if b == "edge_tts":
        if lang not in EDGE_TTS_SUPPORTED_LANGS:
            raise ValueError(
                f"Edge TTS does not have a preset voice for language {lang!r}. "
                f"Switch TTS to OmniVoice or ElevenLabs in Settings, or use: "
                f"{', '.join(sorted(EDGE_TTS_SUPPORTED_LANGS))}."
            )
        return
    if b in ("omnivoice", "elevenlabs"):
        return
