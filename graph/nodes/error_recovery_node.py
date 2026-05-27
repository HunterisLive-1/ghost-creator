"""
graph/nodes/error_recovery_node.py — Self-Healing Error Recovery Agent
=====================================================================
Analyzes errors using Gemini and determines recovery plans (retry, fallback, skip, abort).
"""

import logging
import datetime
from typing import Literal
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from core.config_manager import config
from api.routes.pipeline import get_broadcaster
from graph.state import GhostCreatorState

log = logging.getLogger("error_recovery_node")

class RecoveryPlan(BaseModel):
    is_recoverable: bool = Field(description="True if the pipeline can continue by retrying, using fallback, or skipping.")
    recovery_action: Literal["retry", "fallback", "skip", "abort"] = Field(description="Action to take: retry, fallback (alternative path), skip (omit step), or abort.")
    fallback_instruction: str = Field(description="Instruction for the next node/step if using fallback (e.g. use edge-tts, use stock video).")
    user_message: str = Field(description="Compelling, user-friendly status update explaining the issue and how the agent is recovering.")

def error_recovery_node(state: GhostCreatorState) -> dict:
    """LangGraph node that assesses errors and updates state with retry or fallback settings."""
    errors = state.get("errors", [])
    if not errors:
        return {"recovery_action": "skip", "last_failed_node": ""}

    last_error = errors[-1]
    failed_node = state.get("last_failed_node", "unknown")
    retry_counts = state.get("retry_counts", {}).copy()
    current_retry = retry_counts.get(failed_node, 0)

    log.info(f"Error recovery triggered. Failed node: {failed_node}. Current retry count: {current_retry}. Error: {last_error}")

    # Build prompt
    prompt = f"""
    You are the Ghost Creator AI error recovery agent.
    A pipeline step failed. Decide if it can be recovered automatically.

    Failed node: {failed_node}
    Error: {last_error}
    Current retry count for this node: {current_retry}
    Max retries allowed: 2

    Recovery options:
    - retry: try the same node again (good for network errors, rate limits, temporary API timeout)
    - fallback: use a simpler alternative (e.g., if Imagen fails, use a placeholder image or solid color/stock footage; if high-end TTS fails, fallback to basic Edge TTS)
    - skip: skip this optional step and continue (e.g. YouTube upload fails, skip it as the video is still created locally)
    - abort: this is unrecoverable, stop the pipeline (e.g. FFmpeg assembly fails, script writing fails repeatedly)

    Common recoveries:
    - Image generation API error -> fallback (use stock image or solid color frame)
    - TTS network error -> retry (up to 2x), then fallback to edge-tts
    - Research/web search error -> fallback (use basic pytrends)
    - Assembly FFmpeg error -> abort (critical step)
    - Upload error -> skip (video is still made, just not uploaded)
    """

    gemini_key = config.get("api_keys.gemini", "")
    if not gemini_key:
        log.warning("No Gemini API key for error recovery. Aborting.")
        plan = RecoveryPlan(
            is_recoverable=False,
            recovery_action="abort",
            fallback_instruction="",
            user_message=f"Critical error in {failed_node}: {last_error}. Missing Gemini API key for recovery."
        )
    else:
        try:
            model_name = config.get("gemini_model") or config.get("pipeline.gemini_model") or "gemini-3.1-flash-lite"
            llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=gemini_key, temperature=0.2)
            structured_llm = llm.with_structured_output(RecoveryPlan)
            plan = structured_llm.invoke(prompt)
        except Exception as exc:
            log.error(f"Failed to query recovery agent: {exc}", exc_info=True)
            # Default fallback logic
            if failed_node in ("research", "seo"):
                plan = RecoveryPlan(is_recoverable=True, recovery_action="fallback", fallback_instruction="Use fallback research/SEO", user_message="Web search or SEO failed; falling back to default topic/metadata.")
            elif failed_node in ("image_worker", "voiceover_worker") and current_retry < 2:
                plan = RecoveryPlan(is_recoverable=True, recovery_action="retry", fallback_instruction="", user_message=f"Retrying asset generation for {failed_node}...")
            elif failed_node == "upload":
                plan = RecoveryPlan(is_recoverable=True, recovery_action="skip", fallback_instruction="", user_message="YouTube upload failed, skipping. Video is saved locally.")
            else:
                plan = RecoveryPlan(is_recoverable=False, recovery_action="abort", fallback_instruction="", user_message=f"Unrecoverable error in {failed_node}: {last_error}")

    # Broadcast recovery plan message
    broadcaster = get_broadcaster()
    if broadcaster:
        broadcaster.put({
            "step": 9,
            "message": f"🔧 [Error Recovery] {plan.user_message}",
            "level": "WARNING" if plan.is_recoverable else "ERROR",
            "timestamp": datetime.datetime.now().isoformat(),
            "run_id": state.get("run_id", ""),
            "retry_available": plan.recovery_action == "retry",
        })

    # Prepare state updates
    updates = {
        "recovery_action": plan.recovery_action,
        "fallback_instruction": plan.fallback_instruction,
        "last_failed_node": failed_node if plan.recovery_action == "retry" else "",
    }

    if plan.recovery_action == "retry":
        retry_counts[failed_node] = current_retry + 1
        updates["retry_counts"] = retry_counts

    return updates
