"""Ghost Creator AI -- License verification module.

Handles machine fingerprinting, license activation via remote API,
encrypted local storage, and periodic re-verification.
"""

import os
import sys
import json
import time
import hashlib
import uuid
import platform
import base64

import requests
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _data_dir() -> Path:
    """User-writable data directory (survives Program Files install, UAC, etc.)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.config")
    d = Path(base) / "GhostCreator"
    d.mkdir(parents=True, exist_ok=True)
    return d


LICENSE_FILE = _data_dir() / "license.dat"
API_URL = "https://getmaya.online/api/license/verify-ghost"

# Days the app can run while the license server is unreachable
OFFLINE_GRACE_DAYS = 7

# Seconds between server re-checks (24 hours)
VERIFY_INTERVAL = 24 * 60 * 60

_SALT = b"\x4f\x1c\xa8\x73\xd2\x56\x9b\xe0\x3f\x88\xc1\x47\xfa\x2d\x0e\x65"


def get_machine_id() -> str:
    """SHA-256 hash of CPU info + node name + MAC address."""
    raw = platform.processor() + platform.node() + str(uuid.getnode())
    return hashlib.sha256(raw.encode()).hexdigest()


def _derive_key() -> bytes:
    """Derive a Fernet key from the machine fingerprint (ties license.dat to this PC)."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(get_machine_id().encode()))


def verify_with_server(license_key: str, machine_id: str) -> dict:
    """POST to the licensing API and return the JSON response.

    Distinguishes between:
      - Explicit rejection  → {"success": False, "error": "rejected", ...}
      - Temporary problems  → {"success": False, "error": "connection_error"|"timeout"|"server_error"}
    """
    try:
        resp = requests.post(
            API_URL,
            json={"license_key": license_key, "machine_id": machine_id},
            timeout=10,
        )
        # 4xx/5xx from the server are temporary issues, NOT explicit revocation
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        return {"success": False, "error": "connection_error"}
    except requests.Timeout:
        return {"success": False, "error": "timeout"}
    except requests.HTTPError:
        return {"success": False, "error": "server_error"}
    except (ValueError, Exception):
        # JSON decode error or anything else — treat as server-side problem
        return {"success": False, "error": "server_error"}


def save_license(license_key: str, machine_id: str, activated_at: float | None = None) -> None:
    """Encrypt and write the license to disk, preserving original activation time."""
    fernet = Fernet(_derive_key())
    payload = json.dumps({
        "license_key": license_key,
        "machine_id": machine_id,
        "activated_at": activated_at if activated_at is not None else time.time(),
        "last_verified": time.time(),
    })
    LICENSE_FILE.write_bytes(fernet.encrypt(payload.encode()))


def load_license() -> dict | None:
    """Decrypt and return stored license data, or None if missing/tampered."""
    if not LICENSE_FILE.exists():
        return None
    try:
        fernet = Fernet(_derive_key())
        return json.loads(fernet.decrypt(LICENSE_FILE.read_bytes()).decode())
    except (InvalidToken, json.JSONDecodeError, Exception):
        return None


def _revoke_local_license() -> None:
    """Delete locally cached license data (only on explicit server rejection)."""
    LICENSE_FILE.unlink(missing_ok=True)
    (_app_dir() / ".ghost_runs").unlink(missing_ok=True)


def _within_grace_period(stored: dict) -> bool:
    """True if last successful verification is within OFFLINE_GRACE_DAYS."""
    last_ok = stored.get("last_verified", stored.get("activated_at", 0))
    return (time.time() - last_ok) < (OFFLINE_GRACE_DAYS * 24 * 60 * 60)


def _due_for_check(stored: dict) -> bool:
    """True if VERIFY_INTERVAL has passed since last server check."""
    return (time.time() - stored.get("last_verified", 0)) >= VERIFY_INTERVAL


def is_licensed() -> tuple[bool, str]:
    """Returns (is_valid, message). Checks local cache and periodically pings server."""
    machine_id = get_machine_id()
    stored = load_license()

    if not stored:
        return False, "License key not found."

    if stored.get("machine_id") != machine_id:
        return False, "License file was moved to a different device. Please re-activate."

    # Skip server call if we verified recently
    if not _due_for_check(stored):
        return True, "License valid."

    result = verify_with_server(stored["license_key"], machine_id)

    if result.get("success"):
        # Refresh last_verified, keep original activated_at
        save_license(stored["license_key"], machine_id, activated_at=stored.get("activated_at"))
        return True, "License verified."

    error = result.get("error", "")

    # Temporary problem (network down, server 500, etc.) → use grace period
    if error in ("connection_error", "timeout", "server_error"):
        if _within_grace_period(stored):
            days_left = OFFLINE_GRACE_DAYS - int(
                (time.time() - stored.get("last_verified", stored.get("activated_at", 0)))
                / 86400
            )
            return True, f"License server unreachable. Grace period: {days_left} day(s) remaining."
        else:
            _revoke_local_license()
            return False, (
                "Could not verify your license for over 7 days. "
                "Please connect to the internet to reactivate."
            )

    # Explicit rejection from the server (revoked, expired, etc.)
    _revoke_local_license()
    return False, result.get("message") or "License has been revoked or is no longer valid."


def activate_license(license_key: str) -> tuple[bool, str]:
    """Attempts to activate a license key with the server."""
    license_key = license_key.strip()
    if not license_key:
        return False, "No license key entered."

    machine_id = get_machine_id()
    result = verify_with_server(license_key, machine_id)

    if result.get("success"):
        save_license(license_key, machine_id)
        return True, "Ghost Creator activated successfully!"

    error = result.get("error", "")
    message = result.get("message", "").lower()

    if error in ("connection_error", "timeout", "server_error"):
        return False, "License verification failed. Check your internet connection and try again."
    elif error == "already_activated" or "another" in message:
        return False, "This license key is already active on another device."
    else:
        return False, result.get("message") or "Invalid license key."
