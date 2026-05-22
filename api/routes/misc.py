"""Chrome profile setup routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from core.config_manager import config

router = APIRouter(tags=["misc"])


class ChromeSetupBody(BaseModel):
    name: str


@router.post("/api/chrome-profile/setup")
def chrome_profile_setup(body: ChromeSetupBody) -> dict:
    try:
        from setup_chrome_profile import _run_with_name

        asyncio.run(_run_with_name(body.name.strip()))
        config.load()
        return {"ok": True, "message": f"Profile '{body.name}' setup complete."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
