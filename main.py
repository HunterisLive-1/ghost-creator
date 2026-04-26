"""
main.py — Ghost Creator AI Orchestrator
========================================
Full pipeline with optional skip modes for reuse of existing assets.

Usage:
    python main.py                          # Full pipeline (auto-topic)
    python main.py --topic "AI in India"   # Force a topic

    # --- Skip modes (reuse existing files) ---
    python main.py --skip-images            # Skip steps 1-4, use existing
                                            # output/scene_*.png + temp/voiceover.mp3
                                            # → runs Video Build + Upload

    python main.py --from-video             # Skip steps 1-5, use existing
                                            # output/final_short.mp4
                                            # → runs Upload only

    python main.py --from-video --video-file output/test_short.mp4
                                            # Upload a specific MP4 file
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from config import APP_VERSION, get_logger, TEMP_DIR, OUTPUT_DIR
from core.config_manager import config

from modules.researcher    import find_trending_topic
from modules.scripter      import generate_script
from modules.voicer        import generate_voiceover, ensure_tts_ready
from modules.image_gen     import generate_images
from modules.video_builder import build_video
from modules.uploader      import upload_to_youtube

log = get_logger("main")

# ── Saved metadata path (written by full run, read by skip modes) ─────────────
METADATA_FILE = OUTPUT_DIR / "last_metadata.json"


def _save_metadata(metadata: dict) -> None:
    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_metadata() -> dict:
    if METADATA_FILE.exists():
        return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    log.warning("No last_metadata.json found — using placeholder metadata for upload.")
    return {
        "title": "Ghost Creator AI Short",
        "description": "Amazing AI and Tech content. Subscribe for more!",
        "tags": ["AI", "Technology", "Shorts", "Viral"],
    }


# ── Pipeline modes ─────────────────────────────────────────────────────────────

def run_full(topic: str | None = None) -> None:
    """Steps 1→6: Research → Script → Voice → Images → Video → Upload."""
    log.info("Mode: FULL PIPELINE")

    # Step 1 · Research
    log.info("[1/6] Research …")
    topic = topic or find_trending_topic()
    log.info(f"      → Topic: {topic!r}")

    # Step 2 · Script
    log.info("[2/6] Scripting via Gemini …")
    language = config.get("pipeline.language", "hi")
    target_duration = config.get("target_duration", 60)
    aspect_ratio = config.get("aspect_ratio", "9:16")
    script = generate_script(
        topic,
        lang=language,
        target_duration=target_duration,
        aspect_ratio=aspect_ratio,
    )
    log.info(
        "      → Title: %r  |  num_scenes=%s  |  %ss  |  %s",
        script["metadata"]["title"],
        script.get("num_scenes"),
        target_duration,
        aspect_ratio,
    )
    _save_metadata(script["metadata"])

    # Step 3 · Voiceover (OmniVoice loads then unloads to free GPU for images)
    if not ensure_tts_ready():
        raise RuntimeError("TTS backend is not ready — check Settings and reference audio / API keys.")
    log.info("[3/6] Voiceover (TTS) …")
    audio_path = generate_voiceover(script["voiceover_text"])
    log.info(f"      → Audio: {audio_path}")

    # Step 4 · Images (TTS GPU memory released if local backend)
    log.info("[4/6] Images via ComfyUI …")
    num_scenes = int(script.get("num_scenes", len(script["image_prompts"])))
    image_prompts = script["image_prompts"][:num_scenes]
    if len(script["image_prompts"]) < num_scenes:
        log.warning(
            "      → Only %s prompt(s) from script (expected %s)",
            len(script["image_prompts"]),
            num_scenes,
        )
    image_paths = generate_images(image_prompts, aspect_ratio=aspect_ratio)
    log.info(f"      → {len(image_paths)} images generated")

    # Step 5 · Video
    log.info("[5/6] Assembling video …")
    video_path = build_video(
        image_paths           = image_paths,
        audio_path            = audio_path,
        voiceover_text        = script["voiceover_text"],
        english_subtitle_text = script.get("english_subtitle_text", script["voiceover_text"]),
        title                 = script["metadata"]["title"],
        aspect_ratio          = aspect_ratio,
        cinematic_effects     = config.get("cinematic_effects", {}),
        target_duration       = target_duration,
    )
    log.info(f"      → Video: {video_path}")

    # Step 6 · Upload (optional)
    if config.get("pipeline.upload_enabled", True):
        log.info("[6/6] Uploading to YouTube Studio …")
        upload_to_youtube(video_path=video_path, metadata=script["metadata"])
        log.info("      → Upload complete!")
    else:
        log.info("[6/6] YouTube upload disabled — video kept locally only")
        log.info(f"      → {video_path}")

    _cleanup()


def run_from_images() -> None:
    """
    Steps 5→6: Use existing output/scene_*.png + temp/voiceover.mp3
    → Build video → Upload.
    """
    log.info("Mode: FROM IMAGES  (skipping Research/Script/Voice/ComfyUI)")

    # Find existing images
    image_paths = sorted(OUTPUT_DIR.glob("scene_*.png"))
    if not image_paths:
        raise FileNotFoundError(
            f"No scene_*.png found in {OUTPUT_DIR}. Run the full pipeline first."
        )

    # Find existing audio
    audio_path = TEMP_DIR / "voiceover.mp3"
    if not audio_path.exists():
        raise FileNotFoundError(
            f"voiceover.mp3 not found in {TEMP_DIR}. Run the full pipeline first."
        )

    metadata = _load_metadata()
    log.info(f"Using {len(image_paths)} images + audio ({audio_path.stat().st_size//1024} KB)")

    # Step 5 · Video
    log.info("[5/6] Assembling video …")
    video_path = build_video(
        image_paths           = image_paths,
        audio_path            = audio_path,
        voiceover_text        = metadata.get("description", "AI content for you."),
        english_subtitle_text = metadata.get("english_subtitle_text", metadata.get("description", "AI content for you.")),
        title                 = metadata.get("title", "Ghost Creator Short"),
    )
    log.info(f"      → Video: {video_path}")

    # Step 6 · Upload (optional)
    if config.get("pipeline.upload_enabled", True):
        log.info("[6/6] Uploading to YouTube Studio …")
        upload_to_youtube(video_path=video_path, metadata=metadata)
        log.info("      → Upload complete!")
    else:
        log.info("[6/6] YouTube upload disabled — video kept locally only")
        log.info(f"      → {video_path}")


def run_from_video(video_file: Path | None = None) -> None:
    """
    Step 6 only: Upload an existing MP4 to YouTube Studio.
    Defaults to output/final_short.mp4, or a custom --video-file path.
    """
    log.info("Mode: FROM VIDEO  (upload only)")

    if video_file:
        video_path = Path(video_file)
    else:
        # Try final_short.mp4 first, then test_short.mp4
        for candidate in ["final_short.mp4", "test_short.mp4"]:
            video_path = OUTPUT_DIR / candidate
            if video_path.exists():
                break
        else:
            raise FileNotFoundError(
                f"No MP4 found in {OUTPUT_DIR}. Use --video-file path/to/file.mp4"
            )

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    metadata = _load_metadata()
    if not config.get("pipeline.upload_enabled", True):
        log.info("YouTube upload is disabled in config — skipping upload.")
        log.info(f"Video file: {video_path}")
        return

    log.info(f"Uploading: {video_path}  ({video_path.stat().st_size // (1024*1024)} MB)")
    log.info(f"Title: {metadata.get('title')!r}")

    upload_to_youtube(video_path=video_path, metadata=metadata)
    log.info("Upload complete! 🚀")


def _cleanup() -> None:
    log.info("Cleaning up temp folder …")
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
        TEMP_DIR.mkdir()
    log.info("Done — your Short is live! 🚀")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Ghost Creator AI v{APP_VERSION} — Automated YouTube Shorts Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                              # Auto-topic full pipeline
  python main.py --topic "AI in 2025"        # Forced topic full pipeline
  python main.py --skip-images               # Use existing images + audio
  python main.py --from-video                # Upload existing final_short.mp4
  python main.py --from-video --video-file output/test_short.mp4
        """,
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"Ghost Creator AI {APP_VERSION}",
    )
    parser.add_argument("--topic",       type=str, default=None,
                        help="Force a specific topic (full pipeline only)")
    parser.add_argument("--skip-images", action="store_true",
                        help="Skip Research/Script/Voice/Images — use existing files")
    parser.add_argument("--from-video",  action="store_true",
                        help="Skip everything — upload an existing MP4")
    parser.add_argument("--video-file",  type=str, default=None,
                        help="Path to MP4 to upload (for --from-video mode)")

    args = parser.parse_args()

    try:
        if args.from_video:
            run_from_video(video_file=args.video_file)
        elif args.skip_images:
            run_from_images()
        else:
            run_full(topic=args.topic)
    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        sys.exit(0)
    except Exception as exc:
        log.critical(f"Pipeline failed: {exc}", exc_info=True)
        sys.exit(1)
