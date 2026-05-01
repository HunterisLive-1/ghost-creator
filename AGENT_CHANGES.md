# Agent Changes Log

Is file mein Cursor agents ke saare code updates/fixes ka note likha jayega.

## Entry Format

- Date/Time:
- Task:
- Changes:
  - `<file/path>`: kya change kiya
- Reason:

---

- Date/Time: 2026-04-30 (session 2)
- Task: Ghost Editor — pre-trim before editor, VLC preview, timeline, voice/music tools, BG mix, fast segment pass
- Changes:
  - `core/pipeline_runner.py`: Step 4.5 pe ab `clips_for_edit/` pe **voice-aligned FFmpeg trim/loop** (`_trim_or_loop_clip`) chalti hai — wahi progress user ko editor se pehle dikhti hai; editor ke baad `audio_path` / bg ctx se step 5 read hota hai.
  - `modules/documentary_assembler.py`: Pehle **stream-copy fast trim** try jab clip lambi ho; mix optional **background music** (`amix`) voice ke niche; naye args `bg_music_path` / `bg_music_volume`.
  - `core/vlc_helper.py`: Windows par VLC folder detect + `python-vlc` instance; error par throw nahi.
  - `core/clip_manager.py`: `trim_audio`, `trim_background_music` (voice/bed FFmpeg cut).
  - `gui/components/clip_editor.py`: VLC embed preview (fail par message, pipeline nahi rukti); **timeline canvas** drag se reorder; **VOICE** tab replace+trim; **MUSIC** trim + volume; `on_done` 6th arg `audio_path`; re-assemble passes bg + music.
  - `gui/tabs/documentary_tab.py` / `history_tab.py`: `on_done` callbacks updated; history re-render passes bg + edited voice.
  - `requirements.txt`: `python-vlc` add (preview ke liye; VLC app alag install).
- Reason:
  - User: clipping/editor order, timeline + preview, VLC optional without crash, replace voice + BG music + trim, final assemble me music mix; final pass fast jab clips pehle se fit hon.

---

- Date/Time: 2026-04-30 (session)
- Task: Complete documentary Ghost Editor flow — manual cuts, history re-edit, syntax fix
- Changes:
  - `core/pipeline_runner.py`: After footage download, copy full-length sources into `clips_for_edit/` (no auto pre-trim to voice timing); build `ClipInfo` list with per-segment target durations; pause for Ghost Editor; write `documentary_editor.json` beside `metadata.json` for re-edit.
  - `core/clip_manager.py`: `ClipInfo.target_duration_sec`; `load_clips(..., target_durations=…)`; preserve targets in trim/split/replace; add `export_srt_file` / `export_clips_to_zip` aliases for the editor.
  - `modules/documentary_assembler.py`: `_clip_source_path()` so assembly accepts `Path` or `ClipInfo`.
  - `gui/components/clip_editor.py`: Coerce non-`ClipInfo` inputs via `load_clips`; show voice timing hint per clip; fix SRT `start`/`end` fields; fix trim/split/replace to match `clip_manager` APIs.
  - `gui/tabs/documentary_tab.py`: Remove stray broken lines after `ClipEditorWindow(...)` (syntax error).
  - `gui/tabs/history_tab.py`: List only newest **10** runs; add **Ghost Editor** button when `documentary_editor.json` + `voiceover.mp3` exist; re-assemble on DONE in a background thread and refresh list.
  - `gui/tabs/settings_tab.py`: Relabel `video_preview_enabled` checkbox/hint to Ghost Editor before assembly.
- Reason:
  - Prior agent left invalid Python in `documentary_tab` and auto pre-trimmed clips so manual cutting matched almost no workflow; users need full rushes + voice-aligned targets, snapshot file for past runs, and a bounded history UI for re-opens.

---

- Date/Time: 2026-04-30 16:28
- Task: Settings GUI cleanup for documentary-only flow
- Changes:
  - `gui/tabs/settings_tab.py`: Script provider UI se OpenAI option/model/key controls remove kiye; provider ab Gemini + Ollama only.
  - `gui/tabs/settings_tab.py`: Settings se aspect ratio selector remove kiya (resolution selection), target duration field remove kiya, aur documentary subtitle checkbox remove kiya.
  - `gui/tabs/settings_tab.py`: TTS section se voice post-process + smart silence checkboxes remove kiye; save logic se unke config writes bhi hata diye.
  - `gui/tabs/documentary_tab.py`: Footage settings me `aspect_ratio` selector (9:16 / 16:9) add kiya aur save flow wire kiya, taaki ratio control documentary page par hi rahe.
- Reason:
  - User requirement: OpenAI GUI se hatana; duration/resolution/subtitles/post-process controls Settings se remove karke documentary-centric UX rakhna.

---

- Date/Time: 2026-04-30 16:10
- Task: Refresh build.bat for current documentary-only repo
- Changes:
  - `build.bat`: version banner/footer `v4.1` kiya.
  - `build.bat`: PyInstaller hidden-import list se deleted modules/backends remove kiye (`pipeline_tab`, `image_review`, `image_prep`, `video_builder`, `img2video`, old image backends, `google_tts`).
  - `build.bat`: removed package-level stale imports/collects (`google.cloud.texttospeech`, `fal_client`, `replicate`, `soundfile`, `tqdm`, `websocket`) and kept active ones only.
  - `build.bat`: removed `%WORKFLOW_ARG%` and workflow var block usage from PyInstaller command.
- Reason:
  - User ne repo scan karke `build.bat` ko current codebase ke hisaab se update karne ko bola; old deleted modules ki wajah se build bloat/fail risk tha.

---

- Date/Time: 2026-04-30 16:03
- Task: Remove OpenAI dependency from project requirements
- Changes:
  - `requirements.txt`: `openai>=1.0.0` remove kiya; scripting section label `Gemini + OpenAI` se `Gemini` kiya.
- Reason:
  - User ne confirm kiya ki OpenAI ab project mein required nahi hai.

---

- Date/Time: 2026-04-30 16:00
- Task: Requirements cleanup for external OmniVoice server setup
- Changes:
  - `requirements.txt`: OmniVoice local stack remove kiya — `omnivoice`, `torch`, `torchaudio`, `soundfile` delete; TTS section comment update kiya ki OmniVoice external server path se run hota hai.
- Reason:
  - User architecture mein OmniVoice alag GitHub repo/environment mein install/run hota hai; is project mein local OmniVoice package dependencies unnecessary thi.

---

- Date/Time: 2026-04-30 15:56
- Task: Requirements cleanup — remove unused dependency
- Changes:
  - `requirements.txt`: `tqdm>=4.66.0` remove kiya (repo-wide import/usage nahi mila).
- Reason:
  - User ne unused requirements cleanup bola tha; scan ke baad `tqdm` hi clearly unused nikla.

---

- Date/Time: 2026-04-30 15:50
- Task: OmniVoice TTS server-only (remove package fallback)
- Changes:
  - `backends/tts/omnivoice_tts.py`: module docstring ko server-only banaya; `ensure_running()` mein missing `tts.omnivoice_server_path` par hard fail + user-facing message add kiya; `synthesize()` se package fallback path disable karke server path mandatory kiya; `validate_config()` se package-mode validation hata kar server-path-required validation enforce ki.
- Reason:
  - User requirement ke hisaab se OmniVoice ke liye package mode nahi chahiye tha; backend ko strictly server mode tak limit karna tha.

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

---

- Date/Time: 2026-04-23
- Task: OmniVoice local server — read timeout on long scripts (CPU)
- Changes:
  - `backends/tts/omnivoice_tts.py`: server mode ab poori script ek hi HTTP request mein nahi bhejta; package mode jaisa text chunking + per-chunk retry + `AudioSegment` join; oversize bina-viram sentences ke liye hard split; HTTP `timeout=(connect, read)` jahan read `tts.omnivoice_http_read_timeout` se aata hai (min 120s).
  - `core/config_manager.py`: default + env `OMNIVOICE_HTTP_READ_TIMEOUT` / `tts.omnivoice_http_read_timeout` (default 10800) add.
- Reason: Lambe voiceover (jaise 8000+ chars) CPU pe ek hi request mein 300s+ lag rahe the aur `Read timed out` se pipeline fail; chhote requests + lamba per-chunk read timeout is fix karta hai.

---

- Date/Time: 2026-04-23
- Task: Script prompt — plain voiceover (no emotion flags / symbols)
- Changes:
  - `modules/scripter.py`: `_omnivoice_emotion_rules` hata kar `_voiceover_plain_format_rules` add — Gemini ko continuous spoken prose (shorts style) likhne ko kehta hai; `voiceover_text`/segment `voiceover` me koi [flag], emoji, ya extra markup nahi; documentary + main JSON prompt dono me apply; `tts_backend` ab `_build_prompt` / `_build_documentary_prompt` me use nahi (dead param hata diye).
- Reason: User sample jaisa clean Hindi TTS chahiye tha; purana OmniVoice per-sentence [excited] etc. wala rule models ko galat output deta tha.

---

- Date/Time: 2026-04-23
- Task: Documentary — more auto clips on long video + 1.2× final pace
- Changes:
  - `modules/scripter.py`: auto segment count ab `target_duration / 12` (pehle `/25`), cap `50` (pehle `20`) — lambe target par zyada transitions; `DOC_AUTO_SEG_EVERY_S` / `DOC_SEG_MAX` constants.
  - `modules/documentary_assembler.py`: `playback_speed` param; `1.0` par purana copy-mux; warna `setpts` + `atempo` se video + voice dono same factor (0.5–2.0 clamp).
  - `core/pipeline_runner.py`: `documentary.playback_speed` config se `assemble_documentary` ko pass (default 1.2).
  - `core/config_manager.py`: `documentary.playback_speed` default `1.2`.
  - `gui/tabs/documentary_tab.py`: Clips menu me `25`–`50` options; short/long card copy update.
- Reason: Lambe documentary me zyada clip cuts chahiye the; final output slow lag raha tha — 1.2× synced speed se pace tez.

---

- Date/Time: 2026-04-23
- Task: Script review — 25+ scenes; UI only showed 15
- Changes:
  - `gui/components/script_review.py`: hardcoded `_display_cap = 15` hata diya; ab saare `image_prompts` rows scrollable list me; approve par tail-merge logic hata (ab har row editable/reviewable).
- Reason: User ne 25 clips select kiye the par Step 2 me sirf pehle 15 scenes dikh rahe the.

---

- Date/Time: 2026-04-23
- Task: OmniVoice TTS — Ghost ka output WebUI jaisa (clone quality)
- Changes:
  - `backends/tts/omnivoice_tts.py`: WebUI-aligned — manual `ref_text` only (no Whisper); `/api/status` `defer_load`; fast `num_step` 16; optional `omnivoice_ref_voice_name`.
  - `core/config_manager.py`: `omnivoice_ref_transcript` + `omnivoice_ref_voice_name` (no auto-transcribe key).
  - `gui/tabs/settings_tab.py`: Auto-transcribe checkbox + transcript hint.
- Reason: Standalone `webui.py` reference text ASR + duration se sahi clone deta tha; Ghost static placeholder transcript bhejta tha — ratio/duration kharab.

---

- Date/Time: 2026-04-23
- Task: Voiceover — automatic FFmpeg post-process (no manual tuning)
- Changes:
  - `modules/voicer.py`: `run_voiceover` ab pace ke baad `_apply_voice_post_process` — `highpass=f=80` + EBU R128 `loudnorm` (configurable LUFS); fail par original audio.
  - `core/config_manager.py`: `tts.voice_post_process` (default 1), `tts.voice_post_target_lufs` (default -16); env `VOICE_POST_PROCESS` / `VOICE_POST_TARGET_LUFS`; template lines.
  - `gui/tabs/settings_tab.py`: TTS section me post-process checkbox.
- Reason: User ne bina human touch TTS output aur improve karne ko kaha; sab backends par same last-step polish.

---

- Date/Time: 2026-04-23
- Task: Voice post — smart silence (gap preserve + long dead-air trim)
- Changes:
  - `modules/voicer.py`: FFmpeg `silenceremove` — `stop_duration` = sirf itni se zyada lambi chup hat-ti hai (default 0.42s); `stop_silence` = wahan ~0.22s natural gap rehta hai; shuru/end trim + `loudnorm`; fallback chain: full → edges-only → hpf+loudnorm.
  - `core/config_manager.py`: `tts.voice_post_silence_*` keys + .env `VOICE_POST_SILENCE_*`.
  - `gui/tabs/settings_tab.py`: “Smart silence” checkbox + hint.
- Reason: User ko silence detect/cut chahiye tha, lekin word/sentence beech ka spacing zyada tight ya loose na ho.

---

- Date/Time: 2026-04-23
- Task: Settings tab — shorter scroll, foldable blocks, lean copy
- Changes:
  - `gui/tabs/settings_tab.py`: `_add_foldable()` helper; Quick start banner collapsible (default band); API keys me sirf Gemini upar, baaki 7 “More API keys (optional)” fold; TTS: post-process + smart silence upar, OmniVoice block fold (default khol), Edge/Eleven fold (default band); ComfyUI URL fold; `TTS_DESCRIPTIONS` / `IMG_DESCRIPTIONS` chhote; desc labels chhota font / wrap.
- Reason: User ne settings bahut lamba + UI improve; scroll kam, power users expand kar sakte hain.

---

- Date/Time: 2026-04-23
- Task: Documentary — clips count cap 100
- Changes:
  - `modules/scripter.py`: `DOC_SEG_MAX` 50 → 100 (auto + manual cap).
  - `gui/tabs/documentary_tab.py`: Clips dropdown 60–100; help text "up to 100".
  - `core/config_manager.py`: default comment `max 100`.
- Reason: User ne Documentary Clips max 100 chaha.

---

- Date/Time: 2026-04-23
- Task: Aspect ratio — single place in UI + apply on tap (Pexels portrait/landscape)
- Changes:
  - `gui/tabs/settings_tab.py`: `CTkSegmentedButton` (9:16 / 16:9) ab `command=_on_aspect_segment_change` se turant `config.set("aspect_ratio", ...)` + `config.save()`; hint copy update — [ SAVE CONFIG ] pe depend nahi.
  - `gui/tabs/documentary_tab.py`: Footage se duplicate 9:16/16:9 buttons hata ke ek readout (Settings se source + Pexels portrait/landscape); SHORT form card se “YouTube Shorts” wali zabardasti vertical imply hata; run log + `_refresh_doc_aspect_lbl` se current value dikhe.
- Reason: Teen jagah ratio + Settings par change bina [ SAVE CONFIG ] ke pipeline 9:16 use karti thi; Pexels `video_fetcher` me orientation config se aata hai — config turant sahi rakhna + ek hi controlling UI.

---

- Date/Time: 2026-04-23
- Task: `build.bat` — reliable one-click .exe build
- Changes:
  - `build.bat`: Har run pe `cd /d "%~dp0"`; `gui\app.py` + `venv\Scripts\activate.bat` check with clear errors; `python -m pip` / `python -m PyInstaller` (PATH-independent); `pyinstaller>=6.0` on first install; `--noconfirm` taaki repeat build prompt na roke.
- Reason: User ne .exe build karna; script root/venv miss hone par pehle se fail + PyInstaller `python -m` se build stable.

---

- Date/Time: 2026-04-23
- Task: Documentary — post-preview regen (audio / video) then save-upload
- Changes:
  - `core/pipeline_runner.py`: `set_video_preview_decision(approve|cancel|regen_audio|regen_video)`; `stop()` se preview wait wake; standard pipeline 5.5 ab action read; `_run_documentary` 5.5 loop + `_doc_regen_ctx` + `_documentary_regen_audio` / `_documentary_regen_video` (TTS+mux vs re-fetch+mux; config re-read).
  - `gui/components/video_preview.py`: optional `on_regen_audio` + `on_regen_video` — documentary 2 naye buttons, taller window + copy.
  - `gui/tabs/documentary_tab.py`: regen callables se `set_video_preview_decision`; `_doc_preview_open` guard taaki 500ms poll se modal stack na bane; cancel pe flag clear.
- Reason: User ko preview ke baad sirf audio ya footage dubara, phir approve par upload/local; normal Pipeline approve/cancel same.

---

- Date/Time: 2026-04-24
- Task: Documentary preview — edit plan / narration, then regen (improve before regenerate)
- Changes:
  - `core/pipeline_runner.py`: `_distribute_length_by_weights`, `_resync_segment_voiceovers`, `apply_documentary_preview_script()` — post-preview narration + `video_query` patch with proportional per-segment voiceover split; metadata title sync when present.
  - `gui/components/script_review.py`: optional `show_regenerate_from_llm` (default True), `window_title` / `step_label` / `top_hint` / `approve_button_text` for post-preview “save plan” mode.
  - `gui/components/video_preview.py`: optional `on_edit_plan` + “Edit plan / narration” button; documentary subtitle when edit is available.
  - `gui/tabs/documentary_tab.py`: `on_edit_plan` opens `ScriptReviewWindow` from `_doc_regen_ctx`, applies via runner; `on_regen_*` + explicit `_check_for_video_preview` reschedule.
- Reason: Regen with unchanged script/Pexels queries had little benefit; user can now fix narration and scene search terms, save, then regenerate audio and/or video.

---

- Date/Time: 2026-04-24
- Task: Voicer — no FFmpeg atempo on TTS (natural speed)
- Changes:
  - `modules/voicer.py`: `_apply_pace_speed` + `PACE_ATEMPO` hata diya; TTS ke baad seedha `_apply_voice_post_process`.
  - `core/config_manager.py`: TTS post-process comment se “pace” mention update.
- Reason: User ne “Pace speed applied (1.18x)” sahi nahi; voice normal/unaltered speed, baaki (Pipeline **video** pace / Ken Burns) same.

---

- Date/Time: 2026-04-24
- Task: OmniVoice — bade, smart text chunks (voiceover)
- Changes:
  - `backends/tts/omnivoice_tts.py`: `tts.omnivoice_text_chunk_chars` (clamp 120–800, default 400); blank-line paragraph split + single-newline → space; logs/progress mein `≤N chars`.
  - `core/config_manager.py` + `ENV_LOCAL_MAP` (`OMNIVOICE_TEXT_CHUNK_CHARS`).
  - `gui/tabs/settings_tab.py`: OmniVoice **TEXT CHUNK (chars)** OptionMenu (280–800).
  - `gui/tabs/documentary_tab.py`: OmniVoice hint line — chunk Settings se.
  - `modules/voicer.py`: docstring mein pointer.
- Reason: Zyada chars per chunk = kam TTS pieces, better flow; abhi 220 tha, user ne bada + smart chaha.

---

- Date/Time: 2026-04-24
- Task: OmniVoice — sentence/clause–first chunking, ~800 chars, 5h+ read timeout
- Changes:
  - `backends/tts/omnivoice_tts.py`: `_split_raw_sentences` / `_split_oversize_natural` (comma/`:—` se pehle) / `_pack_units` — ab character mid-sentence tabhi jab beech mein koi `।.!?` / comma break na mile; `CHUNK_SIZE_FALLBACK` 800; `CHUNK_TIMEOUT` 18000s, `_http_read_timeout_sec` max 24h cap.
  - `core/config_manager.py`: `omnivoice_text_chunk_chars` 800, `omnivoice_http_read_timeout` 18000.
  - `gui/tabs/settings_tab.py`: text-chunk / timeout hints; save fallback 800.
- Reason: Alag-alag tone + pause issues char-wise split se; 40+ min job ke liye 3–4h+ per HTTP safe.

---

- Date/Time: 2026-04-24
- Task: OmniVoice — no text chunking; no FFmpeg post on omnivoice
- Changes:
  - `backends/tts/omnivoice_tts.py`: server + package dono me poori script ek hi generate call; `_split_text` / chunk helpers hata; `_normalize_input_text` sirf danda normalize; `_synthesize_one_pkg` (pehle multi-chunk loop).
  - `modules/voicer.py`: `tts.backend == omnivoice` par `_apply_voice_post_process` skip.
  - `core/config_manager.py`: `tts.omnivoice_text_chunk_chars` + `OMNIVOICE_TEXT_CHUNK_CHARS` env map hata.
  - `gui/tabs/settings_tab.py`: TEXT CHUNK (chars) row + save hata.
  - `gui/tabs/documentary_tab.py`: OmniVoice hint line update.
- Reason: User ne full audio single pass + post-process hatane + chunk settings hatane ko kaha.

---

- Date/Time: 2026-04-24
- Task: Documentary — default playback 1× (no speed-up)
- Changes:
  - `core/config_manager.py`: `documentary.playback_speed` default `1.0` (pehle `1.2`).
  - `core/pipeline_runner.py`: `config.get(..., 1.0)` fallback teen jagah.
  - `modules/documentary_assembler.py`: docstring example 1.2 hata.
- Reason: User ko final video + voice normal speed chahiye; optional ab bhi config se >1 set kar sakte hain.

---

- Date/Time: 2026-04-24
- Task: Hindi script — cinematic monologue style + topic ke baad user story
- Changes:
  - `modules/scripter.py`: `_hindi_cinematic_monologue_block()` — `hi` mode par hook/anaphora/staccato closing; topic me separator ke baad wali line ko mandatory story maan kar end me weave; `[संगीत]` avoid (TTS); normal + documentary dono prompts me inject.
- Reason: User ne sample monologue di thi + end me story pass karne ka flow chahiye tha.

---

- Date/Time: 2026-04-24
- Task: Documentary long form — optional burned-in subtitles (UI + regen path)
- Changes:
  - `core/pipeline_runner.py`: `_documentary_regen_video` ab `wants_burned_subtitles` + `burn_subtitles` bhejta hai; docstring me assembly step update.
  - `gui/tabs/documentary_tab.py`: Footage section — checkbox `documentary.burn_subtitles`, Long mode par hi enabled; save + Settings tab se mirror.
  - `gui/tabs/settings_tab.py`: Video format section — Documentary (long) subsection + checkbox; `[ SAVE CONFIG ]` par bhi key save; change par Documentary tab var sync.
- Reason: User ko long documentary output par white bold bottom subs optional chahiye; sirf documentary pipeline, short/long gate pehle se `wants_burned_subtitles` me tha.

---

- Date/Time: 2026-04-24
- Task: YouTube upload — Hinglish SEO title + human description (Hindi pipeline)
- Changes:
  - `modules/scripter.py`: `_youtube_metadata_rules()` — Hindi voiceover par bhi **title** ab Hinglish (English SEO + Roman Hindi, Latin only); **description** mostly English + optional Hinglish hook; **tags** English + Hinglish search terms. `hinglish` / `en` / other langs ke liye alag bullets. `_build_prompt` + `_build_documentary_prompt` me purane "title same as voiceover language" hata kar yeh rules inject; JSON schema hints update.
- Reason: Pure Devanagari titles search/CTR friendly nahi the; user ko readable Hinglish + SEO chahiye tha (upload metadata alag voiceover se).

---

- Date/Time: 2026-04-24
- Task: App version bump → 4.1 (branding + single `APP_VERSION`)
- Changes:
  - `config.py`: `APP_VERSION = "4.1"` (single source; comment to sync installer/README).
  - `gui/app.py`: window title + badge `v{APP_VERSION}` from `config`.
  - `installer_v4.iss`: `MyAppVersion` "4.1"; `OutputBaseFilename` `GhostCreatorAI_v4.1_Setup`.
  - `main.py`: CLI `description` + `--version` / `-V` uses `APP_VERSION`.
  - `README.md`: title, badge, ASCII demo line → v4.1; `setup.bat` window title.
  - `gui/__init__.py`, `core/__init__.py`, `backends/__init__.py`: package comments v4.1.
  - `modules/documentary_assembler.py`: comment only — ASS `ScriptType: v4.00+` subtitle spec unchanged (not app version).
- Reason: User ne saari jagah version 4.1 chahiye tha; PyPI-style dependency versions (e.g. fal `0.4.0`) aur Gemini `imagen-4.0-*` APIs touch nahi kiye.

---

- Date/Time: 2026-04-25
- Task: Documentary — assembly error at burn-in subs (100 clips + emoji output path)
- Changes:
  - `modules/documentary_assembler.py`: `ass` burn pass se pehle agar final MP4 path pure ASCII nahi, `temp` me copy karke `ffmpeg` input (libass/Windows Unicode issue); log line. `_ffmpeg` stderr ab useful lines + tail (purana sirf last 2000). Clip duration split ab `_normalized_segment_durations` — purane `_segment_durations` hata (min 2s per seg se sum>audio, 100+ clips par drift) taaki trim timing subtitles ke saath mile.
- Reason: Screenshot me path `D:\maaya_ai ✅\...` tha; burn step par FFmpeg fail. Zyada segments par per-seg min-2s total ko blow up karta tha.

---

- Date/Time: 2026-04-30
- Task: Documentary-only cleanup (remove shorts pipeline, Vision Matrix, Google Cloud TTS, img2video, image counts)
- Changes:
  - `gui/app.py`: PIPELINE tab hata kar sirf Documentary / Settings / History; footer me sirf `AUDIO_SUBROUTINE` (VISION_MATRIX hata).
  - `gui/tabs/settings_tab.py`: Vision Matrix section + image API keys (Fal/Replicate/Horde/xAI/Google TTS path) + Google Cloud TTS button + img2video UI + image count + thumbnail toggle + cinematic intro/transitions hata; API keys ab Gemini/Eleven/Pexels; script-gen se image-to-video block hata; uplink status `documentary_tab` ko; copy documentary-focused.
  - `gui/tabs/documentary_tab.py`: `pipeline_mode` set hata (runner ab hamesha documentary).
  - `modules/voicer.py`: `google_tts` backend registry se hata.
  - `core/config_manager.py`: `google_tts` legacy config → `edge_tts` migrate `_validate_v3_fields` me.
  - `core/pipeline_runner.py`: normal shorts branch + image review machinery hata; research ke baad hamesha `_run_documentary`; `last_metadata.json` documentary run par bhi likho.
  - `main.py`: CLI ab documentary unattended (script/video preview flags temporarily off) + `--from-video` upload; purana `generate_script`/images/video path hata.
  - `GhostCreatorAI.spec`: dead hiddenimports + `google.cloud.texttospeech` / fal / replicate collect hata.
  - `gui/tabs/pipeline_tab.py`: file delete.
  - `gui/components/image_review.py`: file delete.
- Reason: User ne app ko documentary-only banana tha; shorts AI images, img2video, Vision Matrix, Google Cloud TTS, image counts hatane the.

---

- Date/Time: 2026-04-30
- Task: Remove dead shorts modules + unused image/TTS backend files (keep thumbnail stack)
- Changes:
  - `modules/img2video.py`, `modules/video_builder.py`, `modules/image_prep.py`: deleted (no longer imported).
  - `backends/tts/google_tts.py`: deleted (TTS routing removed earlier).
  - `backends/image/fal_ai.py`, `replicate.py`, `stable_horde.py`, `grok_image.py`: deleted.
  - `modules/image_gen.py`: `BACKEND_MAP` ab sirf `comfyui`, `pollinations`, `gemini_imagen` (thumbnail / future use).
  - `requirements.txt`: `google-cloud-texttospeech`, `fal-client`, `replicate`, `moviepy` hata (ab codebase me use nahi).
- Reason: Documentary-only app; user ne unused files hataane ko kaha, `thumbnail_maker` + `image_gen` rakhna tha baad mein edit ke liye.

---

- Date/Time: 2026-04-30
- Task: Thumbnails fixed 16:9; Gemini-only image backend; remove ComfyUI + Pollinations
- Changes:
  - `backends/image/comfyui.py`: deleted (local Comfy no longer supported).
  - `backends/image/pollinations.py`: deleted (Pollinations removed per user).
  - `modules/image_gen.py`: `BACKEND_MAP` ab sirf `gemini_imagen`; default backend `gemini_imagen`; duplicate local/cloud loop hata.
  - `modules/thumbnail_maker.py`: hamesha 1280×720 / 16:9; 9:16 branches + ratio-aware doc hata; prompt se SD-specific wording hata.
  - `core/config_manager.py`: default `image.backend` = `gemini_imagen`; `comfyui_url` / `pollinations_model` defaults + `COMFYUI_URL` / `POLLINATIONS_MODEL` env map + `.env.local` template lines hata; `_validate_v3_fields` me sirf `gemini_imagen` allowed (purana comfy/pollinations auto-migrate).
  - `config.py`: `WORKFLOW_JSON` + `COMFYUI_URL` hata.
  - `backends/base.py`: `ImageBackend` docstring cloud examples update.
  - `requirements.txt`: `websocket-client` hata (Comfy WebSocket ke liye tha).
  - `setup.bat`: `.env` template / migrate / next-steps se ComfyUI references hata.
  - `installer_v4.iss`: `workflow_api.json` line comment update (legacy optional).
- Reason: User ne kaha thumbnails sirf 16:9 chahiye, image gen sirf Gemini (Comfy/Pollinations nahi).

---

- Date/Time: 2026-04-30
- Task: Graceful thumbnail skip when Gemini API key does not support image generation
- Changes:
  - `backends/image/gemini_imagen.py`: `GeminiImageNotSupportedError` + `is_gemini_image_unsupported()`; unsupported/plan failures par `logger.error` ki jagah `GeminiImageNotSupportedError` (info log), quota/rate-limit alag.
  - `modules/thumbnail_maker.py`: unsupported cases par fallback composite nahi; `progress_callback` par exact user message (`GEMINI_THUMBNAIL_SKIP_USER_MESSAGE`); return `""`; koi ERROR-level user message nahi.
- Reason: Free-tier Gemini keys par image gen fail par pipeline calm rahe; GUI terminal me readable notice, process continue (upload/metadata empty thumbnail se).

---

- Date/Time: 2026-04-30
- Task: YouTube uploader — wait for real 100% upload before wizard; safer browser close
- Changes:
  - `modules/uploader.py`: `_wait_for_upload_complete` ab purane broad selectors (`Checks complete`, early processing copy) hata kar `_upload_completion_pulse` use karta hai (Next enabled / narrow “Upload complete” / progress 100%); **do lagatar polls** (~3s) confirm hone par aage; **timeout par ab proceed nahi** — `RuntimeError` + screenshot taaki video Draft me adhoori upload se na phase. `pipeline.upload_complete_timeout_ms` use; `finally` me success par `post_publish_grace_ms` (default 12s), fail par 4s phir `browser.close()`.
  - `core/config_manager.py` (agar pehle missing ho): `pipeline.upload_complete_timeout_ms` = 900_000, `pipeline.post_publish_grace_ms` = 12_000.
- Reason: Browser jaldi band hone + “timeout par bhi continue” ki wajah se video poori upload hone se pehle publish flow chal jata tha; visibility Draft me chali jati thi. Ab partial upload par flow abort + retry; publish ke baad zyada grace taaki Studio requests complete ho saken.

---

- Date/Time: 2026-04-30
- Task: TTS-friendly numbers — spell digits as words per language (OmniVoice / all TTS)
- Changes:
  - `modules/tts_number_normalize.py`: `expand_numbers_in_text` / `normalize_documentary_script_numbers` for Hindi/Devanagari, English, Marathi, Tamil (open-tamil), Telugu/Bengali/Kannada (num2words), fallbacks.
  - `modules/scripter.py`: documentary outputs pass through `normalize_documentary_script_numbers`; `_voiceover_plain_format_rules()` instructs model to avoid Arabic digits in voiceover; `VOICEOVER_LANG_META` me `te` (Telugu) add.
  - `modules/voicer.py`: `run_voiceover` calls `expand_numbers_in_text` before `synthesize` for manual/regen paths.
  - `requirements.txt`: `num2words`, `open-tamil` add.
- Reason: Raw numerals (1999, 2005, etc.) TTS par galat padhte the; ab pipeline language ke hisaab se spoken words/script me convert karke Omnivoice aur baaki backends consistent rahen.

---

- Date/Time: 2026-04-30
- Task: Telugu + Odia narration; OmniVoice `ory` mapping; Edge voices; TTS language validation
- Changes:
  - `modules/tts_lang_support.py`: naya — `SUPPORTED_PIPELINE_LANGS`, `resolve_omnivoice_language_tag` (Odia `or` → `ory`), Edge default Neural voices (te/or/ta/… + hi hinglish via config), `assert_tts_backend_supports_language`.
  - `backends/tts/omnivoice_tts.py`: `_effective_omnivoice_lang`; clone + design HTTP bodies me `language` tag; `_build_design_params` mapped language.
  - `backends/tts/edge_tts.py`: narration language ke hisaab se multi-regional voices; Edge par assert.
  - `modules/voicer.py`: `run_voiceover` se pehle `assert_tts_backend_supports_language`.
  - `modules/scripter.py`: `VOICEOVER_LANG_META` me Odia (`or`).
  - `modules/tts_number_normalize.py`: Odia numbers → English words fallback (num2words me Odia nahi).
  - `core/config_manager.py`: `allowed_langs` me `hinglish`, `te`, `or`; `.env` template comment.
  - `gui/tabs/settings_tab.py`: Telugu + Odia dropdown; OmniVoice hint.
  - `gui/tabs/documentary_tab.py`: narration language buttons — saari supported list (do rows).
  - `backends/tts/elevenlabs.py`: docstring — multilingual regional langs.
- Reason: User ne Telugu aur Odisha (Odia) add karne ko kaha; OmniVoice official list me dono hain (Odia API tag `ory`); Edge/ElevenLabs ke saath clear error jab combination supported na ho.

---

- Date/Time: 2026-04-30
- Task: Lightweight installer — FFmpeg download on first run (not bundled in .exe)
- Changes:
  - `core/ffmpeg_bootstrap.py`: naya — BtbN zip download/extract to `%LOCALAPPDATA%\GhostCreatorAI\ffmpeg`, `prepare_ffmpeg_runtime`, thread lock.
  - `config.py`: `get_ffmpeg_executable` / `get_ffprobe_executable` — pehle user cache, phir `<exe>/ffmpeg`, phir `_MEIPASS/ffmpeg`, phir PATH.
  - `gui/app.py`: frozen Win32 par `_prepare_ffmpeg_on_first_run` modal dialog.
  - `build.bat`: `--add-data ffmpeg` hata; `--hidden-import core.ffmpeg_bootstrap` add.
  - `installer_v4.iss`: comments update; `[UninstallDelete]` me AppData `ffmpeg` folder optional clean.
  - `ensure_ffmpeg.ps1`: comment — ab sirf dev/local `python gui/app.py` ke liye.
  - `modules/voicer.py`: module-level `_FFMPEG` hata, call time `get_ffmpeg_executable()`.
  - `backends/tts/omnivoice_tts.py`: `_ensure_pydub_ffmpeg()` sirf `synthesize` se.
  - `core/clip_manager.py`: `ffprobe`/`ffmpeg` ab `get_*_executable()`.
  - `modules/error_analyst.py`: ffmpeg troubleshooting text update.
- Reason: User chhota installer; FFmpeg ~100MB bundle se hata kar pehli run par download + cache.

---

- Date/Time: 2026-04-30
- Task: FFmpeg setup UI — progress bar + doc (no system Python for end users)
- Changes:
  - `core/ffmpeg_bootstrap.py`: `progress_ratio` callback (0.0–1.0); download ~88%%, extract/install 92–100%%; module docstring — PyInstaller .exe me embedded Python se chalta hai.
  - `gui/app.py`: first-run dialog me `CTkProgressBar` + taller window.
- Reason: User ko download/extract dauran visual progress; doubt clear — end user ko alag Python ki zaroorat nahi.

---

- Date/Time: 2026-04-30
- Task: Ghost license–gated in-app auto-update + website APIs
- Changes:
  - `core/update_checker.py`: naya — `GHOST_SITE_ORIGIN` se POST `/api/license/ghost-update-check`, JWT ke saath installer download + optional SHA-256 verify, Inno `/CLOSEAPPLICATIONS /SP-` launch.
  - `gui/tabs/settings_tab.py`: license block me app version + "Check for updates"; threaded check, download progress dialog, success par installer launch + `os._exit(0)`.
  - `build.bat`: `--hidden-import core.update_checker` (PyInstaller).
  - `maya-assistant-website/README.md`: env vars `GHOST_*` update flow + API table rows `ghost-update-check` / `ghost/desktop/installer` + closing ``` fix for `.env` block.
  - (Website codebase) `src/lib/ghostLicenseDeskAuth.ts`, `src/lib/ghostInstallerGithub.ts`, `src/app/api/license/ghost-update-check/route.ts`, `src/app/api/ghost/desktop/installer/route.ts` — seat = GhostLicense only, semver + JWT, GitHub stream.
- Reason: User ne Ghost purchase verify ke bina sirf license se desktop update + getmaya side secure download chaha; dono taraf implement.

---

- Date/Time: 2026-04-30
- Task: App version bump 4.2.2 (match Vercel `GHOST_APP_LATEST_VERSION`)
- Changes:
  - `config.py`: `APP_VERSION = "4.2.2"`.
  - `installer_v4.iss`: `MyAppVersion` 4.2.2; `OutputBaseFilename` `GhostCreatorAI_v4.2.2_Setup`.
  - `build.bat`: banner/footer v4.2.2.
  - `core/ffmpeg_bootstrap.py`, `gui/app.py`, `core/__init__.py`, `gui/__init__.py`, `backends/__init__.py`, `setup.bat`, `README.md`: branding strings 4.2.2.
- Reason: Production site par `GHOST_APP_LATEST_VERSION=4.2.2`; shipped app `current_version` match + installer filename aligned.

---

- Date/Time: 2026-04-30
- Task: Logo watermark (PNG/JPG) — Settings + Ghost Editor + FFmpeg overlay
- Changes:
  - `core/config_manager.py`: `documentary.logo_*` defaults (`enabled`, `path`, `position`, `scale`, `margin`, `opacity`).
  - `modules/documentary_assembler.py`: `_normalize_logo_spec`, `_apply_logo_watermark` (overlay after subs); `assemble_documentary(..., logo_watermark=)`; pipeline/editor context support.
  - `gui/tabs/settings_tab.py`: Core → LOGO WATERMARK — browse copies to `watermark_assets/user_logo.*`, SAVE persists.
  - `gui/components/clip_editor.py`: tab 🖼 LOGO — per-render on/off, corner, size, margin, opacity; `on_done` passes `logo_watermark` dict.
  - `gui/tabs/documentary_tab.py` / `gui/tabs/history_tab.py`: `on_done` + re-assemble pass `logo_watermark`.
  - `core/pipeline_runner.py`: Step 5 `assemble_documentary` uses `_doc_regen_ctx["logo_watermark"]`.
- Reason: Users long videos par corner logo chahte — ek baar Settings mein image, Editor mein position/size tweak, FFmpeg se final MP4 par burn.

---

- Date/Time: 2026-04-30
- Task: Idea Workshop — dynamic start (no rigid topic→style→format→tone wizard)
- Changes:
  - `modules/scripter.py`: `_CONSULTANT_SYSTEM` + model ack — natural chat, emit `<<PLAN_START>>` on user start phrases or when AI judges ready; smart defaults; no four-step form.
  - `gui/tabs/documentary_tab.py`: friendlier opening hint; `_coerce_workshop_*` normalizes plan FORMAT/STYLE/TONE from free text (e.g. “Long ~3 min”, “Cinematic type”).
- Reason: User chahta tha ke fixed steps ke bina discussion se hi “okay start / generate” par turant video pipeline chale, baaki fields auto-fill.

---

- Date/Time: 2026-04-30
- Task: Ghost Editor — fix `_replace_voiceover` / `_apply_voice_trim` merge (syntax)
- Changes:
  - `gui/components/clip_editor.py`: `_replace_voiceover` ko wapas proper `try`/`except` ke sath; `_apply_voice_trim` alag method restore — double `try` merge se `SyntaxError` fix (Filmora-style timeline + muxed voice preview path ab import/py_compile clean).
- Reason: A prior edit accidentally merged voice replace aur trim into ek broken block; app `clip_editor` load nahi ho sakta tha.

---

- Date/Time: 2026-04-30
- Task: History → Ghost Editor from any run video + post-edit Direct Upload handoff
- Changes:
  - `gui/tabs/history_tab.py`: `_open_ghost_editor_for_run` — full multi-clip jab `documentary_editor.json` + `voiceover.mp3` dono hon; warna final MP4 se single-clip mode (`_ghost_editor_from_video_audio.m4a` FFmpeg extract, fallback `voiceover.mp3`); `_after_ghost_editor_assemble` success ke baad optional “Open Direct Upload” prompt; card button `✂️ Ghost (video)` jab sirf MP4 available; incomplete snap par video fallback.
  - `gui/app.py`: `open_direct_upload_with_video()` — `CTkTabview.set` se 📤 UPLOAD tab + `upload_tab` prefill.
  - `gui/tabs/direct_upload_tab.py`: `set_video_for_upload()`; browse flow refactor.
- Reason: User history ki last generation ka video Ghost mein kholna chahta tha bina purane snapshot ke, aur edit ke baad YouTube upload tab par seedha path chahiye.

---

- Date/Time: 2026-04-30
- Task: Ghost Editor — fix `config` import (ImportError)
- Changes:
  - `gui/components/clip_editor.py`: `config` ab `core.config_manager` se; `get_ffmpeg_executable` root `config.py` se — `from config import config` galat tha (root module me `config` object nahi).
- Reason: History se Ghost (video) kholte waqt `ImportError: cannot import name 'config' from 'config'`.

---

- Date/Time: 2026-04-30
- Task: Ghost Editor Filmora-style timeline + History multi-clip priority + segment sync on DONE
- Changes:
  - `gui/components/clip_editor.py`: ruler drag = playhead scrub; ruler tap (no drag) = split at time (video **or** VOICE focus = same synced split: `split_clip` + `script_segments` voiceover word-split + SRT regen); MUSIC row click = `_browse_music`; clip list **+ Add clip**; **Delete/BackSpace** removes clip + matching segment; move/reorder/sync split/remove/split tab keep `script_segments` length aligned; `on_done` eighth arg `script_segments` list.
  - `gui/tabs/history_tab.py`: jab `documentary_editor.json` + per-segment clips resolve hon to **multi-clip** kholo; `voiceover.mp3` na ho to final MP4 se audio extract (jor pahle); card **Ghost Editor** jab clips+segments+audio source ready; `assemble_documentary` + `on_done` updated segments use karte hain.
  - `gui/tabs/documentary_tab.py`: `on_done` saves `script["segments"]` when editor returns.
- Reason: User chahta tha history par sab clips timeline par, ruler se split/scrub, music row se browse, clips add/remove, aur DONE par edited segments assembly mein jayein — Filmora-like control.

---

- Date/Time: 2026-04-30
- Task: Ghost Editor `_build_voice_tab` restore + History newest-10 sort
- Changes:
  - `gui/components/clip_editor.py`: `_tl_y_track` ke andar galti se chhap gaya voice-tab UI hata kar `_build_voice_tab(self, parent)` dubara — `AttributeError: _build_voice_tab` / missing `srt_list_frame` fix.
  - `gui/tabs/history_tab.py`: `_run_sort_epoch` — folder `*_YYYYMMDD_HHMMSS`, phir `history_entry` timestamps, warna `metadata.json` mtime; sab runs sort `reverse=True`, top **10** (latest pehle).
- Reason: App crash on Ghost open; user ko 10 recent runs real chronological order mein chahiye.

---

- Date/Time: 2026-04-30
- Task: Ghost Editor — preview title + BGM mux + Filmora ruler zoom + split cue + music context menu
- Changes:
  - `gui/components/clip_editor.py`: VLC preview FFmpeg mux — optional SRT burn, `drawtext` title from `metadata.json` / temp title file, voice + background `amix` (`bg_volume`); fast stream-copy path jab koi overlay/mix nahi; ruler pe dominant horizontal drag = zoom (right=in, left=out), wheel = pan; ruler hover pe ✂ + dashed line (video/voice split mode); clip joints pe gold split markers; MUSIC row left = focus/playhead, right-click = browse / volume ±10% / reset; help + preview blurb text update.
- Reason: Title preview mein dikhna chahiye; timeline Filmora jaisa zoom/split feedback; BGM preview aur narration saath sunna; music volume ko timeline se control.

---

- Date/Time: 2026-05-01
- Task: Ghost Editor — remove right panel, Filmora-style timeline, ASSETS rename, context menus
- Changes:
  - `gui/components/clip_editor.py`:
    - Right panel (tabview: VOICE/TRIM/SPLIT/SUBTITLES/MUSIC/LOGO) removed from layout; all internal widgets now created via `_create_hidden_widgets()` in a hidden CTkFrame — all existing logic unchanged.
    - `_build_ui` restructured: header → preview+ASSETS row (side-by-side) → full-width timeline → footer.
    - New `_build_assets_panel()`: ASSETS panel (renamed from CLIPS) with `+ Video`, `+ Music`, `+ Voice` buttons.
    - `_build_preview_row(parent)`: now accepts parent parameter for inline packing.
    - Timeline canvas: track heights increased (VIDEO 76px, VOICE 56px, MUSIC 46px, RULER 32px); window resized to 1460×960.
    - `_timeline_redraw`: Filmora-style blocks — gradient fill (top highlight + bottom dark strip), left/right handles, clip number + name + duration text, gold split markers with ruler triangle, playhead triangle, waveform fills with track background.
    - `_tl_right_press`: video track right-click → context menu (Preview / Trim / Split / Replace / Move / Remove); voice track → Replace / Trim; music track → Browse / ±vol / Reset (same as before).
    - New context dialogs: `_show_trim_dialog`, `_show_split_dialog`, `_show_voice_dialog`, `_show_subtitles_dialog`, `_show_logo_dialog` — all accessible from footer buttons or right-click menus.
    - `_logo_spec_for_export`: refactored to use instance vars (`_logo_apply`, `_logo_pos`, `_logo_scale`, `_logo_margin`, `_logo_opacity`) set by logo dialog; no longer reads from widget state.
    - `_on_done_clicked`: exports `self.srt_entries` directly (subtitle dialog updates them); no longer calls `_save_srt`.
    - Stats label text: "Clips:" → "Assets:".
- Reason: User requested removal of bottom-right control panel, full timeline-based editing (like Filmora), better timeline visuals, ASSETS naming for the clip list.

---

- Date/Time: 2026-05-01
- Task: Ghost Editor — fix ruler drag (scrub) + Filmora film-strip clip visuals
- Changes:
  - `gui/components/clip_editor.py`:
    - `_tl_motion`: ruler plain drag now always scrubs playhead; Ctrl+drag triggers zoom (removed old "dominant horizontal = zoom" heuristic).
    - `_tl_release`: scrub drag no longer triggers split; quick tap (no movement, no Ctrl) still splits.
    - `_tl_wheel`: plain scroll = pan; Ctrl+scroll = zoom.
    - Timeline help text updated to describe new controls.
    - `_timeline_redraw` video clip blocks: complete Filmora-style redesign — teal/cyan color scheme, film-strip perforation bands at top & bottom, CLIP_GAP separation between adjacent clips, clip #/name/duration text, teal split tick on ruler.
    - Waveform tracks: bottom-up filled bar style (Filmora default), bright peak highlight line, subtle strip bands at track edges.
- Reason: User could not drag ruler to scrub; clips visually needed Filmora film-strip look.

---

## 2026-05-01 — Feature Batch: Lag Fix, Shortcuts, Undo/Redo, Subtitle Track, Audio Splits, Continuous Playback

- Task: Implement 6 major features: timeline lag fix, keyboard shortcuts, undo/redo, subtitle timeline track, audio split markers, continuous playback with VLC poll ticker.
- Changes:
  - `gui/components/clip_editor.py`:
    - **Lag Fix**: Added `_timeline_redraw_schedule()` debounce method with 14 ms `after()` coalescing and dirty-flag (`_redraw_pending`). All hot-path event handlers (`_tl_press`, `_tl_motion`, `_tl_release`, `_tl_wheel`, `_tl_motion_hover`, `<Configure>`) now call `_timeline_redraw_schedule()` instead of direct `_timeline_redraw()`. Waveform loops changed from per-pixel to capped `_TL_MAX_BARS=480` bar blocks using `create_rectangle` for batched draw calls.
    - **Keyboard Shortcuts**: Bound `<Control-z>` → `_undo`, `<Control-Z>` → `_redo` (Ctrl+Shift+Z), `<space>` → `_kbd_play_pause`, `<Control-b>` → `_kbd_split`. Space key guarded against Entry/Text widgets.
    - **Undo/Redo**: Added `_push_undo()` snapshot method (deep-copies clips, srt_entries, script_segments, voice/music splits, selected_clip_idx, playhead into `deque(maxlen=30)`). Added `_undo()`, `_redo()`, `_restore_state()`. `_push_undo()` inserted before every destructive operation: `_move_clip`, `_remove_clip`, `_replace_clip`, `_apply_trim`, `_apply_split`, `_split_timeline_at_global_time`, `_add_clip_dialog`, `_srt_add_at_playhead`, `_srt_delete_cue`, `_srt_edit_inline`.
    - **Subtitle Track**: Added `SUBTITLE_TRACK_H=34` constant. Added subtitle track row in `_timeline_redraw` (dark background, amber cue blocks with text label, selection highlight). `_tl_y_track` updated to return `"subs"`. `_tl_press` handles click-to-select cue. `_tl_double_click` handler + `<Double-Button-1>` binding for inline editing. Right-click on subs track shows "Add/Edit/Delete cue" context menu. New methods: `_srt_add_at_playhead`, `_srt_delete_cue`, `_srt_edit_inline`. `_srt_blocks` list tracks cue canvas positions.
    - **Audio Split Markers**: `_voice_splits` and `_music_splits` lists store split point times. `_split_timeline_at_global_time` now handles voice/music focus tracks by appending visual split markers instead of rejecting. `_kbd_split` (Ctrl+B) splits video, voice, music, or subs depending on `_tl_focus_track`. Split markers rendered as orange `✂` dividers on waveform tracks.
    - **Continuous Playback**: Added `_continuous_play_from_playhead()` which starts mux for the clip at playhead. Added `_vlc_tick()` poll method (every 80 ms): updates `_playhead_sec` from VLC position, auto-advances to next clip when current clip ends (`vlc_ended` state). `_preview_from_playhead` and `_kbd_play_pause` now call `_continuous_play_from_playhead`. `_preview_pause`/`_preview_stop` set `_vlc_poll_active=False` to stop the ticker.
    - **Module-level helper**: Added `_srt_time_to_sec()` wrapper for SRT timestamp parsing.
- Reason: User requested lag fix, Ctrl+Z/Shift+Z undo/redo, Space play/pause, Ctrl+B split, subtitle timeline track, audio split markers, and continuous preview playback through all clips.

---

## 2026-05-01 — Timeline UI Redesign + Lag Fix (Round 2)

- Task: Redesign timeline to match Ghost Editor reference project (`C:\Users\hunte\OneDrive\Desktop\Ghost editor`); fix subtitle track cut-off; fix perceived lag from debounce.
- Changes:
  - `gui/components/clip_editor.py`:
    - **Class constants updated**: `TRACK_LABEL_W=96` (was 72), `RULER_H=28` (was 32), `TRACK_GAP=4` added (gap between tracks). New `_TL_*` colour palette constants matching Ghost Editor reference: `_TL_BG="#0E0E12"`, `_TL_PANEL="#16161C"`, `_TL_PANEL_ALT="#1C1C25"`, `_TL_BORDER="#262631"`, `_TL_VID="#7C5CFF"`, `_TL_VOICE="#5EE6D0"`, `_TL_MUSIC="#E87CFF"`, `_TL_SUBS="#FFB65E"`, `_TL_PLAYHEAD="#FF5E7A"`.
    - **Canvas height fixed**: Added `SUBTITLE_TRACK_H` + three `TRACK_GAP`s to canvas height calculation so subtitle row is never cut off.
    - **Lag fix**: Removed `_timeline_redraw_schedule()` calls from all hot-path events (`_tl_press`, `_tl_motion` scrub+zoom, `_tl_release`). These now call `_timeline_redraw()` directly for instant response. `_timeline_redraw_schedule()` retained only for hover (`_tl_motion_hover`) and resize (`<Configure>`).
    - **`_timeline_redraw` fully rewritten**: New Ghost-Editor-reference visual style: dark `#0E0E12` bg; `#1C1C25` gutter with 4 px accent bar on left per track; `#16161C` lane fill; major ruler ticks in `#5EE6D0` cyan with `MM:SS` labels in `#8A8A96`; minor ticks in `#262631`; video clip blocks use purple gradient bands + left accent strip + border, title text in "Segoe UI"; waveform uses centred bar style (half-height symmetric) in muted accent colours (`#3ABFA0` voice, `#B060CC` music); subtitle cues are `#FFB65E`-bordered amber blocks; playhead in `#FF5E7A` with triangle knob; focused-track glow: 3 px accent bar on the lane's left inner edge; track gap rows drawn as `#0E0E12` separators.
    - **`_tl_y_track` updated**: Uses `TRACK_GAP` offsets so gap zones between tracks return "none" (not misidentified as an adjacent track).
    - **`tl_wrap` background**: Updated from `"#080e14"` to `self._TL_BG` (`"#0E0E12"`).
- Reason: User reported timeline looked bad, subtitle track was cut off, and lag persisted despite earlier debounce fix (debounce caused perceived delay on scrub/click actions).

---

## 2026-05-01 — Ruler UX Redesign, Assets Panel, Speed Control, Selection Highlight

- Task: Filmora-style ruler interaction (tap=split, drag=scrub, top-zone drag=zoom); always-on scissor icon; +SRT import in Assets; per-clip speed menu; white selection border.
- Changes:
  - `gui/components/clip_editor.py`:
    - **Ruler dual-zone**: Top 45% of ruler = zoom zone (drag left=out, right=in); bottom 55% = scrub/split zone (drag=scrub playhead, tap=split). `_ruler_is_zoom_zone()` helper. Zone labels "ZOOM" / "SPLIT" in gutter. `_tl_press` sets mode at press time based on zone. `_tl_motion` routes to zoom or scrub. Removed Ctrl+drag requirement for zoom.
    - **Scissor icon**: Always drawn at horizontal center of the ruler scrub zone (not just on hover). Hover still highlights the scrub position with a white dashed line.
    - **`_tl_ruler_hover_y`**: Stored in `_tl_motion_hover` so scissor hover rendering can check zone.
    - **Assets panel redesign**: Header renamed to "IMPORT MEDIA". Buttons row now has 4 buttons: `+ Video`, `+ Audio`, `+ Voice`, `+ SRT`. Button colours use the track accent palette. Added "VIDEO CLIPS" section label.
    - **`_import_srt_file()`**: New method — opens file dialog for `.srt` files, parses them (via `load_srt` or manual regex fallback), pushes undo, replaces `self.srt_entries`. Shows cue count in status bar.
    - **Speed control**: `_clip_speeds: dict[int, float]` added to `__init__` and undo snapshot. `_set_clip_speed(idx, speed)` and `_set_voice_speed(speed)` methods. Right-click on VIDEO clip shows "Speed (Nx)" cascade submenu with options 0.25×–3.0×. Right-click on VOICE track shows similar submenu. Speed badge (e.g. "1.5×") drawn on clip block when speed ≠ 1.0.
    - **White selection border**: Selected clip block now uses 2 px white border (`#FFFFFF`), unselected remains 1 px `#5030AA`. Makes active clip instantly visible.
- Reason: User requested Filmora-style ruler, scissor icon, SRT import, speed change menu, and visible clip selection.

---

## 2026-05-01 — Ruler Fix v2 + Scissor Tracks Playhead + Fine-grained Speed

- Changes:
  - `gui/components/clip_editor.py`:
    - **`RULER_H` increased to 44 px** (was 28 px) — ruler was too narrow to click reliably.
    - **Removed dual-zone ruler** — replaced with single unified strip: drag = scrub, tap = split, Ctrl+drag = zoom.
    - **`_ruler_is_zoom_zone()` deleted** — mode now determined by Ctrl key state at press time.
    - **`_tl_press` rewritten** — always moves playhead immediately on any ruler click.
    - **`_tl_motion` simplified** — Ctrl+drag = zoom, plain drag = scrub.
    - **`_tl_release` simplified** — scrub-mode tap → split attempt.
    - **Scissor icon tracks playhead** — drawn at playhead X position on ruler (with glow circle), not a fixed center.
    - **Speed menus** — fine-grained steps: 0.5, 0.75, 0.9, 0.95, 1.0, 1.05, 1.10, 1.15, 1.20, 1.25, 1.5, 1.75, 2.0×. Max is now 2.0× (removed 3.0×).
- Reason: User reported ruler not clickable/draggable, scissor icon missing, and needed fine-grained speed steps (1.05/1.10/1.15) with max 2×.

---

## 2026-05-01 — Track Selection Highlight for Voice / Music / Subs

- Changes:
  - `gui/components/clip_editor.py`:
    - **Focus track highlight** — when voice, music, or subtitle track is clicked (selected), the entire track lane now shows a **white 1px border outline** in addition to the coloured left-edge accent bar. Previously only a 3px left-edge glow was drawn, which was barely noticeable.
- Reason: User reported that clicking voice/music/subtitle tracks showed no visible selection highlight on those lanes.

---

## 2026-05-01 — Per-Segment Selection Highlight for Voice / Music / Subs

- Changes:
  - `gui/components/clip_editor.py`:
    - Added `_selected_voice_seg: int`, `_selected_music_seg: int`, `_voice_seg_blocks`, `_music_seg_blocks` in `__init__`.
    - Added `_seg_blocks_for()` helper in `_timeline_redraw` — builds a list of `(canvas_x0, canvas_x1, seg_idx)` for each split-separated segment given the track's duration and split points.
    - Voice waveform draw: after drawing waveform, iterates `_voice_seg_blocks` and draws a 2px white outline around only the `_selected_voice_seg` block when voice is focused.
    - Music waveform draw: same pattern with `_music_seg_blocks` / `_selected_music_seg`.
    - Subtitle track already draws per-cue `#FFDD88` border on `_srt_selected_idx` — no change needed.
    - `_tl_press` (voice branch): on click, finds which segment in `_voice_seg_blocks` contains `e.x` and stores it in `_selected_voice_seg`.
    - `_tl_press` (music branch): same for `_selected_music_seg`.
    - Focus track highlight: removed the "white border around entire track lane"; replaced with a thicker (5px) coloured left-edge accent bar only — segment-level selection provides the white outline now.
- Reason: User wanted only the clicked split-segment to get a white highlight, not the entire track lane.

---

## 2026-05-01 — Voice & Music Volume Control (0–100%)

- Changes:
  - `gui/components/clip_editor.py`:
    - Added `self._voice_volume = 1.0` in `__init__` (voice gain 0.0–1.0).
    - Added `_show_volume_dialog(track)` method — small centred popup with a 0–100 CTkSlider, live % label, Apply/Cancel buttons. Works for both `"voice"` and `"music"` tracks.
    - Voice right-click menu: added `"🔊 Set Volume (0–100%)…"` as the first item, current % shown in header.
    - Music right-click menu: added `"🔊 Set Volume (0–100%)…"` as the first item, current % shown in header. Kept existing +10%/-10%/Reset quick options.
    - `_ffmpeg_mux_preview` — added `voice_gain` parameter; voice FFmpeg filter now uses `volume={vg}` instead of hard-coded `volume=1`. All callers pass `voice_gain=self._voice_volume`.
  - `modules/documentary_assembler.py`:
    - `assemble_documentary` — added `narration_volume: float = 1.0` parameter.
    - `_assemble` — added `narration_volume: float = 1.0` parameter; passes it to `_mix_background_music`.
    - `_mix_background_music` — added `narration_volume` param; filter chain now applies `[0:a]volume={vg}` on voice before amix.
- Reason: User requested ability to adjust voice and music volume in 0–100% range via right-click context menu on those tracks.

---

## 2026-05-01 — Idea Workshop Redesign: Ghost AI Premium Chat UI

- Changes:
  - `gui/tabs/documentary_tab.py`:
    - **`_build_idea_workshop` fully rewritten** — new premium dark chat panel:
      - Panel uses `#060C16` bg, `#3A1880` purple border, rounded corners.
      - Toggle header now reads `[ GHOST AI ] — Idea Workshop`.
      - Status badge (top-right) shows `⬡ GHOST AI  ● ONLINE` with colour-coded dot.
      - Session counter label: "Session: N turns  •  ∞ unlimited".
      - Chat log uses `#030811` bg with rich per-role text tags: `user_hdr/user_body`, `ai_hdr/ai_body`, `sys_hdr/sys_body`, `plan_hdr/plan_body`.
      - SEND button restyled (purple, rounded, "SEND ↵"). GENERATE NOW → "⚡ CREATE NOW". Clear → "⟳ New".
      - USE THIS TOPIC button restyled green rounded card.
    - **`_workshop_append` rewritten** — messages appear as visual chat bubbles using Unicode box chars (`╭─ YOU ─╮ │ │ ╰──╯` for user, `⬡ GHOST AI ──` header+separator for AI, `★ PLAN CONFIRMED` for plan).
    - **`_toggle_workshop`** — updated text to Ghost AI branding.
    - **Thinking animation** — `_workshop_set_thinking()` + `_animate_thinking_dots()`: status dot turns amber, label shows "Ghost AI is thinking ●●●" with animated cycling dots.
    - **Unlimited conversation** — `_chat_history` no longer trimmed. Last 30 turns sent to API for efficiency; full history kept in memory across the session.
    - **Turn counter** — `_workshop_turns` incremented per exchange, displayed in session label.
    - **`_workshop_send` — smart start detection**: `_user_wants_to_start()` checks message for ~20 start-intent phrases (start, generate, banao, bana do, chalo banao, go ahead, create now, shuru karo, etc.) and immediately triggers generation without a Gemini round-trip.
    - **All remaining `_workshop_append` calls** updated to new (who, text, kind) signature.
- Reason: User requested premium AI chat redesign, Ghost AI branding replacing Gemini label, unlimited conversational sessions, and smart video-creation intent detection.

---

## 2026-05-01 — Build v4.3.0: Fix missing hidden-imports + version bump

- Changes:
  - `build.bat`:
    - Added 6 missing `--hidden-import` entries that would cause import errors in the frozen .exe:
      - `gui.tabs.history_tab`
      - `core.clip_manager`
      - `core.vlc_helper`
      - `modules.error_analyst`
      - `modules.tts_lang_support`
      - `modules.tts_number_normalize`
    - Added `--hidden-import vlc` (python-vlc module used by clip editor preview).
    - Added `--collect-all pydub` (pydub has data files that must be collected).
    - Bumped version label to v4.3.0.
  - `installer_v4.iss`:
    - Bumped `MyAppVersion` from 4.2.2 → 4.3.0.
    - Updated `OutputBaseFilename` to `GhostCreatorAI_v4.3.0_Setup`.
- Reason: User asked to verify build correctness before running build.bat + Inno Setup. Several new modules added since v4.2.2 were missing from the PyInstaller hidden-import list, which would have caused `ModuleNotFoundError` at runtime in the frozen .exe.

---

## 2026-05-01 — Website: Ghost Creator Flash Sale ₹199 + v4.2.2 version

- Changes:
  - `maya-assistant-website/src/app/ghost-creator/page.tsx`:
    - Version badge updated: `v4.0 PRO · Windows App` → `v4.2.2 PRO · Windows App`.
    - Added `SALE_END = new Date("2026-05-16T23:59:59+05:30")`, `isSaleActive`, `daysLeft` logic.
    - `price` variable now returns `"199"` while sale is active, otherwise falls back to `NEXT_PUBLIC_PRICE_GHOST || "579"`.
    - Added orange flash-sale banner right below Navbar: "🔥 FLASH SALE — Ghost Creator AI sirf ₹199 (was ₹579) · X din baaki · Ends 16 May 2026".
    - Pricing section updated: shows ₹999 struck → ₹579 struck (when sale active) → ₹199 large; sale badge with countdown; note "Price wapas ₹579 ho jaayegi 16 May ke baad".
    - Download filename updated: `GhostCreatorAI_v4_Setup.exe` → `GhostCreatorAI_v4.2.2_Setup.exe` (both `a.download` attribute and button text).
  - `maya-assistant-website/src/app/page.tsx`:
    - Ghost Creator cross-sell section: added orange flash-sale badge "🔥 FLASH SALE — sirf 15 din · Ends 16 May 2026".
    - Feature bullet updated: "Lifetime access for just ₹579" → "Lifetime access — was ₹579, ab sirf ₹199".
    - Buy button: changed gradient to orange/red, text → "🔥 Buy Now ₹199".
    - Price badge on image card: "₹579" → "🔥 ₹199 ~~₹579~~".
- Reason: User requested 15-day flash sale at ₹199 for Ghost Creator, and version number update to 4.2.2 across the website.

---

## 2026-05-01 — Website: Sale fully env-controlled (no hardcoded dates/prices)

- Changes:
  - `maya-assistant-website/src/app/ghost-creator/page.tsx`:
    - Removed hardcoded `SALE_END` date and `daysLeft` calculation entirely.
    - Sale is now controlled by 3 env vars: `NEXT_PUBLIC_GHOST_SALE_ACTIVE`, `NEXT_PUBLIC_GHOST_SALE_PRICE`, `NEXT_PUBLIC_GHOST_SALE_LABEL`.
    - Banner and pricing section render conditionally only when `NEXT_PUBLIC_GHOST_SALE_ACTIVE=true`; end-date text comes from `NEXT_PUBLIC_GHOST_SALE_LABEL`.
  - `maya-assistant-website/src/app/page.tsx`:
    - Flash sale badge, feature bullet, buy button, and price badge all read from the same 3 env vars.
    - When sale is off, everything reverts to normal blue styling and `NEXT_PUBLIC_PRICE_GHOST` price.
- Reason: User wanted to control sale entirely from `.env` — turn on/off, change price, change end label — without touching code.

---

- Date/Time: 2026-05-01 19:46
- Task: PyInstaller — reduce build noise / optional submodule warnings
- Changes:
  - `build.bat`: `PYTHONWARNINGS=ignore::SyntaxWarning` add kiya (tamil/pydub etc. ke hundreds of SyntaxWarning logs kam); PyInstaller `--exclude-module` add: `google.genai.tests`, `pytest`, `tensorboard`, `torch.utils.tensorboard`, `urllib3.contrib.emscripten` (yeh sab app runtime ke liye zaroori nahi, analysis warnings kam).
  - `GhostCreatorAI.spec`: `Analysis(..., excludes=[...])` mein same module names mirror kiye taaki spec se build karne par bhi match rahe.
- Reason: User ke build log mein submodule collection aur third-party SyntaxWarning spam aa raha tha; exclusions se PyInstaller WARNINGS kam aur log readable; aborted build dubara clean chalayenge to zyada clear output milega.

---

- Date/Time: 2026-05-01 20:39
- Task: Fix EXE/Installer "Not Responding" + continuous CMD flashing when Ghost Editor opens
- Root causes found & fixed:
  1. **pydub subprocess CMD flashing** — pydub's `AudioSegment.from_file()` calls ffprobe/ffmpeg via `subprocess.Popen` without `CREATE_NO_WINDOW`, causing CMD windows to flash repeatedly during waveform generation.
  2. **pydub ffmpeg path unknown in frozen env** — pydub didn't know about `%LOCALAPPDATA%\GhostCreatorAI\ffmpeg`; it tried to run bare `ffmpeg` which either hangs or fails.
  3. **`multiprocessing.freeze_support()` missing** — Required for `--onefile` frozen exe; missing it can cause subprocess spawning to deadlock.
  4. **`sys.stdout`/`sys.stderr` are `None`** in `--windowed` frozen exe — any stray `print()` or logging write crashes the app.
  5. **`core/clip_manager.py` subprocess calls missing `CREATE_NO_WINDOW`** — `get_clip_duration()` spawns ffprobe per clip (up to 14 calls) without the flag.
- Changes:
  - `core/ffmpeg_bootstrap.py`: Added `configure_pydub_subprocess()` function — sets `pydub.AudioSegment.converter` / `.ffprobe` to our cached binaries, patches `pydub.utils.Popen` to use `CREATE_NO_WINDOW` + `stdin=DEVNULL`.
  - `gui/app.py`: (a) Redirect `sys.stdout`/`sys.stderr` to devnull when frozen; (b) Call `configure_pydub_subprocess()` early in `_init_main_ui()`; (c) Add `multiprocessing.freeze_support()` inside `if __name__ == '__main__':` guard.
  - `gui/components/clip_editor.py`: Call `configure_pydub_subprocess()` inside `_compute_waveform_envelope()` as a safety fallback before any pydub usage.
  - `core/clip_manager.py`: Added `_NO_WINDOW` constant; applied `creationflags=_NO_WINDOW` to all three `subprocess.run()` calls in `get_clip_duration()` and `_run_ffmpeg()`.
- Reason: Running the compiled EXE/installer resulted in "Ghost Editor (Not Responding)" and continuous CMD window flashing immediately after clip sync when the Ghost Editor opened. The same code ran fine via `python gui/app.py` because pydub finds ffmpeg on venv PATH and cmd windows are visible. In `--windowed` frozen exe, these subprocess calls expose the bugs.

---

- Date/Time: 2026-05-01 21:01
- Task: AI Workshop language fix + more discussion + auto clip-dur + remove duplicate Script Generation
- Changes:
  - `modules/scripter.py` — `_CONSULTANT_SYSTEM` prompt updated:
    1. **Language rule**: AI now detects user's language and replies in the same language (English → English, Hindi/Hinglish → Hindi). PLAN block values (TOPIC, META_TITLE, META_TAGS) are always in English for YouTube metadata.
    2. **More discussion required**: AI now requires at least 3–4 meaningful exchanges before auto-emitting the PLAN block. Previously it started after 1–2 messages. Explicit start commands (rule 1) still trigger immediately. Updated acknowledgement model message to match.
  - `gui/tabs/documentary_tab.py` — Footage Settings:
    - Removed "Max clip dur:" dropdown and label from UI.
    - Removed `_save_clip_dur()` method.
    - Clip duration is now fully auto-calculated in the pipeline.
  - `core/pipeline_runner.py`:
    - Main pipeline: `max_clip_dur` now auto-calculated as `(total_duration / n_segments) + 20s buffer` instead of reading `documentary.max_clip_duration` from config.
    - Regen path (`_documentary_regen_video`): same auto-calculation using actual audio file duration via `_probe_duration`.
  - `gui/tabs/settings_tab.py`:
    - Removed `self._build_script_generation_section(scroll)` call from `_init_ui`.
    - Deleted the entire `_build_script_generation_section` method body (renamed to `_REMOVED` as tombstone).
    - Moved `_on_provider_switch` to sit right after the removed section comment so it's still defined and available (previously it was inside the removed section's block area).
    - The "AI SCRIPT PROVIDER" quick-grid cell (c11) already contained Gemini model dropdown + Ollama URL/model entry — this is now the single source of truth.
- Reason: User requested: (1) AI replies in English when user speaks English; (2) AI should have more conversation before auto-starting; (3) clip duration should be smart/auto; (4) duplicate Script Generation section removed from settings.

---

- Date/Time: 2026-05-01 21:21
- Task: Kokoro TTS — added then immediately removed (Hindi not supported)
- Changes:
  - `backends/tts/kokoro_tts.py`: Created then deleted — Kokoro TTS only supports English/French/Italian/Japanese/Chinese, NOT Hindi or any Indian language.
  - `modules/voicer.py`: kokoro entry added then removed from BACKEND_MAP.
  - `modules/tts_lang_support.py`: Kokoro language constants added then removed.
  - `gui/tabs/settings_tab.py`: Kokoro description added then removed from TTS_DESCRIPTIONS. OmniVoice description updated to note GPU requirement.
  - `core/pipeline_runner.py`: Added `_has_gpu()` utility + OmniVoice GPU warning (kept). Kokoro mention in warning text replaced with Edge TTS.
  - `modules/error_analyst.py`: Removed stale Kokoro mention from backend list.
- Reason: User requested Kokoro TTS for CPU users, but Kokoro v1.0 doesn't support Hindi/Indian languages. User confirmed to remove it entirely. GPU warning for OmniVoice and _has_gpu() utility were kept as they are useful regardless.

---

- Date/Time: 2026-05-01 21:26
- Task: Version sync to 4.2.2 across all files
- Changes:
  - `installer_v4.iss`: `#define MyAppVersion` changed from `"4.2.0"` → `"4.2.2"` (was the only mismatch).
  - `config.py`: Already `APP_VERSION = "4.2.2"` ✅
  - `build.bat`: Already says `v4.2.2` in echo labels ✅
  - `README.md`: Already `v4.2.2` ✅
- Reason: User requested all version strings be `4.2.2`.

---

- Date/Time: 2026-05-01 21:50
- Task: Fix aspect ratio bug — Long Form was using 9:16 instead of 16:9
- Changes:
  - `gui/tabs/documentary_tab.py`:
    - In `_apply_mode()`: when mode switches to `"long"`, now automatically sets `config aspect_ratio = "16:9"` and calls `_refresh_doc_aspect_lbl()`.
    - In `_on_run()`: added safety enforcement — if `_doc_mode == "long"`, force `aspect_ratio = "16:9"` in config before reading `ar` for the pipeline log.
- Reason: User reported `aspect=9:16` in log when Long Form was selected. Long-form documentaries should always be landscape 16:9. The saved config defaulted to 9:16 (from Short Form preference) and was never overridden when switching to Long mode.
