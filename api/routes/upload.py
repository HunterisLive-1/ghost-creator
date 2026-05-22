"""YouTube upload routes."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from api.services.job_manager import job_manager
from core.config_manager import config
from modules.uploader import upload_to_youtube

router = APIRouter(prefix="/api/upload", tags=["upload"])


class UploadBody(BaseModel):
    video_path: str
    title: str
    description: str
    tags: str
    visibility: str


class AiFillBody(BaseModel):
    video_path: str


@router.post("/start")
def upload_start(body: UploadBody) -> dict:
    video = Path(body.video_path)
    if not video.is_file():
        return {"ok": False, "error": "Video file not found", "job_id": ""}

    def run(log) -> None:
        log(f"Starting upload: {video.name}", "INFO")

        def cb(msg: str) -> None:
            log(msg, "INFO")

        tags = [t.strip() for t in body.tags.split(",") if t.strip()]
        meta = {
            "title": body.title.strip()[:100],
            "description": body.description.strip(),
            "tags": tags,
        }
        config.set("pipeline.upload_mode", body.visibility.lower())
        config.save()
        try:
            upload_to_youtube(video, meta, progress_callback=cb)
            log("✅ Upload complete!", "SUCCESS", done=True)
        except Exception as exc:
            log(f"❌ Upload failed: {exc}", "ERROR", done=True)

    job_id = job_manager.create(run)
    return {"job_id": job_id}


@router.get("/job/{job_id}")
def upload_job_logs(job_id: str, offset: int = 0) -> dict:
    logs, done = job_manager.get_logs_since(job_id, offset)
    return {"logs": logs, "done": done}


@router.post("/ai-fill")
def upload_ai_fill(body: AiFillBody) -> dict:
    import google.generativeai as genai

    key = config.get("api_keys.gemini", "")
    if not key:
        return {"title": "", "description": "", "tags": "", "error": "Gemini API key missing"}

    genai.configure(api_key=key)
    model_name = config.get("gemini_model", "gemini-2.0-flash")
    model = genai.GenerativeModel(model_name)

    stem = Path(body.video_path).stem.replace("_", " ").replace("-", " ")
    prompt = (
        f"Generate YouTube metadata for a video file named '{stem}'. "
        "Return JSON with keys: title (max 100 chars), description (2-3 paragraphs), "
        "tags (comma-separated, max 500 chars total)."
    )
    resp = model.generate_content(prompt)
    text = resp.text or ""
    import json
    import re

    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        data = json.loads(m.group())
        return {
            "title": data.get("title", stem),
            "description": data.get("description", ""),
            "tags": data.get("tags", ""),
        }
    return {"title": stem, "description": text[:500], "tags": ""}
