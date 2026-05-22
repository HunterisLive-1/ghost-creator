# Ghost Creator AI — Overview

**Automated Documentary Pipeline — Electron + React GUI**

Research → Script → Voice → Stock footage → FFmpeg assembly → YouTube upload.

Free, open source (MIT). Hindi and 8+ regional languages supported. No license key required.

---

## What It Does

Ghost Creator AI automates **documentary-style videos** from a topic (or auto-discovered trending subject) through a six-step pipeline:

| Step | Module | What happens |
|------|--------|--------------|
| 1. Research | `researcher.py` | Finds trending topic (or uses your subject) |
| 2. Script | `scripter.py` | Writes narration + per-segment footage queries (Gemini or Ollama) |
| 3. Voice | `voicer.py` | Synthesizes full voiceover via OmniVoice, Edge TTS, or ElevenLabs |
| 4. Footage | `video_fetcher.py` | Downloads HD clips from Pexels (preferred) or YouTube via yt-dlp |
| 5. Assembly | `documentary_assembler.py` | FFmpeg merges clips + audio; optional burned-in subtitles (long form) |
| 6. Upload | `uploader.py` | Optional YouTube Studio upload via Playwright + Chrome profile |

**Pipeline flow:** Research → Script → (optional Script Review) → Voice → Footage → Assembly → Upload

**Modes**

- **SHORT** — 30–60 seconds, vertical 9:16 (default)
- **LONG** — 3 minutes up to 2 hours, horizontal 16:9, optional subtitle burn-in

Each completed run is saved under `output/<title>_<timestamp>/` with metadata, clips, and the final MP4.

---

## Architecture

The desktop app has three layers:

| Layer | Role |
|-------|------|
| **Electron** | Window, native file dialogs, spawns and monitors the Python API process |
| **React (Vite)** | Documentary, Upload, Settings, History tabs |
| **FastAPI** | Local REST + WebSocket on `127.0.0.1:8766`; wraps existing Python pipeline code |
| **CLI (`main.py`)** | Same pipeline without GUI (script review disabled for unattended runs) |

**Data flow:** Electron spawns Python API on startup → React UI talks to FastAPI via REST/WebSocket → `pipeline_runner.py` orchestrates `modules/*`.

---

## Project Structure

```
ghost-creator/
├── electron/                 # Electron main process + Python bridge
├── src/                      # React UI (Vite)
├── api/                      # FastAPI local backend (port 8766)
├── core/                     # config_manager, pipeline_runner, ffmpeg_bootstrap
├── modules/                  # researcher, scripter, voicer, video_fetcher, etc.
├── backends/tts/             # omnivoice, edge_tts, elevenlabs
├── backends/image/           # gemini_imagen (thumbnails/auxiliary)
├── main.py                   # CLI entry point
├── setup.bat                 # One-click dev setup
├── build-api.bat             # PyInstaller API build
├── build-electron.bat        # Full Electron release build
└── LICENSE                   # MIT
```
