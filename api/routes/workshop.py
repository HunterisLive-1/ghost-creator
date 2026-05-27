"""Workshop chat + error analyst routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core.config_manager import config
from modules.error_analyst import analyse_error
from modules.scripter import chat_with_consultant, parse_plan_block

router = APIRouter(tags=["workshop"])


class ChatMessage(BaseModel):
    role: str
    content: str


class WorkshopChatBody(BaseModel):
    message: str
    history: list[ChatMessage]


class ErrorAnalyseBody(BaseModel):
    error_message: str


@router.post("/api/workshop/chat")
def workshop_chat(body: WorkshopChatBody) -> dict:
    cfg = {
        "api_keys.gemini": config.get("api_keys.gemini", ""),
        "gemini_model": config.get("gemini_model") or config.get("pipeline.gemini_model") or "gemini-3.1-flash-lite",
    }
    history = [{"role": m.role, "content": m.content} for m in body.history[-30:]]
    reply = chat_with_consultant(history, body.message, cfg)
    plan = parse_plan_block(reply)
    visible = reply
    if plan:
        import re
        visible = re.sub(r"<<PLAN_START>>.*?<<PLAN_END>>", "", reply, flags=re.DOTALL).strip()
    return {"reply": visible, "plan": plan}


@router.post("/api/error/analyse")
def error_analyse(body: ErrorAnalyseBody) -> dict:
    cfg = {
        "api_keys.gemini": config.get("api_keys.gemini", ""),
        "gemini_model": config.get("gemini_model") or config.get("pipeline.gemini_model") or "gemini-3.1-flash-lite",
    }
    analysis = analyse_error(body.error_message, script_config=cfg)
    return {"analysis": analysis}
