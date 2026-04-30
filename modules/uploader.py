"""
modules/uploader.py — YouTube Studio Auto-Upload via Playwright
===============================================================
Uses a Persistent Chromium Browser Context (pre-logged-in profile) so
you only ever need to log in and do OTP once manually.

Upload flow:
  1. Opens YouTube Studio.
  2. Clicks CREATE → Upload videos.
  3. Selects the MP4 file.
  4. *** WAITS FOR FILE UPLOAD TO REACH 100% *** before touching the form.
  5. Fills Title, Description.
  6. Sets "Not Made for Kids".
  7. Expands "More options" → fills Tags.
  8. Uploads custom thumbnail (on the DETAILS page, before NEXT).
  9. Clicks NEXT × 3 to reach Visibility.
 10. Sets visibility (public / unlisted / private / draft).
 11. Clicks SAVE/DONE.
 12. Waits for the "processing" confirmation dialog.

Config keys (from core.config_manager):
  pipeline.chrome_profiles        — list of {name, path} dicts
  pipeline.active_profile_index   — index into the above list
  pipeline.upload_mode            — "public" | "unlisted" | "private" | "draft"
  pipeline.headless_upload           — bool, default False
  pipeline.upload_slow_mo            — int ms, default 80
  pipeline.upload_timeout            — int ms, default 90_000 (navigation / selectors)
  pipeline.upload_complete_timeout_ms — int ms, default 900_000 (max wait for file 0→100%)
  pipeline.post_publish_grace_ms     — int ms, default 12_000 (pause before closing Chrome after success)
"""

import asyncio
import time
from pathlib import Path
from typing import Callable, Optional

from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

from config import get_logger, OUTPUT_DIR
from core.config_manager import config

log = get_logger("uploader")

UPLOAD_URL = "https://studio.youtube.com"

_HEADLESS = False
_SLOW_MO  = 80
_TIMEOUT  = 90_000

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
    import time
    return str(OUTPUT_DIR / f"upload_{tag}_{int(time.time())}.png")


async def _safe_click(page, selectors: list[str], timeout: int = 8_000, label: str = "") -> bool:
    for sel in selectors:
        try:
            await page.click(sel, timeout=timeout)
            return True
        except Exception:
            continue
    if label:
        log.warning(f"_safe_click: none worked for '{label}'")
    return False


async def _is_checked_or_aria_true(locator) -> bool:
    """True if element reads as checked (aria-checked or native checkbox)."""
    try:
        aria = await locator.get_attribute("aria-checked")
        if aria == "true":
            return True
        if aria == "false":
            return False
    except Exception:
        pass
    try:
        return await locator.is_checked()
    except Exception:
        return False


async def _handle_ad_suitability(page) -> bool:
    """
    Detect and handle YouTube's 'Ad suitability' self-certification step.

    YouTube inserts this between Details and later wizard steps. The flow is:
    leave boxes unchecked or check "None of the above", then the caller clicks
    the standard NEXT button — there is no separate "Submit rating" action.
    """
    detect_timeout_ms = 2_000
    detection_selectors = [
        "ytcp-video-metadata-editor-adbreak",
        '[page-name="AD_SUITABILITY"]',
        'h2:has-text("Ad suitability")',
        ".ytcp-ad-suitability-page",
        ':has-text("Rate your video carefully")',
        "ytcp-ad-suitability",
    ]

    on_ad_page = False
    for sel in detection_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=detect_timeout_ms):
                on_ad_page = True
                break
        except Exception:
            continue

    if not on_ad_page:
        return False

    log.info("[INFO] Ad Suitability step detected — handling...")
    try:
        await page.screenshot(path=_screenshot_path("ad_suitability_detected"))
    except Exception:
        pass

    none_selectors = [
        'ytcp-checkbox-lit[label*="None of the above"]',
        'ytcp-checkbox:has-text("None of the above")',
        'label:has-text("None of the above")',
        '[aria-label*="None of the above" i]',
    ]

    none_handled = False
    for sel in none_selectors:
        try:
            el = page.locator(sel).first
            if not await el.is_visible(timeout=2_000):
                continue
            if await _is_checked_or_aria_true(el):
                log.info("'None of the above' already checked — no click needed")
            else:
                await el.click()
                log.info("Checked 'None of the above' on Ad Suitability step")
            none_handled = True
            break
        except Exception:
            continue

    if not none_handled:
        log.info(
            "No 'None of the above' control matched — leaving defaults (all unchecked)"
        )

    await page.wait_for_timeout(1_000)
    return True


async def _navigate_to_visibility(page, progress: Callable) -> None:
    """
    Adaptively click NEXT through all upload wizard steps until we reach
    the Visibility panel.  Handles the new Ad Suitability step automatically.

    YouTube's current upload wizard has up to 5 steps:
      Details → Ad Suitability (new, optional) → Video elements → Checks → Visibility
    """
    # Selectors that are present ONLY on the Visibility panel
    VISIBILITY_PRESENT = [
        'tp-yt-paper-radio-button[name="PUBLIC"]',
        'tp-yt-paper-radio-button[name="UNLISTED"]',
        'tp-yt-paper-radio-button[name="PRIVATE"]',
        'ytcp-radio-button[name="PUBLIC"]',
        'ytcp-radio-button[name="UNLISTED"]',
        '[name="PUBLIC"]',
        '[name="UNLISTED"]',
    ]
    NEXT_SELS = [
        'ytcp-button#next-button',
        'button:has-text("Next")',
        'ytcp-stepper button:has-text("Next")',
        '#next-button',
    ]

    for step in range(6):   # max 6 NEXT clicks to be safe
        # ── Check if Visibility page is already visible ────────────
        for sel in VISIBILITY_PRESENT:
            try:
                if await page.locator(sel).first.is_visible(timeout=1_200):
                    log.info(f"✓ Visibility page reached after {step} NEXT click(s)")
                    return
            except Exception:
                continue

        # ── Handle Ad Suitability page if present ─────────────────
        handled = await _handle_ad_suitability(page)
        if handled:
            progress("Ad Suitability step handled …")
            await page.wait_for_timeout(1_500)

        # ── Click NEXT ─────────────────────────────────────────────
        progress(f"Navigating step {step + 1} …")
        log.debug(f"Clicking NEXT (step {step + 1}) …")
        clicked = await _safe_click(page, NEXT_SELS, timeout=12_000, label=f"NEXT step {step + 1}")
        if not clicked:
            log.warning(f"NEXT button not found on step {step + 1} — continuing anyway.")
        await page.wait_for_timeout(2_000)

    log.warning("Reached maximum navigation steps — could not confirm Visibility page.")


async def _is_upload_wizard_next_enabled(page) -> bool:
    """True if the main Next button is visible and clickable (YouTube enables it when upload is done)."""
    next_sels = [
        "ytcp-button#next-button",
        "#next-button",
        'ytcp-stepper ytcp-button#next-button',
        'ytcp-stepper button:has-text("Next")',
    ]
    for sel in next_sels:
        try:
            btn = page.locator(sel).first
            if not await btn.is_visible(timeout=1_200):
                continue
            dis = await btn.get_attribute("disabled")
            aria_dis = await btn.get_attribute("aria-disabled")
            if dis is not None or aria_dis == "true":
                return False
            return True
        except Exception:
            continue
    return False


async def _progress_bar_suggests_upload_complete(page) -> bool:
    """True if the upload progress UI shows 100% / complete (best-effort)."""
    try:
        prog = page.locator("ytcp-video-upload-progress").first
        if await prog.is_visible(timeout=1_000):
            txt = (await prog.inner_text()).lower()
            if "100" in txt and "%" in txt:
                return True
            if "complete" in txt and "upload" in txt:
                return True
    except Exception:
        pass
    return False


async def _has_explicit_upload_complete_text(page) -> bool:
    """Narrow 'Upload complete' checks — avoid 'Checks complete' / processing copy on wrong steps."""
    narrow = [
        'ytcp-video-upload-progress:has-text("Upload complete")',
        'ytcp-upload-dialog:has-text("Upload complete")',
        'ytcp-video-upload-dialog :text("Upload complete")',
    ]
    for sel in narrow:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=600):
                return True
        except Exception:
            continue
    try:
        loc = page.get_by_text("Upload complete", exact=True).first
        if await loc.is_visible(timeout=400):
            return True
    except Exception:
        pass
    return False


async def _upload_completion_pulse(page) -> tuple[bool, str]:
    """
    One poll for “file transfer finished” on the Details step.
    Prefer Next enabled (YouTube enables it when the file is on their servers).
    """
    if await _is_upload_wizard_next_enabled(page):
        return True, "Next button enabled"
    if await _has_explicit_upload_complete_text(page):
        return True, "Upload complete (copy)"
    if await _progress_bar_suggests_upload_complete(page):
        return True, "Progress 100%"
    return False, ""


async def _wait_for_upload_complete(page, progress: Callable, timeout: int) -> None:
    """
    Block until the background file-upload reaches 100%.

    Requires the same completion signal on **two** consecutive polls (~3s apart)
    so we don’t race ahead on flaky UI. On timeout, raises — we never continue
    with a partial upload (that is what strands videos in Draft).
    """
    progress("Waiting for file upload to complete (0% → 100%) …")
    log.info("Waiting for YouTube file-upload to finish …")

    deadline = time.monotonic() + timeout / 1000
    stable_need = 2
    stable = 0
    last_reason = ""

    while time.monotonic() < deadline:
        ok, reason = await _upload_completion_pulse(page)
        if ok:
            stable += 1
            last_reason = reason
            log.debug("Upload poll OK (%s), stable %s/%s", reason, stable, stable_need)
            if stable >= stable_need:
                log.info("File upload finished — %s (confirmed stable)", last_reason)
                progress("File upload complete — continuing with details …")
                await page.wait_for_timeout(2_000)
                return
        else:
            stable = 0
        await page.wait_for_timeout(3_000)

    await page.screenshot(path=_screenshot_path("upload_not_complete_timeout"))
    mins = max(1, timeout // 60_000)
    raise RuntimeError(
        f"Video file did not finish uploading within {mins} minute(s). "
        "Continuing would close the browser while YouTube is still receiving the file — "
        "videos often end up in Draft instead of your chosen visibility. "
        "Wait until Studio shows 100%% or the Next button enables, then retry. "
        "For very large files, increase pipeline.upload_complete_timeout_ms in config."
    )


async def _upload_thumbnail_on_details_page(page, thumbnail: str, progress: Callable) -> None:
    """
    Upload a custom thumbnail while still on the Details step (before NEXT×3).
    This is the ONLY time the thumbnail input is accessible.
    """
    if not thumbnail or not Path(thumbnail).exists():
        return

    progress("Uploading thumbnail …")
    log.debug(f"Uploading thumbnail on details page: {thumbnail}")

    # Strategy 1: Look for a hidden file input specifically for thumbnail
    thumb_input_selectors = [
        'ytcp-file-input#still-image-input-container input[type="file"]',
        'input[name="still-image-upload"]',
        'ytcp-thumbnail-picker-item input[type="file"]',
        'ytcp-file-input input[type="file"][accept*="image"]',
        'input[type="file"][accept*="image"]',
    ]

    # Strategy 2: Click "Upload thumbnail" button which opens file chooser
    thumb_btn_selectors = [
        'ytcp-button:has-text("Upload thumbnail")',
        'button:has-text("Upload thumbnail")',
        '[aria-label*="thumbnail" i]',
        '.thumbnail-picker button',
        'ytcp-thumbnail-picker-item:first-child button',
    ]

    # Try hidden input first (most reliable — avoids timing issues)
    for sel in thumb_input_selectors:
        try:
            inp = page.locator(sel).first
            cnt = await inp.count()
            if cnt > 0:
                await inp.set_input_files(thumbnail)
                await page.wait_for_timeout(2_000)
                log.info(f"Thumbnail set via hidden input ({sel!r})")
                progress("Thumbnail uploaded ✓")
                return
        except Exception:
            continue

    # Try clicking button → file chooser
    for btn_sel in thumb_btn_selectors:
        try:
            async with page.expect_file_chooser(timeout=8_000) as fc_info:
                await page.click(btn_sel, timeout=5_000)
            fc = await fc_info.value
            await fc.set_files(thumbnail)
            await page.wait_for_timeout(2_000)
            log.info(f"Thumbnail uploaded via file chooser ({btn_sel!r})")
            progress("Thumbnail uploaded ✓")
            return
        except Exception:
            continue

    log.warning("Could not upload thumbnail — input not found on details page.")


# ── Core upload coroutine ─────────────────────────────────────────────────────

async def _upload(
    video_path: Path,
    metadata: dict,
    progress: Callable[[str], None],
) -> None:
    title       = metadata.get("title", "My YouTube Short")[:100]
    description = metadata.get("description", "")[:5000]
    tags        = metadata.get("tags", [])
    tags_str    = ", ".join(str(t) for t in tags)[:490]   # YT tag field limit
    thumbnail   = metadata.get("thumbnail_path", "")

    config.load()
    headless = bool(config.get("pipeline.headless_upload", _HEADLESS))
    slow_mo  = int(config.get("pipeline.upload_slow_mo",  _SLOW_MO))
    timeout  = int(config.get("pipeline.upload_timeout",  _TIMEOUT))
    upload_complete_timeout = int(config.get("pipeline.upload_complete_timeout_ms", 900_000))
    post_publish_grace_ms = int(config.get("pipeline.post_publish_grace_ms", 12_000))
    vis_mode = str(config.get("pipeline.upload_mode", "unlisted")).lower().strip()

    profiles   = config.get("pipeline.chrome_profiles", [])
    active_idx = config.get("pipeline.active_profile_index", 0)
    if not profiles:
        raise ValueError("No Chrome profile configured. Go to Settings → Chrome Profiles → Setup New Profile")

    active_profile      = profiles[active_idx] if 0 <= active_idx < len(profiles) else profiles[0]
    chrome_profile_path = active_profile["path"]

    log.info(
        f"Upload config: headless={headless}, slow_mo={slow_mo}ms, page_timeout={timeout}ms, "
        f"upload_complete_timeout={upload_complete_timeout}ms, post_publish_grace={post_publish_grace_ms}ms, "
        f"visibility={vis_mode!r}"
    )

    async with async_playwright() as pw:
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

        publish_flow_ok = False
        try:
            # ── 1. Navigate to YouTube Studio ─────────────────────────────────
            progress("Opening YouTube Studio …")
            await page.goto(UPLOAD_URL, timeout=timeout, wait_until="domcontentloaded")
            try:
                await page.wait_for_selector(
                    '#create-icon, ytcp-icon-button[id="create-icon"], button[aria-label="Create"]',
                    timeout=30_000,
                )
            except PWTimeoutError:
                await page.screenshot(path=_screenshot_path("studio_load_fail"))
                raise RuntimeError("YouTube Studio did not load — check login in Chrome profile.")

            # ── 2. CREATE → Upload videos ──────────────────────────────────────
            progress("Opening upload dialog …")
            clicked = await _safe_click(
                page,
                ['button[aria-label="Create"]', '#create-icon', 'ytcp-button#create-icon',
                 'ytcp-icon-button[id="create-icon"]', 'button:has-text("Create")'],
                timeout=10_000, label="CREATE button",
            )
            if not clicked:
                await page.screenshot(path=_screenshot_path("create_btn_fail"))
                raise RuntimeError("Could not find the 'Create' button.")
            await page.wait_for_timeout(1_500)

            clicked = await _safe_click(
                page,
                ['tp-yt-paper-item:has-text("Upload videos")', 'yt-formatted-string:has-text("Upload videos")',
                 '#text-item-0:has-text("Upload")', 'ytcp-ve:has-text("Upload")', ':has-text("Upload videos")'],
                timeout=8_000, label="Upload videos menu item",
            )
            if not clicked:
                await page.screenshot(path=_screenshot_path("upload_menu_fail"))
                raise RuntimeError("Could not click 'Upload videos' from the Create menu.")
            await page.wait_for_timeout(1_500)

            # ── 3. Select the video file ───────────────────────────────────────
            progress("Selecting video file …")
            log.debug(f"Selecting file: {video_path}")
            file_selected = False

            try:
                file_input = page.locator('input[type="file"]').first
                await file_input.wait_for(state="attached", timeout=8_000)
                await file_input.set_input_files(str(video_path.resolve()))
                file_selected = True
                log.debug("File selected via hidden input[type='file']")
            except Exception:
                pass

            if not file_selected:
                for btn_sel in ['button:has-text("SELECT FILES")', 'button:has-text("Select files")',
                                '#select-files-button', 'ytcp-button:has-text("SELECT")']:
                    try:
                        async with page.expect_file_chooser(timeout=10_000) as fc_info:
                            await page.click(btn_sel, timeout=6_000)
                        fc = await fc_info.value
                        await fc.set_files(str(video_path.resolve()))
                        file_selected = True
                        log.debug(f"File selected via file chooser ({btn_sel!r})")
                        break
                    except Exception:
                        continue

            if not file_selected:
                await page.screenshot(path=_screenshot_path("file_select_fail"))
                raise RuntimeError("Could not attach video file to the upload dialog.")

            # ── 4. Wait for details form to appear ────────────────────────────
            progress("Waiting for upload form …")
            TITLE_SEL: Optional[str] = None
            for title_sel in ['#textbox', 'div[aria-label="Title"]',
                               'ytcp-social-suggestion-input[label="Title"] #textbox',
                               'ytcp-social-suggestion-input #textbox', 'div[contenteditable="true"]']:
                try:
                    await page.wait_for_selector(title_sel, timeout=40_000)
                    TITLE_SEL = title_sel
                    log.debug(f"Title field found via {title_sel!r}")
                    break
                except PWTimeoutError:
                    continue

            if not TITLE_SEL:
                await page.screenshot(path=_screenshot_path("title_field_fail"))
                raise RuntimeError("Title field not found in YouTube Studio upload form.")

            await page.wait_for_timeout(1_000)

            # ── 5. *** WAIT FOR ACTUAL FILE UPLOAD TO FINISH *** ──────────────
            # Must happen before NEXT×3 or YouTube saves as Draft
            await _wait_for_upload_complete(page, progress, timeout=upload_complete_timeout)
            await page.wait_for_timeout(1_000)

            # ── 6. Fill in Title ───────────────────────────────────────────────
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

            # ── 7. Fill in Description ─────────────────────────────────────────
            progress("Filling in description …")
            desc_field = page.locator("#textbox").nth(1)
            await desc_field.scroll_into_view_if_needed()
            await desc_field.click(timeout=10_000)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(200)
            if description:
                await page.keyboard.type(description, delay=10)
            await page.wait_for_timeout(400)

            # ── 8. Not Made for Kids ───────────────────────────────────────────
            progress("Setting audience …")
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
                        log.debug(f"Kids toggle set via {kids_sel!r}")
                        break
                except Exception:
                    continue
            await page.wait_for_timeout(400)

            # ── 9. Tags via "More options" ─────────────────────────────────────
            if tags_str:
                progress("Adding tags …")
                log.debug("Expanding 'More options' …")
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
                            # Give the accordion animation time to finish
                            await page.wait_for_timeout(2_000)
                            break
                    except Exception:
                        continue

                if more_expanded:
                    tag_filled = False
                    # Scroll down so the tags section comes into view
                    await page.evaluate("window.scrollBy(0, 400)")
                    await page.wait_for_timeout(800)

                    for tag_sel in [
                        # Most specific first
                        'ytcp-free-text-chip-bar input',
                        'ytcp-free-text-chip-bar input[type="text"]',
                        'ytcp-form-input-container[label="Tags"] input',
                        'ytcp-form-input-container[label="Tags"] ytcp-free-text-chip-bar input',
                        'input[aria-label*="tag" i]',
                        'input[placeholder*="tag" i]',
                        'ytcp-chip-bar input',
                        '#tags-container input',
                    ]:
                        try:
                            tag_input = page.locator(tag_sel).first
                            if await tag_input.is_visible(timeout=4_000):
                                await tag_input.scroll_into_view_if_needed()
                                await tag_input.click()
                                await tag_input.fill(tags_str)
                                await page.keyboard.press("Return")
                                await page.wait_for_timeout(600)
                                tag_filled = True
                                log.info(f"Tags added ({len(tags_str)} chars) via {tag_sel!r}")
                                break
                        except Exception:
                            continue

                    if not tag_filled:
                        log.warning("Tags field not found — trying JS fallback …")
                        # JS fallback: find any visible input near the word "Tags"
                        try:
                            await page.evaluate(f"""
                                const inputs = [...document.querySelectorAll('input[type="text"], input:not([type])')];
                                const tagInput = inputs.find(el => {{
                                    const label = el.closest('[label]') || el.closest('[aria-label]');
                                    return label && (label.getAttribute('label') || label.getAttribute('aria-label') || '').toLowerCase().includes('tag');
                                }});
                                if (tagInput) {{
                                    tagInput.focus();
                                    tagInput.value = {repr(tags_str)};
                                    tagInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                                    tagInput.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}}));
                                }}
                            """)
                            await page.wait_for_timeout(600)
                            log.info("Tags injected via JS fallback")
                        except Exception as js_exc:
                            log.warning(f"JS tag fallback also failed: {js_exc}")
                else:
                    log.warning("'More options' button not found — tags skipped.")

            # ── 10. Upload Thumbnail (DETAILS PAGE — before NEXT×3) ───────────
            await _upload_thumbnail_on_details_page(page, thumbnail, progress)

            # ── 11. Navigate to Visibility (adaptive — handles new Ad Suitability step) ──
            await _navigate_to_visibility(page, progress)

            # ── 12. Set Visibility ─────────────────────────────────────────────
            progress(f"Setting visibility → {vis_mode.upper()} …")
            log.debug(f"Setting visibility → {vis_mode!r}")

            if vis_mode != "draft":
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
                    log.warning(f"Could not set visibility to '{vis_mode}' — using pre-selected value.")
            await page.wait_for_timeout(800)

            # ── 13. Save / Done ────────────────────────────────────────────────
            progress("Saving …")
            saved = await _safe_click(
                page,
                ['ytcp-button#done-button', 'button:has-text("Save")',
                 'button:has-text("Publish")', 'ytcp-button:has-text("Done")', '#done-button'],
                timeout=10_000, label="SAVE/DONE button",
            )
            if not saved:
                await page.screenshot(path=_screenshot_path("save_btn_fail"))
                log.warning("SAVE button not found.")

            # ── 14. Wait for processing confirmation ───────────────────────────
            progress("Waiting for processing confirmation …")
            try:
                await page.wait_for_selector(
                    (
                        'ytcp-video-upload-dialog ytcp-uploads-still-processing-dialog, '
                        'yt-dialog-store[dialog-id="VIDEO_UPLOAD_DIALOG"] *:has-text("Video link"), '
                        ':has-text("Your video is being processed"), '
                        ':has-text("Upload complete"), '
                        ':has-text("Video published"), '
                        ':has-text("Finished processing")'
                    ),
                    timeout=120_000,
                )
                progress("✅ Upload confirmed!")
                log.info(f"✅ Video successfully uploaded! (visibility={vis_mode})")
            except PWTimeoutError:
                await page.screenshot(path=_screenshot_path("confirm_timeout"))
                log.warning(
                    "Confirmation dialog not detected — upload may still have succeeded. "
                    "Check YouTube Studio manually."
                )
                progress("⚠️ Confirmation timed out — check YouTube Studio manually.")

            publish_flow_ok = True

        except Exception:
            try:
                await page.screenshot(path=_screenshot_path("unexpected_error"))
            except Exception:
                pass
            raise

        finally:
            grace_ms = post_publish_grace_ms if publish_flow_ok else 4_000
            try:
                await page.wait_for_timeout(grace_ms)
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass


# ── Public entry point ────────────────────────────────────────────────────────

def upload_to_youtube(
    video_path: Path,
    metadata: dict,
    progress_callback: Optional[Callable[[str], None]] = None,
    retries: int = 1,
) -> None:
    """
    Upload a rendered video to YouTube Studio.

    metadata keys:
        title, description, tags, thumbnail_path (optional)
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    file_size = video_path.stat().st_size
    if file_size == 0:
        raise ValueError(f"Video file is empty: {video_path}")
    if file_size < 10_000:
        log.warning(f"Video file suspiciously small ({file_size} bytes): {video_path}")
    if video_path.suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}:
        raise ValueError(f"Unsupported video format: {video_path.suffix!r}")

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
        f"YouTube upload failed after {retries + 1} attempt(s). Last error: {last_exc}"
    ) from last_exc
