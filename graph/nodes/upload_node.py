"""
graph/nodes/upload_node.py — Upload Node
========================================
LangGraph node wrapper for modules/uploader.py.
"""

import logging
from pathlib import Path
from datetime import datetime
from core.config_manager import config
from modules.uploader import upload_to_youtube
from api.routes.pipeline import get_broadcaster
from graph.state import GhostCreatorState

log = logging.getLogger("upload_node")

def emit_progress(step: int, message: str, level: str = "INFO", run_id: str = ""):
    """Helper to emit progress directly to the WebSocket broadcaster."""
    broadcaster = get_broadcaster()
    if broadcaster:
        broadcaster.put({
            "step": step,
            "message": message,
            "level": level,
            "timestamp": datetime.now().isoformat(),
            "run_id": run_id,
        })

def upload_node(state: GhostCreatorState) -> dict:
    """Uploads the compiled video to YouTube Studio."""
    run_id = state.get("run_id", "")
    video_path = state.get("video_path", "")

    # 1. Check if upload is enabled in settings
    if not config.get("pipeline.upload_enabled", True):
        log.info("YouTube upload is disabled in settings. Skipping upload node.")
        emit_progress(6, "⏭️ Upload disabled — video saved locally.", "SUCCESS", run_id)
        return {
            "upload_status": {
                "ok": True,
                "skipped": True,
                "reason": "Upload disabled in settings"
            },
            "last_failed_node": ""
        }

    # 2. Check if video file exists
    if not video_path or not Path(video_path).exists():
        log.error(f"No video file found to upload at: {video_path}")
        return {
            "upload_status": {
                "ok": False,
                "error": "No video file to upload"
            },
            "last_failed_node": "upload"
        }

    try:
        emit_progress(6, "📤 Uploading to YouTube Studio ...", "INFO", run_id)

        # Get metadata from SEO optimization or fallback to script metadata
        title = state.get("seo_title")
        desc = state.get("seo_description")
        tags = state.get("seo_tags")

        script = state.get("script") or {}
        script_meta = script.get("metadata") or {}

        if not title:
            title = script_meta.get("title", "My Video")
        if not desc:
            desc = script_meta.get("description", "")
        if not tags:
            tags = script_meta.get("tags", [])

        metadata = {
            "title": title,
            "description": desc,
            "tags": tags,
            "thumbnail_path": state.get("thumbnail_path", "")
        }

        # Progress callback for playwright uploader
        def _upload_progress(msg: str) -> None:
            emit_progress(6, msg, "INFO", run_id)

        # Call auto-uploader
        upload_to_youtube(
            video_path=Path(video_path),
            metadata=metadata,
            progress_callback=_upload_progress,
            retries=1
        )

        emit_progress(6, "Upload complete! 🚀", "SUCCESS", run_id)
        
        # We don't have video URL/ID from studio directly unless playwright scraped it,
        # but the uploader logs it. We'll return success.
        return {
            "upload_status": {
                "ok": True,
                "url": "",
                "video_id": ""
            },
            "last_failed_node": ""
        }

    except Exception as exc:
        log.error(f"YouTube upload failed: {exc}", exc_info=True)
        emit_progress(6, f"❌ Upload failed: {exc}", "ERROR", run_id)
        return {
            "upload_status": {
                "ok": False,
                "error": str(exc)
            },
            "last_failed_node": "upload"
        }
