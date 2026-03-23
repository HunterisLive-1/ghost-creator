"""
backends/base.py — Abstract Base Classes for TTS and Image Backends
====================================================================
All TTS and Image backends must implement these interfaces.
The pipeline modules (voicer.py, image_gen.py) call only these
abstract methods — making them completely backend-agnostic.
"""

from abc import ABC, abstractmethod
from typing import Any


class TTSBackend(ABC):
    """
    Abstract base class for Text-to-Speech backends.

    Every TTS backend (Chatterbox, Edge TTS, ElevenLabs, etc.)
    must implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name (e.g. 'Edge TTS', 'Chatterbox')."""
        ...

    @property
    @abstractmethod
    def requires_key(self) -> bool:
        """Whether this backend requires an API key."""
        ...

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """Whether this backend runs locally (vs cloud API)."""
        ...

    @abstractmethod
    async def synthesize(self, text: str, language: str, output_path: str) -> str:
        """
        Synthesize text to speech and save to output_path.

        Parameters
        ----------
        text : str
            The text to convert to speech.
        language : str
            Language code (e.g. "hi", "en").
        output_path : str
            Path to save the output audio file (mp3 or wav).

        Returns
        -------
        str
            Path to the output audio file.
        """
        ...

    def validate_config(self, config: dict) -> tuple[bool, str]:
        """
        Validate that the configuration is correct for this backend.

        Parameters
        ----------
        config : dict
            The full configuration dictionary.

        Returns
        -------
        tuple[bool, str]
            (True, "") if valid, (False, "error message") if not.
        """
        return (True, "")


class ImageBackend(ABC):
    """
    Abstract base class for Image Generation backends.

    Every image backend (ComfyUI, Pollinations, Fal.ai, etc.)
    must implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name (e.g. 'ComfyUI', 'Pollinations.ai')."""
        ...

    @property
    @abstractmethod
    def requires_key(self) -> bool:
        """Whether this backend requires an API key."""
        ...

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """Whether this backend runs locally (vs cloud API)."""
        ...

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        output_path: str,
        width: int,
        height: int,
        aspect_ratio: str = "9:16",
    ) -> str:
        """
        Generate an image from a text prompt and save to output_path.

        Parameters
        ----------
        prompt : str
            The image generation prompt.
        output_path : str
            Path to save the generated image (PNG).
        width : int
            Image width in pixels (backends may override from aspect_ratio).
        height : int
            Image height in pixels (backends may override from aspect_ratio).
        aspect_ratio : str
            Target aspect ratio, e.g. "9:16" or "16:9". Unrecognized values fall back to "9:16".

        Returns
        -------
        str
            Path to the generated image file.
        """
        ...

    def validate_config(self, config: dict) -> tuple[bool, str]:
        """
        Validate that the configuration is correct for this backend.

        Parameters
        ----------
        config : dict
            The full configuration dictionary.

        Returns
        -------
        tuple[bool, str]
            (True, "") if valid, (False, "error message") if not.
        """
        return (True, "")
