"""
graph/nodes/script_node.py — Script Writer Node
==============================================
Generates standard or documentary scripts, or polishes user-provided custom scripts.
"""

import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from core.config_manager import config, uses_video_footage
from graph.state import GhostCreatorState
from modules.scripter import generate_script, generate_documentary_script, VOICEOVER_LANG_META

log = logging.getLogger("script_node")

# Define Pydantic Models for Structured Output
class ImagePromptItem(BaseModel):
    prompt: str = Field(description="Cinematic English image prompt for Stable Diffusion / Imagen")
    scene_index: int = Field(description="Scene number starting from 0")

class VideoMetadata(BaseModel):
    title: str = Field(description="YouTube video title, max 100 chars, click-bait but accurate")
    description: str = Field(description="YouTube description, 150-300 words, SEO rich")
    tags: list[str] = Field(description="10-15 YouTube tags")

class GeneratedScript(BaseModel):
    voiceover_text: str = Field(description="Full TTS-ready narration, no markdown, plain spoken sentences")
    image_prompts: list[ImagePromptItem] = Field(description="5-6 cinematic scene prompts in English")
    metadata: VideoMetadata

def get_language_instruction(lang: str) -> str:
    lang = lang.lower().strip()
    if lang in VOICEOVER_LANG_META:
        return VOICEOVER_LANG_META[lang][1]
    return "Use the correct native writing system for this language."


def _shape_documentary_script(raw_doc_script: dict, topic: str) -> dict:
    """Normalize documentary script output for graph state."""
    return {
        "voiceover_text": raw_doc_script["voiceover_text"],
        "image_prompts": [
            {"prompt": s["video_query"], "scene_index": i}
            for i, s in enumerate(raw_doc_script["segments"])
        ],
        "segments": raw_doc_script["segments"],
        "metadata": raw_doc_script["metadata"],
        "title": raw_doc_script.get("title", topic),
        "_source": "ai_generated",
    }


def _voiceover_to_segments(voiceover_text: str, image_prompts: list) -> list[dict]:
    """Split voiceover into segments aligned with scene prompts for video fetch."""
    prompts: list[str] = []
    for item in image_prompts:
        if isinstance(item, str):
            prompts.append(item)
        else:
            prompts.append(str(item.get("prompt", "")))

    n = max(1, len(prompts))
    words = voiceover_text.split()
    if not words:
        chunks = [""] * n
    else:
        chunk_size = max(1, len(words) // n)
        chunks = []
        for i in range(n):
            start = i * chunk_size
            end = len(words) if i == n - 1 else (i + 1) * chunk_size
            chunks.append(" ".join(words[start:end]))

    return [
        {
            "voiceover": chunks[i],
            "video_query": prompts[i] if i < len(prompts) else (chunks[i][:50] or "documentary b-roll"),
        }
        for i in range(n)
    ]

def script_node(state: GhostCreatorState) -> dict:
    """LangGraph node to write/polish the video script."""
    mode = state.get("mode", "shorts")
    language = state.get("language", "hinglish")
    topic = state.get("topic", "")
    run_id = state.get("run_id", "")
    
    from graph.nodes.research_node import emit_progress

    try:
        script_dict = {}

        # ── BRANCH A: custom_script ──────────────────────────────────
        if mode == "custom_script":
            raw_script = state.get("user_custom_script", "").strip()
            # If too short, fall back to AI generation mode
            if not raw_script or len(raw_script) < 50:
                log.warning("User-provided custom script is too short (< 50 chars). Falling back to AI writing.")
                mode = "shorts"  # Flip mode to shorts for fallback
            else:
                emit_progress(2, "✍️ Polishing custom script ...", "INFO", run_id)
                gemini_key = config.get("api_keys.gemini", "")
                if not gemini_key:
                    raise ValueError("Missing Gemini API Key in configuration.")

                model_name = config.get("gemini_model") or config.get("pipeline.gemini_model") or "gemini-3.1-flash-lite"
                llm = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=gemini_key,
                    temperature=0.4
                )

                lang_inst = get_language_instruction(language)
                polish_prompt = f"""You are a professional YouTube script editor.
The user has written their own script. Polish it:
- Fix grammar, flow, and pacing for spoken narration.
- Ensure the first sentence is a strong hook (question or shocking fact).
- Add natural spoken transitions.
- Language/Writing Style: {lang_inst}
- Do NOT change the core message, facts, or story — only improve delivery.
- Keep it TTS-friendly: no symbols, emojis, bullets, markdown.
- Generate 5-6 cinematic image prompts in English that match the script's scenes.
- Generate an optimized YouTube title, description, and tags.

User's original script:
---
{raw_script}
---
"""
                log.info("Polishing custom script via Gemini structured output...")
                structured_llm = llm.with_structured_output(GeneratedScript)
                result: GeneratedScript = structured_llm.invoke(polish_prompt)

                # Format results to standard dictionary shape
                script_dict = {
                    "voiceover_text": result.voiceover_text,
                    "image_prompts": [{"prompt": item.prompt, "scene_index": item.scene_index} for item in result.image_prompts],
                    "metadata": {
                        "title": result.metadata.title,
                        "description": result.metadata.description,
                        "tags": result.metadata.tags
                    },
                    "_source": "user_custom_polished"
                }
                if uses_video_footage():
                    script_dict["segments"] = _voiceover_to_segments(
                        result.voiceover_text,
                        script_dict["image_prompts"],
                    )

        # ── BRANCH B: shorts / documentary (Full AI generation) ─────────
        if mode in ("shorts", "documentary"):
            target_duration = int(config.get("target_duration", 60))
            aspect_ratio = config.get("aspect_ratio", "9:16")
            image_count = int(config.get("image.image_count", 6))

            script_cfg = {
                "script_provider": config.get("script_provider", "gemini"),
                "gemini_model": config.get("gemini_model") or config.get("pipeline.gemini_model") or "gemini-3.1-flash-lite",
                "openai_model": config.get("openai_model", "gpt-4o"),
                "openai_api_key": config.get("openai_api_key", ""),
                "groq_api_key": config.get("groq_api_key", ""),
                "groq_model": config.get("groq_model", "llama-3.3-70b-versatile"),
                "api_keys.gemini": config.get("api_keys.gemini", ""),
                "ollama_url": config.get("ollama_url", "http://localhost:11434"),
                "ollama_model": config.get("ollama_model", "llama3"),
                "tts_backend": config.get("tts.backend", "omnivoice"),
                "voiceover_tone": config.get("documentary.voiceover_tone", ""),
                "video_style": config.get("documentary.video_style", ""),
            }

            if mode == "documentary" or (mode == "shorts" and uses_video_footage()):
                n_segs_override = int(config.get("documentary.segments", 0) or 0)
                label = "shorts" if mode == "shorts" else "documentary"
                log.info(f"Generating {label} script (video footage) for topic: {topic!r}...")
                emit_progress(2, f"✍️ Generating {label} script for topic: {topic}...", "INFO", run_id)
                raw_doc_script = generate_documentary_script(
                    topic,
                    lang=language,
                    target_duration=target_duration,
                    script_config=script_cfg,
                    n_segments=n_segs_override
                )
                script_dict = _shape_documentary_script(raw_doc_script, topic)
            else:
                log.info(f"Generating shorts script for topic: {topic!r}...")
                emit_progress(2, f"✍️ Generating shorts script for topic: {topic}...", "INFO", run_id)
                raw_short_script = generate_script(
                    topic,
                    lang=language,
                    target_duration=target_duration,
                    aspect_ratio=aspect_ratio,
                    image_count=image_count,
                    script_config=script_cfg
                )
                
                script_dict = {
                    "voiceover_text": raw_short_script["voiceover_text"],
                    "image_prompts": [
                        {"prompt": p, "scene_index": i} if isinstance(p, str) else p
                        for i, p in enumerate(raw_short_script["image_prompts"])
                    ],
                    "metadata": raw_short_script["metadata"],
                    "_source": "ai_generated"
                }

        emit_progress(2, "✅ Script writing completed.", "SUCCESS", run_id)
        return {
            "script": script_dict,
            "script_version": state.get("script_version", 0) + 1,
            "script_attempts": state.get("script_attempts", 0) + 1,
            "last_failed_node": ""
        }

    except Exception as exc:
        log.error(f"Script Node failed: {exc}", exc_info=True)
        emit_progress(2, f"❌ Script writing failed: {exc}", "ERROR", run_id)
        return {
            "errors": [f"Script Node error: {exc}"],
            "script": {},
            "last_failed_node": "script"
        }
