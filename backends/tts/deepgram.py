"""
backends/tts/deepgram.py — Deepgram TTS Backend
================================================
Cloud TTS via Deepgram API.

Uses the Deepgram REST API directly (no SDK dependency).
"""

import logging
import os
from pathlib import Path

import requests

from backends.base import TTSBackend
from core.config_manager import config

logger = logging.getLogger("ghost.tts.deepgram")


class DeepgramTTS(TTSBackend):
    """Cloud TTS via Deepgram — requires API key."""

    @property
    def name(self) -> str:
        return "Deepgram"

    @property
    def requires_key(self) -> bool:
        return True

    @property
    def is_local(self) -> bool:
        return False

    async def synthesize(self, text: str, language: str, output_path: str) -> str:
        os.makedirs(str(Path(output_path).resolve().parent), exist_ok=True)

        api_key = config.get("api_keys.deepgram", "").strip()
        if not api_key:
            raise RuntimeError("Deepgram API key not configured")

        # Deepgram API: model IS the voice — single query param, no separate "voice" param.
        # Valid examples: "aura-asteria-en", "aura-2-asteria-en", "aura-2-zeus-en"
        model = config.get("tts.deepgram_voice", "aura-asteria-en").strip()

        url = "https://api.deepgram.com/v1/speak"
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }
        params = {"model": model}
        payload = {"text": text}

        logger.info(
            f"Deepgram TTS: model={model}, text={len(text)} chars → {output_path}"
        )

        try:
            resp = requests.post(url, headers=headers, json=payload, params=params, timeout=120)
            if resp.status_code >= 400:
                raise RuntimeError(f"Deepgram TTS HTTP {resp.status_code}: {resp.text}")

            with open(output_path, "wb") as f:
                f.write(resp.content)

            logger.info(f"Deepgram TTS: saved → {output_path}")
            return output_path

        except Exception as exc:
            logger.error(f"Deepgram TTS failed: {exc}")
            raise RuntimeError(f"Deepgram TTS failed: {exc}") from exc

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        api_key = config.get("api_keys.deepgram", "").strip()
        if not api_key:
            return (False, "Deepgram API key is required. Get one at console.deepgram.com")

        voice = config.get("tts.deepgram_voice", "").strip()
        if not voice:
            return (False, "Deepgram voice/model is required (e.g. aura-asteria-en).")

        return (True, "")
