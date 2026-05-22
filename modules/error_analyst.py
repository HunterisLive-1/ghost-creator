"""
modules/error_analyst.py — Ghost Creator AI Error Analyst
===========================================================
Reads the Cinema Terminal output log and uses Gemini to explain the error
to the user and provide step-by-step fix instructions.

Called automatically when any pipeline step fails (ERROR level message).
"""

from __future__ import annotations

from config import get_logger, GEMINI_MODEL
from core.config_manager import config

log = get_logger("error_analyst")

# ── Ghost Creator briefing sent to Gemini every time ─────────────────────────
_SOFTWARE_BRIEFING = """
You are the Ghost Creator AI Error Analyst, a built-in support assistant for
the "Ghost Creator AI" application — an automated YouTube documentary video pipeline.

════════════════════════════════════════════════════════
GHOST CREATOR AI — SOFTWARE BRIEFING (for context)
════════════════════════════════════════════════════════

PURPOSE:
  Ghost Creator AI creates fully automated YouTube documentary videos.
  The user picks a topic → the app generates a narrated documentary with
  YouTube footage and assembles it into a final video file.

PIPELINE STEPS (in order):
  Step 1 — RESEARCH   : Finds the topic or uses user input. Uses PyTrends / Google RSS.
                        (Also features Idea Workshop AI chat for brainstorming).
  Step 2 — SCRIPT     : Generates narration script using Gemini AI (JSON output).
                        Requires: Gemini API key in Settings → API Keys.
  Step 3 — VOICE      : Synthesises narration audio using selected TTS backend.
                        Backends: Edge TTS (free cloud), ElevenLabs (paid cloud), OmniVoice (local GPU).
  Step 4 — FOOTAGE    : Downloads video clips from YouTube / Pexels using yt-dlp.
                        Requires: yt-dlp installed + internet + valid Pexels API key (if Pexels).
  Step 5 — ASSEMBLY   : Assembles video using FFmpeg. FFmpeg must be available (first-run download or PATH).
  Step 6 — UPLOAD     : Optional YouTube upload via Playwright + Chrome.
                        (There is also a standalone Direct Upload tab for external videos).

KEY SETTINGS (all in GUI → ⚙ Settings tab):
  • Gemini API Key   — required for script generation (Step 2) and this AI assistant.
                       Get free key: https://aistudio.google.com/app/apikey
  • ElevenLabs Key   — only needed if ElevenLabs TTS is selected.
  • Fal.ai Key       — only needed for Fal.ai image backend (not used in Documentary mode).
  • Pexels API Key   — required if Pexels footage source is selected.
  • TTS Backend      — Edge TTS is free and needs no key. Chatterbox needs NVIDIA GPU.
  • Output Folder    — where completed videos are saved.
  • Script Provider  — Gemini (default), OpenAI, or Ollama.

COMMON ERRORS AND THEIR FIXES:
  • "No Gemini API key"      → Settings → API Keys → Enter Gemini API Key → Save
  • "401 Unauthorized"       → Wrong API key. Re-enter a fresh key from aistudio.google.com
  • "404 NOT_FOUND model"    → Model name is wrong/outdated. Settings → use "gemini-2.5-flash"
  • "quota exceeded"         → Gemini free tier limit hit. Wait or use a different key.
  • "yt-dlp" / "ytdlp" error → yt-dlp not installed. Run: pip install -U yt-dlp
                               Or yt-dlp is outdated: Run: pip install -U yt-dlp
  • "ffmpeg not found"       → Allow first-run FFmpeg download (Internet) or install FFmpeg on PATH.
                               Dev: winget install ffmpeg — or run ensure_ffmpeg.ps1. Needed for assembly, TTS post-process, and clip tools.
  • "Chatterbox" connection  → Chatterbox TTS server not running. Switch to Edge TTS (free)
                               in Settings → Voice Engine → Edge TTS.
  • "ComfyUI" error          → ComfyUI not running. Switch to Pollinations or Gemini Imagen.
  • "ElevenLabs" 401         → Invalid ElevenLabs API key. Check elevenlabs.io dashboard.
  • "Pexels" 401 / 403       → Invalid Pexels API key. Get a free key at pexels.com/api
  • "No module named X"      → Dependency missing. Run: pip install -r requirements.txt
  • "JSON decode" / parse    → Gemini returned malformed JSON. Usually a quota/temp issue.
                               Retry the pipeline (click RETRY STEP button).
  • "CUDA out of memory"     → GPU VRAM full. Switch TTS to Edge TTS, images to Pollinations.
  • "Permission denied"      → Output folder is read-only or file is locked by another app.
  • "Playwright" / Chrome    → Chrome not installed or profile not set up.
                               Run: python setup_chrome_profile.py

FILES AND FOLDERS:
  • config.json    — all settings (in project root)
  • output/        — completed videos stored here
  • venv/          — Python virtual environment (activate before running)
  • requirements.txt — all dependencies

HOW TO RUN:
  • Always activate venv first: venv\\Scripts\\activate.bat
  • GUI: npm run electron:dev
  • CLI: python main.py

════════════════════════════════════════════════════════
YOUR TASK:
  The user is seeing an error in the Cinema Terminal log (shown below).
  Analyse the error carefully. Respond in this exact format:

  🔍 ERROR DETECTED: <one-line plain English summary of what went wrong>

  📌 CAUSE: <brief explanation of why this happens>

  🛠 HOW TO FIX:
  1. <step 1 — very specific, actionable>
  2. <step 2>
  3. <step 3 — if needed>
  (max 5 steps, no fluff)

  💡 TIP: <one optional tip to prevent this error in future>

  Keep your response SHORT and CLEAR. No markdown headers. Use plain English.
  If multiple errors exist, address the most critical one first.
  If the error is not clear, say so and ask what they were trying to do.
════════════════════════════════════════════════════════
"""


def analyse_error(terminal_log: str, script_config: dict | None = None) -> str:
    """
    Send the Cinema Terminal log to Gemini and return a plain-English explanation
    and fix guide for the error.

    Parameters
    ----------
    terminal_log  : recent lines from the _log_box (Cinema Terminal)
    script_config : optional config slice (same as scripter uses)

    Returns
    -------
    str — formatted fix guide from Ghost Agent
    """
    cfg     = script_config or {}
    api_key = (cfg.get("api_keys.gemini") or config.get("api_keys.gemini", "")).strip()

    if not api_key:
        return (
            "⚠ Cannot reach Ghost Agent — No Gemini API key found.\n\n"
            "HOW TO FIX:\n"
            "1. Go to Settings tab → API Keys section.\n"
            "2. Enter your Gemini API key (free at aistudio.google.com/app/apikey).\n"
            "3. Click 💾 Save Settings.\n"
            "4. Retry the pipeline."
        )

    gemini_model = cfg.get("gemini_model") or config.get("gemini_model", GEMINI_MODEL)

    # Truncate log to last 3000 chars to stay within token budget
    truncated_log = terminal_log[-3000:].strip() if len(terminal_log) > 3000 else terminal_log.strip()

    user_prompt = (
        f"Here is the Cinema Terminal output log from Ghost Creator AI:\n\n"
        f"```\n{truncated_log}\n```\n\n"
        "Please analyse this error and tell the user exactly how to fix it."
    )

    full_prompt = _SOFTWARE_BRIEFING + "\n\nCINEMA TERMINAL LOG:\n" + user_prompt

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=gemini_model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,       # lower temp → precise, factual answers
                max_output_tokens=1024,
                safety_settings=[
                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT",        threshold="BLOCK_ONLY_HIGH"),
                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH",       threshold="BLOCK_ONLY_HIGH"),
                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_ONLY_HIGH"),
                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
                ],
            ),
        )
        return response.text or "⚠ Ghost Agent returned an empty response. Please retry."
    except Exception as exc:
        log.warning("error_analyst: Gemini call failed: %s", exc)
        return (
            f"⚠ Ghost Agent could not reach Gemini: {exc}\n\n"
            "Check your Gemini API key in Settings → API Keys."
        )
