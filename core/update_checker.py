"""
core/update_checker.py — Ghost Creator in-app updates (license-gated)
=======================================================================
Checks getmaya.online (or GHOST_SITE_ORIGIN) for a newer version and downloads
the Inno installer using a short-lived JWT from POST /api/license/ghost-update-check.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

from config import APP_VERSION, get_logger
from core.license import _legacy_machine_id_hex, get_machine_id, load_license

log = get_logger("update_checker")

SITE_ORIGIN = (os.getenv("GHOST_SITE_ORIGIN") or "https://getmaya.online").rstrip("/")
UPDATE_CHECK_URL = f"{SITE_ORIGIN}/api/license/ghost-update-check"
INSTALLER_BASE_URL = f"{SITE_ORIGIN}/api/ghost/desktop/installer"


def post_update_check() -> dict:
    """
    Ask server for latest version and optional download_token (JWT).

    Returns JSON dict (success, update_available, message, …).
    On HTTP/network errors returns {success: False, error: ...}.
    """
    stored = load_license()
    if not stored:
        return {
            "success": False,
            "error": "no_license",
            "message": "Activate Ghost Creator first (license key).",
        }

    machine_id = get_machine_id()
    payload: dict = {
        "license_key": stored["license_key"],
        "machine_id": machine_id,
        "current_version": APP_VERSION,
    }
    leg = _legacy_machine_id_hex()
    if leg != machine_id:
        payload["machine_id_legacy"] = leg

    try:
        resp = requests.post(UPDATE_CHECK_URL, json=payload, timeout=45)
        data = resp.json()
    except requests.ConnectionError:
        return {
            "success": False,
            "error": "connection_error",
            "message": "Cannot reach update server. Check your internet connection.",
        }
    except requests.Timeout:
        return {
            "success": False,
            "error": "timeout",
            "message": "Update check timed out. Try again later.",
        }
    except (ValueError, requests.RequestException) as exc:
        log.warning("update check failed: %s", exc)
        return {
            "success": False,
            "error": "server_error",
            "message": "Update check failed. Try again later.",
        }

    if resp.status_code >= 500:
        return {
            "success": False,
            "error": "server_error",
            "message": data.get("message") or "Server error.",
        }

    return data


def download_installer(
    token: str,
    dest: Path,
    *,
    progress=None,
    progress_ratio=None,
    ui_tick=None,
    sha256_expected: str | None = None,
) -> Path:
    """Download installer to ``dest``. Optional SHA-256 verify (hex string)."""
    url = f"{INSTALLER_BASE_URL}?{urlencode({'token': token})}"
    dest = Path(dest).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(url, stream=True, timeout=(30, 600), headers={"User-Agent": f"GhostCreator/{APP_VERSION}"}) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            last_ratio = -1.0
            h = hashlib.sha256()
            with dest.open("wb") as out:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    if not chunk:
                        continue
                    out.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress_ratio and total > 0:
                        ratio = min(1.0, done / total)
                        if ratio >= last_ratio + 0.02 or done >= total:
                            last_ratio = ratio
                            progress_ratio(ratio)
                    if progress and total > 0:
                        pct = min(100, done * 100 // total)
                        if done == total or pct % 5 < 1:
                            progress(f"Downloading… {pct}%")
                    if ui_tick:
                        ui_tick()

        if sha256_expected:
            digest = h.hexdigest().lower()
            expected = sha256_expected.strip().lower()
            if digest != expected:
                try:
                    dest.unlink(missing_ok=True)
                except OSError:
                    pass
                raise RuntimeError(
                    "Installer checksum failed (file corrupted or intercepted). Try again or download from your dashboard."
                )
    except requests.HTTPError as exc:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"Download failed: HTTP {exc.response.status_code}") from exc

    return dest


def launch_installer(installer_path: Path) -> None:
    """Start Inno setup; ``/CLOSEAPPLICATIONS`` lets the installer close Ghost before replacing files."""
    path = Path(installer_path).resolve()
    if not path.is_file():
        raise RuntimeError("Installer file missing.")
    if sys.platform == "win32":
        subprocess.Popen(
            [str(path), "/CLOSEAPPLICATIONS", "/SP-"],
            close_fds=False,
        )
    else:
        subprocess.Popen([str(path)], close_fds=False)
