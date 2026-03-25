"""
img2video.py — Converts selected images to short video clips.
Supports: AnimateDiff, Stable Video Diffusion, Kling AI (via Fal.ai),
          and xAI Grok video (direct API).
"""

import base64
import hashlib
import requests
import time
from pathlib import Path

from config import get_logger

log = get_logger("img2video")

COST_PER_CLIP = {
    "animatediff":    0.005,
    "stable_video":   0.05,
    "kling_standard": 0.14,
    "kling_pro":      0.28,
    "grok_video_5s":  0.25,   # $0.05/sec × 5 sec
    "grok_video_10s": 0.50,   # $0.05/sec × 10 sec
}

FAL_ENDPOINTS = {
    "animatediff": "fal-ai/animatediff-v2v",
    "stable_video": "fal-ai/stable-video-diffusion",
    "kling_standard": "fal-ai/kling-video/v1.6/standard/image-to-video",
    "kling_pro": "fal-ai/kling-video/v1.6/pro/image-to-video",
}

GROK_VIDEO_BACKENDS = {"grok_video_5s", "grok_video_10s"}


# ── Fal.ai helpers ────────────────────────────────────────────────────────────

def upload_image_to_fal(image_path: str) -> str:
    """Upload a local image to Fal.ai temporary storage and return the URL."""
    import fal_client
    return fal_client.upload_file(image_path)


# ── xAI Grok video helpers ────────────────────────────────────────────────────

def _download_video(url: str, source_image_path: str, suffix: str = "", log_fn=None) -> str | None:
    """Download a video from URL and save next to source image."""
    _log = log_fn or (lambda msg: None)
    try:
        h = hashlib.md5(source_image_path.encode()).hexdigest()[:8]
        out_dir = Path(source_image_path).parent
        out_path = str(out_dir / f"clip_{h}{suffix}.mp4")

        r = requests.get(url, timeout=120, stream=True)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        _log(f"[OK] Video clip downloaded: {Path(out_path).name}")
        return out_path
    except Exception as exc:
        _log(f"[ERROR] Failed to download video: {exc}")
        return None


def _generate_with_grok(
    image_path: str,
    prompt: str,
    duration: str,
    api_key: str,
    log_fn=None,
) -> str | None:
    """
    Generate a video clip using xAI grok-imagine-video (direct API).

    # TODO: verify exact endpoint/payload against https://docs.x.ai/api/endpoints#video-generation
    Returns local .mp4 path or None on failure.
    """
    _log = log_fn or (lambda msg: None)

    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        suffix = Path(image_path).suffix.lower()
        mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"

        payload = {
            "model": "grok-2-vision-1212",
            "prompt": prompt + ", cinematic motion, smooth camera movement",
            "image": f"data:{mime};base64,{img_b64}",
            "duration": int(duration),
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        _log(f"[INFO] Submitting to grok-imagine-video (duration={duration}s, may take 30-90s)...")
        response = requests.post(
            "https://api.x.ai/v1/video/generations",
            json=payload, headers=headers, timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        # Synchronous response: video URL directly in data
        if "data" in data and data["data"]:
            video_url = data["data"][0].get("url")
            if video_url:
                return _download_video(video_url, image_path, "_grok", _log)

        # Async response: poll by job_id
        job_id = data.get("id")
        if not job_id:
            _log("[ERROR] grok-imagine-video: no job_id or url in response")
            return None

        _log(f"[INFO] Grok video job submitted, polling id={job_id}...")
        for attempt in range(30):
            time.sleep(10)
            poll = requests.get(
                f"https://api.x.ai/v1/video/generations/{job_id}",
                headers=headers, timeout=30,
            )
            poll.raise_for_status()
            poll_data = poll.json()

            status = poll_data.get("status", "unknown")
            _log(f"[INFO] grok-imagine-video status: {status} ({attempt + 1}/30)")

            if status == "completed":
                video_url = (
                    (poll_data.get("data") or [{}])[0].get("url")
                    or poll_data.get("video_url")
                )
                if video_url:
                    return _download_video(video_url, image_path, "_grok", _log)
                _log("[ERROR] grok-imagine-video completed but no URL in response")
                return None
            elif status in ("failed", "error"):
                _log(f"[ERROR] grok-imagine-video job failed: {poll_data.get('error', poll_data)}")
                return None

        _log("[ERROR] grok-imagine-video timed out after 5 minutes")
        return None

    except Exception as exc:
        _log(f"[ERROR] grok-imagine-video exception: {exc}")
        log.error(f"_generate_with_grok error: {exc}", exc_info=True)
        return None


# ── Main dispatcher ───────────────────────────────────────────────────────────

def generate_video_clip(
    image_path: str,
    prompt: str,
    backend: str,
    duration: str,
    aspect_ratio: str,
    config: dict | None = None,
    log_fn=None,
) -> str | None:
    """
    Convert a single image to a short video clip.

    Routes to xAI Grok (direct API) or Fal.ai depending on backend.
    Returns local path to downloaded .mp4 clip, or None on failure.
    """
    _log = log_fn or (lambda msg: log.info(msg))
    cfg = config or {}

    # ── xAI Grok video ────────────────────────────────────────────────────
    if backend in GROK_VIDEO_BACKENDS:
        dur = "5" if backend == "grok_video_5s" else "10"
        api_key = (cfg.get("xai_api_key") or "").strip()
        if not api_key:
            _log("[ERROR] xAI API key not set for Grok video. Add it in Settings.")
            return None
        return _generate_with_grok(image_path, prompt, dur, api_key, _log)

    # ── Fal.ai backends ───────────────────────────────────────────────────
    try:
        import fal_client

        endpoint = FAL_ENDPOINTS.get(backend)
        if not endpoint:
            _log(f"[ERROR] Unknown img2video backend: {backend!r}")
            return None

        _log(f"[INFO] Uploading image to Fal.ai: {Path(image_path).name}")
        image_url = upload_image_to_fal(image_path)
        _log(f"[INFO] Image uploaded: {image_url[:60]}...")

        if backend == "animatediff":
            args = {
                "image_url": image_url,
                "prompt": prompt + ", cinematic motion, smooth camera movement",
                "num_frames": 64,
                "fps": 8,
            }
        elif backend == "stable_video":
            args = {
                "image_url": image_url,
                "motion_bucket_id": 127,
                "fps": 6,
            }
        else:
            args = {
                "image_url": image_url,
                "prompt": prompt + ", cinematic, smooth motion",
                "duration": duration,
                "aspect_ratio": aspect_ratio,
            }

        _log(f"[INFO] Calling {endpoint} (this may take 30-120s)...")
        result = fal_client.subscribe(endpoint, arguments=args)

        video_url = result["video"]["url"]
        _log("[INFO] Clip generated, downloading...")

        path_hash = hashlib.md5(image_path.encode()).hexdigest()[:8]
        clip_filename = f"clip_{path_hash}.mp4"
        clip_path = str(Path(image_path).parent / clip_filename)

        resp = requests.get(video_url, timeout=120)
        resp.raise_for_status()
        with open(clip_path, "wb") as f:
            f.write(resp.content)

        _log(f"[OK] Clip saved: {clip_filename}")
        return clip_path

    except Exception as exc:
        _log(f"[ERROR] img2video failed for {Path(image_path).name}: {exc}")
        log.error(f"generate_video_clip error: {exc}", exc_info=True)
        return None


def process_selected_images(
    selections: dict,
    config: dict,
    temp_dir: str,
    log_fn=None,
) -> dict:
    """
    Process selected images: convert chosen ones to video clips.

    Parameters:
        selections: dict of {image_path: bool} — True = convert to video
        config: full config dict
        temp_dir: where to save clips (unused directly — clips saved next to images)
        log_fn: optional logging callback fn(message)

    Returns:
        dict of {image_path: {"type": "video_clip"|"image", "path": str}}
    """
    _log = log_fn or (lambda msg: log.info(msg))

    backend = config.get("img2video_backend", "kling_standard")
    duration = config.get("img2video_duration", "5")
    aspect_ratio = config.get("aspect_ratio", "9:16")

    results = {}
    for image_path, should_convert in selections.items():
        if should_convert:
            _log(f"[INFO] Converting to video clip: {Path(image_path).name}...")
            prompt = config.get("_scene_prompts", {}).get(image_path, "cinematic scene")
            clip_path = generate_video_clip(
                image_path,
                prompt,
                backend,
                duration,
                aspect_ratio,
                config=config,
                log_fn=_log,
            )
            if clip_path:
                results[image_path] = {"type": "video_clip", "path": clip_path}
                _log(f"[OK] Video clip ready: {Path(clip_path).name}")
            else:
                _log(f"[WARN] Img2video failed for {Path(image_path).name} — using static image")
                results[image_path] = {"type": "image", "path": image_path}
        else:
            results[image_path] = {"type": "image", "path": image_path}

    return results
