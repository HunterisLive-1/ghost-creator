"""
main.py — Ghost Creator AI (documentary + upload helpers)
=========================================================
Headless entry runs the same documentary pipeline as the GUI (no script review
or video preview modals — those are forced off for the duration of the run).

Usage:
    python main.py                          # Auto-topic documentary
    python main.py --topic "AI in India"   # Fixed subject

    python main.py --from-video            # Upload existing MP4 (metadata from last run)
    python main.py --from-video --video-file output/test.mp4
"""

import argparse
import json
import queue
import sys
from pathlib import Path

from config import APP_VERSION, get_logger, OUTPUT_DIR
from core.config_manager import config

from modules.uploader import upload_to_youtube

log = get_logger("main")

METADATA_FILE = OUTPUT_DIR / "last_metadata.json"


def _load_metadata() -> dict:
    if METADATA_FILE.exists():
        return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    log.warning("No last_metadata.json found — using placeholder metadata for upload.")
    return {
        "title": "Ghost Creator AI Documentary",
        "description": "Documentary content. Subscribe for more!",
        "tags": ["Documentary", "AI", "Technology"],
    }


def run_documentary_cli(topic: str | None = None, upload: bool = False) -> None:
    """Research → documentary script → voice → footage → assemble → optional upload (unattended)."""
    from core.pipeline_runner import PipelineRunner
    from modules.researcher import find_trending_topic

    if topic is None:
        topic = find_trending_topic()
    dur = int(config.get("target_duration", 180) or 180)
    config.set("target_duration", max(60, min(dur, 600)))

    # --upload flag: force YouTube upload regardless of config.json setting
    if upload:
        config.set("pipeline.upload_enabled", True)

    prev_script_review = bool(config.get("script_review_enabled", True))
    prev_video_preview = bool(config.get("video_preview_enabled", True))
    config.set("script_review_enabled", False)
    config.set("video_preview_enabled", False)

    q: queue.Queue = queue.Queue()
    runner = PipelineRunner(q, run_id=0)

    try:
        runner.start(topic=topic)
        while True:
            try:
                evt = q.get(timeout=1.0)
            except queue.Empty:
                th = runner.thread
                if th and not th.is_alive() and q.empty():
                    raise RuntimeError("Pipeline thread ended without a completion event")
                continue
            msg = evt.get("message", "")
            if evt.get("step"):
                log.info("[step %s] %s", evt["step"], msg)
            if evt.get("done"):
                if evt.get("level") == "ERROR":
                    raise RuntimeError(msg)
                out = evt.get("output_path", "") or ""
                if out:
                    log.info("Done — %s", out)
                break
    finally:
        config.set("script_review_enabled", prev_script_review)
        config.set("video_preview_enabled", prev_video_preview)


def run_from_video(video_file: Path | None = None) -> None:
    """Upload an existing MP4 to YouTube Studio."""
    log.info("Mode: FROM VIDEO  (upload only)")

    if video_file:
        video_path = Path(video_file)
    else:
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
    log.info("Upload complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Ghost Creator AI v{APP_VERSION} — Documentary pipeline (CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                              # Auto-topic documentary
  python main.py --topic "AI in 2026"       # Fixed subject
  python main.py --from-video                # Upload existing MP4
  python main.py --from-video --video-file output/film.mp4
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"Ghost Creator AI {APP_VERSION}")
    parser.add_argument("--topic", type=str, default=None, help="Documentary subject (default: trending)")
    parser.add_argument(
        "--from-video",
        action="store_true",
        help="Skip generation — upload an existing MP4",
    )
    parser.add_argument("--video-file", type=str, default=None, help="Path to MP4 (with --from-video)")
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Force YouTube upload after generation (overrides config upload_enabled=false)",
    )

    args = parser.parse_args()

    try:
        if args.from_video:
            run_from_video(video_file=Path(args.video_file) if args.video_file else None)
        else:
            run_documentary_cli(topic=args.topic, upload=args.upload)
    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        sys.exit(0)
    except Exception as exc:
        log.critical("Run failed: %s", exc, exc_info=True)
        sys.exit(1)
