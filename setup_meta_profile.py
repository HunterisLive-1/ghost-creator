"""
setup_meta_profile.py — One-time Chrome profile for Meta AI + Grok browser footage
==================================================================================
Run once, log in to Meta AI and Grok (same Chrome profile), then close the browser.

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
    grok_url = (config.get("grok.base_url") or "https://grok.com/").strip()
    if "/imagine" in grok_url:
        grok_url = "https://grok.com/"
    print(f"\nLaunching Chrome for AI browser login\n  Profile: {profile}\n  Meta: {base_url}\n  Grok: {grok_url}\n")

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
        grok_page = await browser.new_page()
        await grok_page.goto(grok_url, wait_until="domcontentloaded")

        print("=" * 60)
        print("  ACTION REQUIRED:")
        print("  1. Tab 1: Log in to Meta / Facebook on meta.ai")
        print("  2. Tab 2: Sign in to Grok on grok.com (X / xAI account)")
        print("  3. Close ALL Chrome windows when done - profile saves automatically.")
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
    print("(Grok uses the same profile when grok.chrome_profile_path is empty)")
    return profile


def main() -> None:
    config.load()
    asyncio.run(run_setup())


if __name__ == "__main__":
    main()
