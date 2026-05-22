# Installation

## Prerequisites

### Required

| Tool | Version | Why |
|------|---------|-----|
| **Python** | 3.10 – 3.12 | Pipeline + FastAPI backend |
| **Node.js** | 18+ | Electron + React GUI |
| **Git** | Any | Clone the repository |
| **Google Chrome** | Latest | YouTube upload automation (not Chromium) |
| **FFmpeg** | Any recent | Video assembly (PATH, or auto-download on first packaged run) |
| **Gemini API key** | Free tier | Script generation (required) |

Get a Gemini key: [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

### Optional

| Item | When needed |
|------|-------------|
| **Pexels API key** | Faster HD stock footage ([pexels.com/api](https://www.pexels.com/api/)) |
| **ElevenLabs API key** | If using ElevenLabs TTS |
| **OmniVoice server** | If using OmniVoice voice clone (external `.bat` / WebUI) |
| **Reference WAV** | `my_voice_reference.wav` in project root for OmniVoice clone mode |
| **Ollama** | Local script generation instead of Gemini |
| **NVIDIA GPU** | Speeds OmniVoice / long renders (not required for Edge TTS + cloud footage) |

**Python install tip (Windows):** check **Add Python to PATH** during setup.

**FFmpeg verify:**

```powershell
ffmpeg -version
```

If missing, install via `winget install ffmpeg` or run `powershell -ExecutionPolicy Bypass -File ensure_ffmpeg.ps1`.

---

## Step 1 — Clone

```powershell
git clone https://github.com/HunterisLive-1/ghost-creator.git
cd ghost-creator
```

## Step 2 — Run setup.bat

Double-click **`setup.bat`** (Run as Administrator recommended for Windows Long Paths).

It automatically:

| Step | Action |
|------|--------|
| 1 | Enables Windows Long Path support |
| 2 | Detects Python (3.12 → 3.11 → 3.10) |
| 3 | Creates `venv\` virtual environment |
| 4 | Installs Python dependencies from `requirements.txt` |
| 5 | Optional Chatterbox TTS server setup (legacy — skip unless you use it elsewhere) |
| 6 | Installs Playwright Chromium (YouTube upload) |
| 7 | Installs FastAPI + Electron/npm dependencies |
| 8 | Optional paid TTS / image backend packages |
| 9 | Creates `config.json` (migrates legacy `.env` if found) |

First run may take 10–20 minutes depending on network speed.

## Step 3 — First-time configuration

1. Launch the app (see **Launching the App** section)
2. Open **Settings** tab
3. Enter your **Gemini API key**
4. Choose **TTS backend** (default: OmniVoice — requires external server, or switch to **Edge TTS** for zero setup)
5. Click **[ SAVE CONFIG ]**

Alternatively edit `config.json` in the project root, or use **OPEN IN EDITOR** for `.env.local`.

## Step 4 — OmniVoice (optional, default TTS)

If using OmniVoice voice cloning:

1. Set up the OmniVoice WebUI/server separately (external repo)
2. In Settings → OmniVoice: set server `.bat` path and reference audio WAV
3. Place `my_voice_reference.wav` in the project root (10–30 seconds of your voice)

**Quick start without OmniVoice:** Settings → TTS backend → **Edge TTS** (free, no key).

## Step 5 — YouTube upload (optional)

One-time Chrome profile setup for automated uploads:

```powershell
venv\Scripts\activate.bat
python setup_chrome_profile.py
```

Then in Settings → Chrome profiles → **+ SETUP NEW PROFILE** and sign into YouTube once.
