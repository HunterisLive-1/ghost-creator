"""
backends/tts/elevenlabs.py — ElevenLabs TTS Backend
=====================================================
Paid cloud TTS with the highest quality voice synthesis.
Uses the official ElevenLabs SDK with ``eleven_multilingual_v2`` for
Hindi and other languages (Telugu, Odia, Tamil, etc. — choose a multilingual
voice in the ElevenLabs dashboard for best results).
"""

import logging
import os
from pathlib import Path

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
        Voice settings tuned for maximum realism:
        - stability: low (0.25–0.40) → more expressive, natural variation
        - similarity_boost: high (0.85) → stays true to the voice character
        - style: 0.45 → moderate emotional style exaggeration
        - use_speaker_boost: True → higher clarity and presence
        """
        from elevenlabs import ElevenLabs as ElevenLabsClient
        from elevenlabs.types import VoiceSettings

        os.makedirs(str(Path(output_path).resolve().parent), exist_ok=True)

        api_key = config.get("api_keys.elevenlabs", "")
        voice_id = config.get("tts.elevenlabs_voice_id", "")

        if not api_key:
            raise RuntimeError("ElevenLabs API key not configured")
        if not voice_id:
            raise RuntimeError("ElevenLabs voice ID not configured")

        # Read tunable settings from config (with realistic defaults)
        stability         = float(config.get("tts.elevenlabs_stability", 0.30))
        similarity_boost  = float(config.get("tts.elevenlabs_similarity_boost", 0.85))
        style_exaggeration = float(config.get("tts.elevenlabs_style", 0.45))

        logger.info(
            f"ElevenLabs TTS: voice_id={voice_id}, text={len(text)} chars  "
            f"stability={stability} similarity={similarity_boost} style={style_exaggeration}"
        )

        try:
            client = ElevenLabsClient(api_key=api_key)
            audio_generator = client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2",
                voice_settings=VoiceSettings(
                    stability=stability,
                    similarity_boost=similarity_boost,
                    style=style_exaggeration,
                    use_speaker_boost=True,
                ),
            )

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
