"""Single active pipeline runner registry."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.pipeline_runner import PipelineRunner

_lock = threading.Lock()
_runner: "PipelineRunner | None" = None
_run_id = 0


def next_run_id() -> int:
    global _run_id
    with _lock:
        _run_id += 1
        return _run_id


def set_runner(runner: "PipelineRunner | None") -> None:
    global _runner
    with _lock:
        _runner = runner


def get_runner() -> "PipelineRunner | None":
    with _lock:
        return _runner
