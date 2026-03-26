"""
modules/thumbnail_maker.py — AI Thumbnail Generator (ratio-aware)
==================================================================
Generates a clickbait thumbnail in the SAME aspect ratio as the video:

  • 16:9  → 1280 × 720   (YouTube landscape / long-form)
  • 9:16  → 1080 × 1920  (YouTube Shorts portrait)

Steps:
  1. Resolve correct pixel dimensions from aspect_ratio.
  2. Build a cinematic eye-catching image prompt from the video title.
  3. Generate the background image via the configured image backend
     (same one used for video frames, correct dimensions + ratio forced).
  4. Composite with Pillow:
       • Dark gradient overlay (bottom portion — text readability)
       • Attention badge top-left  (e.g. "🔥 VIRAL")
       • Large bold title text — Impact / Arial Bold, white + thick black outline
       • Accent glow bar at very bottom
  5. Save as  output/thumbnails/{safe_title}_{timestamp}_thumbnail.jpg
     (unique per video — never overwritten).

Returns the absolute path string so the pipeline can pass it to uploader.
"""

import asyncio
import re
import textwrap
import time
from pathlib import Path
from typing import Optional

from config import get_logger, OUTPUT_DIR, TEMP_DIR
from core.config_manager import config

log = get_logger("thumbnail")

# ── Output folder ─────────────────────────────────────────────────────────────
THUMB_DIR = OUTPUT_DIR / "thumbnails"
THUMB_DIR.mkdir(parents=True, exist_ok=True)

# ── Dimension map ─────────────────────────────────────────────────────────────
# (width, height) per aspect ratio
_DIMS: dict[str, tuple[int, int]] = {
    "16:9": (1280, 720),
    "9:16": (1080, 1920),
}


def _thumb_dims(aspect_ratio: str) -> tuple[int, int]:
    """Return (width, height) for the given aspect ratio string."""
    return _DIMS.get(aspect_ratio, _DIMS["9:16"])


# ── Windows font search paths (best → fallback) ───────────────────────────────
_WIN_FONTS = [
    r"C:\Windows\Fonts\impact.ttf",        # Impact — classic YT thumbnail font
    r"C:\Windows\Fonts\arialbd.ttf",       # Arial Bold
    r"C:\Windows\Fonts\ariblk.ttf",        # Arial Black
    r"C:\Windows\Fonts\calibrib.ttf",      # Calibri Bold
    r"C:\Windows\Fonts\trebucbd.ttf",      # Trebuchet Bold
    r"C:\Windows\Fonts\verdanab.ttf",      # Verdana Bold
    r"C:\Windows\Fonts\arial.ttf",         # Arial regular fallback
]

# Attention badge labels — one is chosen at random per video
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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_filename(title: str, timestamp: str, aspect_ratio: str) -> str:
    """Convert title → filesystem-safe string, append ratio tag + timestamp."""
    safe = re.sub(
        r"[^\w\u0900-\u097F\u0A00-\u0A7F\u0B00-\u0B7F\u0B80-\u0BFF"
        r"\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0980-\u09FF -]",
        "",
        title,
    )
    safe = re.sub(r"\s+", "_", safe.strip()).strip("_") or "thumbnail"
    ratio_tag = aspect_ratio.replace(":", "x")   # "16:9" → "16x9"
    return f"{safe[:55]}_{ratio_tag}_{timestamp}_thumbnail.jpg"


def _find_font(size: int):
    """Return the best available ImageFont for the given pixel size."""
    from PIL import ImageFont
    for path in _WIN_FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    log.warning("No system TTF font found — using PIL default bitmap font (text will be small)")
    return ImageFont.load_default()


def _build_thumbnail_prompt(title: str, topic: str, aspect_ratio: str) -> str:
    """
    Build a Stable-Diffusion / Imagen prompt for a clickbait thumbnail background.
    All in English, no text/watermarks in image.
    """
    ascii_title = re.sub(r"[^\x00-\x7F]+", " ", title).strip() or topic
    orient = "portrait vertical 9:16" if aspect_ratio == "9:16" else "landscape 16:9 wide"
    return (
        f"Ultra-dramatic YouTube thumbnail background about '{ascii_title}', "
        f"{orient} composition, "
        "cinematic high-contrast lighting, vivid saturated colors, shocking dramatic scene, "
        "8K photorealistic, rule of thirds, deep shadows, vibrant color grading, "
        "eye-catching visual, no text, no watermark, no logo, no UI elements, "
        "clickbait style, professional photography, DreamshaperXL style, ultra-realistic"
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
    """Draw text with a thick outline (8-pass method) for maximum readability."""
    x, y = xy
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    draw.text((x, y), text, font=font, fill=fill)


def _apply_gradient_overlay(img, aspect_ratio: str):
    """
    Apply a dark gradient overlay.
    • 16:9 — starts at 38% height (text area at bottom ~62%)
    • 9:16 — starts at 45% height (taller canvas; keep top clear for visual)
    """
    from PIL import Image
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    w, h = img.size
    start_frac = 0.45 if aspect_ratio == "9:16" else 0.38
    start_y = int(h * start_frac)

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
    aspect_ratio: str,
) -> str:
    """
    Load background image, apply overlays + text, save and return path.
    All layout values scale with the canvas dimensions.
    """
    import random
    from PIL import Image, ImageDraw

    w, h = _thumb_dims(aspect_ratio)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = THUMB_DIR / _safe_filename(title, timestamp, aspect_ratio)

    # ── Load + resize background to exact thumbnail dimensions ────────────
    bg = Image.open(bg_path).convert("RGB")
    bg = bg.resize((w, h), Image.LANCZOS)

    # ── Vignette (soft dark border) ───────────────────────────────────────
    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    vig_draw = ImageDraw.Draw(vignette)
    border = int(min(w, h) * 0.07)       # ~7% of shorter edge
    for i in range(border, 0, -1):
        alpha = int(140 * (1 - i / border) ** 2)
        vig_draw.rectangle(
            [border - i, border - i, w - border + i, h - border + i],
            outline=(0, 0, 0, alpha),
        )
    bg = bg.convert("RGBA")
    bg = Image.alpha_composite(bg, vignette)

    # ── Gradient overlay ──────────────────────────────────────────────────
    bg = _apply_gradient_overlay(bg, aspect_ratio)
    draw = ImageDraw.Draw(bg)

    # ── Scale factors relative to 16:9 base (1280×720) ───────────────────
    scale = min(w / 1280, h / 720)       # uniform scale factor

    # ── 1. Attention badge (top-left) ─────────────────────────────────────
    badge_text  = random.choice(_BADGES)
    badge_fs    = max(20, int(32 * scale))
    badge_font  = _find_font(badge_fs)
    badge_pad   = max(8, int(14 * scale))
    badge_x     = int(30 * scale)
    badge_y     = int(30 * scale)
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

    # ── 2. Title text (bottom area) ───────────────────────────────────────
    ascii_title = re.sub(r"[^\x00-\x7F]+", " ", title).strip() or topic
    max_text_w  = int(w * 0.90)

    # Font size candidates — scaled per ratio
    if aspect_ratio == "9:16":
        # 9:16 is narrower (1080px) but very tall; use slightly larger sizes
        font_sizes = [96, 84, 72, 62, 54, 46, 40]
    else:
        font_sizes = [88, 76, 66, 58, 50, 44, 38]

    title_font = _find_font(font_sizes[0])
    font_size  = font_sizes[0]
    chosen_lines: list[str] = []

    for fs in font_sizes:
        title_font = _find_font(fs)
        # Estimate chars per line from pixel budget
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
        # Worst case: force 3 lines at smallest size
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
    bottom_pad   = int(60 * scale)
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

    # ── 3. Accent glow bar at very bottom ─────────────────────────────────
    bar_h = max(6, int(8 * scale))
    accent_palettes = [
        [(255, 60, 60),  (255, 165, 0)],
        [(0,  180, 255), (0,  80,  255)],
        [(255, 200, 0),  (255, 80,  0)],
        [(0,  220, 80),  (0,  150, 255)],
    ]
    c0, c1 = random.choice(accent_palettes)
    for px in range(w):
        t = px / w
        rr = int(c0[0] * (1 - t) + c1[0] * t)
        gg = int(c0[1] * (1 - t) + c1[1] * t)
        bb = int(c0[2] * (1 - t) + c1[2] * t)
        for py in range(h - bar_h, h):
            draw.point((px, py), fill=(rr, gg, bb, 255))

    # ── Save as JPEG ──────────────────────────────────────────────────────
    final = bg.convert("RGB")
    final.save(str(out_path), "JPEG", quality=95, optimize=True)
    log.info(f"Thumbnail saved → {out_path}  [{w}×{h}, {aspect_ratio}]")
    return str(out_path)


# ── Fallback background ───────────────────────────────────────────────────────

def _create_fallback_bg(out_path: str, w: int, h: int) -> None:
    """Create a dark gradient background when AI generation fails."""
    from PIL import Image, ImageDraw
    img  = Image.new("RGB", (w, h), (10, 10, 20))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        r = int(5  + 30 * (1 - y / h))
        g = int(5  + 15 * (1 - y / h))
        b = int(20 + 60 * (1 - y / h))
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    img.save(out_path, "PNG")
    log.info(f"Fallback thumbnail background saved: {out_path}  [{w}×{h}]")


# ── Public API ────────────────────────────────────────────────────────────────

def generate_thumbnail(
    title: str,
    topic: str,
    aspect_ratio: str = "9:16",
    image_prompts: Optional[list[str]] = None,
    progress_callback=None,
) -> str:
    """
    Generate a clickbait YouTube thumbnail matching the video's aspect ratio.

    Parameters
    ----------
    title : str
        Video title (used for text overlay; may contain Devanagari/Unicode).
    topic : str
        Raw topic string (used to build the image generation prompt).
    aspect_ratio : str
        "9:16" (Shorts portrait) or "16:9" (landscape). Determines canvas size.
    image_prompts : list[str], optional
        Existing scene prompts — first one is extended for the thumbnail BG.
        If None, a fresh prompt is built from the title/topic.
    progress_callback : callable, optional
        Called with status strings for pipeline GUI updates.

    Returns
    -------
    str
        Absolute path to the saved thumbnail JPEG.
    """
    _progress = progress_callback or (lambda m: log.info(f"[thumbnail] {m}"))
    w, h = _thumb_dims(aspect_ratio)

    log.info(f"Generating thumbnail: aspect_ratio={aspect_ratio!r}, canvas={w}×{h}")

    # ── Build image prompt ────────────────────────────────────────────────
    orient_hint = "portrait vertical 9:16" if aspect_ratio == "9:16" else "landscape wide 16:9"
    if image_prompts:
        thumb_prompt = (
            f"{image_prompts[0]}, "
            f"ultra-dramatic YouTube thumbnail style, {orient_hint}, "
            "extreme contrast, vivid colors, cinematic, eye-catching, "
            "no text, no watermarks, high detail"
        )
    else:
        thumb_prompt = _build_thumbnail_prompt(title, topic, aspect_ratio)

    log.debug(f"Thumbnail prompt: {thumb_prompt[:130]}…")
    _progress(f"Generating thumbnail background ({w}×{h}) …")

    # ── Generate background image ─────────────────────────────────────────
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    bg_path   = str(TEMP_DIR / f"thumbnail_bg_{timestamp}.png")

    try:
        from modules.image_gen import _get_backend
        backend = _get_backend()
        asyncio.run(
            backend.generate(
                prompt=thumb_prompt,
                output_path=bg_path,
                width=w,
                height=h,
                aspect_ratio=aspect_ratio,
            )
        )
        log.debug(f"Thumbnail background saved: {bg_path}")
    except Exception as exc:
        log.error(f"Thumbnail image generation failed: {exc} — using fallback background")
        _progress(f"Image gen failed ({exc}) — using fallback background")
        _create_fallback_bg(bg_path, w, h)

    # ── Composite text overlay ────────────────────────────────────────────
    _progress("Compositing thumbnail text …")
    try:
        out_path = _composite_thumbnail(bg_path, title, topic, aspect_ratio)
    except Exception as exc:
        log.error(f"Thumbnail compositing failed: {exc}", exc_info=True)
        _progress(f"Thumbnail text overlay failed: {exc}")
        raise

    _progress(f"Thumbnail ready: {Path(out_path).name}")
    return out_path
