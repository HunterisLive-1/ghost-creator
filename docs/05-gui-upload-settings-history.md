# GUI — Upload, Settings, History

## Upload tab

Upload any local MP4 to YouTube without running the full pipeline.

1. **BROWSE** — select video file
2. Fill **title**, **description**, **tags**, **visibility** (Public / Unlisted / Private / Draft)
3. **AI FILL (Gemini)** — generate metadata from filename
4. **START UPLOAD** — streams log output in the panel

Requires a configured Chrome profile (Settings) and signed-in YouTube account.

---

## Settings tab

All persistent configuration. Click **[ SAVE CONFIG ]** after changes.

### API Keys

- **Gemini** — required for scripting and AI features
- **ElevenLabs** — optional (More API keys section)
- **Pexels** — optional, improves footage download speed/quality

### Audio (TTS)

- Backend selector: OmniVoice / Edge TTS / ElevenLabs
- OmniVoice sub-panel: clone vs design mode, server path, reference audio, model ID, voice design knobs
- Edge / ElevenLabs sub-panel: voice name or ID, stability sliders

### Run Behavior

- **Pause for script review** — enable Script Review modal
- **Narration language** — default pipeline language
- **Output folder** — relative or absolute path for finished runs
- **YouTube upload** — enable/disable + visibility mode (unlisted / public / draft)
- **AI script provider** — Gemini (cloud) or Ollama (local LLM)
- **Gemini model** or **Ollama URL + model**

### Core Parameters

- **Chrome profiles** — manage YouTube upload sessions
- **Logo watermark** — PNG/JPG overlay on final export (position, scale, opacity)

### About

- App version and device name (informational)
- **OPEN DOCUMENTATION** — opens this guide in your browser

### Footer

- Path to `.env.local` — **OPEN IN EDITOR** for direct key editing

---

## History tab

Shows the **10 most recent** completed runs from the output folder.

Per run card:

- Title, timestamp, topic, description snippet, duration
- **Open Folder** — show run directory
- **Re-render (FFmpeg)** — re-assemble from saved `documentary_editor.json` + clips (if available)
- **Play Video** — open MP4 in default player

After re-render, the app can jump to **Upload** tab with the new file pre-filled.

---

## Editor tab (React Timeline SDK)

The in-app **Ghost Editor** uses `@keplar-404/react-timeline-editor` with clips served via `GET /api/local-file`.

- **Load** — reads `documentary_editor.json` + `clips_for_edit/e_XX.mp4` from a History run
- **Edit** — reorder/resize segments, swap clips, subtitle style, background music, transitions/effects
- **Save** — writes `documentary_editor.json` back to the run folder
- **Export (FFmpeg)** — native re-render via `/api/history/rerender` (not FFmpeg.wasm)

**Manual checklist:**
1. Open run → preview shows video at 0:00 (not black)
2. Timeline spans full project duration; playhead scrolls with transport
3. Swap clip, change duration, Save → JSON on disk matches
4. Export → MP4 with subtitles + optional transition
5. Enable "Pause for Ghost Editor" → pipeline stops after clips ready → Continue → final MP4

**Pipeline editor mode** (Settings → Pause for Ghost Editor): after voice-synced clips are built, the pipeline pauses. Use **OPEN EDITOR** on the Documentary tab, save edits, then **CONTINUE PIPELINE** to assemble the final MP4.

Preview is approximate; export always uses the backend FFmpeg assembler (`core/video_effects.py` maps transitions/effects).
