"""
graph/pipeline.py — LangGraph Pipeline Compiler
=============================================
Wired all node components into a stateful graph and compiles with SQLite checkpointer.
"""

import logging
from pathlib import Path
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from core.config_manager import config
from graph.state import GhostCreatorState
from graph.nodes.research_node import research_node
from graph.nodes.script_node import script_node
from graph.nodes.script_critic_node import script_critic_node
from graph.nodes.human_review_node import human_review_node, route_after_review
from graph.nodes.image_node import spawn_parallel_tasks, image_worker_node
from graph.nodes.voiceover_node import voiceover_worker_node
from graph.nodes.seo_node import seo_node
from graph.nodes.editor_prep_node import editor_prep_node
from graph.nodes.assemble_node import assemble_node
from graph.nodes.upload_node import upload_node
from graph.nodes.error_recovery_node import error_recovery_node

log = logging.getLogger("pipeline")

# ── Router functions for Error Recovery ───────────────────────────────
# IMPORTANT: Check last_failed_node (not errors) because errors uses operator.add
# and accumulates across runs if the same checkpoint thread_id is reused.
# last_failed_node is set to "" on success, and to the node name on failure.

def check_research_error(state):
    failed = state.get("last_failed_node", "")
    if failed == "research" and config.get("pipeline.error_recovery_enabled", True):
        return "error_recovery"
    return "script"

def check_script_error(state):
    failed = state.get("last_failed_node", "")
    if failed == "script" and config.get("pipeline.error_recovery_enabled", True):
        return "error_recovery"
    return "script_critic"

def check_critic_error(state):
    failed = state.get("last_failed_node", "")
    if failed == "script_critic" and config.get("pipeline.error_recovery_enabled", True):
        return "error_recovery"
    return "human_review"

def check_seo_error(state):
    failed = state.get("last_failed_node", "")
    if failed == "seo" and config.get("pipeline.error_recovery_enabled", True):
        return "error_recovery"
    return "editor_prep"

def check_editor_prep_error(state):
    failed = state.get("last_failed_node", "")
    if failed == "editor_prep" and config.get("pipeline.error_recovery_enabled", True):
        return "error_recovery"
    return "assemble"

def check_assemble_error(state):
    failed = state.get("last_failed_node", "")
    if failed == "assemble" and config.get("pipeline.error_recovery_enabled", True):
        return "error_recovery"
    return "upload"

def check_upload_error(state):
    failed = state.get("last_failed_node", "")
    if failed == "upload" and config.get("pipeline.error_recovery_enabled", True):
        return "error_recovery"
    return END

def route_error_recovery(state):
    action = state.get("recovery_action", "abort")
    failed_node = state.get("last_failed_node", "")
    
    if action == "abort":
        return END
        
    if action == "retry" and failed_node:
        if failed_node in ("image_worker", "voiceover_worker"):
            return "parallel_spawn"
        return failed_node
        
    # fallback or skip -> route to the next step
    if failed_node == "research":
        return "script"
    elif failed_node == "script":
        return "script_critic"
    elif failed_node == "script_critic":
        return "human_review"
    elif failed_node in ("image_worker", "voiceover_worker", "seo"):
        return "editor_prep"
    elif failed_node == "editor_prep":
        return "assemble"
    elif failed_node == "assemble":
        return "upload"
    elif failed_node == "upload":
        return END
        
    return END


def build_pipeline(checkpointer=None):
    """Builds and compiles the Ghost Creator AI LangGraph state graph."""
    builder = StateGraph(GhostCreatorState)

    # 1. Register Nodes
    builder.add_node("research", research_node)
    builder.add_node("script", script_node)
    builder.add_node("script_critic", script_critic_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("parallel_spawn", lambda state: {})   # Dummy node to trigger fan-out
    builder.add_node("image_worker", image_worker_node)
    builder.add_node("voiceover_worker", voiceover_worker_node)
    builder.add_node("seo", seo_node)
    builder.add_node("editor_prep", editor_prep_node)
    builder.add_node("assemble", assemble_node)
    builder.add_node("upload", upload_node)
    builder.add_node("error_recovery", error_recovery_node)

    # 2. Add Edges with Error Checking
    builder.add_edge(START, "research")
    
    builder.add_conditional_edges(
        "research",
        check_research_error,
        {
            "error_recovery": "error_recovery",
            "script": "script"
        }
    )
    
    builder.add_conditional_edges(
        "script",
        check_script_error,
        {
            "error_recovery": "error_recovery",
            "script_critic": "script_critic"
        }
    )
    
    builder.add_conditional_edges(
        "script_critic",
        check_critic_error,
        {
            "error_recovery": "error_recovery",
            "human_review": "human_review"
        }
    )

    # 3. Add Conditional Review Router
    builder.add_conditional_edges(
        "human_review",
        route_after_review,
        {
            "parallel_generation": "parallel_spawn",
            "script_node": "script",
            END: END
        }
    )

    # 4. Add Fan-out Conditional Edges
    # spawn_parallel_tasks returns the list of Send() objects
    builder.add_conditional_edges(
        "parallel_spawn",
        spawn_parallel_tasks,
        {
            "image_worker": "image_worker",
            "voiceover_worker": "voiceover_worker"
        }
    )

    # 5. Add Fan-in to Join at SEO Node
    builder.add_edge("image_worker", "seo")
    builder.add_edge("voiceover_worker", "seo")
    
    builder.add_conditional_edges(
        "seo",
        check_seo_error,
        {
            "error_recovery": "error_recovery",
            "editor_prep": "editor_prep"
        }
    )

    builder.add_conditional_edges(
        "editor_prep",
        check_editor_prep_error,
        {
            "error_recovery": "error_recovery",
            "assemble": "assemble"
        }
    )
    
    builder.add_conditional_edges(
        "assemble",
        check_assemble_error,
        {
            "error_recovery": "error_recovery",
            "upload": "upload"
        }
    )
    
    builder.add_conditional_edges(
        "upload",
        check_upload_error,
        {
            "error_recovery": "error_recovery",
            END: END
        }
    )
    
    # 6. Add Error Recovery Routing
    builder.add_conditional_edges(
        "error_recovery",
        route_error_recovery,
        {
            "research": "research",
            "script": "script",
            "script_critic": "script_critic",
            "human_review": "human_review",
            "parallel_spawn": "parallel_spawn",
            "editor_prep": "editor_prep",
            "assemble": "assemble",
            "upload": "upload",
            END: END
        }
    )

    # Compile with human review interrupt point
    return builder.compile(checkpointer=checkpointer, interrupt_before=["human_review"])


import threading

_pipeline_lock = threading.Lock()
_graph = None
_checkpointer_context = None
_checkpointer = None

def get_pipeline():
    """Singleton getter for the compiled graph pipeline."""
    global _graph, _checkpointer_context, _checkpointer
    with _pipeline_lock:
        if _graph is None:
            db_path_str = config.get("pipeline.checkpoint_db", "ghost_runs.db")
            from config import get_writable_path
            db_path = get_writable_path(db_path_str)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            log.info(f"Using SQLite checkpoint database at: {db_path}")
            _checkpointer_context = SqliteSaver.from_conn_string(str(db_path))
            _checkpointer = _checkpointer_context.__enter__()
            
            _graph = build_pipeline(checkpointer=_checkpointer)
        return _graph
