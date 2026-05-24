"""
core/pipeline_runner.py — Threaded Pipeline Runner
====================================================
Runs the Ghost Creator pipeline steps in a background thread,
communicating progress to the GUI via a queue.Queue.

Usage:
    import queue
    q = queue.Queue()
    runner = PipelineRunner(q)
    runner.start(topic="AI in 2026")
    # Poll q for progress events
    runner.stop()  # cancel mid-pipeline
"""

import queue
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from config import get_logger, OUTPUT_DIR

log = get_logger("pipeline")

_NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _has_gpu() -> bool:
    """
    Return True if an NVIDIA CUDA GPU is available.
    Fast check — uses nvidia-smi (always present on CUDA systems).
    Falls back to torch.cuda.is_available() if nvidia-smi is not on PATH.
    """
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, timeout=5,
            creationflags=_NO_WINDOW,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        pass
    return False


def _make_run_dir(title: str, config, fallback: Path) -> Path:
    """
    Create a per-run subfolder inside the configured output folder.

    Folder name: <safe_title>_<YYYYMMDD_HHMMSS>
    e.g.  Street_Light_Sapne_20260327_163808/

    Falls back to ``fallback`` (OUTPUT_DIR) if the subfolder cannot be created
    (permission error, invalid path, etc.).
    """
    _safe = re.sub(
        r'[^\w\u0900-\u097F\u0A00-\u0A7F\u0B00-\u0B7F\u0B80-\u0BFF'
        r'\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0980-\u09FF -]',
        '', title,
    )
    _safe = re.sub(r'\s+', '_', _safe.strip()).strip('_')[:40] or "run"
    _stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{_safe}_{_stamp}"

    # Resolve configured base output folder
    _base_str = config.get("pipeline.output_folder", "").strip()
    if _base_str:
        base = Path(_base_str)
        if not base.is_absolute():
            base = fallback.parent / _base_str
    else:
        base = fallback

    try:
        run_dir = base / folder_name
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    except Exception as exc:
        log.warning(f"Could not create run subfolder ({exc}) — using fallback: {fallback}")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _distribute_length_by_weights(total_len: int, weights: list[int]) -> list[int]:
    """Split total_len into len(weights) integers proportional to weights; sum equals total_len."""
    n = len(weights)
    if n == 0:
        return []
    if total_len <= 0:
        return [0] * n
    s = sum(weights) or 1
    raw = [total_len * (weights[i] / s) for i in range(n)]
    parts = [int(r) for r in raw]
    rem = total_len - sum(parts)
    fracs = sorted(range(n), key=lambda i: raw[i] - parts[i], reverse=True)
    for j in range(rem):
        parts[fracs[j]] += 1
    return parts


def _resync_segment_voiceovers(new_voiceover_text: str, segments: list[dict]) -> None:
    """Re-split full narration into segment voiceover strings for cut-length math (proportional to prior segment sizes)."""
    n = len(segments)
    if n == 0:
        return
    t = new_voiceover_text
    l_total = len(t)
    if l_total == 0:
        for seg in segments:
            seg["voiceover"] = ""
        return
    weights = [max(1, len(str(seg.get("voiceover", "")))) for seg in segments]
    part_lens = _distribute_length_by_weights(l_total, weights)
    offset = 0
    for i, plen in enumerate(part_lens):
        segment = segments[i]
        segment["voiceover"] = t[offset : offset + plen]
        offset += plen


class PipelineRunner:
    """
    Orchestrates the 6-step pipeline in a background thread.
    Emits progress events via a queue.Queue for GUI consumption.
    """

    def __init__(self, progress_queue: queue.Queue, run_id: int = 0) -> None:
        self.progress_queue = progress_queue
        self._run_id = run_id
        self.running = False
        self.thread: threading.Thread | None = None

        self._script_review_event = threading.Event()
        self._approved_script: dict | None = None
        self.pending_script_data: dict | None = None
        self.waiting_for_script_review = False

        # Documentary-only: clip sync context for assembly / History re-render
        self._doc_regen_ctx: dict | None = None

        # Per-step retry
        self._retry_event = threading.Event()
        self._retry_requested = False
        self.waiting_for_retry = False

    def start(self, topic: str | None = None) -> None:
        """Start the pipeline in a background thread."""
        if self.thread and self.thread.is_alive():
            log.warning("Pipeline already running!")
            return

        self._approved_script = None
        self.pending_script_data = None
        self.waiting_for_script_review = False
        self._doc_regen_ctx = None

        self.running = True
        self.thread = threading.Thread(
            target=self._run,
            args=(topic,),
            daemon=True,
        )
        self.thread.start()
        log.info(f"Pipeline started (topic={topic!r})")

    def stop(self) -> None:
        """Request the pipeline to stop after the current step."""
        self.running = False
        self.waiting_for_script_review = False
        self.pending_script_data = None
        # Wake a blocked script review or retry wait so the thread can exit
        self._script_review_event.set()
        self._retry_event.set()
        self._emit(0, "Pipeline stopped by user", "WARNING")
        log.info("Pipeline stop requested by user")

    def request_retry(self) -> None:
        """Called by GUI when the user clicks the Retry button on a failed step."""
        self._retry_requested = True
        self.waiting_for_retry = False
        self._retry_event.set()
        log.info("Retry requested by user")

    def _reset_retry(self) -> None:
        """Clear retry state before (re-)attempting a step."""
        self._retry_requested = False
        self.waiting_for_retry = False
        self._retry_event.clear()

    def approve_script(self, approved_data: dict) -> None:
        """Called by GUI when user approves script in review window."""
        self._approved_script = approved_data
        self._script_review_event.set()

    def cancel_pipeline_from_review(self) -> None:
        """Called by GUI when user cancels from review window."""
        self.waiting_for_script_review = False
        self._approved_script = None
        self.stop()

    def apply_documentary_preview_script(self, approved_data: dict) -> bool:
        """
        Patch the in-memory documentary script used for post-preview regen (narration + per-scene search queries).
        Does not touch script-review events or the background worker. Call from GUI after the user
        saves edits in the same shape as :meth:`approve_script` (title, voiceover, image_prompts).
        """
        ctx = self._doc_regen_ctx
        if not ctx or not isinstance(ctx.get("script"), dict):
            log.warning("apply_documentary_preview_script: no documentary preview context")
            return False
        script: dict = ctx["script"]
        segs = script.get("segments") or []
        new_queries = list(approved_data.get("image_prompts") or [])
        if len(new_queries) != len(segs):
            log.warning(
                "apply_documentary_preview_script: %s prompts but %s segments",
                len(new_queries), len(segs),
            )
            return False
        voiceover = (approved_data.get("voiceover") or "").strip()
        if not voiceover:
            return False
        if not any(q.strip() for q in new_queries):
            return False
        title = (approved_data.get("title") or "").strip()
        script["voiceover_text"] = voiceover
        if title:
            script["title"] = title
        for i, q in enumerate(new_queries):
            if i < len(segs):
                segs[i]["video_query"] = q.strip()
        _resync_segment_voiceovers(voiceover, segs)
        md = script.get("metadata")
        if isinstance(md, dict) and title and "title" in md:
            md["title"] = title
        log.info("Documentary preview script updated (%s segment(s))", len(segs))
        return True

    def _run(self, topic: str | None) -> None:
        """Main pipeline execution — runs in background thread."""
        try:
            from core.config_manager import config

            # ── Step 1: Research ──────────────────────────────────────────
            if not self.running:
                return
            self._emit(1, "🔍 Researching trending topic …", "INFO")
            from modules.researcher import find_trending_topic
            if topic:
                self._emit(1, f"Using provided topic: {topic!r}", "INFO")
            else:
                topic = find_trending_topic()
                self._emit(1, f"Found topic: {topic!r}", "SUCCESS")

            self._run_documentary(topic, config)

        except Exception as exc:
            log.error(f"Pipeline failed: {exc}", exc_info=True)
            self.progress_queue.put({
                "step": 0,
                "message": f"❌ Pipeline failed: {exc}",
                "level": "ERROR",
                "timestamp": datetime.now().isoformat(),
                "done": True,
                "output_path": "",
                "run_id": self._run_id,
            })

        finally:
            self.running = False
            self.waiting_for_script_review = False

    def _documentary_regen_audio(self, config, ctx: dict) -> Path:
        """Re-TTS with same script text, same clips, new MP4. Updates ctx['audio_path']."""
        from modules.voicer import run_voiceover
        from modules.documentary_assembler import assemble_documentary, wants_burned_subtitles

        def _v(msg: str) -> None:
            self._emit(3, msg, "INFO")

        def _a(msg: str) -> None:
            self._emit(5, msg, "INFO")

        script = ctx["script"]
        run_dir = ctx["run_dir"]
        run_dir = Path(run_dir) if not isinstance(run_dir, Path) else run_dir
        out_mp3 = run_dir / "voiceover.mp3"
        ap = run_voiceover(
            script["voiceover_text"],
            language=ctx["language"],
            output_path=out_mp3,
            progress_callback=_v,
        )
        if not self.running:
            return Path(ctx["last_video_path"])
        ctx["audio_path"] = ap
        _output_filename = f"documentary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        _pb_speed = float(config.get("documentary.playback_speed", 1.0))
        _burn = wants_burned_subtitles(config)
        ar = str(config.get("aspect_ratio", ctx.get("aspect_ratio", "9:16")))
        vp = assemble_documentary(
            clips=ctx["clips"],
            audio_path=ap,
            segments=script["segments"],
            output_dir=run_dir,
            output_filename=_output_filename,
            aspect_ratio=ar,
            progress_callback=_a,
            playback_speed=_pb_speed,
            burn_subtitles=_burn,
            subtitle_style=ctx.get("subtitle_style"),
            bg_music_path=ctx.get("bg_music"),
            bg_music_volume=float(ctx.get("bg_vol", 0.25)),
        )
        return vp

    def _documentary_regen_video(self, config, ctx: dict) -> Path:
        """Re-fetch footage, then mux with current voiceover. Updates ctx['clips']."""
        from modules.video_fetcher import fetch_clips
        from modules.documentary_assembler import assemble_documentary, wants_burned_subtitles

        def _f(msg: str) -> None:
            self._emit(4, msg, "INFO")

        def _a(msg: str) -> None:
            self._emit(5, msg, "INFO")

        script = ctx["script"]
        run_dir = Path(ctx["run_dir"])
        n_segs = len(script["segments"])
        self._emit(4, f"📹 Re-downloading {n_segs} footage clips …", "INFO")
        # Auto-calculate: spread total audio duration evenly, with a small buffer
        try:
            from modules.documentary_assembler import _probe_duration as _pd
            _audio_dur = _pd(Path(ctx["audio_path"]))
        except Exception:
            _audio_dur = float(ctx.get("target_duration", 600))
        max_clip_dur = max(30, int(_audio_dur / max(1, n_segs)) + 20)
        clips_dir = run_dir / "clips"
        clips = fetch_clips(
            script["segments"],
            clips_dir,
            max_clip_duration=max_clip_dur,
            progress_callback=_f,
        )
        ctx["clips"] = clips
        if not self.running:
            return Path(ctx["last_video_path"])
        ap = Path(ctx["audio_path"])
        _output_filename = f"documentary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        _pb_speed = float(config.get("documentary.playback_speed", 1.0))
        _burn = wants_burned_subtitles(config)
        ar = str(config.get("aspect_ratio", ctx.get("aspect_ratio", "9:16")))
        vp = assemble_documentary(
            clips=clips,
            audio_path=ap,
            segments=script["segments"],
            output_dir=run_dir,
            output_filename=_output_filename,
            aspect_ratio=ar,
            progress_callback=_a,
            playback_speed=_pb_speed,
            burn_subtitles=_burn,
            subtitle_style=ctx.get("subtitle_style"),
            bg_music_path=ctx.get("bg_music"),
            bg_music_volume=float(ctx.get("bg_vol", 0.25)),
        )
        return vp

    # ── Documentary Pipeline ───────────────────────────────────────────────────

    def _run_documentary(self, topic: str, config) -> None:
        """
        Documentary mode pipeline:
          Step 2 → Script with video queries (Gemini)
          Step 3 → Voiceover (OmniVoice)
          Step 4 → Download footage clips (yt-dlp)
          Step 5 → Assemble video (FFmpeg: clips + audio; optional burned-in subs for long form)
          Step 5.5 → Optional video preview
          Step 6 → Upload (optional)
        """
        import json as _json
        from config import OUTPUT_DIR
        from modules.scripter import generate_documentary_script

        language = config.get("pipeline.language", "hi")
        target_duration = config.get("target_duration", 180)
        aspect_ratio = config.get("aspect_ratio", "9:16")
        script_cfg = {
            "script_provider": config.get("script_provider", "gemini"),
            "gemini_model": config.get("gemini_model", "gemini-2.0-flash"),
            "openai_model": config.get("openai_model", "gpt-4o"),
            "openai_api_key": config.get("openai_api_key", ""),
            "api_keys.gemini": config.get("api_keys.gemini", ""),
            "ollama_url": config.get("ollama_url", "http://localhost:11434"),
            "ollama_model": config.get("ollama_model", "llama3"),
            "tts_backend": config.get("tts.backend", "omnivoice"),
        }

        # ── Step 2: Documentary script ────────────────────────────────────
        if not self.running:
            return
        _provider_label = script_cfg["script_provider"].capitalize()

        # Warn upfront for long-form: multiple API calls needed
        from modules.scripter import _DOC_CHUNK_MAX_S
        import math as _math
        if target_duration > _DOC_CHUNK_MAX_S:
            _n_chunks = _math.ceil(target_duration / _DOC_CHUNK_MAX_S)
            self._emit(2,
                f"📝 Long-form video detected ({target_duration//60} min) — "
                f"generating in {_n_chunks} chapters via {_provider_label}. "
                f"This may take {_n_chunks * 20}–{_n_chunks * 40}s …",
                "INFO",
            )
        else:
            self._emit(2, f"📝 Generating documentary script via {_provider_label} …", "INFO")

        n_segs_override = int(config.get("documentary.segments", 0) or 0)
        script = generate_documentary_script(
            topic,
            lang=language,
            target_duration=target_duration,
            script_config=script_cfg,
            n_segments=n_segs_override,
        )
        title = script.get("title") or script.get("metadata", {}).get("title", topic)
        num_segs = len(script["segments"])
        _word_count = len(script["voiceover_text"].split())
        _expected   = int((target_duration / 60) * 130)
        self._emit(2,
            f"Script ready: {title!r} — {num_segs} segments, "
            f"~{_word_count:,} words (target {_expected:,})",
            "SUCCESS",
        )
        log.info("Documentary script: %s segments, ~%s words", num_segs, _word_count)

        if not self.running:
            return

        # Script review (reuse same pause mechanism)
        if config.get("script_review_enabled", True):
            self._emit(2, "Script ready — waiting for your review …", "INFO")
            self.pending_script_data = {
                "title": title,
                "voiceover": script["voiceover_text"],
                "image_prompts": [s["video_query"] for s in script["segments"]],
            }
            self.waiting_for_script_review = True
            self._script_review_event.clear()
            self._script_review_event.wait()

            if not self.running or self._approved_script is None:
                self.progress_queue.put({
                    "step": 0, "message": "Pipeline cancelled", "level": "WARNING",
                    "timestamp": datetime.now().isoformat(), "done": True,
                    "output_path": "", "run_id": self._run_id,
                })
                return

            approved = self._approved_script
            script["voiceover_text"] = approved["voiceover"]
            script["title"] = approved["title"]
            # Update video queries from review (stored in image_prompts slot)
            new_queries = list(approved.get("image_prompts", []))
            for i, q in enumerate(new_queries):
                if i < len(script["segments"]):
                    script["segments"][i]["video_query"] = q
            self.waiting_for_script_review = False
            self.pending_script_data = None
            self._emit(2, "Script approved — continuing …", "SUCCESS")
        else:
            self._emit(2, "Script ready — review disabled, continuing …", "SUCCESS")

        # Create run folder
        run_dir = _make_run_dir(title, config, OUTPUT_DIR)
        self._emit(2, f"[INFO] Run folder: {run_dir}", "INFO")
        log.info("Run output folder: %s", run_dir)

        try:
            (run_dir / "metadata.json").write_text(
                _json.dumps(script["metadata"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # Full script snapshot for History re-render (not just YouTube metadata)
            doc_snap = {
                "title": script.get("title", title),
                "voiceover_text": script["voiceover_text"],
                "segments": script["segments"],
                "language": language,
                "aspect_ratio": aspect_ratio,
            }
            _lp = (str(config.get("documentary.logo_path", "") or "")).strip()
            if (
                bool(config.get("documentary.logo_enabled", False))
                and _lp
                and Path(_lp).is_file()
            ):
                doc_snap["logo_watermark"] = {
                    "enabled": True,
                    "path": _lp,
                    "position": str(config.get("documentary.logo_position", "bottom_right")),
                    "scale": float(config.get("documentary.logo_scale", 0.15)),
                    "margin": int(config.get("documentary.logo_margin", 24)),
                    "opacity": float(config.get("documentary.logo_opacity", 1.0)),
                }
            (run_dir / "documentary_editor.json").write_text(
                _json.dumps(doc_snap, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
        try:
            (OUTPUT_DIR / "last_metadata.json").write_text(
                _json.dumps(script["metadata"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

        # ── Step 3: Voiceover (with retry) ───────────────────────────────
        # OmniVoice GPU check — warn CPU-only users before they wait hours
        _tts_backend = config.get("tts.backend", "omnivoice")
        if _tts_backend == "omnivoice" and not _has_gpu():
            self._emit(
                3,
                "⚠️  OmniVoice GPU Warning: CUDA GPU not detected on this system.\n"
                "   OmniVoice runs on CPU but is extremely slow (2–5 hrs for a 10-min video).\n"
                "   Recommended for CPU users: switch to Edge TTS (free, all Indian languages).\n"
                "   Settings → AUDIO SUBROUTINE → change backend, then retry.",
                "WARNING",
            )

        from modules.voicer import run_voiceover

        def _voice_progress(msg: str) -> None:
            self._emit(3, msg, "INFO")

        audio_path: Path | None = None
        while True:
            if not self.running:
                return
            self._reset_retry()
            self._emit(3, "🎙️ Generating voiceover …", "INFO")
            try:
                audio_path = run_voiceover(
                    script["voiceover_text"],
                    language=language,
                    output_path=run_dir / "voiceover.mp3",
                    progress_callback=_voice_progress,
                )
                self._emit(3, f"Voiceover saved: {audio_path}", "SUCCESS")
                break  # success — move to next step
            except Exception as exc:
                log.error("Step 3 (Voice) failed: %s", exc, exc_info=True)
                self._emit(3, f"❌ Voiceover failed: {exc}", "ERROR", retry_available=True)
                self.waiting_for_retry = True
                self._retry_event.wait()  # block until retry or stop
                if not self.running:
                    return
                self._emit(3, "🔄 Retrying voiceover …", "INFO")

        # ── Step 4: Download footage clips (with retry) ───────────────────
        from modules.video_fetcher import fetch_clips_for_pipeline, footage_source_label

        def _fetch_progress(msg: str) -> None:
            self._emit(4, msg, "INFO")

        _footage_label = footage_source_label()

        # Auto-calculate max clip duration: evenly divide total voiceover duration
        # across clips with a small buffer, clamped to a sensible range.
        _auto_clip_dur = max(30, int(target_duration / max(1, num_segs)) + 20)
        max_clip_dur = _auto_clip_dur
        clips_dir = run_dir / "clips"
        clips: list | None = None
        while True:
            if not self.running:
                return
            self._reset_retry()
            self._emit(
                4,
                f"📹 Fetching {num_segs} clips via {_footage_label} …",
                "INFO",
            )
            try:
                clips = fetch_clips_for_pipeline(
                    script["segments"],
                    clips_dir,
                    max_clip_duration=max_clip_dur,
                    progress_callback=_fetch_progress,
                )
                good = sum(1 for c in clips if c is not None)
                self._emit(4, f"{good}/{num_segs} clips downloaded", "SUCCESS" if good > 0 else "WARNING")
                break  # success
            except Exception as exc:
                log.error("Step 4 (Footage) failed: %s", exc, exc_info=True)
                self._emit(4, f"❌ Footage download failed: {exc}", "ERROR", retry_available=True)
                self.waiting_for_retry = True
                self._retry_event.wait()
                if not self.running:
                    return
                self._emit(4, "🔄 Retrying footage download …", "INFO")

        # ── Step 4.5: Voice-synced clips before FFmpeg assembly ─────────────
        if not self.running:
            return
        from core.clip_manager import generate_srt_from_segments, load_clips
        from modules.documentary_assembler import (
            _audio_duration_sec,
            _normalized_segment_durations,
            _resolution,
            _make_filler,
            _trim_or_loop_clip,
            _vf_scale,
        )

        audio_dur = _audio_duration_sec(audio_path)
        srt_entries = generate_srt_from_segments(script["segments"], audio_dur)
        durations = _normalized_segment_durations(script["segments"], audio_dur)
        vf = _vf_scale(aspect_ratio)
        w, h = _resolution(aspect_ratio)
        n_seg = len(script["segments"])

        clips_for_edit = run_dir / "clips_for_edit"
        clips_for_edit.mkdir(exist_ok=True)
        edit_paths: list[Path] = []
        last_good: Path | None = None

        self._emit(
            4,
            f"🕐 Voiceover: {audio_dur:.1f}s total — syncing footage to narration …",
            "INFO",
        )
        for i in range(n_seg):
            dur = durations[i]
            dst = clips_for_edit / f"e_{i:02d}.mp4"
            src = clips[i] if i < len(clips) else None
            self._emit(4, f"  ✂️  Clip {i+1}/{n_seg}: {dur:.1f}s", "INFO")
            if src and Path(src).exists() and Path(src).stat().st_size > 5000:
                try:
                    _trim_or_loop_clip(Path(src), dst, dur, vf)
                    last_good = dst
                except Exception as exc:
                    log.warning("Pre-edit trim failed for clip %s: %s", i + 1, exc)
                    _make_filler(dst, dur, w, h, last_good, clips_for_edit, i)
                    last_good = dst
            else:
                _make_filler(dst, dur, w, h, last_good, clips_for_edit, i)
                last_good = dst
            edit_paths.append(dst)

        clip_infos = load_clips(edit_paths, script["segments"], target_durations=durations)

        self._doc_regen_ctx = {
            "run_dir": run_dir,
            "script": script,
            "language": language,
            "aspect_ratio": aspect_ratio,
            "clips": clip_infos,
            "audio_path": audio_path,
            "srt": srt_entries,
            "subtitle_style": None,
        }

        clips = clip_infos
        _style = None

        # ── Step 5: Assemble documentary (with retry) ─────────────────────
        from modules.documentary_assembler import assemble_documentary, wants_burned_subtitles

        def _asm_progress(msg: str) -> None:
            self._emit(5, msg, "INFO")

        _ctx = getattr(self, "_doc_regen_ctx", None) or {}
        _bg_music = _ctx.get("bg_music")
        _bg_vol = float(_ctx.get("bg_vol", 0.25))

        _pb_speed = float(config.get("documentary.playback_speed", 1.0))
        _burn = wants_burned_subtitles(config)
        video_path: Path | None = None
        while True:
            if not self.running:
                return
            self._reset_retry()
            self._emit(5, "🎬 Assembling documentary with FFmpeg …", "INFO")
            _output_filename = f"documentary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            try:
                video_path = assemble_documentary(
                    clips=clips,
                    audio_path=audio_path,
                    segments=script["segments"],
                    output_dir=run_dir,
                    output_filename=_output_filename,
                    aspect_ratio=aspect_ratio,
                    progress_callback=_asm_progress,
                    playback_speed=_pb_speed,
                    burn_subtitles=_burn,
                    subtitle_style=_style,
                    bg_music_path=_bg_music,
                    bg_music_volume=_bg_vol,
                    logo_watermark=_ctx.get("logo_watermark"),
                )
                self._emit(5, f"Documentary rendered: {video_path}", "SUCCESS")
                break  # success
            except Exception as exc:
                log.error("Step 5 (Assembly) failed: %s", exc, exc_info=True)
                self._emit(5, f"❌ Assembly failed: {exc}", "ERROR", retry_available=True)
                self.waiting_for_retry = True
                self._retry_event.wait()
                if not self.running:
                    return
                self._emit(5, "🔄 Retrying assembly …", "INFO")

        # ── Step 6: Upload ────────────────────────────────────────────────
        if not self.running:
            return
        if config.get("pipeline.upload_enabled", True):
            self._emit(6, "📤 Uploading to YouTube Studio …", "INFO")
            from modules.uploader import upload_to_youtube

            def _upload_progress(msg: str) -> None:
                self._emit(6, msg, "INFO")

            upload_to_youtube(
                video_path=video_path,
                metadata=script["metadata"],
                progress_callback=_upload_progress,
                retries=1,
            )
            self._emit(6, "Upload complete! 🚀", "SUCCESS")
            done_msg = f"Documentary complete! Video: {video_path}"
        else:
            self._emit(6, "⏭️ Upload disabled — documentary saved locally.", "SUCCESS")
            done_msg = f"Documentary complete (no upload). Saved: {video_path}"

        # ── Write history_entry.json ─────────────────────────────────────────
        _dur_s = int(target_duration)
        _dur_label = (
            f"{_dur_s}s" if _dur_s < 60
            else f"{_dur_s // 60}m {_dur_s % 60}s" if _dur_s % 60
            else f"{_dur_s // 60}m"
        )
        try:
            import json as _json2
            (run_dir / "history_entry.json").write_text(
                _json2.dumps({
                    "topic":      topic or "",
                    "title":      script.get("title", ""),
                    "timestamp":  datetime.now().isoformat(),
                    "duration":   _dur_label,
                    "video_path": str(video_path) if video_path else "",
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

        self.progress_queue.put({
            "step": 7,
            "message": done_msg,
            "level": "SUCCESS",
            "timestamp": datetime.now().isoformat(),
            "done": True,
            "output_path": str(video_path),
            "run_id": self._run_id,
        })


    def _emit(self, step: int, message: str, level: str = "INFO", retry_available: bool = False) -> None:
        """Emit a progress event to the queue."""
        self.progress_queue.put({
            "step": step,
            "message": message,
            "level": level,
            "timestamp": datetime.now().isoformat(),
            "run_id": self._run_id,
            "retry_available": retry_available,
        })
