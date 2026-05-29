"""System info, Ollama probe, FFmpeg bootstrap."""

from __future__ import annotations

import platform
import sys

import requests
from fastapi import APIRouter
from pydantic import BaseModel

from config import APP_VERSION
from core.config_manager import config

router = APIRouter(prefix="/api/system", tags=["system"])


class OllamaTestBody(BaseModel):
    url: str


@router.get("/info")
def system_info() -> dict:
    config.load()
    return {
        "version": APP_VERSION,
        "device_name": platform.node(),
        "env_local_path": str(config.env_local_path),
    }


@router.post("/test-ollama")
def test_ollama(body: OllamaTestBody) -> dict:
    url = body.url.rstrip("/")
    try:
        r = requests.get(f"{url}/api/tags", timeout=8)
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        data = r.json()
        models = [m.get("name", "") for m in data.get("models", [])]
        return {"ok": True, "models": models}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/probe-ollama")
def probe_ollama() -> dict:
    try:
        from modules.scripter import check_ollama_status

        installed, running, models = check_ollama_status()
        if running:
            detail = f"Running — {len(models)} model(s) available"
            suggested = models[0] if models else config.get("ollama_model", "llama3")
        elif installed:
            detail = "Installed but server not responding — run: ollama serve"
            suggested = config.get("ollama_model", "llama3")
        else:
            detail = "Ollama not found on PATH — install from ollama.com"
            suggested = config.get("ollama_model", "llama3")
        return {"status": "ok" if running else "warn", "detail": detail, "suggested_model": suggested}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def bootstrap_ffmpeg() -> None:
    """First-run FFmpeg download for frozen API exe on Windows."""
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        return
    try:
        from core.ffmpeg_bootstrap import configure_pydub_subprocess, ffmpeg_binaries_present, prepare_ffmpeg_runtime
        import threading

        configure_pydub_subprocess()
        if not ffmpeg_binaries_present():
            # Run download in background thread so FastAPI startup is instantaneous
            threading.Thread(target=prepare_ffmpeg_runtime, daemon=True).start()
    except Exception:
        pass
