"""
graph/nodes/editor_prep_node.py — Editor Prep Node
==================================================
Fetches clips, syncs to voiceover, writes editor JSON. Pauses for Ghost Editor when configured.
"""

import logging

from langgraph.types import interrupt

from core.config_manager import config
from graph.nodes.clip_prep import prepare_footage_clips
from graph.nodes.assemble_node import emit_progress
from graph.state import GhostCreatorState

log = logging.getLogger("editor_prep")


def editor_prep_node(state: GhostCreatorState) -> dict:
    """Prepare synced edit clips; optionally interrupt for in-app editor review."""
    from pathlib import Path

    mode = state.get("mode", "shorts")
    script = state.get("script") or {}
    audio_path = state.get("audio_path", "")
    run_dir_str = state.get("run_dir", "")
    run_id = state.get("run_id", "")

    if not run_dir_str:
        return {}

    run_dir = Path(run_dir_str)
    language = state.get("language") or config.get("pipeline.language", "hi")

    try:
        result = prepare_footage_clips(
            run_dir,
            script=script,
            audio_path=audio_path,
            run_id=run_id,
            language=language,
            mode=mode,
            skip_if_ready=False,
        )
        if result is None:
            return {}

        _, _, edit_paths = result
        segments = script.get("segments", [])
        meta = script.get("metadata") or {}
        title = meta.get("title") or script.get("title") or run_dir.name

        if config.get("pipeline_mode") == "editor":
            log.info("Suspending pipeline for Ghost Editor review...")
            emit_progress(
                4,
                "⏸️ Clips ready — open Ghost Editor to review, then continue pipeline.",
                "INFO",
                run_id,
            )
            user_decision = interrupt({
                "event": "editor_review_required",
                "run_dir": str(run_dir.resolve()),
                "title": title,
                "segment_count": len(segments),
                "message": "Synced clips are ready. Edit in Ghost Editor, save, then continue.",
            })

            action = (user_decision or {}).get("action", "continue")
            if action == "cancelled":
                return {
                    "errors": ["Editor review cancelled by user"],
                    "last_failed_node": "editor_prep",
                    "video_path": "",
                }
            emit_progress(4, "▶️ Resuming pipeline after editor review …", "INFO", run_id)

        log.info("Editor prep complete (%d clips)", len(edit_paths))
        return {"last_failed_node": ""}

    except Exception as exc:
        log.error("Editor prep failed: %s", exc, exc_info=True)
        return {
            "errors": [f"Editor prep failed: {exc}"],
            "last_failed_node": "editor_prep",
        }
