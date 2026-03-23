"""
backends/tts/elevenlabs.py — ElevenLabs TTS Backend
=====================================================
Paid cloud TTS with the highest quality voice synthesis.
Uses the official ElevenLabs SDK with multilingual v2 model
for Hindi support.
"""

import logging

from backends.base import TTSBackend
from core.config_manager import config

logger = logging.getLogger("ghost.tts.elevenlabs")


class ElevenLabsTTS(TTSBackend):
    """Paid cloud TTS via ElevenLabs — requires API key and voice ID."""

    @property
    def name(self) -> str:
        return "ElevenLabs"

    @property
    def requires_key(self) -> bool:
        return True

    @property
    def is_local(self) -> bool:
        return False

    async def synthesize(self, text: str, language: str, output_path: str) -> str:
        """
        Synthesize text using ElevenLabs API.

        Uses eleven_multilingual_v2 model for Hindi support.
        """
        from elevenlabs import ElevenLabs as ElevenLabsClient

        api_key = config.get("api_keys.elevenlabs", "")
        voice_id = config.get("tts.elevenlabs_voice_id", "")

        if not api_key:
            raise RuntimeError("ElevenLabs API key not configured")
        if not voice_id:
            raise RuntimeError("ElevenLabs voice ID not configured")

        logger.info(f"ElevenLabs TTS: voice_id={voice_id}, text={len(text)} chars")

        try:
            client = ElevenLabsClient(api_key=api_key)
            audio_generator = client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2",
            )

            # Write audio bytes to file
            with open(output_path, "wb") as f:
                for chunk in audio_generator:
                    f.write(chunk)

            logger.info(f"ElevenLabs TTS: saved → {output_path}")
            return output_path

        except Exception as exc:
            logger.error(f"ElevenLabs TTS failed: {exc}")
            raise RuntimeError(f"ElevenLabs TTS failed: {exc}") from exc

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        """Check API key and voice ID are configured."""
        api_key = config.get("api_keys.elevenlabs", "")
        if not api_key:
            return (False, "ElevenLabs API key is required. Get one at elevenlabs.io")

        voice_id = config.get("tts.elevenlabs_voice_id", "")
        if not voice_id:
            return (False, "ElevenLabs voice ID is required. Find it in your ElevenLabs dashboard.")

        return (True, "")
