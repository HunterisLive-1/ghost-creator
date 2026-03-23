"""
backends/tts/kokoro_tts.py — Kokoro TTS Backend
=================================================
Local free TTS using the Kokoro model.  Downloads ~500MB model
on first use (cached by the kokoro package).  Good English quality,
limited Hindi support.
"""

import logging
import subprocess

from backends.base import TTSBackend
from core.config_manager import config

logger = logging.getLogger("ghost.tts.kokoro")


class KokoroTTS(TTSBackend):
    """Local free TTS using Kokoro — no API key, downloads model on first use."""

    @property
    def name(self) -> str:
        return "Kokoro TTS"

    @property
    def requires_key(self) -> bool:
        return False

    @property
    def is_local(self) -> bool:
        return True

    async def synthesize(self, text: str, language: str, output_path: str) -> str:
        """
        Synthesize text using Kokoro TTS.

        Note: Kokoro has limited Hindi support.  If language is Hindi,
        a warning is logged and English voice is used instead.
        """
        from kokoro import KPipeline
        import soundfile as sf
        import numpy as np

        # Kokoro language codes: "a" = American English
        if language.lower() in ("hi", "hindi"):
            logger.warning("Kokoro TTS has limited Hindi support — using English voice.")
            lang_code = "a"
        else:
            lang_code = "a"  # American English

        # Voice selection
        voice = "af_heart"  # default female voice

        logger.info(f"Kokoro TTS: voice={voice}, lang={lang_code}, text={len(text)} chars")

        try:
            pipeline = KPipeline(lang_code=lang_code)

            # Generate audio samples
            all_samples = []
            for _, _, audio in pipeline(text, voice=voice):
                all_samples.append(audio)

            if not all_samples:
                raise RuntimeError("Kokoro TTS generated no audio samples")

            # Concatenate all samples
            combined = np.concatenate(all_samples)

            # Save as WAV first
            wav_path = output_path.replace(".mp3", ".wav") if output_path.endswith(".mp3") else output_path
            sf.write(wav_path, combined, 24000)

            # Convert to MP3 if needed
            if output_path.endswith(".mp3"):
                subprocess.run(
                    ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame",
                     "-q:a", "2", output_path],
                    check=True,
                    capture_output=True,
                )
                # Clean up temp WAV
                import os
                if os.path.exists(wav_path) and wav_path != output_path:
                    os.remove(wav_path)

            logger.info(f"Kokoro TTS: saved → {output_path}")
            return output_path

        except Exception as exc:
            logger.error(f"Kokoro TTS failed: {exc}")
            raise RuntimeError(f"Kokoro TTS failed: {exc}") from exc

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        """Check if kokoro package is installed."""
        try:
            import kokoro  # noqa: F401
            return (True, "")
        except ImportError:
            return (False, "kokoro package not installed. Run: pip install kokoro soundfile")
