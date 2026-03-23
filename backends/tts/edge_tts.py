"""
backends/tts/edge_tts.py — Microsoft Edge TTS Backend
======================================================
Free, no API key required.  Uses Microsoft Azure voices via the
edge-tts Python package.  High quality for both Hindi and English.
"""

import logging

from backends.base import TTSBackend
from core.config_manager import config

logger = logging.getLogger("ghost.tts.edge")


class EdgeTTS(TTSBackend):
    """Free cloud TTS using Microsoft Edge voices — no API key needed."""

    @property
    def name(self) -> str:
        return "Edge TTS"

    @property
    def requires_key(self) -> bool:
        return False

    @property
    def is_local(self) -> bool:
        return False

    async def synthesize(self, text: str, language: str, output_path: str) -> str:
        """
        Synthesize text to speech using edge-tts.

        Uses Hindi voice for 'hi' language, English voice otherwise.
        Output is saved as MP3.
        """
        import edge_tts

        # Select voice based on language
        if language.lower() in ("hi", "hindi"):
            voice = config.get("tts.edge_tts_voice", "hi-IN-MadhurNeural")
        else:
            voice = "en-US-GuyNeural"

        logger.info(f"Edge TTS: voice={voice}, text={len(text)} chars → {output_path}")

        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            logger.info(f"Edge TTS: saved → {output_path}")
            return output_path
        except Exception as exc:
            logger.error(f"Edge TTS synthesis failed: {exc}")
            raise RuntimeError(f"Edge TTS synthesis failed: {exc}") from exc

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        """Check if edge-tts package is installed."""
        try:
            import edge_tts  # noqa: F401
            return (True, "")
        except ImportError:
            return (False, "edge-tts package not installed. Run: pip install edge-tts")
