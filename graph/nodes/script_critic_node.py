"""
graph/nodes/script_critic_node.py — Script Critic Agent Node
===========================================================
Autonomously evaluates script quality before showing to the user.
"""

import json
from typing import Literal
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from core.config_manager import config
from graph.state import GhostCreatorState
from config import get_logger

log = get_logger("critic")

class CriticOutput(BaseModel):
    hook_score: float = Field(ge=0, le=10, description="First 3 seconds hook strength")
    retention_score: float = Field(ge=0, le=10, description="Will viewers watch till end?")
    emotion_score: float = Field(ge=0, le=10, description="Emotional impact / surprise / curiosity")
    clarity_score: float = Field(ge=0, le=10, description="Are the facts clear and accurate?")
    tts_friendliness: float = Field(ge=0, le=10, description="Is it good for TTS? No symbols, good pacing?")
    overall_score: float = Field(ge=0, le=10, description="Weighted average")
    strengths: list[str] = Field(description="Top 3 things done well")
    weaknesses: list[str] = Field(description="Top 3 things to improve")
    rewrite_suggestion: str = Field(description="One specific rewrite for the opening hook if needed")
    verdict: Literal["excellent", "good", "needs_work", "reject"]

def script_critic_node(state: GhostCreatorState) -> dict:
    """Evaluates the quality of the generated or polished script."""
    script = state.get("script") or {}
    voiceover_text = script.get("voiceover_text", "").strip()
    run_id = state.get("run_id", "")

    from graph.nodes.research_node import emit_progress

    if not script or not voiceover_text:
        log.warning("Empty script passed to critic. Skipping evaluation.")
        return {
            "script_quality_score": 0.0,
            "script_quality_feedback": "Empty script",
            "script_auto_approved": False,
            "review_decision": "pending",
            "last_failed_node": ""
        }

    try:
        emit_progress(2, "🧠 AI Critic analyzing script quality...", "INFO", run_id)
        gemini_key = config.get("api_keys.gemini", "")
        if not gemini_key:
            raise ValueError("Missing Gemini API Key in configuration.")

        model_name = config.get("gemini_model") or config.get("pipeline.gemini_model") or "gemini-3.1-flash-lite"
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=gemini_key,
            temperature=0.2
        )

        language = state.get("language", "hi")
        script_source = script.get("_source", "ai_generated")
        topic = state.get("topic", "")

        critic_prompt = f"""You are a ruthless YouTube Shorts script critic with 10 years of viral content experience.
Evaluate this script as if your job depends on it getting 100K+ views.

Script language: {language}
Script source: {script_source}
Topic: {topic}

SCRIPT:
---
{voiceover_text}
---

Score each dimension from 0-10. Be harsh. A 7 is average.
Viral shorts need hook_score >= 8, emotion_score >= 7.
"""

        log.info("Critic analyzing script...")
        structured_llm = llm.with_structured_output(CriticOutput)
        critic = structured_llm.invoke(critic_prompt)

        # Log details
        log.info(f"=== Critic Verdict: {critic.verdict.upper()} ===")
        log.info(f"Overall Score: {critic.overall_score}/10 (Hook: {critic.hook_score}, Retention: {critic.retention_score}, Emotion: {critic.emotion_score})")
        log.info(f"Strengths: {', '.join(critic.strengths)}")
        log.info(f"Weaknesses: {', '.join(critic.weaknesses)}")
        if critic.rewrite_suggestion:
            log.info(f"Hook Suggestion: {critic.rewrite_suggestion}")

        emit_progress(2, f"📋 Critic overall score: {critic.overall_score}/10 (Verdict: {critic.verdict})", "INFO", run_id)

        # Auto approval logic
        auto_approve_threshold = float(config.get("pipeline.auto_approve_threshold", 8.0))
        skip_human_review = bool(config.get("pipeline.skip_human_review", False))
        auto_approved = skip_human_review and (critic.overall_score >= auto_approve_threshold)

        feedback_data = {
            "scores": {
                "hook_score": critic.hook_score,
                "retention_score": critic.retention_score,
                "emotion_score": critic.emotion_score,
                "clarity_score": critic.clarity_score,
                "tts_friendliness": critic.tts_friendliness
            },
            "strengths": critic.strengths,
            "weaknesses": critic.weaknesses,
            "rewrite_suggestion": critic.rewrite_suggestion,
            "verdict": critic.verdict
        }

        return {
            "script_quality_score": critic.overall_score,
            "script_quality_feedback": json.dumps(feedback_data),
            "script_auto_approved": auto_approved,
            "review_decision": "approved" if auto_approved else "pending",
            "last_failed_node": ""
        }

    except Exception as exc:
        log.error(f"Script Critic failed: {exc}", exc_info=True)
        emit_progress(2, f"⚠️ Script Critic failed: {exc}", "WARNING", run_id)
        return {
            "errors": [f"Critic Node error: {exc}"],
            "script_quality_score": 0.0,
            "script_quality_feedback": f"Critic failure: {exc}",
            "script_auto_approved": False,
            "review_decision": "pending",
            "last_failed_node": "script_critic"
        }
