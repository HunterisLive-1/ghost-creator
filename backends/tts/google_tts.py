"""
backends/tts/google_tts.py — Google Cloud TTS Backend
======================================================
Paid cloud TTS using Google Cloud Text-to-Speech API.
Uses WaveNet voices for high quality.  Requires a service account
JSON key file.
"""

import logging
import os

from backends.base import TTSBackend
from core.config_manager import config

logger = logging.getLogger("ghost.tts.google")


class GoogleTTS(TTSBackend):
    """Google Cloud TTS with WaveNet voices — requires service account key."""

    @property
    def name(self) -> str:
        return "Google Cloud TTS"

    @property
    def requires_key(self) -> bool:
        return True

    @property
    def is_local(self) -> bool:
        return False

    async def synthesize(self, text: str, language: str, output_path: str) -> str:
        """
        Synthesize text using Google Cloud TTS WaveNet voices.
        """
        from google.cloud import texttospeech

        # Set credentials from config
        key_path = config.get("api_keys.google_tts", "")
        if not key_path:
            raise RuntimeError("Google Cloud TTS key path not configured")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path

        # Select voice based on language
        if language.lower() in ("hi", "hindi"):
            voice_name = "hi-IN-Wavenet-C"
            language_code = "hi-IN"
        else:
            voice_name = "en-US-Wavenet-D"
            language_code = "en-US"

        logger.info(f"Google TTS: voice={voice_name}, text={len(text)} chars")

        try:
            client = texttospeech.TextToSpeechClient()

            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
            )

            response = client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )

            with open(output_path, "wb") as f:
                f.write(response.audio_content)

            logger.info(f"Google TTS: saved → {output_path}")
            return output_path

        except Exception as exc:
            logger.error(f"Google TTS failed: {exc}")
            raise RuntimeError(f"Google TTS failed: {exc}") from exc

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        """Check that the service account key file exists."""
        key_path = config.get("api_keys.google_tts", "")
        if not key_path:
            return (False, "Google Cloud TTS requires a service account JSON key path.")

        if not os.path.isfile(key_path):
            return (False, f"Service account key file not found: {key_path}")

        return (True, "")
