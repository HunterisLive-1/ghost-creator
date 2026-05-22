"""Progress event broadcaster — queue.Queue-compatible adapter for WebSocket fan-out."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any


class ProgressBroadcaster:
    """Thread-safe broadcaster; PipelineRunner calls put() from worker threads."""

    def __init__(self) -> None:
        self._clients: set[Any] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def add_client(self, ws: Any) -> None:
        with self._lock:
            self._clients.add(ws)

    def remove_client(self, ws: Any) -> None:
        with self._lock:
            self._clients.discard(ws)

    def put(self, msg: dict) -> None:
        """Called from PipelineRunner thread — schedule async broadcast."""
        with self._lock:
            clients = list(self._clients)
        if not clients or not self._loop:
            return
        payload = json.dumps(msg, ensure_ascii=False)

        async def _send() -> None:
            dead: list[Any] = []
            for ws in clients:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            if dead:
                with self._lock:
                    for ws in dead:
                        self._clients.discard(ws)

        try:
            asyncio.run_coroutine_threadsafe(_send(), self._loop)
        except Exception:
            pass

    def put_nowait(self, msg: dict) -> None:
        self.put(msg)

    def empty(self) -> bool:
        return True

    def get_nowait(self) -> dict:
        raise Exception("ProgressBroadcaster is push-only")
