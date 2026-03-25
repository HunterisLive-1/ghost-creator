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
import threading
from datetime import datetime
from config import get_logger, TEMP_DIR, OUTPUT_DIR

log = get_logger("pipeline")


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
        self._script_review_event.set()
        self._image_review_event.set()
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

            # Save metadata (after optional review edits)
            import json
            metadata_path = OUTPUT_DIR / "last_metadata.json"
            metadata_path.write_text(
                json.dumps(script["metadata"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # ── Step 3: Voice ─────────────────────────────────────────────
            if not self.running:
                return
            self._emit(3, "🎙️ Generating voiceover …", "INFO")
            from modules.voicer import run_voiceover
            audio_path = run_voiceover(script["voiceover_text"], language=language)
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
                from modules.image_gen import generate_images
                image_paths = generate_images(image_prompts, aspect_ratio=aspect_ratio)
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
            import re as _re
            _raw_title = script["metadata"]["title"]
            _safe = _re.sub(r'[^\w\u0900-\u097F\u0A00-\u0A7F\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0980-\u09FF -]', '', _raw_title)
            _safe = _re.sub(r'\s+', '_', _safe.strip()).strip('_') or "video"
            _safe = _safe[:60]
            _timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            _output_filename = f"{_safe}_{_timestamp}.mp4"
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
            )
            self._emit(5, f"Video rendered: {video_path}", "SUCCESS")

            # ── Step 6: Upload (optional) ───────────────────────────────────
            if not self.running:
                return
            if config.get("pipeline.upload_enabled", True):
                self._emit(6, "📤 Uploading to YouTube Studio …", "INFO")
                from modules.uploader import upload_to_youtube
                upload_to_youtube(video_path=video_path, metadata=script["metadata"])
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

    def _emit(self, step: int, message: str, level: str = "INFO") -> None:
        """Emit a progress event to the queue."""
        self.progress_queue.put({
            "step": step,
            "message": message,
            "level": level,
            "timestamp": datetime.now().isoformat(),
            "run_id": self._run_id,
        })
