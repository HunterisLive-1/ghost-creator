# Agent Changes Log

Is file mein Cursor agents ke saare code updates/fixes ka note likha jayega.

## Entry Format

- Date/Time:
- Task:
- Changes:
  - `<file/path>`: kya change kiya
- Reason:

---

- Date/Time: 2026-04-15
- Task: Hindi script output + OmniVoice emotion/design settings + agent logging rule
- Changes:
  - `modules/scripter.py`: Hindi (`hi`) ko Hinglish se pure Devanagari me enforce kiya; OmniVoice backend select hone par emotion flags prompt rules add kiye.
  - `core/pipeline_runner.py`: script generation config me `tts_backend` pass kiya, taaki backend-aware prompt behavior apply ho.
  - `backends/tts/omnivoice_tts.py`: webui-style voice design logic add kiya (voice character, speaking style, quality preset, gender, extra tags, language hint) aur generation kwargs me wire kiya.
  - `gui/tabs/settings_tab.py`: OmniVoice ke liye naya Voice Design settings section add kiya aur save flow me config persist ki.
  - `core/config_manager.py`: OmniVoice design-related naye config keys defaults + env mapping me add kiye.
  - `.cursor/rules/agent-update-log.mdc`: rule update kiya ki har update/fix note `AGENT_CHANGES.md` me likhna mandatory hai.
  - `AGENT_CHANGES.md`: centralized agent change log file create ki.
- Reason:
  - Hindi selection par Roman/Hinglish output issue fix karna tha.
  - OmniVoice me webui-jaisa voice design control settings UI se dena tha.
  - Agent changes ka permanent written audit trail maintain karna tha.

---

- Date/Time: 2026-04-15
- Task: OmniVoice mode switch (Cloning vs Sound Design)
- Changes:
  - `gui/tabs/settings_tab.py`: OmniVoice section me segmented switch add kiya (`Voice Cloning` / `Sound Design`) aur save flow me `tts.omnivoice_mode` persist kiya.
  - `backends/tts/omnivoice_tts.py`: mode-aware synthesis add ki (clone/design); clone mode me reference audio required, design mode me reference bina generation; server/package dono paths me mode pass kiya.
  - `core/config_manager.py`: `tts.omnivoice_mode` ke liye default config, env map, aur `.env.local` template key add ki.
- Reason:
  - WebUI docs/reference ke hisaab se user ko direct mode toggle chahiye tha taaki easily decide kar sake: reference-based cloning use kare ya no-reference sound design.

---

- Date/Time: 2026-04-15
- Task: Remove subtitles from final video
- Changes:
  - `modules/video_builder.py`: ASS subtitle generation aur subtitle burn step remove kiya; final output ab direct audio-muxed video se banta hai (no subtitles).
- Reason:
  - User requirement tha ki final video me subtitles bilkul na aaye.

---

- Date/Time: 2026-04-15
- Task: torchaudio fix + video preview + OmniVoice server auto-start
- Changes:
  - `modules/voicer.py`: `_get_backend_map()` ko truly lazy kiya — sab backends ek saath import nahi hote, sirf selected backend load hota hai. `_get_backend()` mein loader lambda call fix ki.
  - `backends/tts/omnivoice_tts.py`: module-level `import torch` / `import torchaudio` hata ke functions ke andar move kiye (lazy). Phir completely rewrite kiya — **server mode** add kiya: jab `tts.omnivoice_server_path` set ho to `run.bat` auto-start, HTTP se synthesis (chatterbox jaisa protocol). **Package mode** fallback: `omnivoice` pip package se direct synthesis. `validate_config()` bhi mode-aware bana.
  - `requirements.txt`: `torch` version `2.10.0`, `torchaudio` version `2.11.0` pe update kiya; install URL note add ki.
  - `gui/components/video_preview.py`: **naya file** — cyberpunk-style video preview dialog (OS media player mein video auto-open, Approve/Cancel buttons).
  - `core/pipeline_runner.py`: video preview pause logic add kiya — `build_video()` ke baad pipeline block karti hai jab tak user approve ya cancel kare. `approve_video_preview()`, `cancel_from_video_preview()` methods add ki. `stop()` bhi preview event unblock karta hai.
  - `gui/tabs/pipeline_tab.py`: `_check_for_video_preview()` polling loop aur `_show_video_preview_window()` add kiya.
  - `config.json`: `video_preview_enabled: true`, `tts.omnivoice_server_path: "D:/omnivoice/OmniVoice/run.bat"`, `tts.omnivoice_autostart: true` add kiye.
  - `gui/tabs/settings_tab.py`: OmniVoice section mein "SERVER PATH (run.bat)" field + browse button + "Auto-start server" checkbox add kiya. Pipeline Behavior section mein "Pause for video preview before uploading" checkbox add kiya. Save logic bhi wire ki.
- Reason:
  - `torchaudio` install nahi tha, module-level import crash kar raha tha — fix kiya.
  - Users video preview chahte the upload se pehle — preview dialog implement kiya.
  - OmniVoice standalone server (`D:\omnivoice\OmniVoice\run.bat`) ka auto-start option settings mein dena tha.

---

- Date/Time: 2026-04-15
- Task: Remove Chatterbox TTS — cleanup
- Changes:
  - `backends/tts/chatterbox.py`: **deleted** — Chatterbox backend file hataya
  - `_check_server.py`: **deleted** — Chatterbox server-check helper script hataya
  - `backends/tts/omnivoice_tts.py`: config keys rename: `tts.chatterbox_url` → `tts.omnivoice_url`, `tts.chatterbox_reference_audio` → `tts.reference_audio`; docstring clean kiya
  - `config.json`: `chatterbox_url` → `omnivoice_url`, `chatterbox_reference_audio` → `reference_audio`, `chatterbox_path` removed
  - `core/config_manager.py`: defaults + ENV_LOCAL_MAP mein chatterbox keys rename/remove kiye; .env template update kiya
  - `config.py`: `CHATTERBOX_ENABLED`, `CHATTERBOX_API_URL`, `CHATTERBOX_REFERENCE_AUDIO`, `CHATTERBOX_LANGUAGE` constants remove kiye
  - `modules/voicer.py`: `"chatterbox"` entry remove kiya; `ensure_chatterbox_running()` legacy function remove kiya
  - `modules/scripter.py`: `"chatterbox"` backend check se remove kiya
  - `gui/tabs/settings_tab.py`: `_chatterbox_ref` → `_ref_audio` rename; `_browse_chatterbox_ref` → `_browse_ref_audio` rename; chatterbox compat shim remove; save logic + OmniVoice description update
- Reason:
  - User ne Chatterbox TTS use karna band kar diya — saari legacy code, config keys, aur files clean kar di gayi.

---

- Date/Time: 2026-04-15
- Task: Fix OmniVoice server not auto-starting before synthesis
- Changes:
  - `backends/tts/omnivoice_tts.py`: `_synthesize_server()` ke top par `ensure_running()` call add kiya — pehle server check/start hoga, phir HTTP synthesis chalega
- Reason:
  - Server mode mein `ensure_running()` kabhi call nahi ho raha tha — synthesis seedha HTTP pe jaati thi aur "connection refused" error aata tha.

---

- Date/Time: 2026-04-15
- Task: Remove Deepgram TTS + Kokoro TTS
- Changes:
  - `backends/tts/deepgram.py`: **deleted**
  - `backends/tts/kokoro_tts.py`: **deleted**
  - `modules/voicer.py`: `"deepgram"`, `"kokoro"`, `"kokoro_tts"` entries backend map se hataye; comment update kiya
  - `config.json`: `api_keys.deepgram`, `tts.deepgram_voice`, `tts.deepgram_model`, `tts.kokoro_model_path` remove kiye
  - `core/config_manager.py`: deepgram/kokoro se related defaults, ENV_LOCAL_MAP entries, aur .env template blocks remove kiye; TTS options comment update kiya
  - `requirements.txt`: `deepgram-sdk` aur `kokoro` lines remove ki
  - `gui/tabs/settings_tab.py`: TTS_DESCRIPTIONS se kokoro/deepgram entries hataye; API key hint row hataya; backend selector se DEEPGRAM aur KOKORO buttons hataye; Deepgram voice/model settings section hataya; save logic hataya
- Reason:
  - User ko Deepgram TTS aur Kokoro TTS ki zaroorat nahi — saari related code, config, aur UI clean kar di.

---

- Date/Time: 2026-04-15
- Task: Fix OmniVoice server double-launch when already running
- Changes:
  - `backends/tts/omnivoice_tts.py`: `_check_server()` ko `requests.get()` se TCP socket check pe switch kiya — ab sirf port open hai ya nahi check karta hai, HTTP response ki zaroorat nahi
- Reason:
  - OmniVoice server ka root URL GET request ka proper response nahi deta tha, isliye `_check_server()` False return karta tha aur run.bat dobara launch ho jaata tha — TCP check se yeh problem fix ho gaya.

---

- Date/Time: 2026-04-15
- Task: TTS progress messages GUI + terminal mein dikhana
- Changes:
  - `modules/voicer.py`: `run_voiceover()` mein `progress_callback=None` param add kiya; backend pe `_progress_cb` set kiya synthesis se pehle
  - `backends/tts/omnivoice_tts.py`: `_cb()` helper method add kiya (logger + GUI callback dono call karta hai); `_start_server(cb)` mein callback wire kiya — server launch, wait intervals, online confirmation; `ensure_running()` mein status messages add ki; `_synthesize_server()` mein har chunk ke liye progress emit kiya
  - `core/pipeline_runner.py`: `run_voiceover()` ko `progress_callback=_voice_progress` pass kiya jo Step 3 emit karta hai
- Reason:
  - Voice generation ke dauran GUI log aur terminal mein koi progress nahi dikhti thi — ab server start, har chunk, aur final done message GUI mein visible hai.

---

- Date/Time: 2026-04-15
- Task: Fix OmniVoice server launch (CREATE_NO_WINDOW conflict + timeout too short)
- Changes:
  - `backends/tts/omnivoice_tts.py`: `_start_server()` mein `CREATE_NO_WINDOW` + `cmd /c start /min` hataya → `CREATE_NEW_CONSOLE` + `cmd /c <bat>` se replace kiya; max wait 3 min se 8 min kiya; progress messages har 20s pe
- Reason:
  - `CREATE_NO_WINDOW` + `start` command conflict karte the — bat file silently fail ho rahi thi; 3 min bhi first-launch model load ke liye kafi nahi tha.

---

- Date/Time: 2026-04-15
- Task: Fix OmniVoice server port (8004 → 8765)
- Changes:
  - `config.json`: `tts.omnivoice_url` → `http://127.0.0.1:8765`
  - `core/config_manager.py`: default `omnivoice_url` → `http://127.0.0.1:8765`
- Reason:
  - OmniVoice WebUI `8765` port pe serve karta hai, pehle 8004 set tha jo galat tha — TCP check aur HTTP calls fail ho rahe the.

---

## OmniVoice WebUI HTTP API fix (404 → correct endpoints)

- Date/Time: 2026-04-15
- Task: Fix 404 errors when calling OmniVoice server
- Changes:
  - `backends/tts/omnivoice_tts.py`:
    - Removed `_http_one_chunk()` (was posting to non-existent `/tts` endpoint)
    - Added `_wait_for_model_ready()` — polls `GET /api/status` until model is loaded
    - Added `_http_generate()` — calls correct WebUI endpoints:
      - Clone mode → `POST /generate` with `multipart/form-data` (uploads WAV file directly)
      - Design mode → `POST /generate-design` with `multipart/form-data`
    - Rewrote `_synthesize_server()` — chains `ensure_running()` → `_wait_for_model_ready()` → `_http_generate()`
    - No chunking at HTTP level (server handles internally via quality preset)
    - Response is raw WAV bytes → `AudioSegment.from_wav()` → export MP3
- Reason: OmniVoice WebUI Flask app has no `/tts` endpoint. Correct endpoints are `/generate` (clone) and `/generate-design` (design). Reference audio must be uploaded as a file, not referenced by filename.

---

## Documentary Mode

- Date/Time: 2026-04-15
- Task: Add documentary pipeline mode — footage clips from YouTube + OmniVoice + FFmpeg assembly, no image generation
- Changes:
  - `modules/scripter.py`:
    - Added `_build_documentary_prompt()` — Gemini prompt that produces segments with `video_query` per segment
    - Added `_validate_documentary_script()` — validates/normalises the returned JSON
    - Added `generate_documentary_script()` — top-level function (supports Gemini/OpenAI/Ollama)
    - Added `_generate_raw_gemini/openai/ollama()` — raw text generators reused for documentary
  - `modules/video_fetcher.py` (new file):
    - `download_clip(query, output_path, max_duration)` — yt-dlp YouTube search + download
    - `fetch_clips(segments, output_dir, max_clip_duration)` — one clip per segment; returns None on failure
  - `modules/documentary_assembler.py` (new file):
    - `assemble_documentary(clips, audio_path, segments, output_dir, ...)` → final MP4
    - Distributes voiceover duration across clips proportional to text length
    - Trims or loops each clip (FFmpeg `-stream_loop`), scales to 9:16 or 16:9
    - Falls back to last-good clip or black filler when a clip is missing
    - Concatenates, then attaches voiceover audio; strips original clip audio
  - `core/pipeline_runner.py`:
    - Added mode check in `_run()` — branches to `_run_documentary()` when `pipeline_mode == "documentary"`
    - Added `_run_documentary()` — Steps 2→3→4→5→5.5→6 (no image gen step)
  - `gui/tabs/pipeline_tab.py`:
    - Added `_build_pipeline_mode_row()` — segmented button "🤖 Normal" / "🎬 Documentary"
    - Saves `pipeline_mode` to config on selection
  - `config.json`: Added `"pipeline_mode": "normal"`, `"documentary": {"max_clip_duration": 120}`
  - `core/config_manager.py`: Added defaults for `pipeline_mode` and `documentary.max_clip_duration`
  - `requirements.txt`: Added `yt-dlp>=2024.1.1`
- Reason: User requested a documentary mode where narration is split into segments, each mapped to a YouTube footage search query. No AI image generation. yt-dlp fetches clips, FFmpeg assembles with OmniVoice audio.

---

## Documentary Engine — Dedicated Tab with SHORT / LONG modes

- Date/Time: 2026-04-15
- Task: Move documentary to its own full tab; add SHORT (≤60s) and LONG (10-40 min) sub-modes
- Changes:
  - `gui/tabs/documentary_tab.py` (new file):
    - Full standalone `DocumentaryTab` class — mirrors PipelineTab layout
    - Two large mode cards: "⚡ SHORT FORM" (30-60s) and "🎞 LONG FORM" (10-40 min)
    - Clicking a card activates the mode, reconfigures the duration slider range
    - Documentary-specific purple accent colour (distinct from pipeline blue)
    - Topic entry, aspect ratio selector, max clip duration selector, language row
    - "▶ ROLL FILM" / "✂ CUT" control buttons
    - Hexagon step indicators for: Research → Script → Voice → Footage → Assembly → Upload
    - Purple-to-blue progress bar
    - "CINEMA TERMINAL" log box
    - Output preview with folder-open button
    - Own `doc_queue` so progress doesn't cross-contaminate with normal pipeline
  - `gui/app.py`:
    - Added `from gui.tabs.documentary_tab import DocumentaryTab`
    - Added `self.doc_queue = queue.Queue()` — separate queue for documentary
    - Added `"🎬 DOCUMENTARY"` tab between PIPELINE and SETTINGS
    - `DocumentaryTab` instantiated with `doc_queue`
  - `gui/tabs/pipeline_tab.py`:
    - Removed `_build_pipeline_mode_row()` call (mode selector no longer in pipeline tab)
  - `config.json` / `core/config_manager.py`:
    - Added `documentary.length_mode` (default "short")
    - Added `documentary.short_duration` (default 60)
    - Added `documentary.long_duration` (default 1200)
- Reason: User wanted the documentary to be its own page (not a mode inside PIPELINE), with clearly separated SHORT and LONG form modes with different duration ranges.

---

## Documentary Tab — Bug Fix: CTkLabel padx tuple error + LONG mode min duration

- Date/Time: 2026-04-15
- Task: Fix startup crash and update LONG mode minimum duration
- Changes:
  - `gui/tabs/documentary_tab.py`:
    - `_build_footage_settings()`: replaced invalid `padx=(30, 0)` on `CTkLabel` with an invisible spacer `CTkFrame` — tkinter labels don't accept tuple padding, caused `TclError: bad screen distance "30 0"` on startup
    - `_apply_mode("long")`: slider range changed from `600–2400s` (10–40 min) to `180–2400s` (3–40 min); default long duration updated to `600s`
    - Mode card label updated: "10 – 40 minutes" → "3 – 40 minutes"
  - `config.json`: `documentary.long_duration` default changed from `1200` to `600`
  - `core/config_manager.py`: `documentary.long_duration` default changed from `1200` to `600`
- Reason: App crashed on launch due to invalid padx tuple on CTkLabel. User also requested LONG mode minimum be 3 minutes instead of 10 minutes.

---

## Documentary Tab — Voice Engine Selector (OmniVoice / ElevenLabs / Edge TTS)

- Date/Time: 2026-04-15
- Task: Add voice engine selector row to documentary tab
- Changes:
  - `gui/tabs/documentary_tab.py`:
    - Added `_build_voice_engine_row()` — new row between Language and Footage Settings
    - Three selectable buttons: 🔊 OmniVoice, ⚡ ElevenLabs, 🆓 Edge TTS
    - Each button shows a hint label describing the engine
    - Added `_select_voice(code)` — saves choice to `documentary.voice_backend` config key
    - `_on_run()` updated — applies `documentary.voice_backend` to `tts.backend` before starting the pipeline so the voicer uses the chosen engine for that run
  - `config.json`: Added `documentary.voice_backend` key (default: `"omnivoice"`)
  - `core/config_manager.py`: Added `documentary.voice_backend` default (`"omnivoice"`)
- Reason: User requested ElevenLabs voice option in documentary mode. Added all three local/cloud engines (OmniVoice, ElevenLabs, Edge TTS) as quick-select buttons. The choice is saved separately from the main pipeline's TTS setting so they don't interfere.

---

## Version bump: v3 → v4

- Date/Time: 2026-04-15
- Task: Update all project files from v3 to v4
- Changes:
  - `gui/app.py`:
    - Docstring: "Ghost Creator AI v3" → "v4"
    - Window title: "Ghost Creator AI v3 — Neural Interface" → "v4"
    - Badge label: "v3.0 PRO" → "v4.0 PRO"
  - `build.bat`:
    - Header banner: "v3" → "v4"
    - Footer message updated to "Ghost Creator AI v4"
    - Removed stale `--hidden-import` entries for deleted backends: `chatterbox`, `kokoro_tts`, `deepgram`
    - Removed `--collect-all kokoro`, `--collect-all deepgram`
    - Added new v4 `--hidden-import` entries: `gui.tabs.documentary_tab`, `gui.components.video_preview`, `modules.video_fetcher`, `modules.documentary_assembler`, `backends.tts.omnivoice_tts`
    - Added `--hidden-import yt_dlp` and `--collect-all yt_dlp` for documentary mode
    - Updated footer notes (OmniVoice instead of Chatterbox; yt-dlp note added)
  - `installer_v3.iss` → `installer_v4.iss` (file renamed):
    - `MyAppVersion`: "3.1" → "4.0"
    - `OutputBaseFilename`: "GhostCreatorAI_v3_Setup" → "GhostCreatorAI_v4_Setup"
    - Comment updated: Chatterbox reference → OmniVoice reference
    - Old `installer_v3.iss` deleted
- Reason: User requested full project version bump to v4 to reflect the major new features added (Documentary Engine, OmniVoice WebUI integration, removed Chatterbox/Deepgram/Kokoro).

---

## Fix UnicodeDecodeError + yt-dlp Clip Download Failures

- Date/Time: 2026-04-15
- Task: Fix cp1252 UnicodeDecodeError in subprocess calls and yt-dlp clips 2 & 3 failing to download
- Changes:
  - `modules/documentary_assembler.py`:
    - `_ffmpeg()`: added `encoding="utf-8", errors="replace"` to `subprocess.run` — cp1252 couldn't decode UTF-8 FFmpeg output (especially Hindi folder paths)
    - `_probe_duration()`: same fix applied to `ffprobe` subprocess call
  - `modules/voicer.py`:
    - `apply_pace_speed()` subprocess call: added `encoding="utf-8", errors="replace"` — same cp1252 issue during atempo FFmpeg run
  - `modules/video_fetcher.py`:
    - `download_clip()`: removed `--match-filter "duration <= 120"` which was filtering out virtually all YouTube results (most videos are >2 min)
    - Removed `--no-part` flag which conflicted with multi-stream merging (yt-dlp needs temp files when merging video+audio)
    - Added `--socket-timeout 30`, increased retries to 5
    - Improved output file detection with broader extension fallback
- Reason: Only 1 of 3 clips downloaded because `--match-filter duration <= 120` rejected all YouTube search results longer than 2 minutes. `--no-part` caused merge failures. Subprocess encoding was Windows-default cp1252 which cannot decode UTF-8 output from FFmpeg/yt-dlp.

---

## Video Fetcher — Pexels API + yt-dlp Speed Fix

- Date/Time: 2026-04-15
- Task: Fix slow yt-dlp downloads and photo slideshow videos being downloaded instead of real footage
- Changes:
  - `modules/video_fetcher.py` (complete rewrite):
    - Added `_try_pexels()` — searches Pexels stock footage API and directly streams download; real HD footage, no watermarks, downloads in seconds
    - Added `_try_youtube()` — yt-dlp fallback with `--download-sections "*00:00:00-00:01:30"` to download only the first 90 seconds (was downloading full 2-hour videos before); appends `"footage b-roll"` to every query to avoid photo slideshows; added `--concurrent-fragments 4` and `--max-filesize 150M`
    - `download_clip()`: now tries Pexels first, falls back to YouTube
    - Pause between clips reduced from 2s to 1s
  - `config.json`: added `"pexels": ""` to `api_keys` block
  - `core/config_manager.py`: added `"pexels": ""` to `api_keys` defaults
  - `gui/tabs/settings_tab.py`:
    - Added `"api_keys.pexels"` entry to `API_KEY_INFO` dict with hint pointing to pexels.com/api
    - Added `("Pexels API Key", "api_keys.pexels")` to `_build_api_keys_section` keys list — automatically saved/loaded via existing `_key_entries` loop
- Reason: yt-dlp was downloading full YouTube videos (120 MB+ per clip, 3 min per clip). Searches returned photo slideshows instead of real footage. Pexels provides professional stock footage via direct CDN links in seconds. yt-dlp fallback now only downloads the first 90 seconds needed by the assembler.

---

## Build — Missing hidden imports + installer fix

- Date/Time: 2026-04-15
- Task: Pre-build audit of build.bat and installer_v4.iss — add missing PyInstaller hidden imports and fix optional file handling
- Changes:
  - `build.bat`:
    - Added `--hidden-import gui.components.script_review` — was missing, used by both pipeline_tab and documentary_tab
    - Added `--hidden-import gui.components.image_review` — was missing, used by pipeline_tab
    - Added `--hidden-import gui.components.activation_window` — was missing, used at startup
    - Fixed note: yt-dlp IS bundled via `--collect-all yt_dlp`; corrected end-user note to say no separate install needed
  - `installer_v4.iss`:
    - Added `skipifsourcedoesntexist` flag to `workflow_api.json` entry — installer was failing silently if the file didn't exist
- Reason: Three GUI component modules were lazy-imported at runtime so PyInstaller wouldn't discover them automatically. Without explicit `--hidden-import`, the exe would crash with `ModuleNotFoundError` on script review, image review, or activation windows.

---

## Fix: ImportError in video_fetcher.py — wrong config import

- Date/Time: 2026-04-15
- Task: Fix `ImportError: cannot import name 'get' from 'config'` crashing the documentary pipeline at clip download step
- Changes:
  - `modules/video_fetcher.py`:
    - Line 21: replaced `from config import get_logger, get as config_get` → `from config import get_logger` + `from core.config_manager import config`
    - Line 89: replaced `config_get("api_keys.pexels", "")` → `config.get("api_keys.pexels", "")` to match the correct API
- Reason: `config.py` only exposes utility functions (`get_logger`, `get_ffmpeg_executable`, etc.). Config values are accessed via `core.config_manager.config.get()`. The rewrite of `video_fetcher.py` mistakenly tried to import `get` directly from `config.py`.

---

## Documentary — Clip Count Selector + Portrait Pexels Search

- Date/Time: 2026-04-15
- Task: Add manual clip count selector in documentary UI; use portrait orientation from Pexels when aspect ratio is 9:16
- Changes:
  - `modules/video_fetcher.py`:
    - `_try_pexels()`: reads `aspect_ratio` from config; passes `orientation=portrait` to Pexels API when ratio is `9:16`, `orientation=landscape` for `16:9` — avoids needing to crop/reframe vertical footage
  - `modules/scripter.py`:
    - `generate_documentary_script()`: added `n_segments: int = 0` parameter; when > 0 uses it directly (clamped 3–20) instead of auto-calculating from duration
  - `core/pipeline_runner.py`:
    - `_run_documentary()`: reads `documentary.segments` from config and passes it as `n_segments` to `generate_documentary_script()`
  - `gui/tabs/documentary_tab.py`:
    - `_build_footage_settings()`: added "Clips" `CTkOptionMenu` (Auto / 3 / 5 / 7 / 10 / 15 / 20) before the clip duration dropdown
    - Added `_save_segments()` callback — saves `0` for "Auto" or the chosen integer to `documentary.segments`
  - `config.json`: added `"documentary.segments": 0`
  - `core/config_manager.py`: added `"documentary.segments": 0` default
- Reason: User reported all 3 clips were used regardless of desired count. Also, 9:16 Shorts footage was landscape from Pexels requiring FFmpeg crop — now portrait videos are fetched directly so no quality is lost.

---

## Documentary Tab — Script Review & Video Preview windows not appearing

- Date/Time: 2026-04-15
- Task: Fix missing script review panel and video preview in documentary mode
- Changes:
  - `gui/tabs/documentary_tab.py`:
    - `_on_run()`: added `self.after(500, self._check_for_script_review)` and `self.after(500, self._check_for_video_preview)` after starting the runner — these polling loops were missing so neither review window ever triggered
    - Added `_check_for_script_review()` — polls `runner.waiting_for_script_review` every 500ms
    - Added `_show_script_review_window()` — opens `ScriptReviewWindow` with approve/regenerate/cancel callbacks
    - Added `_check_for_video_preview()` — polls `runner.waiting_for_video_preview` every 500ms
    - Added `_show_video_preview_window()` — opens `VideoPreviewWindow` with approve/cancel callbacks
- Reason: Documentary tab had its own `PipelineRunner` and queue but never started the polling loops that pipeline_tab.py uses to detect when the runner is waiting for user input. Script review and video preview windows simply never appeared.

---

- Date/Time: 2026-04-19
- Task: yt-dlp bundled .exe — documentary YouTube fallback
- Changes:
  - `modules/video_fetcher.py`: `_yt_dlp_exe()` ko `_yt_dlp_cmd()` se replace kiya — PyInstaller frozen app me `GhostCreatorAI.exe -m yt_dlp` use hota hai; dev me pehle `yt-dlp` PATH, warna `python -m yt_dlp`.
- Reason: `build.bat` pehle se `--collect-all yt_dlp` bundle karta tha, lekin code sirf external `yt-dlp` CLI dhundhta tha — installed users ke paas PATH par binary nahi hoti, isliye documentary YouTube download fail hota tha.

---

- Date/Time: 2026-04-19
- Task: build.bat Windows console - garbled Unicode in echo lines
- Changes:
  - `build.bat`: `echo` lines me em-dash (`—`) aur arrow ko ASCII se replace kiya (`-`, `Settings, TTS tab`) taaki CMD default code page par `Gamma-Copyright` style mojibake na aaye.
- Reason: User build log me `v4 ΓÇö Build` jaisa text dikh raha tha — UTF-8 characters CMD me sahi render nahi hote.

---

- Date/Time: 2026-04-19
- Task: License — same PC after Windows format / reinstall
- Changes:
  - `core/license.py`: `get_machine_id()` ab Windows par SMBIOS system UUID (`Win32_ComputerSystemProduct.UUID`) par based v2 id use karta hai — OS reinstall ke baad bhi same hardware par id stable; purana v1 hash `_legacy_machine_id_hex()` decrypt + API field `machine_id_legacy` ke liye rakha; `load_license()` dono Fernet keys se decrypt try karti hai; `verify_with_server()` body me `machine_id_legacy` bhejta hai jab v2 se alag ho; `is_licensed()` me local `machine_id` mismatch par server se migrate karke save; `already_activated` message clarify (reinstall / seat reset).
- Reason: Pehle id MAC + hostname par thi — format ke baad MAC/order badal sakta tha, server purani binding dekhta tha aur "already on another device" jaisa response; SMBIOS UUID same machine par reinstall ke baad bhi match karta hai, aur server ko migration ke liye legacy id milti hai.

---

- Date/Time: 2026-04-19
- Task: build.bat — Playwright / upload note vs actual uploader behavior
- Changes:
  - `build.bat`: Post-build notes me `playwright install chromium` hata kar clarify kiya — `modules/uploader.py` `channel="chrome"` use karta hai (system Google Chrome), isliye end users ko Python / `playwright install` ki zaroorat nahi sirf upload ke liye; Chrome install ka short note.
- Reason: Pehle wala message galat expectation deta tha; codebase bundled Chromium se upload nahi karti.
