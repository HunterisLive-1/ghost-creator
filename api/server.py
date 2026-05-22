"""
api/server.py — Ghost Creator AI local FastAPI backend
Spawned by Electron on startup; serves REST + WebSocket to React UI.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root on sys.path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import APP_VERSION
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

app = FastAPI(title="Ghost Creator API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.on_event("startup")
async def on_startup() -> None:
    loop = asyncio.get_event_loop()
    get_broadcaster().bind_loop(loop)
    bootstrap_ffmpeg()
    try:
        from core.ffmpeg_bootstrap import configure_pydub_subprocess
        configure_pydub_subprocess()
    except Exception:
        pass


def main() -> None:
    import uvicorn

    port = int(os.environ.get("GHOST_API_PORT", "8766"))
    uvicorn.run(
        "api.server:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
