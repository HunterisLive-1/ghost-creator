"""
core/pipeline_runner.py — Threaded Pipeline Runner
====================================================
Runs the Ghost Creator pipeline steps in a background thread,
communicating progress to the GUI via a queue.Queue.

Usage:
    import queue
    q = queue.Queue()
    runner = PipelineRunner(q)
    runner.start(topic="AI in 2026")
    # Poll q for progress events
    runner.stop()  # cancel mid-pipeline
"""

import queue
import re
import subprocess
import sys
import threading
import os
from datetime import datetime
from pathlib import Path
from config import get_logger, OUTPUT_DIR

log = get_logger("pipeline")
USE_LANGGRAPH = os.environ.get("GHOST_USE_LANGGRAPH", "1") == "1"


_NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _has_gpu() -> bool:
    """
    Return True if an NVIDIA CUDA GPU is available.
    Fast check — uses nvidia-smi (always present on CUDA systems).
    Falls back to torch.cuda.is_available() if nvidia-smi is not on PATH.
    """
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, timeout=5,
            creationflags=_NO_WINDOW,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        pass
    return False


def resolve_output_base(fallback: Path | None = None) -> Path:
    """Resolve configured pipeline output folder (same path pipeline + history use)."""
    from core.config_manager import config as cfg

    fb = fallback or OUTPUT_DIR
    folder = (cfg.get("pipeline.output_folder", "") or "").strip()
    if folder:
        base = Path(folder)
        if not base.is_absolute():
            base = fb.parent / folder
    else:
        base = fb
    return base


def _make_run_dir(title: str, config, fallback: Path) -> Path:
    """
    Create a per-run subfolder inside the configured output folder.

    Folder name: <safe_title>_<YYYYMMDD_HHMMSS>
    e.g.  Street_Light_Sapne_20260327_163808/

    Falls back to ``fallback`` (OUTPUT_DIR) if the subfolder cannot be created
    (permission error, invalid path, etc.).
    """
    _safe = re.sub(
        r'[^\w\u0900-\u097F\u0A00-\u0A7F\u0B00-\u0B7F\u0B80-\u0BFF'
        r'\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0980-\u09FF -]',
        '', title,
    )
    _safe = re.sub(r'\s+', '_', _safe.strip()).strip('_')[:40] or "run"
    _stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{_safe}_{_stamp}"

    base = resolve_output_base(fallback)

    try:
        run_dir = base / folder_name
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    except Exception as exc:
        log.warning(f"Could not create run subfolder ({exc}) — using fallback: {fallback}")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _distribute_length_by_weights(total_len: int, weights: list[int]) -> list[int]:
    """Split total_len into len(weights) integers proportional to weights; sum equals total_len."""
    n = len(weights)
    if n == 0:
        return []
    if total_len <= 0:
        return [0] * n
    s = sum(weights) or 1
    raw = [total_len * (weights[i] / s) for i in range(n)]
    parts = [int(r) for r in raw]
    rem = total_len - sum(parts)
    fracs = sorted(range(n), key=lambda i: raw[i] - parts[i], reverse=True)
    for j in range(rem):
        parts[fracs[j]] += 1
    return parts


def _resync_segment_voiceovers(new_voiceover_text: str, segments: list[dict]) -> None:
    """Re-split full narration into segment voiceover strings for cut-length math (proportional to prior segment sizes)."""
    n = len(segments)
    if n == 0:
        return
    t = new_voiceover_text
    l_total = len(t)
    if l_total == 0:
        for seg in segments:
            seg["voiceover"] = ""
        return
    weights = [max(1, len(str(seg.get("voiceover", "")))) for seg in segments]
    part_lens = _distribute_length_by_weights(l_total, weights)
    offset = 0
    for i, plen in enumerate(part_lens):
        segment = segments[i]
        segment["voiceover"] = t[offset : offset + plen]
        offset += plen


class PipelineRunner:
    """
    Orchestrates the 6-step pipeline.
    Delegates entirely to LangGraph and broadcasts progress events.
    """

    def __init__(self, progress_queue: queue.Queue, run_id: int = 0) -> None:
        self.progress_queue = progress_queue
        self._run_id = run_id
        self.thread: threading.Thread | None = None

    def start(self, topic: str | None = None, mode: str = "shorts", custom_script: str = "") -> None:
        """Start the pipeline by delegating to LangGraph."""
        from graph.pipeline import get_pipeline
        from graph.state import default_state
        
        thread_id = f"run_{self._run_id}"
        run_dir = _make_run_dir(topic or "custom_script", config, OUTPUT_DIR)
        
        initial_state = default_state()
        initial_state.update({
            "mode": mode,
            "topic": topic or "",
            "user_custom_script": custom_script,
            "run_id": thread_id,
            "run_dir": str(run_dir),
            "language": config.get("pipeline.language", "hinglish"),
        })
        
        # Register progress queue to broadcaster
        from api.routes.pipeline import get_broadcaster
        broadcaster = get_broadcaster()
        if broadcaster and hasattr(broadcaster, "add_queue"):
            broadcaster.add_queue(self.progress_queue)
            
        from api.routes.pipeline import _run_graph_in_background
        _run_graph_in_background(thread_id, initial_state)
        
        # Get active running thread reference
        import time
        time.sleep(0.1) # Wait a tiny bit for the thread to start
        from api.routes.pipeline import _active_run_thread
        self.thread = _active_run_thread

    def stop(self) -> None:
        """Request the pipeline to stop."""
        log.info("Stop requested. Deregistering queue listener.")
        from api.routes.pipeline import get_broadcaster
        broadcaster = get_broadcaster()
        if broadcaster and hasattr(broadcaster, "remove_queue"):
            broadcaster.remove_queue(self.progress_queue)

    def request_retry(self) -> None:
        pass

    def approve_script(self, approved_data: dict) -> None:
        pass

    def cancel_pipeline_from_review(self) -> None:
        pass

    def continue_from_editor(self) -> None:
        pass

    def cancel_from_editor(self) -> None:
        pass
