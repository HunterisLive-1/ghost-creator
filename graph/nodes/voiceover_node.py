"""
graph/nodes/voiceover_node.py — Voiceover Worker Node
===================================================
Implements parallel voiceover TTS synthesis step.
"""

import logging
import time
from pathlib import Path
from core.config_manager import config
from graph.state import GhostCreatorState

log = logging.getLogger("voiceover_node")

def voiceover_worker_node(worker_state: dict) -> dict:
    """
    Voiceover generation worker. Runs in parallel with image generation.
    """
    voiceover_text = worker_state.get("voiceover_text", "").strip()
    language = worker_state.get("language", "hi")
    run_dir = worker_state.get("run_dir", "")
    run_id = worker_state.get("run_id", "")
    
    from graph.nodes.research_node import emit_progress
    
    if not voiceover_text:
        log.warning("Empty voiceover text passed to worker.")
        return {"audio_path": ""}

    output_path = Path(run_dir) / "voiceover.mp3"
    
    from modules.voicer import run_voiceover
    
    emit_progress(3, "🎙️ Starting voiceover TTS generation ...", "INFO", run_id)

    max_attempts = 3  # 1 initial + 2 retries
    for attempt in range(1, max_attempts + 1):
        try:
            log.info(f"Generating voiceover (attempt {attempt}/{max_attempts}) ...")
            emit_progress(3, f"🎙️ Generating voiceover (attempt {attempt}/{max_attempts}) ...", "INFO", run_id)
            
            # Simple progress callback to log progress
            def voice_progress(msg: str) -> None:
                log.info(f"[TTS Progress] {msg}")
                emit_progress(3, f"🗣️ {msg}", "INFO", run_id)

            audio_path = run_voiceover(
                voiceover_text,
                language=language,
                output_path=output_path,
                progress_callback=voice_progress
            )
            
            log.info(f"Successfully generated voiceover saved to {audio_path}")
            emit_progress(3, "✅ Voiceover generation completed successfully.", "SUCCESS", run_id)
            return {"audio_path": str(audio_path)}
            
        except Exception as exc:
            log.warning(f"Attempt {attempt} failed to generate voiceover: {exc}")
            emit_progress(3, f"⚠️ Attempt {attempt} failed to generate voiceover: {exc}", "WARNING", run_id)
            if attempt < max_attempts:
                log.info("Sleeping for 5 seconds before retry...")
                time.sleep(5)
            else:
                log.error("Voiceover worker failed all attempts.")
                emit_progress(3, f"❌ Voiceover generation failed all attempts: {exc}", "ERROR", run_id)
                return {
                    "audio_path": "",
                    "errors": [f"Voiceover failed: {exc}"]
                }
                
    return {"audio_path": ""}
