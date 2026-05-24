"""
modules/ai_video/grok_browser.py
=================================
Generate documentary B-roll via Grok Imagine web UI (Playwright + shared Chrome profile).

Uses the same Chrome profile as Meta AI (log in to grok.com once via setup_meta_profile.py).

Setup:
  python setup_meta_profile.py   # log in to Meta + Grok in the same Chrome window
  Settings -> Footage source -> Grok (browser)
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests
from playwright.async_api import async_playwright

from config import OUTPUT_DIR, get_logger
from core.config_manager import config

log = get_logger("grok_ai")

_CB = Callable[[str], None] | None

_LOGIN_URL_FRAGMENTS = (
    "accounts.x.ai",
    "x.com/i/flow/login",
    "x.com/login",
    "twitter.com/login",
    "/login",
    "/signin",
)

_PROMPT_SELECTORS = [
    '[contenteditable="true"]',
    'textarea[placeholder*="What do you want" i]',
    'textarea[aria-label*="Ask Grok" i]',
    'input[placeholder*="Describe" i]',
    'input[placeholder*="Prompt" i]',
    'input[placeholder*="Imagine" i]',
    'textarea[placeholder*="Describe" i]',
    'div[contenteditable="true"][role="textbox"]',
    "textarea",
    "input[type='text']",
    '[role="textbox"]',
]

_POPUP_SELECTORS = [
    'button:has-text("Got it")',
    '[aria-label="Close"]',
    'button:has-text("Dismiss")',
]

_PROMPT_PLACEHOLDERS = (
    "What do you want to know",
    "Describe",
    "Prompt",
    "Imagine",
    "Ask",
)

_GENERATE_SELECTORS = [
    '[aria-label*="Send" i]',
    '[aria-label*="Submit" i]',
    'button[type="submit"]',
    'button:has-text("Generate")',
    'button:has-text("Create")',
]

_IMAGINE_SELECTORS = [
    'a[aria-label="Imagine"]',
    'a:has-text("Imagine")',
    'button:has-text("Imagine")',
]

_VIDEO_MODE_SELECTORS = [
    'button:has-text("Video")',
    '[aria-label*="Video" i]',
]

_COOKIE_SELECTORS = [
    'button:has-text("Accept All Cookies")',
    'button:has-text("Accept All")',
    'button:has-text("Reject All")',
]


def _notify(fn: _CB, msg: str) -> None:
    log.info(msg)
    if fn:
        try:
            fn(msg)
        except UnicodeEncodeError:
            fn(msg.encode("ascii", errors="replace").decode("ascii"))


def _profile_path() -> Path:
    raw = (config.get("grok.chrome_profile_path") or config.get("meta_ai.chrome_profile_path") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(r"C:\ChromeProfiles\GhostCreator_MetaAI")


def _headless() -> bool:
    v = config.get("grok.headless", config.get("meta_ai.headless", False))
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes")


def _timeout_ms() -> int:
    try:
        return max(60_000, int(config.get("grok.generation_timeout_ms", 600_000)))
    except (TypeError, ValueError):
        return 600_000


def _clip_delay_sec() -> float:
    try:
        return max(0.0, float(config.get("grok.clip_delay_sec", 5)))
    except (TypeError, ValueError):
        return 5.0


def _base_url() -> str:
    return (config.get("grok.base_url") or "https://grok.com/imagine").strip()


def _fallback_to_stock() -> bool:
    v = config.get("grok.fallback_to_stock", True)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() not in ("0", "false", "no")


async def _screenshot_async(page, tag: str) -> str:
    path = OUTPUT_DIR / f"grok_debug_{tag}_{int(time.time())}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        await page.screenshot(path=str(path), full_page=True)
    except Exception as exc:
        log.debug("Screenshot failed: %s", exc)
    return str(path)


def _is_login_url(url: str) -> bool:
    u = (url or "").lower()
    return any(frag in u for frag in _LOGIN_URL_FRAGMENTS)


async def _needs_login(page) -> bool:
    if _is_login_url(page.url):
        return True
    try:
        for label in (r"^sign in$", r"^log in$"):
            btn = page.get_by_role("button", name=re.compile(label, re.I))
            if await btn.count() > 0 and await btn.first.is_visible():
                return True
    except Exception:
        pass
    return False


async def _ensure_logged_in(page) -> None:
    if not await _needs_login(page):
        return
    shot = await _screenshot_async(page, "login_required")
    raise RuntimeError(
        "Grok not logged in. Run: python setup_meta_profile.py - "
        "open the Grok tab, sign in with X/xAI, close Chrome, then retry. "
        f"Debug screenshot: {shot}"
    )


async def _dismiss_cookies(page) -> None:
    await _click_first(page, _COOKIE_SELECTORS, timeout=3_000)


async def _dismiss_popups(page) -> None:
    await _click_first(page, _POPUP_SELECTORS, timeout=2_000)


async def _select_video_mode(page) -> None:
    buttons = page.locator("button")
    count = await buttons.count()
    for i in range(count):
        btn = buttons.nth(i)
        try:
            if not await btn.is_visible():
                continue
            txt = (await btn.inner_text()).strip()
            if txt == "Video":
                await btn.click(timeout=5_000)
                return
        except Exception:
            continue
    await _click_first(page, _VIDEO_MODE_SELECTORS, timeout=3_000)


async def _click_first(page, selectors: list[str], timeout: int = 8_000) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


async def _fill_prompt(page, prompt: str) -> bool:
    text = prompt[:2000]

    for ph in _PROMPT_PLACEHOLDERS:
        try:
            loc = page.get_by_placeholder(ph, exact=False)
            if await loc.count() == 0 or not await loc.first.is_visible():
                continue
            box = loc.first
            await box.click(timeout=5_000)
            await box.fill(text)
            return True
        except Exception:
            continue

    try:
        loc = page.get_by_label(re.compile(r"ask grok", re.I))
        if await loc.count() > 0 and await loc.first.is_visible():
            await loc.first.click(timeout=5_000)
            await loc.first.fill(text)
            return True
    except Exception:
        pass

    for sel in _PROMPT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0 or not await loc.is_visible():
                continue
            await loc.click(timeout=5_000)
            try:
                await loc.fill(text)
            except Exception:
                await page.keyboard.press("Control+A")
                await page.keyboard.type(text, delay=5)
            return True
        except Exception:
            continue
    return False


def _looks_like_video_url(url: str) -> bool:
    if not url or url.startswith("blob:"):
        return False
    lower = url.lower()
    if any(x in lower for x in (".mp4", ".webm", "video", "mime=video")):
        return True
    path = urlparse(url).path.lower()
    return path.endswith((".mp4", ".webm", ".mov"))


def _download_video_url(url: str, output_path: Path) -> bool:
    try:
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return output_path.is_file() and output_path.stat().st_size > 10_000
    except Exception as exc:
        log.warning("Video download failed %s: %s", url[:80], exc)
        return False


async def _wait_for_video_url(
    page, captured: list[str], timeout_ms: int, *, min_dom_wait_sec: float = 12.0
) -> str | None:
    deadline = time.time() + timeout_ms / 1000.0
    dom_ok_after = time.time() + min_dom_wait_sec
    while time.time() < deadline:
        for url in reversed(captured):
            if _looks_like_video_url(url):
                return url
        if time.time() >= dom_ok_after:
            try:
                for video in await page.locator("video").all():
                    if not await video.is_visible():
                        continue
                    src = await video.get_attribute("src")
                    if src and _looks_like_video_url(src):
                        return src
            except Exception:
                pass
        await page.wait_for_timeout(1500)
    return None


async def _open_imagine(page) -> None:
    url = _base_url()
    if "/imagine" not in page.url.lower():
        if not await _click_first(page, _IMAGINE_SELECTORS, timeout=5_000):
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(2000)
    if "/imagine" not in page.url.lower():
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(2000)


async def _generate_one_clip(
    page,
    prompt: str,
    output_path: Path,
    progress_callback: _CB,
) -> Path | None:
    timeout_ms = _timeout_ms()
    captured_urls: list[str] = []
    listening = False

    def on_response(response):
        if not listening:
            return
        try:
            url = response.url
            ct = (response.headers.get("content-type") or "").lower()
            if "video" in ct or _looks_like_video_url(url):
                captured_urls.append(url)
        except Exception:
            pass

    page.on("response", on_response)

    start_url = _base_url()
    _notify(progress_callback, f"  Grok: opening {start_url}")
    await page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3000)
    await _dismiss_cookies(page)
    await _ensure_logged_in(page)
    await _open_imagine(page)
    await _dismiss_cookies(page)
    await _dismiss_popups(page)
    await _select_video_mode(page)
    await page.wait_for_timeout(1500)

    video_prompt = (
        f"Create a short cinematic documentary video, no text, no watermark: {prompt}"
    )
    if not await _fill_prompt(page, video_prompt):
        await _screenshot_async(page, "no_prompt_box")
        raise RuntimeError("Could not find Grok prompt input - UI may have changed.")

    if not await _click_first(page, _GENERATE_SELECTORS, timeout=10_000):
        await page.keyboard.press("Enter")

    listening = True
    captured_urls.clear()

    _notify(progress_callback, f"  Grok generating (up to {timeout_ms // 60000} min) ...")
    video_url = await _wait_for_video_url(page, captured_urls, timeout_ms, min_dom_wait_sec=15.0)
    if not video_url:
        await _screenshot_async(page, "no_video")
        return None

    _notify(progress_callback, "  Downloading generated clip ...")
    if video_url.startswith("http"):
        ok = await asyncio.to_thread(_download_video_url, video_url, output_path)
        if ok:
            return output_path

    try:
        for video in await page.locator("video").all():
            src = await video.get_attribute("src")
            if src and src.startswith("http"):
                ok = await asyncio.to_thread(_download_video_url, src, output_path)
                if ok:
                    return output_path
    except Exception:
        pass

    return None


async def _with_browser(coro_factory):
    profile = _profile_path()
    if not profile.parent.exists() and not profile.exists():
        profile.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            channel="chrome",
            headless=_headless(),
            slow_mo=80,
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            no_viewport=True,
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        try:
            return await coro_factory(page)
        finally:
            await browser.close()


async def check_grok_login() -> dict:
    async def _check(page):
        await page.goto(_base_url(), wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(3000)
        await _dismiss_cookies(page)
        if await _needs_login(page):
            return {
                "ok": False,
                "message": "Not logged in to Grok. Run: python setup_meta_profile.py and sign in on grok.com",
            }
        await _open_imagine(page)
        await _dismiss_popups(page)
        filled = await _fill_prompt(page, "test")
        if not filled:
            return {
                "ok": False,
                "message": "Logged in but prompt box not found — Grok UI may have changed.",
            }
        return {"ok": True, "message": f"Grok session OK (profile: {_profile_path()})"}

    try:
        return await _with_browser(_check)
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


async def _fetch_clips_grok_async(
    segments: list[dict],
    output_dir: Path,
    max_clip_duration: int,
    progress_callback: _CB,
) -> list[Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(segments)
    results: list[Path | None] = []

    profile = _profile_path()
    if not profile.exists():
        raise RuntimeError(
            f"Chrome profile not found: {profile}\nRun: python setup_meta_profile.py"
        )

    async def _run_all(page):
        nonlocal results
        for i, seg in enumerate(segments, 1):
            query = seg.get("video_query") or seg.get("voiceover", "documentary scenery")[:60]
            clip_path = output_dir / f"clip_{i:02d}.mp4"
            _notify(progress_callback, f"Grok clip {i}/{total}: {query!r}")

            result: Path | None = None
            try:
                result = await _generate_one_clip(page, query, clip_path, progress_callback)
            except Exception as exc:
                _notify(progress_callback, f"  Grok error: {exc}")

            if result is None and _fallback_to_stock():
                _notify(progress_callback, f"  Fallback to stock footage for clip {i}")
                from modules.video_fetcher import download_clip

                result = await asyncio.to_thread(
                    download_clip, query, clip_path, max_clip_duration, progress_callback
                )

            results.append(result)
            if i < total and _clip_delay_sec() > 0:
                await asyncio.sleep(_clip_delay_sec())

    await _with_browser(_run_all)
    success = sum(1 for c in results if c is not None)
    _notify(progress_callback, f"Grok clips ready: {success}/{total}")
    return results


def fetch_clips_grok(
    segments: list[dict],
    output_dir: Path,
    max_clip_duration: int = 120,
    progress_callback: _CB = None,
) -> list[Path | None]:
    return asyncio.run(
        _fetch_clips_grok_async(segments, output_dir, max_clip_duration, progress_callback)
    )


async def generate_test_clip(prompt: str, output_path: Path) -> Path | None:
    async def _one(page):
        return await _generate_one_clip(page, prompt, output_path, print)

    return await _with_browser(_one)


if __name__ == "__main__":
    import sys

    test_prompt = sys.argv[1] if len(sys.argv) > 1 else "ocean waves at sunset documentary"
    out = OUTPUT_DIR / "grok_test_clip.mp4"
    print(f"Grok test clip -> {out}")
    print(f"Profile: {_profile_path()}")
    path = asyncio.run(generate_test_clip(test_prompt, out))
    if path:
        print(f"OK: {path} ({path.stat().st_size // 1024} KB)")
    else:
        print("FAILED - check logs and output/grok_debug_*.png")
        sys.exit(1)
