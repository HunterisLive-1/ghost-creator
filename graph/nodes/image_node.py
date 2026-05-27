"""
graph/nodes/image_node.py — Image Spawner and Worker Nodes
=========================================================
Implements LangGraph Send() structure to generate images in parallel.
"""

import logging
import asyncio
import time
from pathlib import Path
from langgraph.types import Send
from core.config_manager import config
from graph.state import GhostCreatorState

log = logging.getLogger("image_node")

def spawn_parallel_tasks(state: GhostCreatorState) -> list:
    """
    Fan-out node: spawns one image worker per image prompt + one voiceover worker.
    Returns a list of Send() objects for LangGraph parallel execution.
    """
    sends = []
    image_prompts = state["script"].get("image_prompts", [])
    run_dir = state.get("run_dir", "")
    run_id = state.get("run_id", "")
    mode = state.get("mode", "shorts")
    
    # 1. Spawn image generation workers only if mode is not documentary
    if mode != "documentary":
        for i, prompt_item in enumerate(image_prompts):
            prompt_str = prompt_item if isinstance(prompt_item, str) else prompt_item.get("prompt", "")
            sends.append(Send("image_worker", {
                "image_prompt": prompt_str,
                "scene_index": i,
                "run_dir": run_dir,
                "run_id": run_id,
                "mode": mode,
            }))
        
    # 2. Spawn voiceover generation worker (runs in parallel)
    sends.append(Send("voiceover_worker", {
        "voiceover_text": state["script"].get("voiceover_text", ""),
        "language": state.get("language", "hi"),
        "run_dir": run_dir,
        "run_id": run_id,
    }))
    
    log.info(f"Fanned out: Spawned {len(sends) - 1 if mode != 'documentary' else 0} image workers and 1 voiceover worker.")
    return sends


def image_worker_node(worker_state: dict) -> dict:
    """
    Single image generation worker. Called once per image prompt in parallel.
    """
    image_prompt = worker_state.get("image_prompt", "")
    scene_index = worker_state.get("scene_index", 0)
    run_dir = worker_state.get("run_dir", "")
    run_id = worker_state.get("run_id", "")
    mode = worker_state.get("mode", "shorts")
    
    from graph.nodes.research_node import emit_progress
    
    if mode == "documentary":
        log.info(f"Bypassing image worker {scene_index} in documentary mode.")
        return {"image_paths": []}
        
    if not image_prompt:
        return {"image_paths": []}

    target_path = Path(run_dir) / f"image_{scene_index:02d}.png"
    
    from modules.image_gen import _get_backend
    
    emit_progress(4, f"🎨 Generating image {scene_index + 1} ...", "INFO", run_id)

    max_attempts = 3  # 1 initial try + 2 retries
    for attempt in range(1, max_attempts + 1):
        try:
            log.info(f"Generating image {scene_index} (attempt {attempt}/{max_attempts}) ...")
            backend = _get_backend()
            width = config.get("image.width", 1080)
            height = config.get("image.height", 1920)
            aspect_ratio = config.get("aspect_ratio", "9:16")
            
            # Validate backend config
            valid, error = backend.validate_config(config.data)
            if not valid:
                raise ValueError(f"Image backend config validation error: {error}")
                
            # Run image generation (run async in synchronous runner context)
            asyncio.run(backend.generate(image_prompt, str(target_path), width, height, aspect_ratio=aspect_ratio))
            
            log.info(f"Successfully generated image {scene_index} saved to {target_path}")
            emit_progress(4, f"✅ Generated image {scene_index + 1} successfully.", "INFO", run_id)
            return {"image_paths": [str(target_path)]}
            
        except Exception as exc:
            log.warning(f"Attempt {attempt} failed to generate image {scene_index}: {exc}")
            emit_progress(4, f"⚠️ Attempt {attempt} failed to generate image {scene_index + 1}: {exc}", "WARNING", run_id)
            if attempt < max_attempts:
                log.info("Sleeping for 3 seconds before retry...")
                time.sleep(3)
            else:
                log.error(f"Image worker {scene_index} failed all attempts.")
                emit_progress(4, f"❌ Image {scene_index + 1} failed all attempts: {exc}", "ERROR", run_id)
                return {
                    "image_paths": [], 
                    "errors": [f"Image {scene_index} failed: {exc}"]
                }
                
    return {"image_paths": []}
