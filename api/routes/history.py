"""History list + re-render routes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from api.services.job_manager import job_manager
from core.config_manager import config
from api.services.history_rerender import rerender_run

router = APIRouter(prefix="/api/history", tags=["history"])


class RerenderBody(BaseModel):
    run_dir: str


def _resolve_output_base() -> Path:
    folder = config.get("pipeline.output_folder", "output").strip()
    base = Path(folder)
    if not base.is_absolute():
        base = config.path.parent / folder
    return base


@router.get("")
def list_history() -> dict:
    config.load()
    base = _resolve_output_base()
    entries = []
    if not base.is_dir():
        return {"entries": []}

    run_dirs = sorted(
        [p for p in base.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:10]

    for run_dir in run_dirs:
        meta_path = run_dir / "metadata.json"
        if not meta_path.is_file():
            continue
        meta: dict = {}
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        hist_file = run_dir / "history_entry.json"
        hist: dict = {}
        if hist_file.is_file():
            try:
                hist = json.loads(hist_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        video_path = meta.get("video_path", "")
        if not video_path:
            for mp4 in run_dir.glob("*.mp4"):
                video_path = str(mp4)
                break

        ts = hist.get("timestamp") or meta.get("timestamp", "")
        if not ts:
            ts = datetime.fromtimestamp(run_dir.stat().st_mtime).isoformat()

        editor_json = run_dir / "documentary_editor.json"

        entries.append({
            "run_dir": str(run_dir),
            "title": meta.get("title") or hist.get("title", run_dir.name),
            "topic": hist.get("topic", ""),
            "timestamp": ts,
            "description": meta.get("description", ""),
            "tags": meta.get("tags", ""),
            "video_path": video_path or hist.get("video_path", ""),
            "duration": hist.get("duration", ""),
            "can_rerender": editor_json.is_file(),
        })

    return {"entries": entries}


@router.post("/rerender")
def history_rerender(body: RerenderBody) -> dict:
    run_dir = Path(body.run_dir)

    def run(log) -> None:
        log(f"Re-rendering from {run_dir.name}…", "INFO")
        try:
            out = rerender_run(run_dir, lambda m: log(m, "INFO"))
            log(f"✅ Re-render complete: {out}", "SUCCESS", done=True, result={"video_path": str(out)})
        except Exception as exc:
            log(f"❌ Re-render failed: {exc}", "ERROR", done=True)

    job_id = job_manager.create(run)
    return {"job_id": job_id}


@router.get("/job/{job_id}")
def history_job_logs(job_id: str, offset: int = 0) -> dict:
    logs, done = job_manager.get_logs_since(job_id, offset)
    return {"logs": logs, "done": done}
