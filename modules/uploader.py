"""
modules/uploader.py — YouTube Studio Auto-Upload via Playwright
===============================================================
Uses a Persistent Chromium Browser Context (pre-logged-in profile) so
you only ever need to log in and do OTP once manually.

Steps performed:
  1. Opens YouTube Studio upload dialog.
  2. Selects the rendered MP4 file via file input.
  3. Waits for upload progress to complete.
  4. Fills in Title, Description, and Tags (via "More options").
  5. Marks the video as "Not Made for Kids".
  6. Clicks NEXT × 3 to reach the Visibility screen.
  7. Sets visibility per config (public / unlisted / draft / private).
  8. Clicks SAVE/DONE and waits for confirmation.
  9. Optionally uploads a custom thumbnail if metadata contains one.

Config keys read (from core.config_manager):
  pipeline.chrome_profiles        — list of {name, path} dicts
  pipeline.active_profile_index   — index into the above list
  pipeline.upload_mode            — "public" | "unlisted" | "private" | "draft"
  pipeline.headless_upload        — bool, default False
  pipeline.upload_slow_mo         — int ms, default 80
  pipeline.upload_timeout         — int ms, default 90_000

First-time setup:
  python -m playwright install chromium
  # Then run this script once with headless=False, log in manually, complete
  # OTP, and close — the session is saved to the profile dir permanently.
"""

import asyncio
import os
from pathlib import Path
from typing import Callable, Optional

from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

from config import get_logger, OUTPUT_DIR
from core.config_manager import config

log = get_logger("uploader")

UPLOAD_URL = "https://studio.youtube.com"

# Fallback defaults (overridden by config at runtime)
_HEADLESS   = False
_SLOW_MO    = 80
_TIMEOUT    = 90_000

# Visibility selector map — key matches pipeline.upload_mode values
_VIS_SEL: dict[str, list[str]] = {
    "public": [
        'tp-yt-paper-radio-button[name="PUBLIC"]',
        'ytcp-radio-button[name="PUBLIC"]',
        '[name="PUBLIC"]',
    ],
    "unlisted": [
        'tp-yt-paper-radio-button[name="UNLISTED"]',
        'ytcp-radio-button[name="UNLISTED"]',
        '[name="UNLISTED"]',
    ],
    "private": [
        'tp-yt-paper-radio-button[name="PRIVATE"]',
        'ytcp-radio-button[name="PRIVATE"]',
        '[name="PRIVATE"]',
    ],
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _screenshot_path(tag: str = "debug") -> str:
    """Return a timestamped screenshot path inside output/."""
    import time
    ts = int(time.time())
    p = OUTPUT_DIR / f"upload_{tag}_{ts}.png"
    return str(p)


async def _safe_click(page, selectors: list[str], timeout: int = 8_000, label: str = "") -> bool:
    """Try each selector in order; return True on first success."""
    for sel in selectors:
        try:
            await page.click(sel, timeout=timeout)
            return True
        except Exception:
            continue
    if label:
        log.warning(f"_safe_click: none of the selectors worked for '{label}'")
    return False


async def _wait_and_fill(page, selector: str, text: str, timeout: int = 20_000) -> None:
    """Wait for a contenteditable/input field, clear it, and type text."""
    field = page.locator(selector).first
    await field.wait_for(state="visible", timeout=timeout)
    await field.scroll_into_view_if_needed()
    await field.click(timeout=timeout)
    # Select-all + Delete is more reliable than triple_click on contenteditable
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Delete")
    await page.wait_for_timeout(200)
    # Verify cleared
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Delete")
    await page.keyboard.type(text, delay=25)
    await page.wait_for_timeout(300)


# ── Core upload coroutine ─────────────────────────────────────────────────────

async def _upload(
    video_path: Path,
    metadata: dict,
    progress: Callable[[str], None],
) -> None:
    """Core async Playwright upload coroutine."""

    title       = metadata.get("title", "My YouTube Short")[:100]   # YT hard limit = 100
    description = metadata.get("description", "")[:5000]            # YT hard limit = 5000
    tags        = metadata.get("tags", [])
    tags_str    = ", ".join(str(t) for t in tags[:500])              # YT tag limit ~500 chars total
    thumbnail   = metadata.get("thumbnail_path", "")

    # ── Read runtime config ────────────────────────────────────────────────────
    config.load()
    headless   = bool(config.get("pipeline.headless_upload", _HEADLESS))
    slow_mo    = int(config.get("pipeline.upload_slow_mo",  _SLOW_MO))
    timeout    = int(config.get("pipeline.upload_timeout",  _TIMEOUT))
    vis_mode   = str(config.get("pipeline.upload_mode", "unlisted")).lower().strip()

    profiles   = config.get("pipeline.chrome_profiles", [])
    active_idx = config.get("pipeline.active_profile_index", 0)

    if not profiles:
        raise ValueError(
            "No Chrome profile configured. "
            "Go to Settings → Chrome Profiles → Setup New Profile"
        )

    active_profile    = profiles[active_idx] if 0 <= active_idx < len(profiles) else profiles[0]
    chrome_profile_path = active_profile["path"]

    log.info(
        f"Upload config: headless={headless}, slow_mo={slow_mo}ms, "
        f"timeout={timeout}ms, visibility={vis_mode!r}"
    )

    async with async_playwright() as pw:
        # ── Launch with persistent profile ────────────────────────────────────
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir = chrome_profile_path,
            channel       = "chrome",
            headless      = headless,
            slow_mo       = slow_mo,
            args          = [
                "--start-maximized",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        try:
            # ── 1. Navigate to YouTube Studio ─────────────────────────────────
            progress("Opening YouTube Studio …")
            log.debug("Navigating to YouTube Studio …")
            await page.goto(UPLOAD_URL, timeout=timeout, wait_until="domcontentloaded")
            # Wait for Studio to fully load (sidebar appears)
            try:
                await page.wait_for_selector(
                    '#create-icon, ytcp-icon-button[id="create-icon"], button[aria-label="Create"]',
                    timeout=30_000,
                )
            except PWTimeoutError:
                await page.screenshot(path=_screenshot_path("studio_load_fail"))
                raise RuntimeError(
                    "YouTube Studio did not load. "
                    "Make sure you are logged in to your channel in the Chrome profile."
                )

            # ── 2. Click CREATE → Upload videos ───────────────────────────────
            progress("Opening upload dialog …")
            log.debug("Clicking Create button …")
            clicked = await _safe_click(
                page,
                [
                    'button[aria-label="Create"]',
                    '#create-icon',
                    'ytcp-button#create-icon',
                    'ytcp-icon-button[id="create-icon"]',
                    'button:has-text("Create")',
                ],
                timeout=10_000,
                label="CREATE button",
            )
            if not clicked:
                await page.screenshot(path=_screenshot_path("create_btn_fail"))
                raise RuntimeError("Could not find the 'Create' button in YouTube Studio.")

            # Wait for dropdown
            await page.wait_for_timeout(1500)

            log.debug("Clicking 'Upload videos' …")
            clicked = await _safe_click(
                page,
                [
                    'tp-yt-paper-item:has-text("Upload videos")',
                    'yt-formatted-string:has-text("Upload videos")',
                    '#text-item-0:has-text("Upload")',
                    'ytcp-ve:has-text("Upload")',
                    ':has-text("Upload videos")',
                ],
                timeout=8_000,
                label="Upload videos menu item",
            )
            if not clicked:
                await page.screenshot(path=_screenshot_path("upload_menu_fail"))
                raise RuntimeError("Could not click 'Upload videos' from the Create menu.")

            await page.wait_for_timeout(1500)

            # ── 3. Select the video file ───────────────────────────────────────
            progress("Selecting video file …")
            log.debug(f"Selecting file: {video_path}")
            file_selected = False

            # Method A: direct input[type="file"] (most reliable, hidden input)
            try:
                file_input = page.locator('input[type="file"]').first
                await file_input.wait_for(state="attached", timeout=8_000)
                await file_input.set_input_files(str(video_path.resolve()))
                file_selected = True
                log.debug("File selected via hidden input[type='file']")
            except Exception:
                pass

            # Method B: click SELECT FILES button → file chooser dialog
            if not file_selected:
                for btn_sel in [
                    'button:has-text("SELECT FILES")',
                    'button:has-text("Select files")',
                    '#select-files-button',
                    'ytcp-button:has-text("SELECT")',
                ]:
                    try:
                        async with page.expect_file_chooser(timeout=10_000) as fc_info:
                            await page.click(btn_sel, timeout=6_000)
                        fc = await fc_info.value
                        await fc.set_files(str(video_path.resolve()))
                        file_selected = True
                        log.debug(f"File selected via file chooser (button: {btn_sel!r})")
                        break
                    except Exception:
                        continue

            if not file_selected:
                await page.screenshot(path=_screenshot_path("file_select_fail"))
                raise RuntimeError("Could not attach video file to the upload dialog.")

            # ── 4. Wait for upload + form to appear ────────────────────────────
            progress("Waiting for upload form …")
            log.debug("Waiting for upload progress + details form …")

            # Wait until the title field appears (upload has started, form is ready)
            TITLE_SEL: Optional[str] = None
            for title_sel in [
                '#textbox',
                'div[aria-label="Title"]',
                'ytcp-social-suggestion-input[label="Title"] #textbox',
                'ytcp-social-suggestion-input #textbox',
                'div[contenteditable="true"]',
            ]:
                try:
                    await page.wait_for_selector(title_sel, timeout=40_000)
                    TITLE_SEL = title_sel
                    log.debug(f"Title field found via {title_sel!r}")
                    break
                except PWTimeoutError:
                    continue

            if not TITLE_SEL:
                await page.screenshot(path=_screenshot_path("title_field_fail"))
                raise RuntimeError(
                    "Title field not found in YouTube Studio upload form. "
                    "Check output/upload_title_field_fail_*.png for a screenshot."
                )

            # Wait a beat for the form to fully stabilise
            await page.wait_for_timeout(1_500)

            # ── 5. Fill in Title ───────────────────────────────────────────────
            progress("Filling in title …")
            log.debug(f"Filling title: {title!r}")
            title_field = page.locator(TITLE_SEL).first
            await title_field.scroll_into_view_if_needed()
            await title_field.click(timeout=15_000)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(200)
            await page.keyboard.type(title, delay=30)
            await page.wait_for_timeout(400)

            # ── 6. Fill in Description ─────────────────────────────────────────
            progress("Filling in description …")
            log.debug("Filling description …")
            # Description is the 2nd #textbox in the form
            desc_field = page.locator("#textbox").nth(1)
            await desc_field.scroll_into_view_if_needed()
            await desc_field.click(timeout=10_000)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(200)
            if description:
                await page.keyboard.type(description, delay=10)
            await page.wait_for_timeout(400)

            # ── 7. Not Made for Kids ───────────────────────────────────────────
            progress("Setting audience (Not Made for Kids) …")
            log.debug("Setting audience …")
            for kids_sel in [
                'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
                'ytcp-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
                '[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
                'div[aria-label*="No, it"]',
                'tp-yt-paper-radio-button:has-text("No")',
            ]:
                try:
                    el = page.locator(kids_sel).first
                    if await el.is_visible(timeout=5_000):
                        await el.click()
                        log.debug(f"Kids toggle clicked via {kids_sel!r}")
                        break
                except Exception:
                    continue
            await page.wait_for_timeout(400)

            # ── 8. Add Tags via "More options" ────────────────────────────────
            # IMPORTANT: "More options" is only available on the DETAILS step,
            # before clicking NEXT. It disappears once the form is submitted.
            if tags_str:
                progress("Adding tags …")
                log.debug("Expanding 'More options' for tags …")
                more_expanded = False
                for more_sel in [
                    'ytcp-button#toggle-button',
                    'ytcp-button:has-text("More options")',
                    'button:has-text("More options")',
                    '#toggle-button',
                ]:
                    try:
                        el = page.locator(more_sel).first
                        if await el.is_visible(timeout=5_000):
                            await el.click()
                            more_expanded = True
                            log.debug(f"'More options' expanded via {more_sel!r}")
                            await page.wait_for_timeout(1_000)
                            break
                    except Exception:
                        continue

                if more_expanded:
                    tag_filled = False
                    for tag_sel in [
                        'ytcp-form-input-container[label="Tags"] input',
                        'input[aria-label*="tags" i]',
                        'ytcp-chip-bar input',
                        '#tags-container input',
                        'input[placeholder*="tag" i]',
                    ]:
                        try:
                            tag_input = page.locator(tag_sel).first
                            if await tag_input.is_visible(timeout=5_000):
                                await tag_input.click()
                                await tag_input.fill(tags_str)
                                await page.keyboard.press("Return")
                                tag_filled = True
                                log.info(f"Tags added: {tags_str[:80]}…")
                                await page.wait_for_timeout(500)
                                break
                        except Exception:
                            continue
                    if not tag_filled:
                        log.warning("Tags field not found inside 'More options' — skipping.")
                else:
                    log.warning("'More options' button not found — tags skipped.")
            else:
                log.debug("No tags provided — skipping tag step.")

            # ── 9. Click NEXT × 3 to reach Visibility ─────────────────────────
            for step in range(3):
                progress(f"Navigating form step {step + 1}/3 …")
                log.debug(f"Clicking NEXT ({step + 1}/3) …")
                clicked = await _safe_click(
                    page,
                    [
                        'ytcp-button#next-button',
                        'button:has-text("Next")',
                        'ytcp-stepper button:has-text("Next")',
                        '#next-button',
                    ],
                    timeout=10_000,
                    label=f"NEXT button step {step + 1}",
                )
                if not clicked:
                    log.warning(f"NEXT button not found on step {step + 1} — continuing anyway.")
                # Wait for the next panel to load
                await page.wait_for_timeout(1_800)

            # ── 10. Set Visibility ─────────────────────────────────────────────
            progress(f"Setting visibility → {vis_mode.upper()} …")
            log.debug(f"Setting visibility → {vis_mode!r}")

            if vis_mode == "draft":
                # Draft = don't publish, just click SAVE (no radio needed)
                log.info("Draft mode: skipping visibility radio, clicking Save as draft …")
            else:
                vis_selectors = _VIS_SEL.get(vis_mode, _VIS_SEL["unlisted"])
                vis_set = False
                for vis_sel in vis_selectors:
                    try:
                        el = page.locator(vis_sel).first
                        if await el.is_visible(timeout=8_000):
                            await el.click()
                            vis_set = True
                            log.debug(f"Visibility set via {vis_sel!r}")
                            break
                    except Exception:
                        continue
                if not vis_set:
                    log.warning(
                        f"Could not set visibility to '{vis_mode}' — "
                        "defaulting to whatever is pre-selected."
                    )
            await page.wait_for_timeout(800)

            # ── 11. Save / Done ────────────────────────────────────────────────
            progress("Saving upload …")
            log.debug("Clicking SAVE/DONE …")
            saved = await _safe_click(
                page,
                [
                    'ytcp-button#done-button',
                    'button:has-text("Save")',
                    'button:has-text("Publish")',
                    'ytcp-button:has-text("Done")',
                    '#done-button',
                ],
                timeout=10_000,
                label="SAVE/DONE button",
            )
            if not saved:
                await page.screenshot(path=_screenshot_path("save_btn_fail"))
                log.warning("SAVE button not found — upload may be stalled.")

            # ── 12. Wait for confirmation ──────────────────────────────────────
            progress("Waiting for upload confirmation …")
            log.debug("Waiting for upload confirmation …")
            try:
                await page.wait_for_selector(
                    (
                        'ytcp-video-upload-dialog ytcp-uploads-still-processing-dialog, '
                        'yt-dialog-store[dialog-id="VIDEO_UPLOAD_DIALOG"] *:has-text("Video link"), '
                        ':has-text("Your video is being processed"), '
                        ':has-text("Upload complete"), '
                        ':has-text("Finished processing"), '
                        ':has-text("Video published")'
                    ),
                    timeout=120_000,
                )
                progress("Upload confirmed!")
                log.info(f"✅ Video successfully uploaded! (visibility={vis_mode})")
            except PWTimeoutError:
                await page.screenshot(path=_screenshot_path("confirm_timeout"))
                log.warning(
                    "Confirmation dialog not detected — upload may still have succeeded. "
                    "Check output/upload_confirm_timeout_*.png and YouTube Studio."
                )
                progress("Upload confirmation timed out — check YouTube Studio manually.")

            # ── 13. Upload Thumbnail (optional) ───────────────────────────────
            if thumbnail and Path(thumbnail).exists():
                progress("Uploading custom thumbnail …")
                log.debug(f"Uploading thumbnail: {thumbnail}")
                try:
                    for thumb_btn_sel in [
                        'ytcp-button:has-text("Upload thumbnail")',
                        'button:has-text("Upload thumbnail")',
                        '#upload-thumbnail',
                    ]:
                        try:
                            thumb_input = page.locator('input[type="file"][accept*="image"]').first
                            if await thumb_input.count() > 0:
                                await thumb_input.set_input_files(thumbnail)
                                log.info("Thumbnail uploaded.")
                                await page.wait_for_timeout(2_000)
                                break
                        except Exception:
                            pass
                except Exception as e:
                    log.warning(f"Thumbnail upload skipped: {e}")

        except Exception:
            # Take a screenshot for any unexpected failure
            try:
                await page.screenshot(path=_screenshot_path("unexpected_error"))
            except Exception:
                pass
            raise

        finally:
            await page.wait_for_timeout(3_000)
            await browser.close()


# ── Public entry point ────────────────────────────────────────────────────────

def upload_to_youtube(
    video_path: Path,
    metadata: dict,
    progress_callback: Optional[Callable[[str], None]] = None,
    retries: int = 1,
) -> None:
    """
    Upload a rendered video to YouTube Studio.

    Parameters
    ----------
    video_path : Path
        Path to the final rendered MP4.
    metadata : dict
        {
            'title':          str,
            'description':    str,
            'tags':           list[str],
            'thumbnail_path': str  (optional — path to a JPG/PNG thumbnail)
        }
    progress_callback : callable, optional
        Called with a status string at each major upload step so the
        pipeline GUI can display real-time progress.
    retries : int
        How many additional attempts to make on failure (default 1).
    """
    video_path = Path(video_path)

    # ── Pre-flight validation ─────────────────────────────────────────────────
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    file_size = video_path.stat().st_size
    if file_size == 0:
        raise ValueError(f"Video file is empty (0 bytes): {video_path}")
    if file_size < 10_000:
        log.warning(f"Video file is suspiciously small ({file_size} bytes): {video_path}")

    suffix = video_path.suffix.lower()
    if suffix not in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}:
        raise ValueError(
            f"Unsupported video format: {suffix!r}. YouTube accepts .mp4, .mov, .avi, .mkv, .webm, .flv"
        )

    _progress = progress_callback or (lambda msg: log.info(f"[upload] {msg}"))
    _progress(f"Starting upload: {metadata.get('title', '')!r}")
    log.info(
        f"Starting YouTube upload: title={metadata.get('title')!r}, "
        f"file={video_path.name}, size={file_size / (1024 * 1024):.1f} MB"
    )

    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 2):
        try:
            asyncio.run(_upload(Path(video_path), metadata, _progress))
            return
        except Exception as exc:
            last_exc = exc
            log.error(f"Upload attempt {attempt} failed: {exc}", exc_info=(attempt == retries + 1))
            if attempt <= retries:
                log.info(f"Retrying upload (attempt {attempt + 1}/{retries + 1}) …")
                _progress(f"Upload failed (attempt {attempt}) — retrying …")
            else:
                _progress(f"Upload failed after {retries + 1} attempt(s).")

    raise RuntimeError(
        f"YouTube upload failed after {retries + 1} attempt(s). "
        f"Last error: {last_exc}"
    ) from last_exc
