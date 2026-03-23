"""
modules/uploader.py — YouTube Studio Auto-Upload via Playwright
===============================================================
Uses a Persistent Chromium Browser Context (pre-logged-in profile) so
you only ever need to log in and do OTP once manually.

Steps performed:
  1. Opens YouTube Studio upload dialog.
  2. Selects the rendered MP4 file.
  3. Waits for processing to initialise.
  4. Fills in Title, Description, and Tags.
  5. Marks the video as "Not Made for Kids".
  6. Sets visibility to "Unlisted".
  7. Clicks SAVE and waits for confirmation.

Environment variables required:
  YT_PROFILE_DIR  — path to Chromium user data directory
  YT_PROFILE_NAME — profile name inside that directory (default: "Default")

First-time setup:
  python -m playwright install chromium
  # Then run this script once with HEADLESS=False, log in manually, complete
  # OTP, and close — the session is saved to YT_PROFILE_DIR permanently.
"""

import asyncio
import time
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

from config import get_logger
from core.config_manager import config

log = get_logger("uploader")

UPLOAD_URL  = "https://studio.youtube.com"
HEADLESS    = False       # Set to True for fully silent background uploads
SLOW_MO     = 80          # ms between actions (more reliable than instant clicks)
TIMEOUT     = 90_000      # 90 s for most waits


async def _upload(video_path: Path, metadata: dict) -> None:
    """Core async Playwright upload coroutine."""

    title       = metadata.get("title", "My YouTube Short")[:70]   # YT limit
    description = metadata.get("description", "")
    tags        = metadata.get("tags", [])
    tags_str    = ", ".join(tags)

    config.load()
    profiles = config.get("pipeline.chrome_profiles", [])
    active_idx = config.get("pipeline.active_profile_index", 0)

    if not profiles:
        raise ValueError("No Chrome profile configured. Go to Settings → Chrome Profiles → Setup New Profile")

    active_profile = profiles[active_idx] if 0 <= active_idx < len(profiles) else profiles[0]
    chrome_profile_path = active_profile["path"]

    async with async_playwright() as pw:
        # ── Launch with persistent profile (avoids re-login) ───────────────
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir = chrome_profile_path,
            channel       = "chrome",   # real Chrome avoids Google sign-in blocks
            headless      = HEADLESS,
            slow_mo       = SLOW_MO,
            args          = [
                "--start-maximized",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        try:
            # ── 1. Navigate to YouTube Studio ──────────────────────────────
            log.debug("Navigating to YouTube Studio …")
            await page.goto(UPLOAD_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # ── 2. Click CREATE → Upload videos ───────────────────────────
            log.debug("Opening upload dialog …")
            # Try multiple selectors for CREATE button
            for sel in [
                'button[aria-label="Create"]',
                '#create-icon',
                'ytcp-button#create-icon',
                'button:has-text("Create")',
            ]:
                try:
                    await page.click(sel, timeout=8000)
                    break
                except Exception:
                    continue

            # Try multiple selectors for Upload option
            for sel in [
                'tp-yt-paper-item:has-text("Upload videos")',
                'yt-formatted-string:has-text("Upload videos")',
                '#text-item-0:has-text("Upload")',
                'ytcp-ve:has-text("Upload")',
            ]:
                try:
                    await page.click(sel, timeout=8000)
                    break
                except Exception:
                    continue

            await page.wait_for_timeout(2000)

            # ── 3. Select the video file ───────────────────────────────────
            log.debug(f"Selecting file: {video_path}")
            for sel in [
                'button:has-text("SELECT FILES")',
                'button:has-text("Select files")',
                'input[type="file"]',
                '#select-files-button',
            ]:
                try:
                    if sel == 'input[type="file"]':
                        await page.locator(sel).set_input_files(str(video_path.resolve()))
                    else:
                        async with page.expect_file_chooser(timeout=10000) as fc_info:
                            await page.click(sel, timeout=8000)
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(str(video_path.resolve()))
                    break
                except Exception:
                    continue

            # Wait for upload dialog and metadata form
            log.debug("Waiting for upload form …")
            await page.wait_for_timeout(5000)

            # ── Wait for the title field (confirms form is ready) ──────────
            # YouTube Studio uses #textbox contenteditable divs for title+desc
            TITLE_SEL = None
            for title_sel in [
                '#textbox',                     # most reliable in current YT Studio
                'div[aria-label="Title"]',
                'ytcp-social-suggestion-input[label="Title"] #textbox',
                'ytcp-social-suggestion-input #textbox',
                'div[contenteditable="true"]',
            ]:
                try:
                    await page.wait_for_selector(title_sel, timeout=20000)
                    log.debug(f"Title field found: {title_sel!r}")
                    TITLE_SEL = title_sel
                    break
                except Exception:
                    continue

            if not TITLE_SEL:
                log.error("Could not find title field — taking screenshot for debugging")
                await page.screenshot(path="output/debug_upload.png")
                raise RuntimeError("Title field not found in YouTube Studio upload form")

            # ── 4. Fill in Title ────────────────────────────────────────────
            log.debug("Filling in title …")
            # Title is always the FIRST #textbox
            title_field = page.locator(TITLE_SEL).first
            await title_field.scroll_into_view_if_needed()
            await title_field.click(timeout=15000)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Delete")          # clear existing text
            await page.keyboard.type(title, delay=40)
            await page.wait_for_timeout(500)

            # ── 5. Fill in Description ──────────────────────────────────────
            log.debug("Filling in description …")
            # Description is the SECOND #textbox
            desc_field = page.locator("#textbox").nth(1)
            await desc_field.scroll_into_view_if_needed()
            await desc_field.click(timeout=10000)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Delete")
            await page.keyboard.type(description, delay=15)
            await page.wait_for_timeout(500)


            # ── 6. Not made for kids ────────────────────────────────────────
            log.debug("Setting audience …")
            for kids_sel in [
                'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
                'ytcp-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
                'div[aria-label*="No, it"]',
            ]:
                try:
                    el = page.locator(kids_sel)
                    if await el.is_visible(timeout=5000):
                        await el.click()
                        break
                except Exception:
                    continue

            await page.wait_for_timeout(500)

            # ── 7. Click NEXT ×3 to reach Visibility ───────────────────────
            for step in range(3):
                log.debug(f"Clicking NEXT ({step + 1}/3) …")
                for next_sel in [
                    'ytcp-button#next-button',
                    'button:has-text("Next")',
                    'ytcp-stepper button:has-text("Next")',
                ]:
                    try:
                        await page.click(next_sel, timeout=10000)
                        break
                    except Exception:
                        continue
                await page.wait_for_timeout(1500)

            # ── 8. Set Visibility → Public ────────────────────────────────
            log.debug("Setting visibility → Public …")
            for vis_sel in [
                'tp-yt-paper-radio-button[name="PUBLIC"]',
                'ytcp-radio-button[name="PUBLIC"]',
                'div[aria-label="Public"]',
                ':has-text("Public")',
            ]:
                try:
                    await page.locator(vis_sel).first.click(timeout=10000)
                    break
                except Exception:
                    continue
            await page.wait_for_timeout(800)

            # ── 9. Save / Done ─────────────────────────────────────────────
            log.debug("Clicking SAVE/DONE …")
            for done_sel in [
                'ytcp-button#done-button',
                'button:has-text("Save")',
                'button:has-text("Publish")',
                'ytcp-button:has-text("Done")',
            ]:
                try:
                    await page.click(done_sel, timeout=10000)
                    break
                except Exception:
                    continue

            # Wait for confirmation
            log.debug("Waiting for upload confirmation …")
            try:
                await page.wait_for_selector(
                    'ytcp-video-upload-dialog ytcp-uploads-still-processing-dialog, '
                    'yt-dialog-store[dialog-id="VIDEO_UPLOAD_DIALOG"] *:has-text("Video link"), '
                    ':has-text("Your video is being processed"), '
                    ':has-text("Upload complete")',
                    timeout=120_000,
                )
                log.info("✅ Video successfully uploaded to YouTube Studio (Public)!")
            except PWTimeoutError:
                log.warning("Confirmation dialog not detected — upload may still have succeeded. Check YouTube Studio.")



            # ── 10. Add Tags (via URL hack — Studio hides tag field by default) ─
            # Note: YouTube Studio sometimes hides the tag field. We add tags
            # by clicking "More options" if available.
            # This is best-effort; tags can also be added post-upload via YT API.
            try:
                await page.click('ytcp-button#toggle-button:has-text("More options")', timeout=5000)
                tag_input = page.locator('ytcp-form-input-container[label="Tags"] input')
                await tag_input.fill(tags_str, timeout=5000)
                log.info(f"Tags added: {tags_str[:60]}…")
            except PWTimeoutError:
                log.warning("Tags field not found — skipping (add manually or via YT API).")

        finally:
            await page.wait_for_timeout(3000)
            await browser.close()


def upload_to_youtube(video_path: Path, metadata: dict) -> None:
    """
    Public synchronous entry point — wraps the async coroutine.

    Parameters
    ----------
    video_path : Path
        Path to the final rendered MP4.
    metadata   : dict
        {'title': str, 'description': str, 'tags': list[str]}
    """
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    log.info(f"Starting YouTube upload for: {metadata.get('title')!r}")
    asyncio.run(_upload(Path(video_path), metadata))
