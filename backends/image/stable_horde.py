"""
backends/image/stable_horde.py — Stable Horde Image Backend
=============================================================
Free community-powered image generation via the Stable Horde API.
Requires a free API key from stablehorde.net.
Generation speed varies depending on community GPU donors.
"""

import base64
import logging
import time

import requests

from backends.base import ImageBackend
from core.config_manager import config

logger = logging.getLogger("ghost.image.stable_horde")

API_BASE = "https://stablehorde.net/api/v2"
POLL_INTERVAL = 10     # seconds between polls
MAX_POLL_TIME = 120    # 2 minute timeout


def _horde_dimensions(aspect_ratio: str) -> tuple[int, int]:
    """Width/height divisible by 64; unknown → 9:16."""
    if aspect_ratio == "16:9":
        return (1920, 1088)
    return (1088, 1920)


class StableHordeBackend(ImageBackend):
    """Stable Horde — free community image generation with variable speed."""

    @property
    def name(self) -> str:
        return "Stable Horde"

    @property
    def requires_key(self) -> bool:
        return True  # free key from stablehorde.net

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
        Generate an image using Stable Horde async API.

        Flow: POST async request → poll for completion → download result.
        """
        width, height = _horde_dimensions(aspect_ratio)
        api_key = config.get("api_keys.stable_horde", "0000000000")

        headers = {
            "apikey": api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "prompt": prompt,
            "params": {
                "width": width,
                "height": height,
                "steps": 30,
                "n": 1,
            },
            "models": ["Dreamshaper"],
            "r2": True,
        }

        logger.info(f"Stable Horde: submitting job, size={width}x{height}")
        logger.debug(f"  Prompt: {prompt[:80]}…")

        try:
            # Step 1: Submit async generation request
            resp = requests.post(
                f"{API_BASE}/generate/async",
                json=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            job_id = resp.json().get("id")
            if not job_id:
                raise RuntimeError(f"Stable Horde did not return a job ID: {resp.json()}")

            logger.info(f"Stable Horde: job submitted → {job_id}")

            # Step 2: Poll for completion
            start_time = time.time()
            while time.time() - start_time < MAX_POLL_TIME:
                time.sleep(POLL_INTERVAL)
                check_resp = requests.get(
                    f"{API_BASE}/generate/check/{job_id}",
                    timeout=10,
                )
                check_resp.raise_for_status()
                check_data = check_resp.json()

                if check_data.get("done"):
                    break

                elapsed = int(time.time() - start_time)
                wait_time = check_data.get("wait_time", "?")
                logger.debug(f"  Polling ({elapsed}s elapsed, est. wait: {wait_time}s)")
            else:
                raise TimeoutError(f"Stable Horde job timed out after {MAX_POLL_TIME}s")

            # Step 3: Fetch result
            status_resp = requests.get(
                f"{API_BASE}/generate/status/{job_id}",
                timeout=30,
            )
            status_resp.raise_for_status()
            generations = status_resp.json().get("generations", [])
            if not generations:
                raise RuntimeError("Stable Horde returned no generations")

            # Download the image (could be URL or base64)
            gen = generations[0]
            img_data = gen.get("img")

            if img_data.startswith("http"):
                # It's a URL — download it
                img_resp = requests.get(img_data, timeout=30)
                img_resp.raise_for_status()
                with open(output_path, "wb") as f:
                    f.write(img_resp.content)
            else:
                # It's base64 data
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(img_data))

            logger.info(f"Stable Horde: saved → {output_path}")
            return output_path

        except TimeoutError:
            raise
        except Exception as exc:
            logger.error(f"Stable Horde failed: {exc}")
            raise RuntimeError(f"Stable Horde failed: {exc}") from exc

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        """Check API key — warn if using anonymous key."""
        api_key = config.get("api_keys.stable_horde", "")
        if not api_key:
            return (False, "Stable Horde API key required (free at stablehorde.net)")

        if api_key == "0000000000":
            logger.warning("Using anonymous Stable Horde key — generation will be slower")

        return (True, "")
