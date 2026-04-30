"""
modules/thumbnail_maker.py — AI Thumbnail Generator (16:9)
===========================================================
Generates a clickbait thumbnail at **1280 × 720 (16:9)** — YouTube standard.
Video aspect ratio settings do not apply to thumbnails.

Steps:
  1. Build a cinematic image prompt from the video title (Gemini Imagen).
  2. Generate the background via `modules.image_gen` (Gemini only).
  3. Composite with Pillow (gradient, badge, title, accent bar).
  4. Save as  output/thumbnails/{safe_title}_16x9_{timestamp}_thumbnail.jpg

Returns the absolute path string so callers can pass it to the uploader.
"""

import asyncio
import re
import textwrap
import time
from pathlib import Path
from typing import Optional

from config import get_logger, OUTPUT_DIR, TEMP_DIR

log = get_logger("thumbnail")

THUMB_DIR = OUTPUT_DIR / "thumbnails"
THUMB_DIR.mkdir(parents=True, exist_ok=True)

THUMB_W = 1280
THUMB_H = 720
THUMB_ASPECT = "16:9"

# Shown in GUI progress / terminal when the Gemini key/plan cannot generate images (e.g. free tier).
GEMINI_THUMBNAIL_SKIP_USER_MESSAGE = (
    "Gemini image generation is not succeeded because the API doesn't support image generation."
)

_WIN_FONTS = [
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\ariblk.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
    r"C:\Windows\Fonts\trebucbd.ttf",
    r"C:\Windows\Fonts\verdanab.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]

_BADGES = [
    "🔥 VIRAL",
    "⚠️ SHOCKING",
    "😱 MUST WATCH",
    "💥 BREAKING",
    "✅ TRUTH EXPOSED",
    "🚨 WARNING",
    "🤯 MIND-BLOWING",
    "👀 YOU WON'T BELIEVE",
]


def _safe_filename(title: str, timestamp: str) -> str:
    """Convert title → filesystem-safe string, append 16x9 + timestamp."""
    safe = re.sub(
        r"[^\w\u0900-\u097F\u0A00-\u0A7F\u0B00-\u0B7F\u0B80-\u0BFF"
        r"\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0980-\u09FF -]",
        "",
        title,
    )
    safe = re.sub(r"\s+", "_", safe.strip()).strip("_") or "thumbnail"
    return f"{safe[:55]}_16x9_{timestamp}_thumbnail.jpg"


def _find_font(size: int):
    from PIL import ImageFont
    for path in _WIN_FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    log.warning("No system TTF font found — using PIL default bitmap font (text will be small)")
    return ImageFont.load_default()


def _build_thumbnail_prompt(title: str, topic: str) -> str:
    """Build an Imagen-friendly prompt for the thumbnail background (no text in image)."""
    ascii_title = re.sub(r"[^\x00-\x7F]+", " ", title).strip() or topic
    return (
        f"Ultra-dramatic YouTube thumbnail background about '{ascii_title}', "
        "landscape 16:9 wide composition, "
        "cinematic high-contrast lighting, vivid saturated colors, shocking dramatic scene, "
        "8K photorealistic, rule of thirds, deep shadows, vibrant color grading, "
        "eye-catching visual, no text, no watermark, no logo, no UI elements, "
        "clickbait style, professional photography, ultra-realistic"
    )


def _draw_text_with_outline(
    draw,
    xy: tuple[int, int],
    text: str,
    font,
    fill: tuple,
    outline_color: tuple = (0, 0, 0, 255),
    outline_width: int = 5,
) -> None:
    x, y = xy
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    draw.text((x, y), text, font=font, fill=fill)


def _apply_gradient_overlay(img):
    """Dark gradient from ~38% height (text readability at bottom)."""
    from PIL import Image
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    w, h = img.size
    start_y = int(h * 0.38)

    for y in range(start_y, h):
        alpha = int(215 * ((y - start_y) / (h - start_y)) ** 1.4)
        for x in range(w):
            overlay.putpixel((x, y), (0, 0, 0, min(alpha, 215)))

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return Image.alpha_composite(img, overlay)


def _composite_thumbnail(
    bg_path: str,
    title: str,
    topic: str,
) -> str:
    import random
    from PIL import Image, ImageDraw

    w, h = THUMB_W, THUMB_H
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = THUMB_DIR / _safe_filename(title, timestamp)

    bg = Image.open(bg_path).convert("RGB")
    bg = bg.resize((w, h), Image.LANCZOS)

    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    vig_draw = ImageDraw.Draw(vignette)
    border = int(min(w, h) * 0.07)
    for i in range(border, 0, -1):
        alpha = int(140 * (1 - i / border) ** 2)
        vig_draw.rectangle(
            [border - i, border - i, w - border + i, h - border + i],
            outline=(0, 0, 0, alpha),
        )
    bg = bg.convert("RGBA")
    bg = Image.alpha_composite(bg, vignette)

    bg = _apply_gradient_overlay(bg)
    draw = ImageDraw.Draw(bg)

    scale = min(w / 1280, h / 720)

    badge_text = random.choice(_BADGES)
    badge_fs = max(20, int(32 * scale))
    badge_font = _find_font(badge_fs)
    badge_pad = max(8, int(14 * scale))
    badge_x = int(30 * scale)
    badge_y = int(30 * scale)
    try:
        bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        bw, bh = len(badge_text) * badge_fs // 2, badge_fs + 4

    draw.rounded_rectangle(
        [
            badge_x - badge_pad,
            badge_y - badge_pad // 2,
            badge_x + bw + badge_pad,
            badge_y + bh + badge_pad // 2,
        ],
        radius=int(10 * scale),
        fill=(220, 30, 30, 235),
    )
    _draw_text_with_outline(
        draw,
        (badge_x, badge_y),
        badge_text,
        badge_font,
        fill=(255, 255, 255, 255),
        outline_color=(150, 0, 0, 255),
        outline_width=max(2, int(2 * scale)),
    )

    ascii_title = re.sub(r"[^\x00-\x7F]+", " ", title).strip() or topic
    max_text_w = int(w * 0.90)
    font_sizes = [88, 76, 66, 58, 50, 44, 38]

    title_font = _find_font(font_sizes[0])
    font_size = font_sizes[0]
    chosen_lines: list[str] = []

    for fs in font_sizes:
        title_font = _find_font(fs)
        approx_char_w = max(1, int(fs * 0.54))
        chars_per_line = max(6, max_text_w // approx_char_w)
        wrapped = textwrap.fill(ascii_title, width=chars_per_line)
        lines = wrapped.split("\n")
        max_line_px = max(
            (draw.textbbox((0, 0), ln, font=title_font)[2] for ln in lines),
            default=0,
        )
        if max_line_px <= max_text_w and len(lines) <= 3:
            font_size = fs
            chosen_lines = lines
            break
    else:
        fs = font_sizes[-1]
        title_font = _find_font(fs)
        approx_char_w = max(1, int(fs * 0.54))
        chars_per_line = max(6, max_text_w // approx_char_w)
        wrapped = textwrap.fill(ascii_title, width=chars_per_line)
        chosen_lines = wrapped.split("\n")[:3]
        font_size = fs

    try:
        _, top_off, _, bot_off = draw.textbbox((0, 0), "Ag", font=title_font)
        line_h = (bot_off - top_off) + int(14 * scale)
    except Exception:
        line_h = font_size + int(14 * scale)

    total_text_h = line_h * len(chosen_lines)
    bottom_pad = int(60 * scale)
    text_y_start = h - total_text_h - bottom_pad

    for i, line in enumerate(chosen_lines):
        try:
            lw = draw.textbbox((0, 0), line, font=title_font)[2]
        except Exception:
            lw = len(line) * (font_size // 2)
        lx = (w - lw) // 2
        ly = text_y_start + i * line_h
        _draw_text_with_outline(
            draw,
            (lx, ly),
            line,
            title_font,
            fill=(255, 255, 255, 255),
            outline_color=(0, 0, 0, 255),
            outline_width=max(4, int(5 * scale)),
        )

    bar_h = max(6, int(8 * scale))
    accent_palettes = [
        [(255, 60, 60), (255, 165, 0)],
        [(0, 180, 255), (0, 80, 255)],
        [(255, 200, 0), (255, 80, 0)],
        [(0, 220, 80), (0, 150, 255)],
    ]
    c0, c1 = random.choice(accent_palettes)
    for px in range(w):
        t = px / w
        rr = int(c0[0] * (1 - t) + c1[0] * t)
        gg = int(c0[1] * (1 - t) + c1[1] * t)
        bb = int(c0[2] * (1 - t) + c1[2] * t)
        for py in range(h - bar_h, h):
            draw.point((px, py), fill=(rr, gg, bb, 255))

    final = bg.convert("RGB")
    final.save(str(out_path), "JPEG", quality=95, optimize=True)
    log.info(f"Thumbnail saved → {out_path}  [{w}×{h}, {THUMB_ASPECT}]")
    return str(out_path)


def _create_fallback_bg(out_path: str, w: int, h: int) -> None:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), (10, 10, 20))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        r = int(5 + 30 * (1 - y / h))
        g = int(5 + 15 * (1 - y / h))
        b = int(20 + 60 * (1 - y / h))
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    img.save(out_path, "PNG")
    log.info(f"Fallback thumbnail background saved: {out_path}  [{w}×{h}]")


def generate_thumbnail(
    title: str,
    topic: str,
    aspect_ratio: str = "16:9",
    image_prompts: Optional[list[str]] = None,
    progress_callback=None,
) -> str:
    """
    Generate a 16:9 (1280×720) clickbait thumbnail via Gemini Imagen.

    If the API key does not support image generation (common on free tier), returns
    ``""`` after notifying via ``progress_callback`` — no exception, no fallback image.

    Parameters
    ----------
    title, topic : str
        Title (overlay text) and topic (prompt fallback).
    aspect_ratio : str
        Ignored; thumbnails are always 16:9. Kept for call-site compatibility.

    Returns
    -------
    str
        Path to the JPEG, or empty string if thumbnail generation was skipped.
    """
    from backends.image.gemini_imagen import (
        GeminiImageNotSupportedError,
        is_gemini_image_unsupported,
    )

    _ = aspect_ratio
    w, h = THUMB_W, THUMB_H
    ar = THUMB_ASPECT

    _progress = progress_callback or (lambda m: log.info(f"[thumbnail] {m}"))
    log.info(f"Generating thumbnail: fixed canvas={w}×{h} ({ar})")

    if image_prompts:
        thumb_prompt = (
            f"{image_prompts[0]}, "
            "ultra-dramatic YouTube thumbnail style, landscape wide 16:9, "
            "extreme contrast, vivid colors, cinematic, eye-catching, "
            "no text, no watermarks, high detail"
        )
    else:
        thumb_prompt = _build_thumbnail_prompt(title, topic)

    log.debug(f"Thumbnail prompt: {thumb_prompt[:130]}…")
    _progress(f"Generating thumbnail background ({w}×{h}) …")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    bg_path = str(TEMP_DIR / f"thumbnail_bg_{timestamp}.png")

    try:
        from modules.image_gen import _get_backend

        backend = _get_backend()
        asyncio.run(
            backend.generate(
                prompt=thumb_prompt,
                output_path=bg_path,
                width=w,
                height=h,
                aspect_ratio=ar,
            )
        )
        log.debug(f"Thumbnail background saved: {bg_path}")
    except GeminiImageNotSupportedError:
        _progress(GEMINI_THUMBNAIL_SKIP_USER_MESSAGE)
        log.info("Thumbnail skipped: Gemini image generation not supported for this API key.")
        return ""
    except Exception as exc:
        if is_gemini_image_unsupported(exc):
            _progress(GEMINI_THUMBNAIL_SKIP_USER_MESSAGE)
            log.info(
                "Thumbnail skipped: Gemini image generation not supported (%s)",
                exc,
            )
            return ""
        log.error(f"Thumbnail image generation failed: {exc} — using fallback background")
        _progress(f"Image gen failed ({exc}) — using fallback background")
        _create_fallback_bg(bg_path, w, h)

    _progress("Compositing thumbnail text …")
    try:
        out_path = _composite_thumbnail(bg_path, title, topic)
    except Exception as exc:
        log.error(f"Thumbnail compositing failed: {exc}", exc_info=True)
        _progress(f"Thumbnail text overlay failed: {exc}")
        raise

    _progress(f"Thumbnail ready: {Path(out_path).name}")
    return out_path
