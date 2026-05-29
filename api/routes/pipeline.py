"""FastAPI pipeline routes + WebSocket progress."""

from __future__ import annotations

import os
import uuid
import logging
import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from api.services.progress_broadcaster import ProgressBroadcaster
from api.services.runner_registry import get_runner, next_run_id, set_runner
from core.config_manager import config
from core.pipeline_runner import PipelineRunner

log = logging.getLogger("pipeline_routes")
router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

_broadcaster = ProgressBroadcaster()


def get_broadcaster() -> ProgressBroadcaster:
    return _broadcaster


# Global states for LangGraph pipeline mode
USE_LANGGRAPH = os.environ.get("GHOST_USE_LANGGRAPH", "1") == "1"
_active_thread_id: str | None = None
_active_run_id: int = 0          # integer run_id sent back to the UI
_active_run_thread: threading.Thread | None = None


class StartBody(BaseModel):
    topic: str | None = None
    run_id: int | None = None
    mode: str = "shorts"                      # shorts | documentary | custom_script
    custom_script: str = ""                   # custom script from user


class ScriptApproveBody(BaseModel):
    title: str
    voiceover: str
    image_prompts: list[str]


def _get_editor_interrupt_payload(graph_state) -> dict | None:
    """Return editor_review_required payload when graph is paused mid editor_prep."""
    tasks = getattr(graph_state, "tasks", None) or ()
    for task in tasks:
        for intr in getattr(task, "interrupts", None) or ():
            val = getattr(intr, "value", intr)
            if isinstance(val, dict) and val.get("event") == "editor_review_required":
                return val
    return None


def _run_graph_in_background(thread_id: str, input_val: Any = None):
    """Invokes or resumes the LangGraph pipeline in a daemon thread."""
    global _active_run_thread

    # Capture the integer run_id at scheduling time so the closure always
    # sends the correct value even if _active_run_id changes later.
    run_id_int = _active_run_id
    
    def target():
        try:
            from graph.pipeline import get_pipeline
            graph = get_pipeline()
            config_dict = {"configurable": {"thread_id": thread_id}}
            log.info(f"Invoking graph in background with input: {input_val} and config: {config_dict}")
            final_state = graph.invoke(input_val, config=config_dict)
            log.info("Background graph execution finished.")
            
            # Check if graph is merely PAUSED at an interrupt (e.g. human_review)
            # rather than truly finished. graph.invoke() returns early on interrupts.
            graph_state = graph.get_state(config_dict)
            if graph_state.next:
                # Graph is paused waiting for user input — do NOT emit done
                paused_at = ", ".join(graph_state.next)
                log.info(f"Graph paused at interrupt: {paused_at}. Waiting for user resume.")
                editor_payload = _get_editor_interrupt_payload(graph_state)
                if editor_payload:
                    _broadcaster.put({
                        "step": 4,
                        "message": "⏸️ Clips ready — open Ghost Editor to review, then continue pipeline.",
                        "level": "INFO",
                        "timestamp": datetime.now().isoformat(),
                        "run_id": run_id_int,
                    })
                else:
                    _broadcaster.put({
                        "step": 2,
                        "message": "⏸️ Script ready for review — waiting for your approval...",
                        "level": "INFO",
                        "timestamp": datetime.now().isoformat(),
                        "run_id": run_id_int,
                    })
                return

            editor_payload = _get_editor_interrupt_payload(graph_state)
            if editor_payload:
                log.info("Graph paused at editor review interrupt.")
                _broadcaster.put({
                    "step": 4,
                    "message": "⏸️ Clips ready — open Ghost Editor to review, then continue pipeline.",
                    "level": "INFO",
                    "timestamp": datetime.now().isoformat(),
                    "run_id": run_id_int,
                })
                return
            
            # Graph truly finished — emit done
            video_path = (final_state or {}).get("video_path", "") if isinstance(final_state, dict) else ""
            _broadcaster.put({
                "step": 6,
                "message": f"✅ Pipeline complete! {('Video saved: ' + video_path) if video_path else 'Done.'}",
                "level": "SUCCESS",
                "timestamp": datetime.now().isoformat(),
                "run_id": run_id_int,
                "done": True,
                "output_path": video_path,
            })
        except Exception as e:
            log.error(f"Error in background LangGraph runner: {e}", exc_info=True)
            _broadcaster.put({
                "step": 9,
                "message": f"❌ [Graph Run Error] {e}",
                "level": "ERROR",
                "timestamp": datetime.now().isoformat(),
                "run_id": run_id_int,
                "done": True,
            })
            
    _active_run_thread = threading.Thread(target=target, daemon=True)
    _active_run_thread.start()



@router.post("/start")
def pipeline_start(body: StartBody) -> dict:
    global _active_thread_id, _active_run_id
    
    from graph.state import default_state
    
    # Stop existing run if any
    _active_thread_id = None
    
    # Clear progress buffer for new run
    _broadcaster.clear_buffer()
    
    run_id_val = body.run_id if body.run_id is not None else next_run_id()
    # Use UUID suffix to guarantee a fresh checkpoint every run.
    # Reusing the same thread_id (e.g. "run_1") would cause LangGraph to resume
    # the old checkpoint and inherit accumulated `errors` from previous failed runs.
    thread_id = f"run_{run_id_val}_{uuid.uuid4().hex[:8]}"
    _active_thread_id = thread_id
    _active_run_id = run_id_val      # store integer so WS messages carry the right id
    
    # Build base directory for the run
    from core.pipeline_runner import _make_run_dir, OUTPUT_DIR
    title_hint = body.topic or "custom_script"
    run_dir = _make_run_dir(title_hint, config, OUTPUT_DIR)
    
    # Initialize state
    initial_state = default_state()
    initial_state.update({
        "mode": body.mode,
        "topic": body.topic or "",
        "user_custom_script": body.custom_script,
        "run_id": thread_id,
        "run_dir": str(run_dir),
        "language": config.get("pipeline.language", "hinglish"),
    })
    
    # Run graph in background thread
    _run_graph_in_background(thread_id, initial_state)
    
    return {"ok": True, "run_id": run_id_val}


@router.post("/stop")
def pipeline_stop() -> dict:
    global _active_thread_id
    _active_thread_id = None
    return {"ok": True}


@router.post("/retry")
def pipeline_retry() -> dict:
    if not _active_thread_id:
        return {"ok": False, "error": "No active LangGraph run to retry."}
        
    from graph.pipeline import get_pipeline
    config_dict = {"configurable": {"thread_id": _active_thread_id}}
    graph = get_pipeline()
    state = graph.get_state(config_dict)
    
    failed_node = state.values.get("last_failed_node", "")
    if failed_node:
        # Reset retry count for failed node so it doesn't abort
        retry_counts = state.values.get("retry_counts", {}).copy()
        if failed_node in retry_counts:
            retry_counts[failed_node] = 0
        
        # Clear errors and set failed node to empty so it goes back
        graph.update_state(config_dict, {
            "retry_counts": retry_counts,
            "last_failed_node": "",
            "errors": []
        })
        
    # Re-invoke graph from checkpoint
    _run_graph_in_background(_active_thread_id, None)
    return {"ok": True}


@router.get("/script-review")
def script_review_status() -> dict:
    if not _active_thread_id:
        return {"waiting": False, "data": None, "run_id": None}
        
    from graph.pipeline import get_pipeline
    config_dict = {"configurable": {"thread_id": _active_thread_id}}
    graph = get_pipeline()
    state = graph.get_state(config_dict)
    
    # Check if the graph is paused before human_review
    if "human_review" in state.next:
        script_val = state.values.get("script", {})
        # Format to the shape expected by Electron React frontend
        data = {
            "title": script_val.get("metadata", {}).get("title", "") or script_val.get("title", ""),
            "voiceover": script_val.get("voiceover_text", ""),
            "image_prompts": [
                p.get("prompt", "") if isinstance(p, dict) else p
                for p in script_val.get("image_prompts", [])
            ]
        }
        return {
            "waiting": True,
            "data": data,
            "run_id": _active_run_id,
        }
        
    return {"waiting": False, "data": None, "run_id": None}


@router.post("/script/approve")
def script_approve(body: ScriptApproveBody) -> dict:
    if not _active_thread_id:
        return {"ok": False, "error": "No active LangGraph run."}
        
    from graph.pipeline import get_pipeline
    from langgraph.types import Command
    
    config_dict = {"configurable": {"thread_id": _active_thread_id}}
    graph = get_pipeline()
    state = graph.get_state(config_dict)
    
    script_val = state.values.get("script", {}).copy()
    
    # Format the edited script fields to restore back to the state schema
    edited_script = {
        "voiceover_text": body.voiceover,
        "metadata": {
            "title": body.title,
            "description": script_val.get("metadata", {}).get("description", ""),
            "tags": script_val.get("metadata", {}).get("tags", [])
        }
    }
    
    if state.values.get("mode") == "documentary":
        segments = script_val.get("segments", []).copy()
        for i, p in enumerate(body.image_prompts):
            if i < len(segments):
                segments[i] = {**segments[i], "video_query": p}
        edited_script["segments"] = segments
        edited_script["image_prompts"] = [{"prompt": p, "scene_index": i} for i, p in enumerate(body.image_prompts)]
    else:
        edited_script["image_prompts"] = [{"prompt": p, "scene_index": i} for i, p in enumerate(body.image_prompts)]
        
    # Send decision payload to resume interrupt
    decision = {
        "action": "edited",
        "feedback": "Approved by user",
        "edited_script": edited_script
    }
    
    # Resume graph with decision
    _run_graph_in_background(_active_thread_id, Command(resume=decision))
    return {"ok": True}


@router.post("/script/cancel")
def script_cancel() -> dict:
    if not _active_thread_id:
        return {"ok": False, "error": "No active LangGraph run."}
        
    from graph.pipeline import get_pipeline
    from langgraph.types import Command
    
    config_dict = {"configurable": {"thread_id": _active_thread_id}}
    graph = get_pipeline()
    state = graph.get_state(config_dict)
    
    # Set attempts to max_attempts so that route_after_review goes to END
    max_attempts = state.values.get("max_script_attempts", 3)
    graph.update_state(config_dict, {
        "script_attempts": max_attempts,
        "review_decision": "rejected"
    })
    
    # Resume and route to END
    decision = {
        "action": "rejected",
        "feedback": "Cancelled by user"
    }
    _run_graph_in_background(_active_thread_id, Command(resume=decision))
    return {"ok": True}


@router.get("/editor-review")
def editor_review_status() -> dict:
    if not _active_thread_id:
        return {"waiting": False, "data": None, "run_id": None}

    from graph.pipeline import get_pipeline

    config_dict = {"configurable": {"thread_id": _active_thread_id}}
    graph = get_pipeline()
    state = graph.get_state(config_dict)

    payload = _get_editor_interrupt_payload(state)
    if payload:
        return {
            "waiting": True,
            "data": {
                "run_dir": payload.get("run_dir", state.values.get("run_dir", "")),
                "title": payload.get("title", ""),
                "segment_count": payload.get("segment_count", 0),
            },
            "run_id": _active_run_id,
        }

    return {"waiting": False, "data": None, "run_id": None}


@router.post("/editor/continue")
def editor_continue() -> dict:
    if not _active_thread_id:
        return {"ok": False, "error": "No active LangGraph run."}

    from langgraph.types import Command

    _run_graph_in_background(_active_thread_id, Command(resume={"action": "continue"}))
    return {"ok": True}


@router.post("/editor/cancel")
def editor_cancel() -> dict:
    if not _active_thread_id:
        return {"ok": False, "error": "No active LangGraph run."}

    from langgraph.types import Command

    _run_graph_in_background(_active_thread_id, Command(resume={"action": "cancelled"}))
    return {"ok": True}


@router.get("/progress")
def pipeline_progress(after: int = 0) -> dict:
    """HTTP endpoint to poll for pipeline progress events when WebSocket fails."""
    msgs, latest = _broadcaster.get_messages_since(after)
    return {
        "messages": msgs,
        "latest_seq": latest
    }


@router.websocket("/ws")
async def pipeline_ws(websocket: WebSocket):
    await websocket.accept()
    _broadcaster.add_client(websocket)
    log.info("WebSocket client connected. Total clients: %d", len(_broadcaster._clients))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _broadcaster.remove_client(websocket)
        log.info("WebSocket client disconnected. Total clients: %d", len(_broadcaster._clients))

