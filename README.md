<div align="center">

# 👻 Hunter Ghost Creator AI v4.2.2

### Fully Automated YouTube Shorts Pipeline — Now with GUI + Swappable Backends
### by [HunterIsLive](https://github.com/HunterisLive-1)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Gemini](https://img.shields.io/badge/Google-Gemini%202.0-4285F4?logo=google&logoColor=white)](https://ai.google.dev)
[![Chatterbox](https://img.shields.io/badge/Chatterbox-TTS%20Local%20Free-black)](https://github.com/resemble-ai/chatterbox)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-Local%20AI-orange)](https://github.com/comfyanonymous/ComfyUI)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Direct%20Render-green)](https://ffmpeg.org)
[![Electron](https://img.shields.io/badge/GUI-Electron%20%2B%20React-47848F?logo=electron&logoColor=white)](https://www.electronjs.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows)](https://microsoft.com)

> **One click → Trending research → Hindi/English script → AI voice → 6× AI images → 9:16 Short → YouTube upload.**
> Now with a full GUI, 5 TTS options, 6 image backends, and 5–10× faster rendering via FFmpeg.

![Ghost Creator Banner](https://img.shields.io/badge/🚀%20Ghost%20Creator%20AI%20v4.2.2-GUI%20%2B%20Swappable%20Backends-blueviolet?style=for-the-badge)

</div>

---

## 📋 Table of Contents

- [What's New in v2](#-whats-new-in-v2)
- [What It Does](#-what-it-does)
- [Pipeline Overview](#-pipeline-overview)
- [GUI Screenshots](#-gui-screenshots)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation--step-by-step)
- [Launching the App](#-launching-the-app)
- [TTS Backends](#-tts-backends)
- [Image Backends](#-image-backends)
- [FFmpeg Rendering](#-ffmpeg-rendering--5-10x-faster)
- [Pipeline Skip Modes](#-pipeline-skip-modes-cli)
- [Project Structure](#-project-structure)
- [Troubleshooting](#-troubleshooting)

---

## 🆕 What's New in v2 / v3

| Feature | v1 | v2 | v3.3 |
|---------|----|----|------|
| Interface | Terminal only | **Full GUI (Dark mode)** | ← same |
| TTS options | Chatterbox only | **5 backends** | ← same |
| Image options | ComfyUI only | **6 backends** | **7 backends (+Grok Imagine ⭐)** |
| Video render | MoviePy (3–5 min) | **FFmpeg direct (25–45 sec) ⚡** | ← same |
| Script provider | Gemini only | Gemini only | **Gemini + OpenAI** |
| Image review | None | None | **Visual image review + approval step** |
| Image-to-video | None | None | **Fal.ai + xAI Grok Video clips** |
| Video effects | Always on | Always on | **Master ON/OFF toggle** |
| Config | `.env` file | **GUI Settings → `config.json`** | ← same |
| YouTube Upload | Single Profile | **Multi-Profile Chrome Manager** | ← same |
| xAI Grok support | ❌ | ❌ | **✅ Grok images + Grok video** |

> **v3.3 note:** xAI Grok Imagine — $0.02/image standard, one key works for both images and video clips.

---

## 🎯 What It Does

Ghost Creator AI is a **zero-touch YouTube Shorts factory**. Give it a topic (or let it auto-find one), and it produces a complete, ready-to-upload Short:

| Step | Module | What happens |
|------|--------|-------------|
| 1 | `researcher.py` | Finds trending AI/Tech topics via PyTrends + Google RSS |
| 2 | `scripter.py` | Generates voiceover script + image prompts + metadata via Gemini 2.0 |
| 3 | `voicer.py` | Synthesises speech via your chosen TTS backend |
| 4 | `image_gen.py` | Generates 6× cinematic images via your chosen image backend |
| 5 | `video_builder.py` | Assembles 1080×1920 Short with Ken Burns zoom + subtitles via **FFmpeg** |
| 6 | `uploader.py` | Auto-uploads to YouTube Studio via Playwright + Chrome |

---

## 🔄 Pipeline Overview

```
[1] PyTrends / RSS
        │
        ▼
[2] Gemini 2.0 ──► Script + Image Prompts + Metadata
        │
        ▼
[3] TTS Backend (Chatterbox / Edge TTS / ElevenLabs / Google / Kokoro)
        │
        ▼
[4] Image Backend (ComfyUI / Pollinations / Gemini Imagen-3 / Fal.ai / Stable Horde / Replicate)
        │
        ▼
[5] FFmpeg Direct ──► 1080×1920 final_short.mp4 + Subtitles (25–45 sec render)
        │
        ▼
[6] Playwright + Chrome ──► YouTube Studio (Auto Upload)
```

---

## 🖥️ GUI Screenshots

> Launch with `npm run electron:dev` (requires `npm install` + Python venv)

### Pipeline Tab
```
┌─────────────────────────────────────────────────────────┐
│  👻 Ghost Creator AI                              v4.2.2 🟢 │
├─────────────────────────────────────────────────────────┤
│  ▶ Pipeline  |  ⚙ Settings  |  📋 History               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Topic: [Enter topic or leave blank for auto-trending ] │
│         [ ] Auto-find trending topic                    │
│                                                         │
│  [▶ Run Full Pipeline]              [⏹ Stop]            │
│                                                         │
│  Research → Script → Voice → Images → Video → Upload   │
│  [████████████████████░░░░░░░░░░░░░░░░░]  66%          │
│                                                         │
│  ┌─ Live Log ────────────────────────────────────────┐  │
│  │ [INFO]  Researching trending topics...            │  │
│  │ [OK]    Topic found: "Gemini 2.5 Pro released"    │  │
│  │ [INFO]  Generating script via Gemini 2.0...       │  │
│  │ [OK]    Script ready (380 chars, 6 scenes)        │  │
│  │ [INFO]  Chatterbox TTS synthesising...            │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Settings Tab
```
┌─────────────────────────────────────────────────────────┐
│  ⚙ Settings                                             │
├─────────────────────────────────────────────────────────┤
│  API Keys                                               │
│  Gemini API Key:      [••••••••••••••••••] 👁           │
│  ElevenLabs Key:      [                  ] 👁           │
│  Fal.ai Key:          [                  ] 👁           │
│                                                         │
│  Voice (TTS)                                            │
│  [Chatterbox] [Edge TTS] [ElevenLabs] [Google] [Kokoro] │
│  Reference Audio: [C:\...\my_voice.wav]  [Browse]       │
│                                                         │
│  Image Generation                                       │
│  [ComfyUI] [Pollinations] [Gemini Imagen] [Fal] [Horde] │
│                                                         │
│  Pipeline Settings                                      │
│  Language: [Hindi ▼]  Images: [6 ▼]  Upload: [Unlisted]│
│  Chrome Profiles: [Tech Channel ▼]      [ + SETUP NEW ]│
│                                                         │
│                              [💾 Save Settings]         │
└─────────────────────────────────────────────────────────┘
```

---

## 📦 Prerequisites

### Required — Install First

| Tool | Version | Why | Download |
|------|---------|-----|----------|
| **Python** | 3.10 or 3.12 | Main language + API backend | [python.org](https://www.python.org/downloads/) |
| **Node.js** | 18+ | Electron + React GUI | [nodejs.org](https://nodejs.org/) |
| **Git** | Any | Clone the repo | [git-scm.com](https://git-scm.com/downloads) |
| **Google Chrome** | Latest | YouTube upload automation | [google.com/chrome](https://www.google.com/chrome/) |
| **FFmpeg** | Any | Video rendering (required) | [ffmpeg.org](https://ffmpeg.org/download.html) or `winget install ffmpeg` |

> ⚠️ **FFmpeg must be in PATH.** After install, verify: `ffmpeg -version` in terminal.

> ⚠️ **Python install tip:** Check both boxes:
> - `[x] Add Python to PATH`
> - `[x] Install py launcher for all users`

### Optional — Only if using local backends

| Service | Port | Required for |
|---------|------|-------------|
| **ComfyUI** | `http://127.0.0.1:8188` | Local AI image generation (default) |
| **Chatterbox TTS** | `http://127.0.0.1:8004` | Local voice cloning (default) |

> If you use cloud backends (Pollinations, Edge TTS, etc.), neither ComfyUI nor Chatterbox is needed.

### API Keys — By Backend

| Backend | Key needed | Cost | Get it |
|---------|-----------|------|--------|
| **Gemini** | Yes | Free tier | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| **Gemini Imagen-3** | Uses Gemini key | Free (30 imgs/day) | Same key |
| **Chatterbox TTS** | No | **FREE** | Built-in |
| **Edge TTS** | No | **FREE** | Built-in |
| **Pollinations.ai** | No | **FREE** | Built-in |
| **ElevenLabs** | Yes | Paid | [elevenlabs.io](https://elevenlabs.io) |
| **Google Cloud TTS** | Yes (JSON) | Paid | [console.cloud.google.com](https://console.cloud.google.com) |
| **Kokoro TTS** | No | **FREE** (local) | Built-in |
| **Fal.ai** | Yes | ~$0.003/img | [fal.ai](https://fal.ai) |
| **Replicate** | Yes | ~$0.004/img | [replicate.com](https://replicate.com) |
| **Stable Horde** | Free key | **FREE** | [stablehorde.net](https://stablehorde.net) |

---

## 🛠️ Installation — Step by Step

### Step 1 — Clone the Repo

```powershell
git clone https://github.com/HunterisLive-1/Hunter-Ghost-Creator.git
cd Hunter-Ghost-Creator
```

---

### Step 2 — Run setup.bat

**Double-click `setup.bat`** (or right-click → Run as Administrator).

It will automatically:

| Step | What it does |
|------|-------------|
| `[1/8]` | Enables Windows Long Path support |
| `[2/8]` | Detects Python (tries 3.12 → 3.11 → 3.10) |
| `[3/8]` | Creates `venv` virtual environment |
| `[4/8]` | Installs Ghost Creator core dependencies |
| `[5/8]` | Sets up Chatterbox TTS server |
| `[7/10]` | Installs FastAPI + Electron deps (Python API, npm) |
| `[7/8]` | Installs Playwright Chromium browser |
| `[8/8]` | Creates `config.json` from defaults (migrates `.env` if found) |

> ⏱️ **Time:** First run takes 10–20 minutes (PyTorch CUDA ~2.5 GB for NVIDIA).

---

### Step 3 — Record Your Voice Reference (for Chatterbox)

Only needed if using **Chatterbox TTS** (default voice backend):

1. Record yourself speaking for 10–30 seconds (WAV format, quiet room)
2. Rename to `my_voice_reference.wav`
3. Place in project root (same folder as `main.py`)

> Skip this step if using Edge TTS, ElevenLabs, Google TTS, or Kokoro.

---

### Step 4 — Set up ComfyUI (for local image gen)

Only needed if using **ComfyUI** (default image backend):

```powershell
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt
```

Download DreamshaperXL model → place in `ComfyUI/models/checkpoints/`.

> Skip this step entirely if using Pollinations.ai, Gemini Imagen-3, or any cloud image backend.

---

### Step 5 — Configure via GUI

Launch the app and go to **⚙ Settings** tab:

1. Enter your **Gemini API key** (required for scripting)
2. Select your **TTS backend** (default: Chatterbox)
3. Select your **Image backend** (default: ComfyUI)
4. Click **💾 Save Settings**

---

## 🚀 Launching the App

```powershell
# Activate venv first
venv\Scripts\activate.bat

# GUI mode (recommended — Electron + React)
npm install
npm run electron:dev

# API backend only (for debugging)
python -m api.server

# CLI mode (unchanged, fully backward compatible)
python main.py
python main.py --topic "AI in 2026"
python main.py --from-script    # skip research
python main.py --from-audio     # skip research + script + TTS
python main.py --from-video     # only upload
```

---

## 🎙️ TTS Backends

Choose your voice backend from the **Settings tab**. Default is Chatterbox.

### Chatterbox TTS — Default ⭐
- **Cost:** Free
- **Quality:** Best (clones your voice)
- **Requires:** NVIDIA GPU, `my_voice_reference.wav`
- **Languages:** Hindi + English + 21 more
- Auto-starts/stops to manage VRAM

### Edge TTS — Best Free Cloud Option
- **Cost:** Free, no API key
- **Quality:** Good (Microsoft Azure neural voices)
- **Requires:** Internet connection only
- **Languages:** Hindi (`hi-IN-MadhurNeural`) + English
- Best choice if you don't have a GPU

### ElevenLabs
- **Cost:** Paid (subscription)
- **Quality:** Best cloud option
- **Requires:** API key + Voice ID
- **Languages:** Hindi via `eleven_multilingual_v2`

### Google Cloud TTS
- **Cost:** Paid (per character)
- **Quality:** Very good (WaveNet voices)
- **Requires:** Service account JSON key
- **Languages:** `hi-IN-Wavenet-C` + `en-US-Wavenet-D`

### Kokoro TTS
- **Cost:** Free (local)
- **Quality:** Very good (English)
- **Requires:** No GPU needed, ~500MB model (auto-downloads)
- **Languages:** English primarily, limited Hindi

---

## 🖼️ Image Backends

Choose your image backend from the **Settings tab**. Default is ComfyUI.

### ComfyUI — Default ⭐
- **Cost:** Free
- **Quality:** Best (DreamshaperXL, full control)
- **Requires:** NVIDIA GPU, ComfyUI running at port 8188
- **Speed:** ~3–5 min for 6 images (RTX 3050)

### Pollinations.ai — Best Free Cloud Option
- **Cost:** Free, **no API key**
- **Quality:** Good (SDXL-class)
- **Requires:** Internet connection only
- **Speed:** ~20s per image
- Best choice if you don't have a GPU

### Gemini Imagen-3 ⭐ — Zero Extra Setup
- **Cost:** Free tier (30 images/day)
- **Quality:** Very good
- **Requires:** Your existing **Gemini API key** — nothing new to set up
- **Speed:** ~5–10s per image
- Best cloud option if you already have a Gemini key

### Fal.ai
- **Cost:** ~$0.003/image
- **Quality:** High (fast-sdxl / FLUX Schnell)
- **Requires:** Fal.ai API key
- **Speed:** ~3s per image (fastest cloud)

### Stable Horde
- **Cost:** Free (community GPU donors)
- **Quality:** Good
- **Requires:** Free API key from [stablehorde.net](https://stablehorde.net)
- **Speed:** Variable (depends on available donors)

### Replicate
- **Cost:** ~$0.004/image
- **Quality:** High (SDXL)
- **Requires:** Replicate API key
- **Speed:** ~10s per image

### Grok Imagine — Recommended Alternative ⭐
- **Cost:** $0.02/image (standard) or $0.07/image (pro)
- **Quality:** Very good, consistent, fast
- **Requires:** xAI API key from [console.x.ai](https://console.x.ai)
- **Speed:** ~5–10s per image
- **Why use it:** Gemini Imagen free tier is often exhausted/unreliable. Grok Imagine is affordable, reliable, and **one key works for both images AND video clips (img2video)**.

---

## 🔑 API Keys — By Backend

| Backend | Key needed | Cost | Get it |
|---------|-----------|------|--------|
| Gemini Script | Gemini API Key | Free tier | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| Gemini Imagen-3 | Gemini API Key | Free tier | Same key |
| ElevenLabs TTS | ElevenLabs API Key | Paid | [elevenlabs.io](https://elevenlabs.io) |
| Fal.ai Images | Fal.ai API Key | ~$0.003/img | [fal.ai/dashboard](https://fal.ai/dashboard/keys) |
| Fal.ai Img2Video | Fal.ai API Key | $0.005–$0.28/clip | Same key |
| Replicate | Replicate API Key | ~$0.004/img | [replicate.com](https://replicate.com/account/api-tokens) |
| OpenAI Script | OpenAI API Key | ~$0.001–$0.01/script | [platform.openai.com](https://platform.openai.com/api-keys) |
| **Grok Imagine (image)** | **xAI API Key** | **$0.02–$0.07/img** | [console.x.ai](https://console.x.ai) |
| **Grok Video (img2video)** | **xAI API Key** | **$0.25–$0.50/clip** | Same key |

## 💰 Cost Reference Card

| Use case | Backend combo | Cost per video |
|----------|--------------|---------------|
| Free (unreliable) | Gemini Imagen + no img2video | $0 |
| Budget | Grok Standard images + no img2video | ~$0.12 (6 imgs) |
| Recommended | Grok Standard images + Grok Video (2 clips) | ~$0.62 |
| Premium | Grok Pro images + Grok Video 10s (3 clips) | ~$1.92 |
| Best quality | Kling Pro (3 clips) + Grok images | ~$1.26 |

---

## ⚡ FFmpeg Rendering — 5-10× Faster

v2 replaces MoviePy with **direct FFmpeg subprocess calls**.

| Method | 60s Short render time |
|--------|-----------------------|
| MoviePy (v1) | 3–5 minutes |
| **FFmpeg direct (v2)** | **25–45 seconds** |

MoviePy processed video frame-by-frame in Python (slow). FFmpeg handles everything natively in C — Ken Burns zoom, audio mix, subtitle burn — all in one pass.

> FFmpeg must be installed and available in PATH. Verify: `ffmpeg -version`

---

## 🔀 Pipeline Skip Modes (CLI)

For re-running specific stages without redoing everything:

```powershell
# Full pipeline (default)
python main.py

# Skip research — provide your own topic
python main.py --topic "Your topic here"

# Skip research + scripting — uses existing script in temp/
python main.py --from-script

# Skip research + script + TTS — uses existing voiceover.mp3 in temp/
python main.py --from-audio

# Skip everything except upload — uses existing final_short.mp4
python main.py --from-video
```

---

## 📁 Project Structure

```
Hunter-Ghost-Creator/
│
├── electron/                     # Electron main process + Python bridge
├── src/                          # React renderer (Documentary, Upload, Settings, History)
├── api/                          # FastAPI local backend (wraps core/ + modules/)
│   ├── server.py                 # uvicorn entry — spawned by Electron
│   └── routes/                   # REST + WebSocket endpoints
├── package.json                  # Node/Electron toolchain
│
├── backends/                     # Swappable backend system
│   ├── base.py                   # Abstract base classes
│   ├── tts/
│   │   ├── chatterbox.py         # DEFAULT — local voice clone
│   │   ├── edge_tts.py           # Free, no key
│   │   ├── elevenlabs.py         # Paid
│   │   ├── google_tts.py         # Google Cloud
│   │   └── kokoro_tts.py         # Local free
│   └── image/
│       ├── comfyui.py            # DEFAULT — local SDXL
│       ├── pollinations.py       # Free, no key
│       ├── Gemini_imagen.py      # Imagen-3, reuses Gemini key
│       ├── fal_ai.py             # Fast paid
│       ├── stable_horde.py       # Free community
│       └── replicate.py          # Paid
│
├── core/
│   ├── config_manager.py         # JSON config (read/write)
│   └── pipeline_runner.py        # Threaded pipeline orchestrator
│
├── modules/
│   ├── researcher.py             # Trending topic finder
│   ├── scripter.py               # Gemini script generator
│   ├── voicer.py                 # TTS dispatcher
│   ├── image_gen.py              # Image gen dispatcher
│   ├── video_builder.py          # FFmpeg video assembler
│   └── uploader.py               # YouTube auto-uploader
│
├── config.json                   # All settings (auto-created)
├── my_voice_reference.wav        # Your voice sample (Chatterbox only)
├── main.py                       # CLI entry point
├── setup_chrome_profile.py       # Chrome profile initializer script
├── setup.bat                     # One-click installer
└── requirements.txt              # All dependencies (CLI + GUI + backends)
```

---

## 🛠️ Troubleshooting

### GUI won't launch
```powershell
venv\Scripts\activate.bat
pip install -r requirements.txt
npm install
npm run electron:dev
```

### FFmpeg not found
```powershell
winget install ffmpeg
# Restart terminal after install
ffmpeg -version  # verify
```

### `config.json` missing
Run `setup.bat` — it auto-creates `config.json` from defaults.
Or run: `python -c "from core.config_manager import ConfigManager; ConfigManager()"`

### Chatterbox TTS not starting
```powershell
cd Chatterbox-TTS-Server-windows-easyInstallation
venv\Scripts\activate.bat
python server.py
# Look for errors
```

### ComfyUI not connecting
Make sure ComfyUI is running before pipeline starts:
```powershell
cd ComfyUI
python main.py --listen
# Should show: "To see the GUI go to: http://127.0.0.1:8188"
```

### CUDA out of memory (RTX 3050 6GB)
- Pipeline auto-manages VRAM: kills Chatterbox before ComfyUI starts
- If still OOM: close Chrome, OBS, other GPU apps
- Or switch to cloud backends: Edge TTS + Pollinations (zero GPU needed)

### `.env` from v1 not working
v2 uses `config.json`. Run `setup.bat` — it auto-migrates your `.env` to `config.json`.

### `No module named 'X'`
```powershell
venv\Scripts\activate.bat
pip install -r requirements.txt
```

### YouTube upload: `Google sign-in blocked`
Use real **Google Chrome** (not Chromium). Install from [google.com/chrome](https://www.google.com/chrome/).

---

## 📜 License

**MIT License** — free and open source. No activation or license key required.

See [LICENSE](LICENSE) for the full text.

---

<div align="center">

**Made with ❤️ by [HunterIsLive](https://github.com/HunterisLive-1)**

*Ghost Creator AI — Automate your YouTube Shorts. Stay Ghost. Stay Consistent.*

**[GitHub Repository](https://github.com/HunterisLive-1/Hunter-Ghost-Creator)**

</div>
