"""
graph/state.py — LangGraph TypedDict State
========================================
Defines the central state structure for Ghost Creator AI.
"""

from typing import TypedDict, Annotated, Literal
import operator

# Define mode type
PipelineMode = Literal["shorts", "documentary", "custom_script"]

class GhostCreatorState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────
    mode: PipelineMode
    topic: str                          # user-provided or auto-discovered
    user_custom_script: str             # raw text the user typed themselves
    language: str                       # "hi" / "hinglish" / "en" etc.
    run_id: str
    run_dir: str                        # absolute path to per-run output folder

    # ── Research ───────────────────────────────────────────────────
    research_summary: str               # multi-source research paragraph
    trending_score: float               # 0.0–1.0 virality estimate
    research_sources: list[str]         # URLs / feed names used

    # ── Script ─────────────────────────────────────────────────────
    script: dict                        # {"voiceover_text", "image_prompts", "metadata": {title, description, tags}}
    script_version: int                 # increments on each regeneration
    script_attempts: int                # total generation attempts
    max_script_attempts: int            # configurable limit (default 3)

    # ── Script Quality ─────────────────────────────────────────────
    script_quality_score: float         # 0.0–10.0 from script_critic_node
    script_quality_feedback: str        # critic's detailed feedback
    script_auto_approved: bool          # True if score >= threshold and skip_review=True

    # ── Human Review ───────────────────────────────────────────────
    review_decision: Literal["approved", "rejected", "pending"]
    review_feedback: str                # user typed feedback when rejecting

    # ── Parallel Generation ────────────────────────────────────────
    image_paths: Annotated[list[str], operator.add]   # parallel workers append here
    audio_path: str
    thumbnail_path: str

    # ── SEO ────────────────────────────────────────────────────────
    seo_title: str
    seo_description: str
    seo_tags: list[str]
    seo_optimized: bool

    # ── Assembly & Upload ──────────────────────────────────────────
    video_path: str
    upload_status: dict                 # {"ok", "url", "video_id", "error"}

    # ── Agentic Error Recovery ─────────────────────────────────────
    errors: Annotated[list[str], operator.add]
    retry_counts: dict[str, int]        # node_name → retry count
    last_failed_node: str

    # ── Analytics Feedback (from previous runs) ────────────────────
    past_performance_hint: str          # summary injected from yt_analytics


def default_state() -> GhostCreatorState:
    """Return a state dictionary with sensible defaults."""
    return {
        "mode": "shorts",
        "topic": "",
        "user_custom_script": "",
        "language": "hi",
        "run_id": "",
        "run_dir": "",
        "research_summary": "",
        "trending_score": 0.0,
        "research_sources": [],
        "script": {},
        "script_version": 0,
        "script_attempts": 0,
        "max_script_attempts": 3,
        "script_quality_score": 0.0,
        "script_quality_feedback": "",
        "script_auto_approved": False,
        "review_decision": "pending",
        "review_feedback": "",
        "image_paths": [],
        "audio_path": "",
        "thumbnail_path": "",
        "seo_title": "",
        "seo_description": "",
        "seo_tags": [],
        "seo_optimized": False,
        "video_path": "",
        "upload_status": {},
        "errors": [],
        "retry_counts": {},
        "last_failed_node": "",
        "past_performance_hint": "",
    }


def merge_state(base: dict, updates: dict) -> dict:
    """Shallow-merge updates into base dict, handling lists correctly."""
    result = base.copy()
    for k, v in updates.items():
        if k in ("image_paths", "errors") and k in result:
            # Annotated operator.add logic
            result[k] = result[k] + v
        else:
            result[k] = v
    return result
