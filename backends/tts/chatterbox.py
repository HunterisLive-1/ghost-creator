"""
backends/tts/chatterbox.py — Chatterbox TTS Backend
=====================================================
Local voice-cloning TTS via a Chatterbox server running on localhost.
This is the DEFAULT backend — refactored from the original voicer.py.

Features:
  - Auto-start/stop Chatterbox server subprocess
  - Chunked synthesis for long text (avoids timeouts)
  - Voice cloning from a reference audio file
  - Retry logic per chunk
  - Kills server after synthesis to free GPU VRAM
"""

import io
import logging
import re
import shutil
import subprocess
import sys
import time

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
from pathlib import Path

import requests
from pydub import AudioSegment

from backends.base import TTSBackend
from core.config_manager import config

logger = logging.getLogger("ghost.tts.chatterbox")

MAX_RETRIES = 2
RETRY_DELAY = 5        # seconds
CHUNK_TIMEOUT = 300    # 5 min per chunk
CHUNK_SIZE = 200       # chars per chunk (Hindi/Devanagari)

_multilingual_loaded = False


class ChatterboxTTS(TTSBackend):
    """
    Local voice-cloning TTS via Chatterbox server (DEFAULT backend).

    Auto-starts the server if not running, synthesizes text in chunks,
    and kills the server after to free GPU VRAM for image generation.
    """

    @property
    def name(self) -> str:
        return "Chatterbox TTS"

    @property
    def requires_key(self) -> bool:
        return False

    @property
    def is_local(self) -> bool:
        return True

    # ── Server management ─────────────────────────────────────────────────

    def _get_server_url(self) -> str:
        return config.get("tts.chatterbox_url", "http://127.0.0.1:8004")

    def _get_base_dir(self) -> Path:
        """Project root directory."""
        return Path(config.path).parent

    def _get_chatterbox_dir(self) -> Path:
        configured_path = config.get("tts.chatterbox_path", "").strip()
        if configured_path:
            return Path(configured_path)
            
        return self._get_base_dir() / "Chatterbox-TTS-Server-windows-easyInstallation"

    def _get_ref_dir(self) -> Path:
        return self._get_chatterbox_dir() / "reference_audio"

    def _check_server(self) -> bool:
        """Return True if Chatterbox server is responding."""
        try:
            requests.get(self._get_server_url(), timeout=5)
            return True
        except Exception:
            return False

    def _start_server(self) -> bool:
        """Launch Chatterbox TTS server and wait until it responds."""
        cb_dir = self._get_chatterbox_dir()
        win_run = cb_dir / "win-run.bat"

        if not win_run.exists():
            logger.warning(f"Cannot auto-start Chatterbox — {win_run} not found.")
            return False

        logger.info("Launching Chatterbox TTS server in background …")
        subprocess.Popen(
            ["cmd", "/c", "start", "Chatterbox TTS", "/min", str(win_run)],
            cwd=str(cb_dir),
            shell=False,
            creationflags=_NO_WINDOW,
        )

        logger.info("Waiting for server to come online (can take 30–60 seconds) …")
        for i in range(90):  # 180 seconds max
            time.sleep(2)
            if self._check_server():
                logger.info(f"Chatterbox TTS server is online! (took ~{(i+1)*2}s)")
                return True
            if (i + 1) % 10 == 0:
                logger.info(f"  Still waiting … {(i+1)*2}s elapsed")

        logger.warning("Chatterbox server did not respond after 180 seconds.")
        return False

    def _kill_server(self) -> None:
        """Kill the Chatterbox server to free GPU VRAM."""
        global _multilingual_loaded
        try:
            result = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=10,
                creationflags=_NO_WINDOW,
            )
            for line in result.stdout.splitlines():
                if ":8004" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    subprocess.run(
                        ["taskkill", "/PID", pid, "/F", "/T"],
                        capture_output=True, timeout=10,
                        creationflags=_NO_WINDOW,
                    )
                    _multilingual_loaded = False
                    logger.info(f"Chatterbox server killed (PID {pid}) — ALL GPU VRAM freed.")
                    time.sleep(5)
                    return
            logger.warning("No process found on port 8004 — VRAM may already be free.")
        except Exception as exc:
            logger.warning(f"Could not kill Chatterbox server: {exc}")

    def _ensure_multilingual_model(self, language: str) -> None:
        """Load multilingual model on the server if needed for non-English."""
        global _multilingual_loaded
        if _multilingual_loaded:
            return
        if language.lower() in ("en", "english"):
            _multilingual_loaded = True
            return

        logger.info(f"Language is '{language}' — loading multilingual model …")
        try:
            resp = requests.post(
                f"{self._get_server_url()}/load_multilingual_model",
                timeout=300,
            )
            resp.raise_for_status()
            logger.info("Multilingual model loaded successfully!")
            _multilingual_loaded = True
        except Exception as exc:
            logger.warning(f"Could not load multilingual model: {exc}")
            _multilingual_loaded = True  # don't retry

    def ensure_running(self, language: str = "hi") -> bool:
        """Ensure Chatterbox server is running and ready."""
        if self._check_server():
            logger.info("Chatterbox TTS server is online")
            self._ensure_multilingual_model(language)
            return True

        logger.info("Chatterbox TTS server is not running — auto-starting …")
        if self._start_server() and self._check_server():
            logger.info("Chatterbox TTS server is online")
            self._ensure_multilingual_model(language)
            return True

        logger.error("Chatterbox TTS server failed to start!")
        return False

    # ── Text splitting ────────────────────────────────────────────────────

    @staticmethod
    def _split_text(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
        """Split text into chunks on sentence boundaries."""
        sentences = re.split(r'(?<=[।.!?])\s+', text.strip())
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

    # ── Single chunk synthesis ────────────────────────────────────────────

    def _tts_one_chunk(
        self, chunk: str, language: str, ref_filename: str,
        chunk_idx: int, total: int,
    ) -> AudioSegment:
        """Send a single chunk to Chatterbox and return an AudioSegment."""
        payload = {
            "text": chunk,
            "language": language,
            "voice_mode": "clone",
            "reference_audio_filename": ref_filename,
            "temperature": 0.4,
            "speed_factor": 1.0,
            "split_text": False,
        }

        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"  Chunk {chunk_idx}/{total} (attempt {attempt}) — {len(chunk)} chars …")
                resp = requests.post(
                    f"{self._get_server_url()}/tts",
                    json=payload,
                    timeout=CHUNK_TIMEOUT,
                )
                resp.raise_for_status()
                return AudioSegment.from_wav(io.BytesIO(resp.content))
            except requests.ConnectionError as exc:
                last_exc = exc
                logger.warning(f"  Chunk {chunk_idx} connection refused (attempt {attempt})")
            except requests.HTTPError as exc:
                last_exc = exc
                logger.warning(f"  Chunk {chunk_idx} HTTP error (attempt {attempt})")
            except Exception as exc:
                last_exc = exc
                logger.warning(f"  Chunk {chunk_idx} failed (attempt {attempt}): {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        raise RuntimeError(f"Chunk {chunk_idx} failed after {MAX_RETRIES} attempts: {last_exc}")

    # ── Main synthesis ────────────────────────────────────────────────────

    async def synthesize(self, text: str, language: str, output_path: str) -> str:
        """
        Synthesize text via Chatterbox TTS with chunked processing.

        Auto-starts server if needed, copies reference audio,
        processes chunks sequentially, and kills server after.
        """
        if not self.ensure_running(language):
            raise RuntimeError("Chatterbox TTS server could not be started.")

        ref_audio = config.get("tts.chatterbox_reference_audio", "my_voice_reference.wav")
        ref_filename = Path(ref_audio).name
        base_dir = self._get_base_dir()

        # Auto-copy reference audio into Chatterbox's reference_audio/ folder
        src = Path(ref_audio)
        if not src.is_absolute():
            src = base_dir / src
        ref_dir = self._get_ref_dir()
        dst = ref_dir / ref_filename
        if src.exists() and ref_dir.exists() and not dst.exists():
            shutil.copy2(src, dst)
            logger.info(f"Copied reference audio → {dst}")

        # Split and process chunks
        chunks = self._split_text(text)
        logger.info(f"TTS: {len(text)} chars → {len(chunks)} chunk(s), ref={ref_filename}")

        combined = AudioSegment.empty()
        for idx, chunk in enumerate(chunks, start=1):
            segment = self._tts_one_chunk(chunk, language, ref_filename, idx, len(chunks))
            combined += segment
            logger.info(f"  Chunk {idx}/{len(chunks)} done ✓ ({len(segment)}ms audio)")

        combined.export(output_path, format="mp3")
        import os
        size_kb = os.path.getsize(output_path) / 1024
        logger.info(f"Voiceover saved → {output_path} ({size_kb:.1f} KB, {len(combined)}ms total)")

        # Kill server to free GPU VRAM for image generation
        self._kill_server()
        return output_path

    def validate_config(self, config_data: dict) -> tuple[bool, str]:
        """Check Chatterbox server directory and reference audio."""
        cb_dir = self._get_chatterbox_dir()
        if not cb_dir.exists():
            return (False, f"Chatterbox server folder not found at: {cb_dir}")

        ref_audio = config.get("tts.chatterbox_reference_audio", "my_voice_reference.wav")
        ref_path = Path(ref_audio)
        if not ref_path.is_absolute():
            ref_path = self._get_base_dir() / ref_path
        if not ref_path.exists():
            return (False, f"Reference audio file not found: {ref_path}")

        return (True, "")
