"""Progress event broadcaster — queue.Queue-compatible adapter for WebSocket fan-out + HTTP poll buffer."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from typing import Any

_log = logging.getLogger("broadcaster")


class ProgressBroadcaster:
    """Thread-safe broadcaster; PipelineRunner calls put() from worker threads.

    In addition to pushing messages to WebSocket clients, a ring buffer of
    recent messages is maintained so the frontend can HTTP-poll for progress
    when WebSocket is unavailable (e.g. Windows IPv6 / mixed-origin issues).
    """

    MAX_BUFFER = 200  # keep last N messages for HTTP polling

    def __init__(self) -> None:
        self._clients: set[Any] = set()
        self._queues: set[Any] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

        # ── HTTP poll buffer ──────────────────────────────────────
        self._buffer: deque[dict] = deque(maxlen=self.MAX_BUFFER)
        self._msg_counter: int = 0  # monotonically increasing cursor

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ── WebSocket client management ──────────────────────────────
    def add_client(self, ws: Any) -> None:
        with self._lock:
            self._clients.add(ws)

    def remove_client(self, ws: Any) -> None:
        with self._lock:
            self._clients.discard(ws)

    def add_queue(self, q: Any) -> None:
        with self._lock:
            self._queues.add(q)

    def remove_queue(self, q: Any) -> None:
        with self._lock:
            self._queues.discard(q)

    # ── Core put — called from background threads ────────────────
    def put(self, msg: dict) -> None:
        """Called from PipelineRunner thread — schedule async broadcast + buffer for HTTP poll."""
        # 0. Buffer for HTTP polling (always works, no event loop needed)
        with self._lock:
            self._msg_counter += 1
            msg_with_seq = {**msg, "_seq": self._msg_counter}
            self._buffer.append(msg_with_seq)

        # 1. Forward to registered queues
        with self._lock:
            queues = list(self._queues)
        for q in queues:
            try:
                q.put(msg_with_seq)
            except Exception:
                pass

        # 2. Forward to WebSockets
        with self._lock:
            clients = list(self._clients)
        if not clients:
            return

        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
                self._loop = loop
            except RuntimeError:
                return

        payload = json.dumps(msg_with_seq, ensure_ascii=False)

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
            asyncio.run_coroutine_threadsafe(_send(), loop)
        except Exception:
            pass

    # ── HTTP poll helpers ─────────────────────────────────────────
    def get_messages_since(self, after_seq: int) -> tuple[list[dict], int]:
        """Return (messages_after_seq, latest_seq). Thread-safe."""
        with self._lock:
            msgs = [m for m in self._buffer if m.get("_seq", 0) > after_seq]
            latest = self._msg_counter
        return msgs, latest

    def clear_buffer(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._msg_counter = 0

    def put_nowait(self, msg: dict) -> None:
        self.put(msg)

    def empty(self) -> bool:
        return True

    def get_nowait(self) -> dict:
        raise Exception("ProgressBroadcaster is push-only")
