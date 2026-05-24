"""FastAPI pipeline routes + WebSocket progress."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from api.services.progress_broadcaster import ProgressBroadcaster
from api.services.runner_registry import get_runner, next_run_id, set_runner
from core.config_manager import config
from core.pipeline_runner import PipelineRunner

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

_broadcaster = ProgressBroadcaster()


def get_broadcaster() -> ProgressBroadcaster:
    return _broadcaster


class StartBody(BaseModel):
    topic: str | None = None
    run_id: int | None = None


class ScriptApproveBody(BaseModel):
    title: str
    voiceover: str
    image_prompts: list[str]


@router.post("/start")
def pipeline_start(body: StartBody) -> dict:
    existing = get_runner()
    if existing and existing.thread and existing.thread.is_alive():
        existing.stop()
        existing.thread.join(timeout=3.0)
        if existing.thread.is_alive():
            return {
                "ok": False,
                "error": "Previous pipeline still stopping (script generation may be running). Wait a few seconds and try again.",
            }

    run_id = body.run_id if body.run_id is not None else next_run_id()
    runner = PipelineRunner(_broadcaster, run_id=run_id)
    set_runner(runner)
    runner.start(topic=body.topic)
    return {"ok": True, "run_id": run_id}


@router.post("/stop")
def pipeline_stop() -> dict:
    runner = get_runner()
    if runner:
        runner.stop()
        runner.waiting_for_script_review = False
        runner.pending_script_data = None
    return {"ok": True}


@router.post("/retry")
def pipeline_retry() -> dict:
    runner = get_runner()
    if runner:
        runner.request_retry()
    return {"ok": True}


@router.get("/script-review")
def script_review_status() -> dict:
    runner = get_runner()
    if not runner or not runner.waiting_for_script_review:
        return {"waiting": False, "data": None, "run_id": None}
    return {
        "waiting": True,
        "data": runner.pending_script_data,
        "run_id": runner._run_id,
    }


@router.post("/script/approve")
def script_approve(body: ScriptApproveBody) -> dict:
    runner = get_runner()
    if runner:
        runner.approve_script(body.model_dump())
    return {"ok": True}


@router.post("/script/cancel")
def script_cancel() -> dict:
    runner = get_runner()
    if runner:
        runner.cancel_pipeline_from_review()
    return {"ok": True}


@router.websocket("/ws")
async def pipeline_ws(websocket: WebSocket):
    await websocket.accept()
    _broadcaster.add_client(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _broadcaster.remove_client(websocket)
