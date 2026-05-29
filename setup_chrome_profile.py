"""
setup_chrome_profile.py — One-time Chrome Profile Setup for YouTube Upload
===========================================================================
Run this script ONCE to create a dedicated Chrome profile and log in
to YouTube manually. After you close the browser, the session is saved
permanently — you will NEVER need to log in again for Ghost Creator AI.

USES YOUR REAL INSTALLED GOOGLE CHROME (not bundled Chromium).
This avoids Google's "Couldn't sign you in" security block.

Usage:
    python setup_chrome_profile.py
"""

import asyncio
import os
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("❌  Playwright is not installed.\n"
          "    Run:  pip install playwright && python -m playwright install chromium")
    sys.exit(1)

import re
import threading
import tkinter as tk
import tkinter.messagebox as mb
from core.config_manager import config

profile_name = ""
sanitized = ""
PROFILE_DIR = None
PROFILE_NAME = "Default"

async def _run_with_name(name: str):
    global profile_name, sanitized, PROFILE_DIR
    profile_name = name
    sanitized = "".join([c for c in name if c.isalnum() or c in (' ', '_', '-')]).strip().replace(' ', '_')
    if not sanitized:
        sanitized = "Default_Profile"
    from config import get_user_data_dir
    PROFILE_DIR = get_user_data_dir() / "ChromeProfiles" / f"GhostCreator_{sanitized}"
    await _run()

async def _run():
    if not PROFILE_DIR:
        print("❌ PROFILE_DIR is not set.")
        return
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n🚀  Launching Chrome with persistent profile at:\n    {PROFILE_DIR}\n")

    async with async_playwright() as pw:
        # Use real installed Google Chrome — avoids Google's
        # "Couldn't sign you in" block that affects bundled Chromium.
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",        # ← uses C:\Program Files\Google\Chrome
            headless=False,
            slow_mo=50,
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",  # hide automation
            ],
            no_viewport=True,
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        print("📌  Navigating to YouTube Studio …")
        await page.goto("https://studio.youtube.com", wait_until="domcontentloaded")

        print("\n" + "=" * 60)
        print("  ACTION REQUIRED:")
        print("  ► Log in to YouTube in the browser window that just opened.")
        print("  ► Complete any OTP / 2FA steps.")
        print("  ► Once you see YouTube Studio dashboard, come back here.")
        print("=" * 60)
        
        # GUI Dialog instead of terminal input for exe compatibility
        import asyncio
        
        def _show_dialog_sync():
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            mb.showinfo(
                "Ghost Creator AI — Chrome Login",
                "Log in to YouTube in the Chrome window.\n\n"
                "Complete any OTP/2FA steps.\n\n"
                "Click OK here once you see YouTube Studio dashboard.",
                parent=root
            )
            root.destroy()
            
        # Run blocking tkinter dialog in executor so asyncio event loop doesn't freeze
        await asyncio.to_thread(_show_dialog_sync)

        print("💾  Saving session … (do NOT close the browser yet)")
        await page.wait_for_timeout(2000)
        await browser.close()

    print("\n✅  Profile saved! Your session is now permanent.")
    print(f"    Profile directory: {PROFILE_DIR}")

    # ── Auto-update config.json ───────────────────────────────────────────────
    config.load()
    profiles = config.get("pipeline.chrome_profiles", [])
    profiles.append({
        "name": profile_name,
        "path": str(PROFILE_DIR).replace("\\", "/"),
        "profile_name": PROFILE_NAME
    })
    config.set("pipeline.chrome_profiles", profiles)
    config.set("pipeline.active_profile_index", len(profiles) - 1)
    config.save()

    print("\n🎉  Setup complete! You can now close this window.")


if __name__ == "__main__":
    try:
        p_name = sys.argv[1] if len(sys.argv) > 1 else input("Enter a name for this profile (e.g. 'Tech Channel'): ")
        asyncio.run(_run_with_name(p_name))
    except KeyboardInterrupt:
        print("\n⚠️  Setup cancelled.")
