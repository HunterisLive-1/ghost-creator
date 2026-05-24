"""History list + re-render routes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, File, UploadFile
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


class SaveEditorBody(BaseModel):
    run_dir: str
    data: dict


@router.get("/load-editor")
def load_editor(run_dir: str) -> dict:
    from fastapi import HTTPException
    p = Path(run_dir) / "documentary_editor.json"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="documentary_editor.json not found in run directory")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/save-editor")
def save_editor(body: SaveEditorBody) -> dict:
    from fastapi import HTTPException
    run_dir = Path(body.run_dir)
    p = run_dir / "documentary_editor.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(body.data, f, indent=2, ensure_ascii=False)
        
        # Sync title back to metadata.json if present
        title = body.data.get("title")
        if title:
            meta_path = run_dir / "metadata.json"
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    meta["title"] = title
                    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass
            hist_path = run_dir / "history_entry.json"
            if hist_path.is_file():
                try:
                    hist = json.loads(hist_path.read_text(encoding="utf-8"))
                    hist["title"] = title
                    hist_path.write_text(json.dumps(hist, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass
                    
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/list-clips")
def list_clips(run_dir: str) -> dict:
    run_path = Path(run_dir)
    clips = []
    
    # Check clips_for_edit, clips, and root run folder
    folders_to_check = [
        ("clips_for_edit", run_path / "clips_for_edit"),
        ("clips", run_path / "clips"),
        ("root", run_path)
    ]
    
    seen_names = set()
    for category, folder in folders_to_check:
        if folder.is_dir():
            for f in folder.glob("*.mp4"):
                # Avoid duplicate names from different folders
                if f.name in seen_names or "documentary" in f.name:
                    continue
                seen_names.add(f.name)
                clips.append({
                    "name": f.name,
                    "path": str(f.resolve()),
                    "category": category,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2)
                })
                
    return {"clips": clips}


@router.post("/upload-audio")
async def upload_audio(
    run_dir: str = Form(...),
    file: UploadFile = File(...)
) -> dict:
    from fastapi import HTTPException
    p = Path(run_dir)
    if not p.is_dir():
        raise HTTPException(status_code=404, detail="Run directory not found")
    out_path = p / file.filename
    try:
        content = await file.read()
        out_path.write_bytes(content)
        return {
            "ok": True,
            "filename": file.filename,
            "path": str(out_path.resolve())
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/upload-clip")
async def upload_clip(
    run_dir: str = Form(...),
    file: UploadFile = File(...)
) -> dict:
    from fastapi import HTTPException
    p = Path(run_dir)
    if not p.is_dir():
        raise HTTPException(status_code=404, detail="Run directory not found")
    
    cfe_dir = p / "clips_for_edit"
    cfe_dir.mkdir(parents=True, exist_ok=True)
    out_path = cfe_dir / file.filename
    try:
        content = await file.read()
        out_path.write_bytes(content)
        return {
            "ok": True,
            "filename": file.filename,
            "path": str(out_path.resolve())
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stock-assets")
def get_stock_assets() -> dict:
    music_dir = Path("assets/stock/music")
    sfx_dir = Path("assets/stock/sfx")
    
    music = []
    if music_dir.is_dir():
        for f in music_dir.glob("*.mp3"):
            music.append({
                "name": f.stem.replace("_", " ").title(),
                "filename": f.name,
                "path": str(f.resolve())
            })
            
    sfx = []
    if sfx_dir.is_dir():
        for f in sfx_dir.glob("*.mp3"):
            sfx.append({
                "name": f.stem.replace("_", " ").title(),
                "filename": f.name,
                "path": str(f.resolve())
            })
            
    return {"music": music, "sfx": sfx}

