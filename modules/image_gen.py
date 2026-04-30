"""
modules/image_gen.py — Image Generation Dispatcher (Thin Wrapper)
==================================================================
Routes image generation to Gemini Imagen (Google AI).

Usage:
    from modules.image_gen import run_image_generation, generate_images

    paths = run_image_generation(prompts, output_dir)
    # or legacy:
    paths = generate_images(prompts)
"""

import asyncio
from pathlib import Path

from config import get_logger, OUTPUT_DIR
from core.config_manager import config

log = get_logger("image_gen")

# ── Backend registry ──────────────────────────────────────────────────────────

BACKEND_MAP: dict[str, type] = {}


def _get_backend_map() -> dict[str, type]:
    """Lazy-load backend classes only when needed."""
    global BACKEND_MAP
    if BACKEND_MAP:
        return BACKEND_MAP

    from backends.image.gemini_imagen import GeminiImagenBackend

    BACKEND_MAP = {
        "gemini_imagen": GeminiImagenBackend,
    }
    return BACKEND_MAP


def _get_backend():
    """Instantiate the configured image backend (Gemini Imagen only)."""
    backend_name = config.get("image.backend", "gemini_imagen")
    backend_map = _get_backend_map()

    if backend_name not in backend_map:
        raise ValueError(
            f"Unknown image backend: {backend_name!r}. "
            f"Available: {list(backend_map.keys())}"
        )

    backend = backend_map[backend_name]()
    log.info(f"Image backend: {backend.name} (local={backend.is_local}, key={backend.requires_key})")
    return backend


# ── Public API ────────────────────────────────────────────────────────────────

def run_image_generation(
    prompts: list[str],
    output_dir: str | Path | None = None,
    aspect_ratio: str | None = None,
) -> list[str]:
    """
    Generate images for a list of prompts using Gemini Imagen.

    Parameters
    ----------
    prompts : list[str]
        List of image generation prompts.
    output_dir : str or Path, optional
        Directory to save images. Defaults to OUTPUT_DIR from config.
    aspect_ratio : str, optional
        Overrides ``config`` aspect ratio for this run when set (e.g. ``"9:16"`` / ``"16:9"``).

    Returns
    -------
    list[str]
        Ordered list of output image paths.
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    backend = _get_backend()
    width = config.get("image.width", 1080)
    height = config.get("image.height", 1920)
    ar = aspect_ratio if aspect_ratio is not None else config.get("aspect_ratio", "9:16")

    # Validate backend config
    valid, error = backend.validate_config(config.data)
    if not valid:
        raise ValueError(f"Image backend {backend.name} config error: {error}")

    log.info(f"Generating {len(prompts)} images with {backend.name} ({width}x{height})")

    saved_paths: list[str] = []

    for idx, prompt in enumerate(prompts, start=1):
        out_path = str(output_dir / f"scene_{idx:02d}.png")
        log.info(f"Generating image {idx}/{len(prompts)} …")
        asyncio.run(backend.generate(prompt, out_path, width, height, aspect_ratio=ar))
        saved_paths.append(out_path)

    log.info(f"All {len(saved_paths)} image(s) saved to {output_dir}")
    return saved_paths


# ── Legacy compatibility ──────────────────────────────────────────────────────

def generate_images(
    image_prompts: list[str],
    aspect_ratio: str | None = None,
) -> list[Path]:
    """Generate images; ``aspect_ratio`` overrides config when set."""
    paths = run_image_generation(image_prompts, aspect_ratio=aspect_ratio)
    return [Path(p) for p in paths]


if __name__ == "__main__":
    test_prompts = [
        "A futuristic AI robot brain with glowing neural pathways, ultra-realistic, 8K, cinematic lighting",
    ]
    paths = generate_images(test_prompts)
    for p in paths:
        print(f"  {p}")
