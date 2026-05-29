"""
modules/ai_video/meta_ai_browser.py
====================================
Generate documentary B-roll clips via Meta AI web UI (Playwright + Chrome profile).

No official Meta video API — uses persistent Chrome login and automates meta.ai.
UI selectors may break when Meta updates the site; see output/ meta_ai_debug_*.png on failure.

Setup:
  python setup_meta_profile.py
  Settings → Footage source → Meta AI (browser)
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests
from playwright.async_api import TimeoutError as PWTimeoutError
from playwright.async_api import async_playwright

from config import OUTPUT_DIR, get_logger
from core.config_manager import config

log = get_logger("meta_ai")

_CB = Callable[[str], None] | None

_LOGIN_URL_FRAGMENTS = (
    "facebook.com/login",
    "accounts.google.com",
    "accountscenter.meta.com",
    "login.php",
    "/login",
)

_PROMPT_SELECTORS = [
    'input[placeholder*="Ask Meta AI" i]',
    'input[placeholder*="Ask" i]',
    'input[placeholder*="Describe" i]',
    'textarea[placeholder*="Ask" i]',
    'textarea[placeholder*="Describe" i]',
    'textarea[placeholder*="video" i]',
    'div[contenteditable="true"][role="textbox"]',
    'div[contenteditable="true"]',
    "input[type='text']",
    "textarea",
    '[role="textbox"]',
]

_PROMPT_PLACEHOLDERS = (
    "Ask Meta AI",
    "Ask",
    "Describe",
    "Message",
    "What do you want",
)

_GENERATE_SELECTORS = [
    '[aria-label*="Send" i]',
    '[aria-label*="Submit" i]',
    'button[type="submit"]',
    'button:has-text("Generate")',
    'button:has-text("Create")',
    'button:has-text("Animate")',
    '[aria-label*="Generate" i]',
    '[aria-label*="Create video" i]',
]

_VIDEO_MODE_SELECTORS = [
    'button:has-text("Video")',
    'a:has-text("Video")',
    '[aria-label*="Video" i]',
    'button:has-text("Imagine")',
]


def _notify(fn: _CB, msg: str) -> None:
    log.info(msg)
    if fn:
        try:
            fn(msg)
        except UnicodeEncodeError:
            fn(msg.encode("ascii", errors="replace").decode("ascii"))


def _profile_path() -> Path:
    raw = (config.get("meta_ai.chrome_profile_path") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    from config import get_user_data_dir
    return get_user_data_dir() / "ChromeProfiles" / "GhostCreator_MetaAI"


def _headless() -> bool:
    v = config.get("meta_ai.headless", False)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes")


def _timeout_ms() -> int:
    try:
        return max(60_000, int(config.get("meta_ai.generation_timeout_ms", 600_000)))
    except (TypeError, ValueError):
        return 600_000


def _clip_delay_sec() -> float:
    try:
        return max(0.0, float(config.get("meta_ai.clip_delay_sec", 5)))
    except (TypeError, ValueError):
        return 5.0


def _base_url() -> str:
    return (config.get("meta_ai.base_url") or "https://www.meta.ai/").strip()


def _fallback_to_stock() -> bool:
    v = config.get("meta_ai.fallback_to_stock", True)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() not in ("0", "false", "no")


def _debug_screenshot(page, tag: str) -> str:
    path = OUTPUT_DIR / f"meta_ai_debug_{tag}_{int(time.time())}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.get_event_loop().run_until_complete(page.screenshot(path=str(path), full_page=True))
    except Exception:
        pass
    return str(path)


async def _screenshot_async(page, tag: str) -> str:
    path = OUTPUT_DIR / f"meta_ai_debug_{tag}_{int(time.time())}.png"
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
        login_btn = page.get_by_role("button", name=re.compile(r"^log in$", re.I))
        if await login_btn.count() > 0 and await login_btn.first.is_visible():
            return True
    except Exception:
        pass
    return False


async def _ensure_logged_in(page, progress_callback: _CB) -> None:
    if not await _needs_login(page):
        return
    shot = await _screenshot_async(page, "login_required")
    raise RuntimeError(
        "Meta AI not logged in. Run: python setup_meta_profile.py — "
        "log in to Meta/Facebook in Chrome, close the window, then retry. "
        f"Debug screenshot: {shot}"
    )


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

    for sel in _PROMPT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0 or not await loc.is_visible():
                continue
            await loc.click(timeout=5_000)
            await loc.fill("")
            await loc.fill(text)
            return True
        except Exception:
            try:
                await loc.click(timeout=3_000)
                await page.keyboard.press("Control+A")
                await page.keyboard.type(text, delay=5)
                return True
            except Exception:
                continue
    return False


async def _wait_for_video_url(page, captured: list[str], timeout_ms: int) -> str | None:
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        for url in reversed(captured):
            if _looks_like_video_url(url):
                return url
        try:
            video = page.locator("video").first
            if await video.count() > 0:
                src = await video.get_attribute("src")
                if src and _looks_like_video_url(src):
                    return src
        except Exception:
            pass
        await page.wait_for_timeout(1500)
    return None


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


async def _generate_one_clip(
    page,
    prompt: str,
    output_path: Path,
    progress_callback: _CB,
) -> Path | None:
    timeout_ms = _timeout_ms()
    captured_urls: list[str] = []

    def on_response(response):
        try:
            url = response.url
            ct = (response.headers.get("content-type") or "").lower()
            if "video" in ct or _looks_like_video_url(url):
                captured_urls.append(url)
        except Exception:
            pass

    page.on("response", on_response)

    url = _base_url()
    _notify(progress_callback, f"  🌐 Meta AI: opening {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(4000)

    await _ensure_logged_in(page, progress_callback)

    await _click_first(page, _VIDEO_MODE_SELECTORS, timeout=5_000)
    await page.wait_for_timeout(1500)

    video_prompt = (
        f"Create a short cinematic documentary video, no text, no watermark: {prompt}"
    )
    if not await _fill_prompt(page, video_prompt):
        await _screenshot_async(page, "no_prompt_box")
        raise RuntimeError("Could not find Meta AI prompt input — UI may have changed.")

    if not await _click_first(page, _GENERATE_SELECTORS, timeout=10_000):
        await page.keyboard.press("Enter")

    _notify(progress_callback, f"  ⏳ Meta AI generating (up to {timeout_ms // 60000} min) …")
    video_url = await _wait_for_video_url(page, captured_urls, timeout_ms)
    if not video_url:
        await _screenshot_async(page, "no_video")
        return None

    _notify(progress_callback, f"  ⬇️ Downloading generated clip …")
    if video_url.startswith("http"):
        ok = await asyncio.to_thread(_download_video_url, video_url, output_path)
        if ok:
            return output_path

    try:
        video = page.locator("video").first
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


async def check_meta_login() -> dict:
    """Return {ok, message} after opening Meta AI and checking login state."""

    async def _check(page):
        await page.goto(_base_url(), wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(3000)
        if await _needs_login(page):
            return {
                "ok": False,
                "message": "Not logged in. Run: python setup_meta_profile.py",
            }
        filled = await _fill_prompt(page, "test")
        if not filled:
            return {
                "ok": False,
                "message": "Logged in but prompt box not found — Meta UI may have changed.",
            }
        return {"ok": True, "message": f"Meta AI session OK (profile: {_profile_path()})"}

    try:
        return await _with_browser(_check)
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


async def _fetch_clips_meta_ai_async(
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
            f"Meta AI Chrome profile not found: {profile}\n"
            "Run: python setup_meta_profile.py"
        )

    async def _run_all(page):
        nonlocal results
        for i, seg in enumerate(segments, 1):
            query = seg.get("video_query") or seg.get("voiceover", "documentary scenery")[:60]
            clip_path = output_dir / f"clip_{i:02d}.mp4"
            _notify(progress_callback, f"🎬 Meta AI clip {i}/{total}: {query!r}")

            result: Path | None = None
            try:
                result = await _generate_one_clip(page, query, clip_path, progress_callback)
            except Exception as exc:
                _notify(progress_callback, f"  ⚠️ Meta AI error: {exc}")

            if result is None and _fallback_to_stock():
                _notify(progress_callback, f"  ↩️ Fallback to stock footage for clip {i}")
                from modules.video_fetcher import download_clip

                result = await asyncio.to_thread(
                    download_clip, query, clip_path, max_clip_duration, progress_callback
                )

            results.append(result)
            if i < total and _clip_delay_sec() > 0:
                await asyncio.sleep(_clip_delay_sec())

    await _with_browser(_run_all)
    success = sum(1 for c in results if c is not None)
    _notify(progress_callback, f"🎬 Meta AI clips ready: {success}/{total}")
    return results


def fetch_clips_meta_ai(
    segments: list[dict],
    output_dir: Path,
    max_clip_duration: int = 120,
    progress_callback: _CB = None,
) -> list[Path | None]:
    """Sync entry for pipeline — one browser session, all segments."""
    return asyncio.run(
        _fetch_clips_meta_ai_async(segments, output_dir, max_clip_duration, progress_callback)
    )


async def generate_test_clip(prompt: str, output_path: Path) -> Path | None:
    """CLI/API PoC — single prompt to one MP4."""

    async def _one(page):
        return await _generate_one_clip(page, prompt, output_path, print)

    return await _with_browser(_one)


if __name__ == "__main__":
    import sys

    test_prompt = sys.argv[1] if len(sys.argv) > 1 else "ocean waves at sunset documentary"
    out = OUTPUT_DIR / "meta_ai_test_clip.mp4"
    print(f"Meta AI test clip -> {out}")
    print(f"Profile: {_profile_path()}")
    path = asyncio.run(generate_test_clip(test_prompt, out))
    if path:
        print(f"OK: {path} ({path.stat().st_size // 1024} KB)")
    else:
        print("FAILED - check logs and output/meta_ai_debug_*.png")
        sys.exit(1)
