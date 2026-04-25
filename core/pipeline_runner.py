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
import threading
from datetime import datetime
from pathlib import Path
from config import get_logger, TEMP_DIR, OUTPUT_DIR

log = get_logger("pipeline")


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

        self._image_review_event = threading.Event()
        self._image_review_selections: dict | None = None
        self.pending_image_paths: list | None = None
        self.pending_scene_prompts: list | None = None
        self.waiting_for_image_review = False

        self._video_preview_event = threading.Event()
        self._video_preview_approved: bool = False
        self._video_preview_action: str | None = None  # approve|cancel|regen_audio|regen_video
        self.pending_video_path: str | None = None
        self.waiting_for_video_preview = False
        # Documentary-only: regen from preview reuses this context
        self._doc_regen_ctx: dict | None = None

    def start(self, topic: str | None = None) -> None:
        """Start the pipeline in a background thread."""
        if self.thread and self.thread.is_alive():
            log.warning("Pipeline already running!")
            return

        self._approved_script = None
        self.pending_script_data = None
        self.waiting_for_script_review = False

        self._image_review_selections = None
        self.pending_image_paths = None
        self.pending_scene_prompts = None
        self.waiting_for_image_review = False

        self._video_preview_event.clear()
        self._video_preview_approved = False
        self._video_preview_action = None
        self.pending_video_path = None
        self.waiting_for_video_preview = False
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
        # Wake a blocked video preview wait (worker treats as cancel)
        self._video_preview_action = "cancel"
        self._script_review_event.set()
        self._image_review_event.set()
        self._video_preview_event.set()
        self._emit(0, "Pipeline stopped by user", "WARNING")
        log.info("Pipeline stop requested by user")

    def approve_script(self, approved_data: dict) -> None:
        """Called by GUI when user approves script in review window."""
        self._approved_script = approved_data
        self._script_review_event.set()

    def cancel_pipeline_from_review(self) -> None:
        """Called by GUI when user cancels from review window."""
        self.waiting_for_script_review = False
        self._approved_script = None
        self.stop()

    def continue_from_image_review(self, selections: dict) -> None:
        """Called by GUI when user clicks Continue in image review window."""
        self._image_review_selections = selections
        self._image_review_event.set()

    def skip_image_review(self) -> None:
        """Called by GUI when user clicks Skip in image review window."""
        if self.pending_image_paths:
            self._image_review_selections = {p: False for p in self.pending_image_paths}
        else:
            self._image_review_selections = {}
        self._image_review_event.set()

    def cancel_from_image_review(self) -> None:
        """Called when user closes image review window."""
        self._image_review_selections = {}
        self.stop()
        self._image_review_event.set()

    def set_video_preview_decision(self, action: str) -> None:
        """
        GUI calls this when the user acts on the video preview modal.
        actions: 'approve' | 'cancel' | 'regen_audio' | 'regen_video' (documentary only for regen_*).
        """
        valid = ("approve", "cancel", "regen_audio", "regen_video")
        if action not in valid:
            return
        if action == "approve":
            self._video_preview_approved = True
        else:
            self._video_preview_approved = False
        self._video_preview_action = action
        self.waiting_for_video_preview = False
        if action == "cancel":
            self.stop()
        else:
            self._video_preview_event.set()

    def approve_video_preview(self) -> None:
        """Called by GUI when user approves the video preview and wants to continue."""
        self.set_video_preview_decision("approve")

    def cancel_from_video_preview(self) -> None:
        """Called by GUI when user cancels from the video preview window."""
        self.set_video_preview_decision("cancel")

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

            pipeline_mode = config.get("pipeline_mode", "normal")

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

            if pipeline_mode == "documentary":
                self._run_documentary(topic, config)
                return

            # ── Step 2: Script ────────────────────────────────────────────
            if not self.running:
                return
            from modules.scripter import generate_script
            language = config.get("pipeline.language", "hi")
            target_duration = config.get("target_duration", 60)
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
            _provider_label = script_cfg["script_provider"].capitalize()
            self._emit(2, f"📝 Generating script via {_provider_label} …", "INFO")
            script = generate_script(
                topic,
                lang=language,
                target_duration=target_duration,
                aspect_ratio=aspect_ratio,
                script_config=script_cfg,
            )
            title = script["metadata"]["title"]
            self._emit(2, f"Script ready: {title!r}", "SUCCESS")
            log.info(
                "Script v3: num_scenes=%s, target_duration=%ss, aspect_ratio=%s, language=%s",
                script.get("num_scenes"),
                target_duration,
                aspect_ratio,
                language,
            )

            # ── Script review pause ─────────────────────────────────────
            if config.get("script_review_enabled", True):
                self._emit(2, "Script ready — waiting for your review...", "INFO")
                self.pending_script_data = {
                    "title": script["metadata"]["title"],
                    "voiceover": script["voiceover_text"],
                    "image_prompts": list(script["image_prompts"]),
                }
                self.waiting_for_script_review = True
                self._script_review_event.clear()

                self._script_review_event.wait()

                if not self.running:
                    self.progress_queue.put({
                        "step": 0,
                        "message": "Pipeline cancelled",
                        "level": "WARNING",
                        "timestamp": datetime.now().isoformat(),
                        "done": True,
                        "output_path": "",
                        "run_id": self._run_id,
                    })
                    return
                if self._approved_script is None:
                    self.progress_queue.put({
                        "step": 0,
                        "message": "Pipeline cancelled",
                        "level": "WARNING",
                        "timestamp": datetime.now().isoformat(),
                        "done": True,
                        "output_path": "",
                        "run_id": self._run_id,
                    })
                    return

                approved = self._approved_script
                script["voiceover_text"] = approved["voiceover"]
                script["metadata"]["title"] = approved["title"]
                script["image_prompts"] = list(approved["image_prompts"])
                n_prompts = len(script["image_prompts"])
                script["num_scenes"] = max(1, min(n_prompts, 40))

                self.waiting_for_script_review = False
                self.pending_script_data = None
                self._emit(2, "Script approved — continuing pipeline...", "SUCCESS")
            else:
                self._emit(2, "Script ready — review disabled, continuing...", "SUCCESS")

            # ── Per-run output subfolder ──────────────────────────────────
            # Title is final now (post-review). Create a dated subfolder so
            # images + video for this run are never overwritten by the next run.
            import json
            run_dir = _make_run_dir(script["metadata"]["title"], config, OUTPUT_DIR)
            self._emit(2, f"[INFO] Run folder: {run_dir}", "INFO")
            log.info(f"Run output folder: {run_dir}")

            # Save metadata (after optional review edits)
            try:
                (run_dir / "metadata.json").write_text(
                    json.dumps(script["metadata"], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass
            # Also keep a "last run" reference at the top-level output dir
            try:
                (OUTPUT_DIR / "last_metadata.json").write_text(
                    json.dumps(script["metadata"], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

            # ── Step 3: Voice ─────────────────────────────────────────────
            if not self.running:
                return
            self._emit(3, "🎙️ Generating voiceover …", "INFO")
            from modules.voicer import run_voiceover

            def _voice_progress(msg: str) -> None:
                self._emit(3, msg, "INFO")

            audio_path = run_voiceover(
                script["voiceover_text"],
                language=language,
                output_path=run_dir / "voiceover.mp3",
                progress_callback=_voice_progress,
            )
            self._emit(3, f"Voiceover saved: {audio_path}", "SUCCESS")

            # ── Step 4: Images ────────────────────────────────────────────
            if not self.running:
                return
            self._emit(4, "🎨 Generating images …", "INFO")
            num_scenes = int(script.get("num_scenes", len(script["image_prompts"])))
            image_prompts = script["image_prompts"][:num_scenes]
            if len(script["image_prompts"]) < num_scenes:
                log.warning(
                    "Gemini returned %s prompts but num_scenes=%s — generating %s image(s)",
                    len(script["image_prompts"]),
                    num_scenes,
                    len(image_prompts),
                )
            log.info(
                "Image step: %s prompt(s) for num_scenes=%s, aspect_ratio=%s",
                len(image_prompts),
                num_scenes,
                aspect_ratio,
            )

            image_source = config.get("image_source", "ai_generate")

            if image_source == "custom_images":
                custom_paths = config.get("custom_image_paths", [])
                if not custom_paths:
                    self._emit(4, "Custom images mode selected but no images provided!", "ERROR")
                    self.progress_queue.put({
                        "step": 0,
                        "message": "❌ No custom images provided",
                        "level": "ERROR",
                        "timestamp": datetime.now().isoformat(),
                        "done": True,
                        "output_path": "",
                        "run_id": self._run_id,
                    })
                    return

                self._emit(4, f"Preparing {len(custom_paths)} custom images...", "INFO")
                from modules.image_prep import fill_image_list, prepare_custom_images

                def _prep_log(msg: str) -> None:
                    lvl = "ERROR" if "[ERROR]" in msg else "SUCCESS" if "[OK]" in msg else "INFO"
                    clean = msg.replace("[ERROR] ", "").replace("[OK] ", "").replace("[INFO] ", "")
                    self._emit(4, clean, lvl)

                prepared = prepare_custom_images(
                    image_paths=custom_paths,
                    aspect_ratio=config.get("aspect_ratio", "9:16"),
                    output_dir=str(TEMP_DIR),
                    log=_prep_log,
                )
                image_paths = fill_image_list(
                    prepared,
                    num_scenes,
                    log=_prep_log,
                )
                self._emit(4, f"{len(image_paths)} images ready for video", "SUCCESS")
            else:
                from modules.image_gen import run_image_generation
                image_paths = run_image_generation(
                    image_prompts,
                    output_dir=run_dir,
                    aspect_ratio=aspect_ratio,
                )
                self._emit(4, f"{len(image_paths)} images generated", "SUCCESS")

            # ── Image review pause ────────────────────────────────────────
            self._emit(4, f"[OK] {len(image_paths)} images ready", "SUCCESS")
            self.pending_image_paths = [str(p) for p in image_paths]
            self.pending_scene_prompts = list(script.get("image_prompts", []))

            # Auto-convert all images to video if img2video_enabled is True for custom images
            img2video_auto = (
                image_source == "custom_images"
                and bool(config.get("img2video_enabled", False))
            )
            if img2video_auto:
                self._emit(4, "[INFO] Auto-converting all uploaded images to video clips...", "INFO")
                self._image_review_selections = {str(p): True for p in image_paths}
                self.waiting_for_image_review = False
            else:
                self.waiting_for_image_review = True
                self._image_review_event.clear()
                self._emit(4, "[INFO] Waiting for image review...", "INFO")
                self._image_review_event.wait()

            if not img2video_auto:
                if not self.running:
                    self.progress_queue.put({
                        "step": 0,
                        "message": "Pipeline cancelled",
                        "level": "WARNING",
                        "timestamp": datetime.now().isoformat(),
                        "done": True,
                        "output_path": "",
                        "run_id": self._run_id,
                    })
                    return
                self.waiting_for_image_review = False

            selections = self._image_review_selections

            if selections and any(v for v in selections.values()):
                self._emit(4, "[INFO] Converting selected images to video clips...", "INFO")
                from modules.img2video import process_selected_images

                def _i2v_log(msg: str) -> None:
                    lvl = "ERROR" if "[ERROR]" in msg else "SUCCESS" if "[OK]" in msg else "WARNING" if "[WARN]" in msg else "INFO"
                    self._emit(4, msg, lvl)

                img_prompts_map = {
                    str(image_paths[i]): (self.pending_scene_prompts[i] if i < len(self.pending_scene_prompts) else "")
                    for i in range(len(image_paths))
                }
                cfg_with_prompts = dict(config.data)
                cfg_with_prompts["_scene_prompts"] = img_prompts_map

                scene_data_map = process_selected_images(
                    selections=selections,
                    config=cfg_with_prompts,
                    temp_dir=str(TEMP_DIR),
                    log_fn=_i2v_log,
                )
                scene_data = [scene_data_map.get(str(p), {"type": "image", "path": str(p)}) for p in image_paths]
            else:
                scene_data = [{"type": "image", "path": str(p)} for p in image_paths]

            # ── Step 5: Video ─────────────────────────────────────────────
            if not self.running:
                return
            self._emit(5, "🎬 Assembling video with FFmpeg …", "INFO")
            from modules.video_builder import build_video
            cinematic_effects = config.get("cinematic_effects", {})
            log.info(
                "Video step: %s scene(s), aspect_ratio=%s, target_duration=%ss",
                len(scene_data),
                aspect_ratio,
                target_duration,
            )
            _raw_title = script["metadata"]["title"]
            _output_filename = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            video_path = build_video(
                scene_data=scene_data,
                audio_path=audio_path,
                voiceover_text=script["voiceover_text"],
                english_subtitle_text=script.get("english_subtitle_text", script["voiceover_text"]),
                title=_raw_title,
                aspect_ratio=aspect_ratio,
                cinematic_effects=cinematic_effects,
                target_duration=target_duration,
                output_filename=_output_filename,
                output_dir=run_dir,
            )
            self._emit(5, f"Video rendered: {video_path}", "SUCCESS")

            # ── Step 5.5: Video preview (optional pause before upload) ───────
            if config.get("video_preview_enabled", True):
                if not self.running:
                    return
                self._video_preview_action = None
                self.pending_video_path = str(video_path)
                self.waiting_for_video_preview = True
                self._video_preview_event.clear()
                self._emit(5, "🎬 Video ready — waiting for your preview …", "INFO")
                self._video_preview_event.wait()   # blocks until GUI approves or cancels
                self.waiting_for_video_preview = False
                act = self._video_preview_action
                self._video_preview_action = None
                if not self.running or act == "cancel" or act in ("regen_audio", "regen_video"):
                    return
                if act == "approve" or self._video_preview_approved:
                    self._emit(5, "Video approved ✓ — continuing …", "SUCCESS")
                else:
                    return

            # ── Step 5.7: Thumbnail (optional, only when upload is enabled) ──
            thumbnail_path: str = ""
            if config.get("pipeline.upload_enabled", True) and config.get("pipeline.thumbnail_enabled", True):
                if not self.running:
                    return
                self._emit(5, "🖼️ Generating clickbait thumbnail …", "INFO")
                try:
                    from modules.thumbnail_maker import generate_thumbnail

                    def _thumb_progress(msg: str) -> None:
                        self._emit(5, msg, "INFO")

                    thumbnail_path = generate_thumbnail(
                        title=script["metadata"]["title"],
                        topic=topic,
                        aspect_ratio=aspect_ratio,
                        image_prompts=script.get("image_prompts", []),
                        progress_callback=_thumb_progress,
                    )
                    self._emit(5, f"Thumbnail saved: {Path(thumbnail_path).name}", "SUCCESS")
                    script["metadata"]["thumbnail_path"] = thumbnail_path
                except Exception as thumb_exc:
                    log.warning(f"Thumbnail generation failed (non-fatal): {thumb_exc}")
                    self._emit(5, f"⚠️ Thumbnail skipped: {thumb_exc}", "WARNING")

            # ── Step 6: Upload (optional) ───────────────────────────────────
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
                done_msg = f"Pipeline complete! Video: {video_path}"
            else:
                self._emit(6, "⏭️ YouTube upload disabled — video saved locally.", "SUCCESS")
                log.info(
                    "Skipping YouTube upload (pipeline.upload_enabled=False). File: %s",
                    video_path,
                )
                done_msg = f"Pipeline complete (no upload). Video saved: {video_path}"

            # ── Done ──────────────────────────────────────────────────────
            self.progress_queue.put({
                "step": 7,
                "message": done_msg,
                "level": "SUCCESS",
                "timestamp": datetime.now().isoformat(),
                "done": True,
                "output_path": str(video_path),
                "run_id": self._run_id,
            })

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
            self.waiting_for_image_review = False

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
        self._emit(4, f"📹 Re-downloading {len(script['segments'])} footage clips …", "INFO")
        max_clip_dur = int(config.get("documentary.max_clip_duration", 120))
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
        self._emit(2, f"Script ready: {title!r} ({num_segs} segments)", "SUCCESS")
        log.info("Documentary script: %s segments", num_segs)

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
        except Exception:
            pass

        # ── Step 3: Voiceover ─────────────────────────────────────────────
        if not self.running:
            return
        self._emit(3, "🎙️ Generating voiceover …", "INFO")
        from modules.voicer import run_voiceover

        def _voice_progress(msg: str) -> None:
            self._emit(3, msg, "INFO")

        audio_path = run_voiceover(
            script["voiceover_text"],
            language=language,
            output_path=run_dir / "voiceover.mp3",
            progress_callback=_voice_progress,
        )
        self._emit(3, f"Voiceover saved: {audio_path}", "SUCCESS")

        # ── Step 4: Download footage clips ────────────────────────────────
        if not self.running:
            return
        self._emit(4, f"📹 Downloading {num_segs} footage clips from YouTube …", "INFO")
        from modules.video_fetcher import fetch_clips

        def _fetch_progress(msg: str) -> None:
            self._emit(4, msg, "INFO")

        max_clip_dur = int(config.get("documentary.max_clip_duration", 120))
        clips_dir = run_dir / "clips"
        clips = fetch_clips(
            script["segments"],
            clips_dir,
            max_clip_duration=max_clip_dur,
            progress_callback=_fetch_progress,
        )
        good = sum(1 for c in clips if c is not None)
        self._emit(4, f"{good}/{num_segs} clips downloaded", "SUCCESS" if good > 0 else "WARNING")

        # ── Step 5: Assemble documentary ──────────────────────────────────
        if not self.running:
            return
        self._emit(5, "🎬 Assembling documentary with FFmpeg …", "INFO")
        from modules.documentary_assembler import assemble_documentary, wants_burned_subtitles

        def _asm_progress(msg: str) -> None:
            self._emit(5, msg, "INFO")

        _output_filename = f"documentary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        _pb_speed = float(config.get("documentary.playback_speed", 1.0))
        _burn = wants_burned_subtitles(config)
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
        )
        self._emit(5, f"Documentary rendered: {video_path}", "SUCCESS")

        # ── Step 5.5: Video preview (loop: approve, or regen audio/video, then re-preview) ─
        if config.get("video_preview_enabled", True):
            if not self.running:
                return
            self._doc_regen_ctx = {
                "run_dir": run_dir,
                "script": script,
                "language": language,
                "aspect_ratio": aspect_ratio,
                "clips": clips,
                "audio_path": audio_path,
                "last_video_path": str(video_path),
            }
            try:
                while self.running:
                    video_path = Path(self._doc_regen_ctx["last_video_path"])
                    self._video_preview_action = None
                    self.pending_video_path = str(video_path)
                    self.waiting_for_video_preview = True
                    self._video_preview_event.clear()
                    self._emit(5, "🎬 Video ready — waiting for your preview …", "INFO")
                    self._video_preview_event.wait()
                    self.waiting_for_video_preview = False

                    if not self.running:
                        return
                    act = self._video_preview_action
                    self._video_preview_action = None

                    if act == "approve":
                        self._emit(5, "Video approved ✓ — continuing …", "SUCCESS")
                        break
                    if act in (None, "cancel"):
                        return
                    if act == "regen_audio":
                        if not self.running:
                            return
                        try:
                            self._emit(3, "🎙️ Regenerating voiceover (uses current Settings) …", "INFO")
                            new_vp = self._documentary_regen_audio(config, self._doc_regen_ctx)
                            self._doc_regen_ctx["last_video_path"] = str(new_vp)
                        except Exception as exc:
                            log.error("Regen audio failed: %s", exc, exc_info=True)
                            self._emit(5, f"❌ Regen audio failed: {exc}", "ERROR")
                        continue
                    if act == "regen_video":
                        if not self.running:
                            return
                        try:
                            self._emit(4, "📹 Regenerating footage (uses current Settings) …", "INFO")
                            new_vp = self._documentary_regen_video(config, self._doc_regen_ctx)
                            self._doc_regen_ctx["last_video_path"] = str(new_vp)
                        except Exception as exc:
                            log.error("Regen video failed: %s", exc, exc_info=True)
                            self._emit(5, f"❌ Regen video failed: {exc}", "ERROR")
                        continue
                    return
            finally:
                self._doc_regen_ctx = None

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

        self.progress_queue.put({
            "step": 7,
            "message": done_msg,
            "level": "SUCCESS",
            "timestamp": datetime.now().isoformat(),
            "done": True,
            "output_path": str(video_path),
            "run_id": self._run_id,
        })

    def _emit(self, step: int, message: str, level: str = "INFO") -> None:
        """Emit a progress event to the queue."""
        self.progress_queue.put({
            "step": step,
            "message": message,
            "level": level,
            "timestamp": datetime.now().isoformat(),
            "run_id": self._run_id,
        })
