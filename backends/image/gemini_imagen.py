"""
backends/image/gemini_imagen.py — Gemini Image Generation Backend
==================================================================
Supports both Gemini native image generation (Nano Banana models)
and Imagen models via the Gemini API.

Nano Banana models use generate_content with IMAGE response modality.
Imagen models use generate_images API.

Reuses the same GEMINI_API_KEY — zero extra setup.
"""

import logging

from backends.base import ImageBackend
from core.config_manager import config

logger = logging.getLogger("ghost.image.gemini")


class GeminiImageNotSupportedError(RuntimeError):
    """Raised when the configured API key or project cannot use image generation (e.g. free tier)."""


def is_gemini_image_unsupported(exc: BaseException) -> bool:
    """
    Return True if this failure is due to image generation not being allowed for the key/plan,
    as opposed to quota/rate limits or transient errors.
    """
    if isinstance(exc, GeminiImageNotSupportedError):
        return True

    try:
        from google.genai.errors import APIError
    except ImportError:
        APIError = ()  # type: ignore[misc, assignment]

    def _walk_chain(err: BaseException) -> list[BaseException]:
        out: list[BaseException] = []
        seen: set[int] = set()
        e: BaseException | None = err
        while e is not None and id(e) not in seen and len(out) < 8:
            seen.add(id(e))
            out.append(e)
            e = e.__cause__
        return out

    for e in _walk_chain(exc):
        msg = str(e).lower()

        if "resourceexhausted" in msg.replace(" ", "") or "resource exhausted" in msg:
            return False
        if "429" in msg and ("quota" in msg or "rate" in msg or "exhausted" in msg):
            return False
        if "rate limit" in msg or "too many requests" in msg:
            return False

        code = getattr(e, "code", None)
        status = getattr(e, "status", None)
        st = status.upper() if isinstance(status, str) else ""

        if APIError and isinstance(e, APIError):
            if code == 429:
                return False
            if code in (403, 404):
                return True
            if st in ("PERMISSION_DENIED", "FAILED_PRECONDITION", "NOT_FOUND"):
                return True

        if "returned no image" in msg or "did not contain an image" in msg:
            return True
        if "imagen returned no images" in msg:
            return True

        if (
            any(
                p in msg
                for p in (
                    "not supported",
                    "does not support",
                    "cannot generate images",
                    "image generation is not",
                    "requested modality",
                    "permission_denied",
                    "not enabled for",
                    "billing has not been enabled",
                    "must be logged in to a",
                )
            )
            and (
                "image" in msg
                or "modality" in msg
                or "imagen" in msg
                or "generate_images" in msg
                or "generate_content" in msg
            )
        ):
            return True

    return False


# Available Gemini image models (from ListModels API)
GEMINI_IMAGE_MODELS = {
    "nano_banana":     "gemini-2.5-flash-image",
    "nano_banana_pro": "nano-banana-pro-preview",
    "gemini_3_pro":    "gemini-3-pro-image-preview",
    "gemini_3_flash":  "gemini-3.1-flash-image-preview",
    "imagen_4":        "imagen-4.0-generate-001",
    "imagen_4_fast":   "imagen-4.0-fast-generate-001",
    "imagen_4_ultra":  "imagen-4.0-ultra-generate-001",
}


class GeminiImagenBackend(ImageBackend):
    """Gemini image generation — Nano Banana + Imagen models, uses your Gemini key."""

    @property
    def name(self) -> str:
        return "Gemini Image Gen"

    @property
    def requires_key(self) -> bool:
        return True

    @property
    def is_local(self) -> bool:
        return False

    def _get_model(self) -> str:
        """Get the configured model name, resolving aliases."""
        model_key = config.get("image.gemini_image_model", "nano_banana")
        # If it's an alias, resolve it
        if model_key in GEMINI_IMAGE_MODELS:
            return GEMINI_IMAGE_MODELS[model_key]
        # Otherwise treat as a raw model name
        return model_key

    async def generate(
        self,
        prompt: str,
        output_path: str,
        width: int,
        height: int,
        aspect_ratio: str = "9:16",
    ) -> str:
        """
        Generate an image using Gemini API.

        Uses generate_content with IMAGE modality for Nano Banana / Gemini models.
        Falls back to generate_images for Imagen models.
        """
        from google import genai
        from google.genai import types

        api_key = config.get("api_keys.gemini", "")
        if not api_key:
            raise RuntimeError("Gemini API key not configured")

        model = self._get_model()
        logger.info(f"Gemini Image: model={model}")
        logger.debug(f"  Prompt: {prompt[:80]}…")

        try:
            client = genai.Client(api_key=api_key)

            # Imagen models use generate_images API
            if "imagen" in model.lower():
                return await self._generate_imagen(client, types, model, prompt, output_path, aspect_ratio)
            else:
                # Nano Banana / Gemini models use generate_content with IMAGE modality
                return await self._generate_native(client, types, model, prompt, output_path)

        except Exception as exc:
            error_msg = str(exc)
            if "ResourceExhausted" in error_msg or "quota" in error_msg.lower():
                logger.warning("Gemini image quota exceeded!")
            if is_gemini_image_unsupported(exc):
                logger.info(
                    "Gemini image generation not available for this API key/plan: %s",
                    exc,
                )
                raise GeminiImageNotSupportedError(
                    "Gemini image generation is not available for this API key"
                ) from exc
            logger.error(f"Gemini image gen failed: {exc}")
            raise RuntimeError(f"Gemini image gen failed: {exc}") from exc

    async def _generate_native(self, client, types, model: str, prompt: str, output_path: str) -> str:
        """Generate using Gemini native image generation (Nano Banana models)."""
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # Extract image from response parts
        if not response.candidates or not response.candidates[0].content.parts:
            raise RuntimeError("Gemini returned no image in response")

        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                image_bytes = part.inline_data.data
                with open(output_path, "wb") as f:
                    f.write(image_bytes)
                logger.info(f"Gemini native: saved → {output_path} ({len(image_bytes) / 1024:.1f} KB)")
                return output_path

        raise RuntimeError("Gemini response did not contain an image")

    async def _generate_imagen(
        self, client, types, model: str, prompt: str, output_path: str, aspect_ratio: str
    ) -> str:
        """Generate using Imagen models (generate_images API)."""
        ar = aspect_ratio if aspect_ratio in ("9:16", "16:9") else "9:16"

        response = client.models.generate_images(
            model=model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=ar,
            ),
        )

        if not response.generated_images:
            raise RuntimeError("Imagen returned no images")

        image = response.generated_images[0].image
        with open(output_path, "wb") as f:
            f.write(image.image_bytes)

        logger.info(f"Imagen: saved → {output_path}")
        return output_path

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        """Check that Gemini API key is configured."""
        api_key = config.get("api_keys.gemini", "")
        if not api_key:
            return (False, "Gemini API key required. Get one at aistudio.google.com")
        return (True, "")
