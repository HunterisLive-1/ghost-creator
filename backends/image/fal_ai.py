"""
backends/image/fal_ai.py — Fal.ai Image Backend
=================================================
Fast paid image generation via Fal.ai SDK.
~$0.003/image, ~3s generation time.
"""

import logging
import os

import requests

from backends.base import ImageBackend
from core.config_manager import config

logger = logging.getLogger("ghost.image.fal")


def _fal_image_size(aspect_ratio: str) -> str:
    """Fal fast-sdxl / FLUX image_size preset; unknown → portrait 9:16."""
    if aspect_ratio == "16:9":
        return "landscape_16_9"
    return "portrait_9_16"


class FalAIBackend(ImageBackend):
    """Fal.ai — paid, fast cloud image generation (~$0.003/image)."""

    @property
    def name(self) -> str:
        return "Fal.ai"

    @property
    def requires_key(self) -> bool:
        return True

    @property
    def is_local(self) -> bool:
        return False

    async def generate(
        self,
        prompt: str,
        output_path: str,
        width: int,
        height: int,
        aspect_ratio: str = "9:16",
    ) -> str:
        """
        Generate an image using Fal.ai API.
        """
        import fal_client

        api_key = config.get("api_keys.fal_ai", "")
        if not api_key:
            raise RuntimeError("Fal.ai API key not configured")

        # Set the API key in environment (required by fal-client)
        os.environ["FAL_KEY"] = api_key

        model = config.get("image.fal_model", "fal-ai/fast-sdxl")
        image_size = _fal_image_size(aspect_ratio)

        logger.info(f"Fal.ai: model={model}, image_size={image_size}")
        logger.debug(f"  Prompt: {prompt[:80]}…")

        try:
            result = fal_client.run(
                model,
                arguments={
                    "prompt": prompt,
                    "image_size": image_size,
                },
            )

            # Download the generated image
            image_url = result["images"][0]["url"]
            resp = requests.get(image_url, timeout=30)
            resp.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(resp.content)

            logger.info(f"Fal.ai: saved → {output_path} ({len(resp.content) / 1024:.1f} KB)")
            return output_path

        except Exception as exc:
            logger.error(f"Fal.ai failed: {exc}")
            raise RuntimeError(f"Fal.ai failed: {exc}") from exc

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        """Check that Fal.ai API key is configured."""
        api_key = config.get("api_keys.fal_ai", "")
        if not api_key:
            return (False, "Fal.ai API key required. Get one at fal.ai")
        return (True, "")
