"""Background job manager for upload / re-render log streaming."""

from __future__ import annotations

import threading
import uuid
from typing import Any, Callable


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, fn: Callable[[Callable], None]) -> str:
        job_id = uuid.uuid4().hex[:12]

        def log(msg: str, level: str = "INFO", done: bool = False, result: Any = None) -> None:
            with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id]["logs"].append(
                        {"message": msg, "level": level, "done": done, "result": result}
                    )

        with self._lock:
            self._jobs[job_id] = {"logs": [], "running": True}

        def worker() -> None:
            try:
                fn(log)
            except Exception as exc:
                log(f"❌ {exc}", "ERROR", done=True)
            finally:
                with self._lock:
                    if job_id in self._jobs:
                        self._jobs[job_id]["running"] = False

        threading.Thread(target=worker, daemon=True).start()
        return job_id

    def get_logs_since(self, job_id: str, offset: int) -> tuple[list[dict], bool]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return [], True
            logs = job["logs"][offset:]
            return logs, not job["running"] and offset + len(logs) >= len(job["logs"])


job_manager = JobManager()
