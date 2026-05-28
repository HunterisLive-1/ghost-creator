"""
api/server.py — Ghost Creator AI local FastAPI backend
Spawned by Electron on startup; serves REST + WebSocket to React UI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root on sys.path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def ensure_dependencies() -> None:
    import sys
    import subprocess
    try:
        import google.oauth2.credentials
        import google_auth_oauthlib.flow
        import googleapiclient.discovery
    except ImportError:
        print("[Server Startup] Google client libraries not found. Installing automatically...")
        try:
            py_exe = sys.executable
            subprocess.check_call([py_exe, "-m", "pip", "install", "google-auth-oauthlib", "google-api-python-client"])
            print("[Server Startup] Google client libraries installed successfully!")
        except Exception as e:
            print(f"[Server Startup] Failed to automatically install dependencies: {e}")

ensure_dependencies()


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import APP_VERSION, get_logger
from api.routes import config as config_routes
from api.routes import docs as docs_routes
from api.routes import history as history_routes
from api.routes import misc as misc_routes
from api.routes import pipeline as pipeline_routes
from api.routes import system as system_routes
from api.routes import upload as upload_routes
from api.routes import workshop as workshop_routes
from api.routes.pipeline import get_broadcaster
from api.routes.system import bootstrap_ffmpeg

log = get_logger("server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    get_broadcaster().bind_loop(loop)
    bootstrap_ffmpeg()

    try:
        from graph.pipeline import get_pipeline
        get_pipeline()
    except Exception as e:
        log.error(f"Failed to eagerly initialize LangGraph pipeline: {e}", exc_info=True)

    try:
        from core.ffmpeg_bootstrap import configure_pydub_subprocess
        configure_pydub_subprocess()
    except Exception:
        pass
    try:
        from core.stock_manager import ensure_stock_assets
        ensure_stock_assets()
    except Exception:
        pass

    yield


app = FastAPI(title="Ghost Creator API", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)

app.include_router(config_routes.router)
app.include_router(docs_routes.router)
app.include_router(pipeline_routes.router)
app.include_router(system_routes.router)
app.include_router(workshop_routes.router)
app.include_router(upload_routes.router)
app.include_router(history_routes.router)
app.include_router(misc_routes.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": APP_VERSION}


def _health_ok(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if Ghost Creator API is already responding on host:port."""
    import urllib.error
    import urllib.request

    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _port_in_use(host: str, port: int) -> bool:
    """Return True if something is already bound to host:port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return False
        except OSError:
            return True


class _QuietAccessLogFilter(logging.Filter):
    """Hide high-frequency poll and preflight lines from uvicorn access logs."""

    _SKIP_PATHS = (
        "/api/pipeline/script-review",
        "/api/pipeline/editor-review",
        "/api/history",
        "/health",
        "/api/config",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "OPTIONS " in msg:
            return False
        return not any(path in msg for path in self._SKIP_PATHS)


def main() -> None:
    import uvicorn

    logging.getLogger("uvicorn.access").addFilter(_QuietAccessLogFilter())

    host = os.environ.get("GHOST_API_HOST", "127.0.0.1")
    port = int(os.environ.get("GHOST_API_PORT", "8766"))

    if _health_ok(host, port):
        print(f"[Ghost Creator API] Already running at http://{host}:{port}/health - not starting a second server.")
        return

    if _port_in_use(host, port):
        print(
            f"[Ghost Creator API] ERROR: Port {port} is already in use on {host}, "
            "but /health did not respond.\n"
            "  • Close the other app using this port, or\n"
            "  • Kill the stale process:  netstat -ano | findstr :8766  then  taskkill /PID <pid> /F\n"
            "  • Or use a different port:  set GHOST_API_PORT=8767"
        )
        sys.exit(1)

    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
