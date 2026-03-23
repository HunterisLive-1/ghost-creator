"""
backends/image/comfyui.py — ComfyUI Image Backend
===================================================
Local image generation via a ComfyUI server running DreamshaperXL.
This is the DEFAULT backend — refactored from the original image_gen.py.

Pipeline: DreamshaperXL → KSampler → VAEDecode → 4K Upscale → SaveImage
"""

import copy
import json
import logging
import random
import time
import uuid
from pathlib import Path

import requests

from backends.base import ImageBackend
from core.config_manager import config

logger = logging.getLogger("ghost.image.comfyui")

POLL_INTERVAL = 3       # seconds between /history polls
MAX_POLL_RETRIES = 120  # 6 minutes max per image


class ComfyUIBackend(ImageBackend):
    """Local ComfyUI image generation (DEFAULT backend) — DreamshaperXL pipeline."""

    @property
    def name(self) -> str:
        return "ComfyUI"

    @property
    def requires_key(self) -> bool:
        return False

    @property
    def is_local(self) -> bool:
        return True

    def _get_url(self) -> str:
        return config.get("image.comfyui_url", "http://127.0.0.1:8188")

    def _get_workflow_path(self) -> Path:
        """Path to workflow_api.json in project root."""
        return Path(config.path).parent / "workflow_api.json"

    def _load_workflow(self) -> dict:
        """Read and return the base ComfyUI workflow JSON."""
        wf_path = self._get_workflow_path()
        if not wf_path.exists():
            raise FileNotFoundError(f"workflow_api.json not found at {wf_path}")
        with open(wf_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _apply_empty_latent_aspect(self, wf: dict, aspect_ratio: str) -> None:
        """Set EmptyLatentImage width/height from aspect ratio; unknown → 9:16."""
        if aspect_ratio == "16:9":
            w, h = 1920, 1080
        else:
            w, h = 1080, 1920
        for node in wf.values():
            if isinstance(node, dict) and node.get("class_type") == "EmptyLatentImage":
                node.setdefault("inputs", {})
                node["inputs"]["width"] = w
                node["inputs"]["height"] = h

    def _inject_prompt(self, workflow: dict, prompt_text: str, aspect_ratio: str = "9:16") -> dict:
        """
        Deep-copy the workflow, inject prompt into node '3' (positive
        CLIPTextEncode) and a random seed into node '15' (KSampler).
        """
        wf = copy.deepcopy(workflow)
        wf["3"]["inputs"]["text"] = prompt_text
        wf["15"]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
        self._apply_empty_latent_aspect(wf, aspect_ratio)
        return wf

    def _submit_prompt(self, workflow: dict) -> str:
        """POST the workflow to ComfyUI and return the assigned prompt_id."""
        url = self._get_url()
        client_id = str(uuid.uuid4())
        payload = {"prompt": workflow, "client_id": client_id}
        resp = requests.post(f"{url}/prompt", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return a prompt_id: {data}")
        logger.debug(f"Queued ComfyUI job → prompt_id: {prompt_id}")
        return prompt_id

    def _wait_for_job(self, prompt_id: str) -> list[dict]:
        """Poll /history until the job completes. Returns output image info list."""
        url = f"{self._get_url()}/history/{prompt_id}"
        for attempt in range(MAX_POLL_RETRIES):
            time.sleep(POLL_INTERVAL)
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            history = resp.json()

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_id in ["9", *outputs.keys()]:
                    node_out = outputs.get(str(node_id), {})
                    if "images" in node_out:
                        images = node_out["images"]
                        logger.debug(f"Job done — {len(images)} image(s) from node {node_id}")
                        return images
            logger.debug(f"Polling … attempt {attempt + 1}/{MAX_POLL_RETRIES}")

        raise TimeoutError(f"ComfyUI job {prompt_id} did not complete in time.")

    def _download_image(self, image_info: dict, out_path: str) -> None:
        """Download a single image from ComfyUI /view endpoint."""
        url = self._get_url()
        params = {
            "filename": image_info["filename"],
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        }
        resp = requests.get(f"{url}/view", params=params, timeout=30)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        logger.info(f"Image downloaded → {out_path} ({len(resp.content) / 1024:.1f} KB)")

    def _free_models(self) -> None:
        """Tell ComfyUI to unload all models so they reload with full VRAM."""
        try:
            url = self._get_url()
            resp = requests.post(
                f"{url}/free",
                json={"unload_models": True},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("ComfyUI models unloaded — will reload with full VRAM on next prompt.")
        except Exception as exc:
            logger.warning(f"Could not free ComfyUI models: {exc}")

    async def generate(
        self,
        prompt: str,
        output_path: str,
        width: int,
        height: int,
        aspect_ratio: str = "9:16",
    ) -> str:
        """
        Generate a single image via ComfyUI pipeline.
        """
        logger.info(f"ComfyUI: generating image → {output_path}")
        logger.debug(f"  Prompt: {prompt[:80]}…")

        base_workflow = self._load_workflow()
        wf = self._inject_prompt(base_workflow, prompt, aspect_ratio)
        prompt_id = self._submit_prompt(wf)
        images_info = self._wait_for_job(prompt_id)
        self._download_image(images_info[0], output_path)

        return output_path

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        """Check if ComfyUI server is reachable."""
        url = self._get_url()
        try:
            resp = requests.get(f"{url}/system_stats", timeout=5)
            resp.raise_for_status()
            return (True, "")
        except Exception:
            return (False, f"ComfyUI not running at {url}. Start ComfyUI first.")
