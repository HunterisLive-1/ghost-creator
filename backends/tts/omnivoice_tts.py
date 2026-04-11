"""
backends/tts/omnivoice_tts.py — OmniVoice local TTS (replaces Chatterbox server)
===============================================================================
Zero-shot voice cloning via k2-fsa/OmniVoice (pip package `omnivoice`).
Uses the same reference-audio setting as the old Chatterbox flow (config key
tts.chatterbox_reference_audio) plus an optional transcript line.
"""

from __future__ import annotations

import asyncio
import gc
import io
import logging
import os
import re
import tempfile
import threading
from pathlib import Path

import torch
import torchaudio
from pydub import AudioSegment

from backends.base import TTSBackend
from config import get_base_dir, get_ffmpeg_executable
from core.config_manager import config

AudioSegment.converter = get_ffmpeg_executable()

logger = logging.getLogger("ghost.tts.omnivoice")

MAX_RETRIES = 2
RETRY_DELAY = 5
CHUNK_SIZE = 220

_model = None
_load_lock = threading.Lock()


def _ref_audio_path() -> Path:
    raw = config.get("tts.chatterbox_reference_audio", "my_voice_reference.wav")
    p = Path(raw)
    if not p.is_absolute():
        p = get_base_dir() / p
    return p.resolve()


def _ref_transcript() -> str:
    return (
        config.get("tts.omnivoice_ref_transcript", "").strip()
        or "Transcription of the reference audio."
    )


def _model_id() -> str:
    return config.get("tts.omnivoice_model_id", "k2-fsa/OmniVoice").strip() or "k2-fsa/OmniVoice"


def _ensure_model_loaded() -> None:
    global _model
    with _load_lock:
        if _model is not None:
            return
        from omnivoice import OmniVoice

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device.startswith("cuda") else torch.float32
        mid = _model_id()
        logger.info("Loading OmniVoice %s on %s (dtype=%s) …", mid, device, dtype)
        _model = OmniVoice.from_pretrained(
            mid,
            device_map=device,
            dtype=dtype,
        )


def _unload_model() -> None:
    global _model
    with _load_lock:
        _model = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    logger.info("OmniVoice unloaded — GPU memory released for image stage.")


class OmniVoiceTTS(TTSBackend):
    """Local voice cloning with OmniVoice (no separate HTTP server)."""

    @property
    def name(self) -> str:
        return "OmniVoice TTS"

    @property
    def requires_key(self) -> bool:
        return False

    @property
    def is_local(self) -> bool:
        return True

    @staticmethod
    def _split_text(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
        sentences = re.split(r"(?<=[।.!?])\s+", text.strip())
        chunks: list[str] = []
        current = ""
        for sent in sentences:
            if current and len(current) + len(sent) + 1 > max_chars:
                chunks.append(current.strip())
                current = sent
            else:
                current = f"{current} {sent}" if current else sent
        if current.strip():
            chunks.append(current.strip())
        return chunks if chunks else [text]

    def ensure_running(self, language: str = "hi") -> bool:
        """Fast checks only — full model loads on first synthesis."""
        ok, err = self.validate_config(config.data)
        if not ok:
            logger.error("OmniVoice not ready: %s", err)
            return False
        return True

    def _synthesize_chunk(
        self,
        chunk: str,
        ref_path: str,
        ref_text: str,
        idx: int,
        total: int,
    ) -> torch.Tensor:
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    "  OmniVoice chunk %s/%s (try %s) — %s chars",
                    idx,
                    total,
                    attempt,
                    len(chunk),
                )
                with _load_lock:
                    if _model is None:
                        raise RuntimeError("OmniVoice model is not loaded")
                    audio = _model.generate(
                        text=chunk,
                        ref_audio=ref_path,
                        ref_text=ref_text,
                    )
                return audio[0]
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("  Chunk %s failed (try %s): %s", idx, attempt, exc)
                if attempt < MAX_RETRIES:
                    import time

                    time.sleep(RETRY_DELAY)
        raise RuntimeError(f"OmniVoice chunk {idx} failed: {last_exc}") from last_exc

    def _synthesize_sync(self, text: str, language: str, output_path: str) -> str:
        del language  # OmniVoice infers from text; pipeline language kept for API parity

        ref_path = str(_ref_audio_path())
        ref_text = _ref_transcript()
        os.makedirs(str(Path(output_path).resolve().parent), exist_ok=True)

        _ensure_model_loaded()

        chunks = self._split_text(text)
        logger.info(
            "OmniVoice: %s chars → %s chunk(s), ref=%s",
            len(text),
            len(chunks),
            Path(ref_path).name,
        )

        tensors: list[torch.Tensor] = []
        try:
            for i, chunk in enumerate(chunks, start=1):
                t = self._synthesize_chunk(chunk, ref_path, ref_text, i, len(chunks))
                t = t.detach().cpu().float()
                if t.dim() == 1:
                    t = t.unsqueeze(0)
                tensors.append(t)
            full = torch.cat(tensors, dim=-1)

            tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_wav.close()
            try:
                torchaudio.save(tmp_wav.name, full, 24000)
                combined = AudioSegment.from_wav(tmp_wav.name)
                combined.export(output_path, format="mp3")
            finally:
                try:
                    os.unlink(tmp_wav.name)
                except OSError:
                    pass

            size_kb = os.path.getsize(output_path) / 1024
            logger.info(
                "Voiceover saved → %s (%.1f KB, %sms)",
                output_path,
                size_kb,
                len(combined),
            )
        finally:
            _unload_model()

        return output_path

    async def synthesize(self, text: str, language: str, output_path: str) -> str:
        return await asyncio.to_thread(self._synthesize_sync, text, language, output_path)

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        ref = _ref_audio_path()
        if not ref.exists():
            return (False, f"Reference audio not found: {ref}")
        try:
            import omnivoice  # noqa: F401
        except ImportError:
            return (
                False,
                "Python package 'omnivoice' not installed. "
                "Install PyTorch for your platform, then: pip install omnivoice",
            )
        return (True, "")
