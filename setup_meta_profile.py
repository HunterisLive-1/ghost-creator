"""
setup_meta_profile.py — One-time Chrome profile for Meta AI video generation
=============================================================================
Run once, log in to Meta AI / Facebook in the opened Chrome window, then close.

Usage:
    python setup_meta_profile.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed. Run: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

from core.config_manager import config


DEFAULT_PROFILE = Path(r"C:\ChromeProfiles\GhostCreator_MetaAI")


async def run_setup(profile_dir: Path | None = None) -> Path:
    profile = profile_dir or Path(
        (config.get("meta_ai.chrome_profile_path") or "").strip() or str(DEFAULT_PROFILE)
    ).expanduser().resolve()
    profile.mkdir(parents=True, exist_ok=True)

    base_url = (config.get("meta_ai.base_url") or "https://www.meta.ai/").strip()
    print(f"\nLaunching Chrome for Meta AI login\n  Profile: {profile}\n  URL: {base_url}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            channel="chrome",
            headless=False,
            slow_mo=50,
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            no_viewport=True,
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto(base_url, wait_until="domcontentloaded")

        print("=" * 60)
        print("  ACTION REQUIRED:")
        print("  1. Log in to Meta / Facebook in the browser window.")
        print("  2. Confirm Meta AI works (no 'Log in' button on homepage).")
        print("  3. Close ALL Chrome windows when done — this script saves automatically.")
        print("=" * 60)
        print("\nWaiting for you to log in and close Chrome …\n")

        try:
            await browser.wait_for_event("close", timeout=0)
        except Exception:
            pass
        try:
            await browser.close()
        except Exception:
            pass

    config.set("meta_ai.chrome_profile_path", str(profile))
    config.save()
    print(f"\nSaved meta_ai.chrome_profile_path -> {profile}")
    return profile


def main() -> None:
    config.load()
    asyncio.run(run_setup())


if __name__ == "__main__":
    main()
