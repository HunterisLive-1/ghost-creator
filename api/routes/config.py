"""FastAPI config routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from core.config_manager import config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config() -> dict:
    config.load()
    return config.data


@router.patch("")
def patch_config(body: dict[str, Any]) -> dict:
    for key, value in body.items():
        config.set(key, value)
    return {"ok": True}


@router.post("/save")
def save_config() -> dict:
    config.save()
    return {"ok": True}


@router.post("/open-env")
def open_env_local() -> dict:
    config.open_env_local()
    return {"ok": True}
