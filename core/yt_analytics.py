"""
core/yt_analytics.py — YouTube Analytics API (OAuth2)
=====================================================
Uses Google OAuth 2.0 to authenticate and fetch real analytics
from YouTube Data API v3 + YouTube Analytics API.

Flow:
  1. First time: open browser for OAuth consent → save token to file
  2. Next time: load saved token (auto-refresh if expired)
  3. Fetch: views, subscribers, estimated revenue for last 28 days
"""
from __future__ import annotations

import json
import os
import threading
import webbrowser
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# These are installed by google-api-python-client + google-auth-oauthlib
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_LIBS_OK = True
except ImportError:
    import subprocess
    import sys
    try:
        print("[yt_analytics] Attempting to install missing Google client libraries...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-auth-oauthlib", "google-api-python-client"])
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        GOOGLE_LIBS_OK = True
    except Exception as exc:
        print(f"[yt_analytics] Auto-install failed: {exc}")
        GOOGLE_LIBS_OK = False

# ── Scopes needed ─────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",  # earnings
]

# ── Token storage — one per profile (by index) ────────────────────────────────
TOKEN_DIR = Path(os.environ.get("APPDATA", Path.home())) / "GhostCreatorAI" / "yt_tokens"
CLIENT_SECRETS_PATH = Path(__file__).parent.parent / "yt_client_secrets.json"


def _token_path(profile_index: int) -> Path:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    return TOKEN_DIR / f"token_profile_{profile_index}.json"


def _load_creds(profile_index: int) -> Optional[Credentials]:
    tp = _token_path(profile_index)
    if not tp.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(tp), SCOPES)
        return creds
    except Exception:
        return None


def _save_creds(creds: Credentials, profile_index: int):
    tp = _token_path(profile_index)
    tp.write_text(creds.to_json())


def _get_valid_creds(profile_index: int) -> Optional[Credentials]:
    """Load existing creds, refresh if expired, return None if need new login."""
    creds = _load_creds(profile_index)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_creds(creds, profile_index)
            return creds
        except Exception:
            pass
    return None


def is_connected(profile_index: int) -> bool:
    """Return True if we have a valid (or refreshable) token for this profile."""
    if not GOOGLE_LIBS_OK:
        return False
    return _get_valid_creds(profile_index) is not None


def start_oauth_flow(profile_index: int) -> dict:
    """
    Start OAuth2 flow. Opens browser for consent.
    Blocks until user completes login (uses local server callback on port 8788+index).
    Returns {"ok": True} or {"ok": False, "error": str}
    """
    if not GOOGLE_LIBS_OK:
        return {"ok": False, "error": "google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib google-api-python-client"}

    if not CLIENT_SECRETS_PATH.exists():
        return {
            "ok": False,
            "error": (
                f"Client secrets file not found: {CLIENT_SECRETS_PATH}\n"
                "Please download OAuth 2.0 credentials from Google Cloud Console:\n"
                "  1. Go to console.cloud.google.com\n"
                "  2. Create project → Enable YouTube Data API v3 + YouTube Analytics API\n"
                "  3. Create OAuth 2.0 Client ID (Desktop app)\n"
                "  4. Download JSON → save as 'yt_client_secrets.json' in the ghost-creator folder"
            ),
        }

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_PATH), SCOPES)
        try:
            creds = flow.run_local_server(port=0, open_browser=True, prompt="consent", timeout_seconds=120)
        except TypeError:
            creds = flow.run_local_server(port=0, open_browser=True, prompt="consent")
        _save_creds(creds, profile_index)
        return {"ok": True, "message": "Google account connected successfully!"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fetch_analytics(profile_index: int, channel_id: Optional[str] = None) -> dict:
    """
    Fetch real YouTube analytics for last 28 days.
    Returns: {"ok": True, "views": int, "subs": int, "earnings": float, "channel_name": str, ...}
    """
    if not GOOGLE_LIBS_OK:
        return {"ok": False, "error": "google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib google-api-python-client"}

    creds = _get_valid_creds(profile_index)
    if creds is None:
        return {"ok": False, "error": "Not connected. Please click 'Connect Google Account' first."}

    try:
        # Date range: last 28 days
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=28)).isoformat()

        # ── YouTube Data API: get channel ID ─────────────────────────────────
        yt_service = build("youtube", "v3", credentials=creds, cache_discovery=False)
        # Always fetch channels owned by the logged-in user to avoid 403 Forbidden reports queries
        channels_resp = yt_service.channels().list(part="snippet,statistics", mine=True).execute()
        items = channels_resp.get("items", [])
        if not items:
            return {"ok": False, "error": "No YouTube channel found for this Google account."}

        # If user owns multiple channels, match the target channel_id if possible
        channel = items[0]
        if channel_id:
            for item in items:
                if item["id"] == channel_id:
                    channel = item
                    break

        channel_id = channel["id"]
        channel_name = channel["snippet"].get("title", "Unknown")
        channel_thumb = channel["snippet"].get("thumbnails", {}).get("default", {}).get("url", "")
        stats = channel.get("statistics", {})
        total_subs = int(stats.get("subscriberCount", 0))

        # ── YouTube Analytics API: views + revenue for last 28 days ─────────
        analytics_service = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        
        # Views
        views_resp = analytics_service.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics="views",
        ).execute()
        views_28d = 0
        if views_resp.get("rows"):
            views_28d = int(views_resp["rows"][0][0])

        # Subscriber gains in 28d
        subs_resp = analytics_service.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics="subscribersGained,subscribersLost",
        ).execute()
        subs_28d = 0
        if subs_resp.get("rows"):
            subs_28d = int(subs_resp["rows"][0][0]) - int(subs_resp["rows"][0][1])

        # Revenue (monetized channels only — non-monetized returns 0)
        earnings_28d = 0.0
        try:
            rev_resp = analytics_service.reports().query(
                ids=f"channel=={channel_id}",
                startDate=start_date,
                endDate=end_date,
                metrics="estimatedRevenue",
                currency="USD",
            ).execute()
            if rev_resp.get("rows"):
                earnings_28d = float(rev_resp["rows"][0][0])
        except Exception:
            pass  # Non-monetized channel — earnings = 0

        # ── Real daily series data ───────────────────────────────────────────
        views_series = []
        try:
            v_series_resp = analytics_service.reports().query(
                ids=f"channel=={channel_id}",
                startDate=start_date,
                endDate=end_date,
                metrics="views",
                dimensions="day",
            ).execute()
            if v_series_resp.get("rows"):
                sorted_rows = sorted(v_series_resp["rows"], key=lambda r: r[0])
                views_series = [int(r[1]) for r in sorted_rows]
        except Exception:
            pass

        subs_series = []
        try:
            s_series_resp = analytics_service.reports().query(
                ids=f"channel=={channel_id}",
                startDate=start_date,
                endDate=end_date,
                metrics="subscribersGained,subscribersLost",
                dimensions="day",
            ).execute()
            if s_series_resp.get("rows"):
                sorted_rows = sorted(s_series_resp["rows"], key=lambda r: r[0])
                subs_series = [int(r[1]) - int(r[2]) for r in sorted_rows]
        except Exception:
            pass

        earnings_series = []
        try:
            e_series_resp = analytics_service.reports().query(
                ids=f"channel=={channel_id}",
                startDate=start_date,
                endDate=end_date,
                metrics="estimatedRevenue",
                dimensions="day",
            ).execute()
            if e_series_resp.get("rows"):
                sorted_rows = sorted(e_series_resp["rows"], key=lambda r: r[0])
                earnings_series = [float(r[1]) for r in sorted_rows]
        except Exception:
            pass

        # ── Growth rates compared to previous 28 days ────────────────────────
        prev_end_date = (date.today() - timedelta(days=29)).isoformat()
        prev_start_date = (date.today() - timedelta(days=57)).isoformat()
        
        views_growth = ""
        subs_growth = ""
        earnings_growth = ""
        
        try:
            prev_v_resp = analytics_service.reports().query(
                ids=f"channel=={channel_id}",
                startDate=prev_start_date,
                endDate=prev_end_date,
                metrics="views",
            ).execute()
            prev_views = int(prev_v_resp["rows"][0][0]) if prev_v_resp.get("rows") else 0
            if prev_views > 0:
                pct = ((views_28d - prev_views) / prev_views) * 100
                views_growth = f"{'+' if pct >= 0 else ''}{pct:.1f}%"
            else:
                views_growth = "+100%" if views_28d > 0 else "0%"
        except Exception:
            pass
            
        try:
            prev_s_resp = analytics_service.reports().query(
                ids=f"channel=={channel_id}",
                startDate=prev_start_date,
                endDate=prev_end_date,
                metrics="subscribersGained,subscribersLost",
            ).execute()
            prev_subs = int(prev_s_resp["rows"][0][0]) - int(prev_s_resp["rows"][0][1]) if prev_s_resp.get("rows") else 0
            if prev_subs > 0:
                pct = ((subs_28d - prev_subs) / prev_subs) * 100
                subs_growth = f"{'+' if pct >= 0 else ''}{pct:.1f}%"
            else:
                subs_growth = f"{'+' if subs_28d >= 0 else ''}100%" if subs_28d != 0 else "0%"
        except Exception:
            pass

        try:
            prev_e_resp = analytics_service.reports().query(
                ids=f"channel=={channel_id}",
                startDate=prev_start_date,
                endDate=prev_end_date,
                metrics="estimatedRevenue",
            ).execute()
            prev_earnings = float(prev_e_resp["rows"][0][0]) if prev_e_resp.get("rows") else 0.0
            if prev_earnings > 0:
                pct = ((earnings_28d - prev_earnings) / prev_earnings) * 100
                earnings_growth = f"{'+' if pct >= 0 else ''}{pct:.1f}%"
            else:
                earnings_growth = "+100%" if earnings_28d > 0 else "0%"
        except Exception:
            pass

        return {
            "ok": True,
            "views": views_28d,
            "subs": subs_28d,
            "earnings": earnings_28d,
            "views_series": views_series,
            "subs_series": subs_series,
            "earnings_series": earnings_series,
            "views_growth": views_growth,
            "subs_growth": subs_growth,
            "earnings_growth": earnings_growth,
            "channel_name": channel_name,
            "channel_thumb": channel_thumb,
            "total_subs": total_subs,
            "channel_id": channel_id,
        }

    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def disconnect(profile_index: int) -> dict:
    """Remove saved token for this profile."""
    tp = _token_path(profile_index)
    if tp.exists():
        tp.unlink()
    return {"ok": True, "message": "Disconnected."}


def resolve_channel_from_url(url: str) -> dict:
    """
    Use regex + yt-dlp to extract channel_id, channel_name, and avatar_url from any YouTube URL.
    Returns: {"ok": True, "channel_id": str, "channel_name": str, "avatar_url": str}
             or {"ok": False, "error": str}
    """
    import subprocess
    import json
    import sys
    import shutil
    import re

    url_str = url.strip()
    
    # Try direct regex extraction first
    match = re.search(r"/channel/(UC[a-zA-Z0-9_-]{22})", url_str)
    regex_channel_id = match.group(1) if match else None

    # Build yt-dlp command path
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "-m", "yt_dlp"]
    else:
        exe = shutil.which("yt-dlp")
        cmd = [exe] if exe else [sys.executable, "-m", "yt_dlp"]

    args = cmd + [
        "--dump-single-json",
        "--flat-playlist",
        "--playlist-end", "1",
        url_str
    ]

    try:
        # Hide console window on Windows
        no_window = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
            creationflags=no_window
        )
        if result.returncode != 0:
            if regex_channel_id:
                # Graceful fallback: we have the channel ID from regex, even if yt-dlp failed (e.g. auth required for studio URL)
                return {
                    "ok": True,
                    "channel_id": regex_channel_id,
                    "channel_name": "Studio Channel",
                    "avatar_url": ""
                }
            return {"ok": False, "error": f"yt-dlp error: {result.stderr.strip()}"}

        data = json.loads(result.stdout)
        
        # Get channel ID
        channel_id = data.get("channel_id") or data.get("id") or regex_channel_id
        # Get channel name
        channel_name = data.get("channel") or data.get("uploader") or data.get("title")
        
        # Get thumbnail / avatar URL
        avatar_url = ""
        thumbnails = data.get("thumbnails", [])
        if thumbnails:
            # Sort by height descending to get high res avatar
            sorted_thumbs = sorted(thumbnails, key=lambda t: t.get("height", 0) or t.get("preference", 0) or 0, reverse=True)
            avatar_url = sorted_thumbs[0].get("url", "")
            
        if not channel_id:
            return {"ok": False, "error": "Could not extract channel ID from URL"}
            
        return {
            "ok": True,
            "channel_id": channel_id,
            "channel_name": channel_name or "Resolved Channel",
            "avatar_url": avatar_url
        }
    except Exception as exc:
        if regex_channel_id:
            return {
                "ok": True,
                "channel_id": regex_channel_id,
                "channel_name": "Studio Channel",
                "avatar_url": ""
            }
        return {"ok": False, "error": str(exc)}
