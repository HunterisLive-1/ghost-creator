"""Chrome profile setup routes + YouTube Analytics API routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.config_manager import config

router = APIRouter(tags=["misc"])


class ChromeSetupBody(BaseModel):
    name: str


class ChromeSyncBody(BaseModel):
    profile_index: int


class ResolveChannelBody(BaseModel):
    url: str


@router.post("/api/chrome-profile/setup")
def chrome_profile_setup(body: ChromeSetupBody) -> dict:
    try:
        from setup_chrome_profile import _run_with_name

        asyncio.run(_run_with_name(body.name.strip()))
        config.load()
        return {"ok": True, "message": f"Profile '{body.name}' setup complete."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


# ── YouTube Analytics API routes ──────────────────────────────────────────────

@router.get("/api/yt-analytics/status")
def yt_analytics_status(profile_index: int = 0) -> dict:
    """Check if a profile has a connected Google account (valid OAuth token)."""
    try:
        from core.yt_analytics import is_connected
        connected = is_connected(profile_index)
        return {"ok": True, "connected": connected}
    except Exception as exc:
        return {"ok": False, "connected": False, "error": str(exc)}


@router.post("/api/yt-analytics/connect")
async def yt_analytics_connect(body: ChromeSyncBody) -> dict:
    """Start OAuth2 flow — opens browser for Google sign-in consent."""
    try:
        from core.yt_analytics import start_oauth_flow
        # Run in thread so it doesn't block the event loop
        result = await asyncio.to_thread(start_oauth_flow, body.profile_index)
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/api/yt-analytics/resolve-channel")
async def yt_analytics_resolve_channel(body: ResolveChannelBody) -> dict:
    """Extract channel ID, name, and avatar from a YouTube URL using yt-dlp."""
    try:
        from core.yt_analytics import resolve_channel_from_url
        result = await asyncio.to_thread(resolve_channel_from_url, body.url.strip())
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/api/yt-analytics/sync")
async def yt_analytics_sync(body: ChromeSyncBody) -> dict:
    """Fetch real YouTube analytics (views, subs, earnings) via Analytics API."""
    try:
        from core.yt_analytics import fetch_analytics
        
        # Retrieve channel ID from configuration if set
        profiles = config.get("pipeline.chrome_profiles", [])
        channel_id = None
        if 0 <= body.profile_index < len(profiles):
            channel_id = profiles[body.profile_index].get("channel_id")
            
        result = await asyncio.to_thread(fetch_analytics, body.profile_index, channel_id)

        if result.get("ok"):
            # Also persist the fetched values into config
            profiles = config.get("pipeline.chrome_profiles", [])
            if 0 <= body.profile_index < len(profiles):
                profiles[body.profile_index]["views_28d"] = result["views"]
                profiles[body.profile_index]["subs_28d"] = result["subs"]
                profiles[body.profile_index]["earnings_28d"] = result["earnings"]
                profiles[body.profile_index]["views_series"] = result.get("views_series", [])
                profiles[body.profile_index]["subs_series"] = result.get("subs_series", [])
                profiles[body.profile_index]["earnings_series"] = result.get("earnings_series", [])
                profiles[body.profile_index]["views_growth"] = result.get("views_growth", "")
                profiles[body.profile_index]["subs_growth"] = result.get("subs_growth", "")
                profiles[body.profile_index]["earnings_growth"] = result.get("earnings_growth", "")
                if result.get("channel_name"):
                    profiles[body.profile_index]["yt_channel_name"] = result["channel_name"]
                if result.get("channel_thumb"):
                    profiles[body.profile_index]["yt_channel_thumb"] = result["channel_thumb"]
                if result.get("channel_id"):
                    profiles[body.profile_index]["channel_id"] = result["channel_id"]
                config.set("pipeline.chrome_profiles", profiles)
                config.save()

        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/api/yt-analytics/disconnect")
def yt_analytics_disconnect(body: ChromeSyncBody) -> dict:
    """Remove saved OAuth token for a profile."""
    try:
        from core.yt_analytics import disconnect
        return disconnect(body.profile_index)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Legacy scraper sync (kept as fallback) ───────────────────────────────────

@router.post("/api/chrome-profile/sync")
async def chrome_profile_sync(body: ChromeSyncBody) -> dict:
    try:
        from core.youtube_scraper import scrape_youtube_studio

        profiles = config.get("pipeline.chrome_profiles", [])
        if body.profile_index < 0 or body.profile_index >= len(profiles):
            return {"ok": False, "error": f"Invalid profile index: {body.profile_index}"}

        profile = profiles[body.profile_index]
        profile_path = profile.get("path")
        channel_id = profile.get("channel_id")

        if not profile_path:
            return {"ok": False, "error": "Profile path is not set."}

        res = await scrape_youtube_studio(profile_path, channel_id)

        if res.get("ok"):
            profile["views_28d"] = res["views"]
            profile["subs_28d"] = res["subs"]
            profile["earnings_28d"] = res["earnings"]
            profile["views_series"] = []
            profile["subs_series"] = []
            profile["earnings_series"] = []
            profile["views_growth"] = ""
            profile["subs_growth"] = ""
            profile["earnings_growth"] = ""
            config.set("pipeline.chrome_profiles", profiles)
            config.save()

            return {
                "ok": True,
                "views": res["views"],
                "subs": res["subs"],
                "earnings": res["earnings"]
            }
        else:
            return {"ok": False, "error": res.get("error")}

    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Meta AI browser footage ───────────────────────────────────────────────────

@router.post("/api/meta-ai/test-login")
async def meta_ai_test_login() -> dict:
    try:
        from modules.ai_video.meta_ai_browser import check_meta_login

        return await check_meta_login()
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@router.post("/api/meta-ai/setup-profile")
def meta_ai_setup_profile() -> dict:
    try:
        from setup_meta_profile import run_setup

        profile = asyncio.run(run_setup())
        config.load()
        return {
            "ok": True,
            "message": f"Meta AI profile saved: {profile}",
            "profile_path": str(profile),
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@router.get("/api/local-file")
def get_local_file(path: str):
    import os
    from fastapi import HTTPException
    
    # Strip quotes if copied with quotes
    clean_path = path.strip('\'"')
    # Normalize path formatting
    clean_path = os.path.abspath(os.path.normpath(clean_path))
    
    if os.path.isfile(clean_path):
        return FileResponse(clean_path)
    
    raise HTTPException(status_code=404, detail=f"File not found: {clean_path}")
