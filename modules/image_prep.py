"""
image_prep.py — Prepares custom user images for video pipeline.
Handles resizing, cropping, and format conversion via FFmpeg + Pillow.
"""

import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image

SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"}


def get_image_dimensions(path: str | Path) -> tuple[int, int]:
    """Return (width, height) using Pillow."""
    p = Path(path)
    with Image.open(p) as im:
        return im.size


def validate_custom_images(image_paths: list) -> dict:
    """
    Returns dict with valid flag, count, errors, and warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []
    existing: list[str] = []

    for raw in image_paths or []:
        p = Path(raw)
        if not p.is_file():
            errors.append(f"File not found: {raw}")
            continue
        existing.append(str(p.resolve()))

    count = len(existing)
    if count == 0:
        errors.append("No valid image files selected.")

    if count == 1:
        warnings.append("Only 1 image — will be repeated for all scenes")

    for p in existing:
        try:
            w, h = get_image_dimensions(p)
            if w < 500 or h < 500:
                warnings.append(f"Low resolution image detected: {Path(p).name} ({w}×{h})")
        except OSError as e:
            errors.append(f"Cannot read image {p}: {e}")

    return {
        "valid": len(errors) == 0 and count > 0,
        "count": count,
        "errors": errors,
        "warnings": warnings,
    }


def fill_image_list(prepared_paths: list, num_scenes: int, log=None) -> list:
    """
    Repeat or truncate prepared paths to match num_scenes.
    If prepared_paths is empty, returns [] and logs an error when log is set.
    """
    if not prepared_paths:
        if log:
            log("[ERROR] No prepared images to assign to scenes.")
        return []
    n = max(0, int(num_scenes))
    if n == 0:
        return []
    out: list[str] = []
    for i in range(n):
        out.append(prepared_paths[i % len(prepared_paths)])
    return out


def prepare_custom_images(
    image_paths: list,
    aspect_ratio: str,
    output_dir: str,
    log=None,
) -> list:
    """
    Takes user-provided image paths, resizes/crops each to match target resolution.
    Returns list of prepared image paths in output_dir (same order as input).
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    prefix = f"prep_{ts}_"

    if aspect_ratio == "16:9":
        w, h = 1920, 1080
    else:
        w, h = 1080, 1920

    prepared: list[str] = []
    total = len(image_paths or [])

    for i, raw in enumerate(image_paths or []):
        src = Path(raw)
        filename = f"{prefix}custom_{i:02d}.jpg"
        dest = out_dir / filename

        if not src.is_file():
            raise FileNotFoundError(f"Image not found: {raw}")

        ext = src.suffix.lower()
        work_path = src
        tmp_converted: Path | None = None

        try:
            if ext not in SUPPORTED_FORMATS:
                tmp_converted = out_dir / f"{prefix}conv_{i:02d}.png"
                with Image.open(src) as im:
                    im = im.convert("RGB")
                    im.save(tmp_converted, "PNG")
                work_path = tmp_converted
                ext = ".png"

            cur_w, cur_h = get_image_dimensions(work_path)
            if cur_w == w and cur_h == h:
                shutil.copy2(work_path, dest)
            else:
                vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-loglevel",
                        "quiet",
                        "-i",
                        str(work_path),
                        "-vf",
                        vf,
                        str(dest),
                    ],
                    check=True,
                )

            prepared.append(str(dest))
            if log:
                log(f"[OK] Prepared image {i + 1}/{total}: {filename}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"FFmpeg failed to resize {src.name}: {e}"
            ) from e
        except OSError as e:
            raise RuntimeError(f"Could not process image {src}: {e}") from e
        finally:
            if tmp_converted and tmp_converted.exists():
                try:
                    tmp_converted.unlink()
                except OSError:
                    pass

    return prepared
