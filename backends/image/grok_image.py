"""
grok_image.py — Image generation via xAI Grok Imagine API
==========================================================
Model: grok-2-image / grok-2-image-1212
Cost:  ~$0.07/img (pro) or ~$0.02/img (standard)
Docs:  https://docs.x.ai/api/endpoints#image-generation
"""

import base64
import time
import logging
import requests
from pathlib import Path

from backends.base import ImageBackend
from core.config_manager import config

logger = logging.getLogger("ghost.image.grok")

GROK_IMAGE_MODELS = {
    "grok-2-image-1212": {"cost": 0.02, "label": "Grok Imagine Standard"},
    "grok-2-image":      {"cost": 0.07, "label": "Grok Imagine Pro"},
}

_RATE_LIMIT_SLEEP = 2  # seconds between calls (respect 30 rpm limit)


class GrokImageBackend(ImageBackend):
    """xAI Grok Imagine image generation — uses xAI API key, no local GPU."""

    API_URL = "https://api.x.ai/v1/images/generations"

    @property
    def name(self) -> str:
        return "Grok Imagine"

    @property
    def requires_key(self) -> bool:
        return True

    @property
    def is_local(self) -> bool:
        return False

    def _get_api_key(self) -> str:
        return (config.get("xai_api_key") or "").strip()

    def _get_model(self) -> str:
        return config.get("grok_image_model", "grok-2-image-1212")

    async def generate(
        self,
        prompt: str,
        output_path: str,
        width: int,
        height: int,
        aspect_ratio: str = "9:16",
    ) -> str:
        """Generate one image via xAI Grok Imagine and save to output_path."""
        import asyncio
        return await asyncio.to_thread(
            self._generate_sync, prompt, output_path, aspect_ratio
        )

    def _generate_sync(self, prompt: str, output_path: str, aspect_ratio: str) -> str:
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("xAI API key not set. Add it in Settings.")

        model = self._get_model()

        # Append composition hint since Grok doesn't support aspect_ratio param
        if aspect_ratio == "16:9":
            enhanced_prompt = prompt + ", wide landscape composition, cinematic 16:9 aspect ratio"
        else:
            enhanced_prompt = prompt + ", vertical portrait composition, 9:16 aspect ratio"

        payload = {
            "model": model,
            "prompt": enhanced_prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        logger.info(f"Grok Imagine: model={model}")
        logger.debug(f"  Prompt: {enhanced_prompt[:80]}…")

        response = requests.post(self.API_URL, json=payload, headers=headers, timeout=60)

        if response.status_code == 401:
            raise Exception("Invalid xAI API key.")
        if response.status_code == 429:
            raise Exception("xAI rate limit hit (30 rpm). Wait and retry.")
        response.raise_for_status()

        data = response.json()
        image_b64 = data["data"][0]["b64_json"]
        image_bytes = base64.b64decode(image_b64)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(image_bytes)

        logger.info(f"Grok Imagine: saved → {output_path} ({len(image_bytes) / 1024:.1f} KB)")

        # Respect rate limits between sequential calls
        time.sleep(_RATE_LIMIT_SLEEP)

        return output_path

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        api_key = (config_data.get("xai_api_key") or "").strip()
        if not api_key:
            return (False, "xAI API key required. Get one at console.x.ai")
        return (True, "")

    @classmethod
    def validate_key(cls, api_key: str) -> bool:
        """Quick ping to check if key is valid (returns False on 401)."""
        try:
            r = requests.post(
                cls.API_URL,
                json={"model": "grok-2-image-1212", "prompt": "test", "n": 1, "response_format": "b64_json"},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=10,
            )
            return r.status_code != 401
        except Exception:
            return False
