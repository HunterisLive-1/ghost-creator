"""
graph/nodes/human_review_node.py — Human Review Node
===================================================
Suspends execution using LangGraph native interrupt() for human review of scripts.
"""

import json
import logging
from typing import Literal
from langgraph.types import interrupt
from langgraph.graph import END
from graph.state import GhostCreatorState

log = logging.getLogger("human_review")

def human_review_node(state: GhostCreatorState) -> dict:
    """Suspends the graph for human review unless auto-approved or already approved."""
    decision = state.get("review_decision", "pending")
    auto_approved = state.get("script_auto_approved", False)
    run_id = state.get("run_id", "")

    from graph.nodes.research_node import emit_progress

    if decision == "approved" or auto_approved:
        log.info("Script already approved or auto-approved. Skipping human review node.")
        emit_progress(2, "⏭️ Script approved/auto-approved. Skipping human review.", "INFO", run_id)
        return {"review_decision": "approved"}

    quality_feedback = {}
    qf_str = state.get("script_quality_feedback", "")
    if qf_str:
        try:
            quality_feedback = json.loads(qf_str)
        except Exception:
            quality_feedback = {"raw": qf_str}

    # Suspend execution here
    log.info("Suspending graph execution for human script review...")
    emit_progress(2, "⏸️ Script is ready! Waiting for human review/approval...", "INFO", run_id)
    user_decision = interrupt({
        "event": "script_review_required",
        "run_id": state.get("run_id", ""),
        "script": state.get("script", {}),
        "quality_score": state.get("script_quality_score", 0.0),
        "quality_feedback": quality_feedback,
        "script_version": state.get("script_version", 1),
        "script_attempts": state.get("script_attempts", 1),
        "max_attempts": state.get("max_script_attempts", 3),
        "message": "Script ready for your review. Approve, reject with feedback, or edit directly."
    })

    # Handle the response when resumed
    # Expected shape of user_decision: 
    # {"action": "approved"|"rejected"|"edited", "feedback": str, "edited_script": dict|None}
    log.info(f"Resuming execution. User action: {user_decision.get('action')}")
    action = user_decision.get("action", "approved")
    emit_progress(2, f"✅ Human review action: {action}", "INFO", run_id)

    if action == "approved":
        return {
            "review_decision": "approved",
            "review_feedback": "",
            "last_failed_node": ""
        }
    elif action == "edited":
        edited = user_decision.get("edited_script", {})
        original_script = state.get("script") or {}
        new_script = {**original_script, **edited}
        return {
            "review_decision": "approved",
            "script": new_script,
            "review_feedback": "User edited directly",
            "last_failed_node": ""
        }
    elif action == "rejected":
        feedback = user_decision.get("feedback", "No feedback provided")
        return {
            "review_decision": "rejected",
            "review_feedback": feedback,
            "last_failed_node": ""
        }

    return {"review_decision": "approved"}


def route_after_review(state: GhostCreatorState) -> str:
    """Determines where the graph flows after the human review step."""
    decision = state.get("review_decision", "pending")
    attempts = state.get("script_attempts", 0)
    max_attempts = state.get("max_script_attempts", 3)

    if decision == "approved":
        return "parallel_generation"
    
    if decision == "rejected":
        if attempts < max_attempts:
            log.info(f"Script rejected. Attempt {attempts}/{max_attempts}. Routing back to script generator node.")
            return "script_node"
        else:
            log.warning(f"Script rejected. Maximum attempts ({max_attempts}) reached. Stopping pipeline.")
            return END
            
    return END
