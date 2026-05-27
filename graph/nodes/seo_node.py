"""
graph/nodes/seo_node.py — SEO Optimization Agent Node
===================================================
Autonomous agent node that rewrites/optimizes video metadata using structured output.
"""

import logging
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from core.config_manager import config
from graph.state import GhostCreatorState

log = logging.getLogger("seo_node")

class SEOOutput(BaseModel):
    title: str = Field(description="YouTube title: max 60 chars, front-load keywords, power word first")
    description: str = Field(description="YouTube description: keyword-rich, 150-250 words, natural language")
    tags: list[str] = Field(description="Exactly 15 tags: mix of broad + niche + long-tail")
    hashtags: list[str] = Field(description="5 hashtags for the video description footer")
    chapters: list[str] = Field(description="YouTube chapter timestamps if script has natural sections, else empty list")

def seo_node(state: GhostCreatorState) -> dict:
    """Optimizes video title, description and tags for YouTube search."""
    script = state.get("script") or {}
    metadata = script.get("metadata") or {}
    run_id = state.get("run_id", "")

    from graph.nodes.research_node import emit_progress

    current_title = metadata.get("title", "")
    current_desc = metadata.get("description", "")
    current_tags = metadata.get("tags", [])

    emit_progress(5, "🔍 Optimizing metadata for SEO (title, description, tags)...", "INFO", run_id)

    # 1. Skip if SEO optimization is disabled in config
    if not config.get("pipeline.seo_enabled", True):
        log.info("SEO optimization is disabled in settings. Skipping SEO node.")
        emit_progress(5, "⏭️ SEO optimization disabled, using script metadata.", "INFO", run_id)
        return {
            "seo_title": current_title,
            "seo_description": current_desc,
            "seo_tags": current_tags,
            "seo_optimized": False,
            "last_failed_node": ""
        }

    try:
        gemini_key = config.get("api_keys.gemini", "")
        if not gemini_key:
            raise ValueError("Missing Gemini API key.")

        model_name = config.get("gemini_model") or config.get("pipeline.gemini_model") or "gemini-3.1-flash-lite"
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=gemini_key,
            temperature=0.3
        )

        topic = state.get("topic", "")
        voiceover_text = script.get("voiceover_text", "")
        voiceover_preview = voiceover_text[:400]
        language = state.get("language", "hi")

        seo_prompt = f"""You are a YouTube SEO specialist. Optimize this video's metadata to maximize impressions and click-through rate.

Topic: {topic}
Script (first 400 chars for context): {voiceover_preview}
Current title: {current_title}
Current tags: {current_tags}
Language of voiceover: {language}

SEO Rules:
- Title: Put the most searched keyword in the FIRST 3 words. Use numbers or "?" if natural.
  Examples of power openers: "यह क्या है?", "2025 में...", "जो कोई नहीं बताता..."
- Tags: Start with exact-match tags, then broader category tags, then question tags.
- Description: First 2 lines must be compelling (shown before "Show more").
  Include a soft CTA: "Subscribe karo aur bell icon dabao!"
- All metadata in language: {language}
- Hashtags go at the very END of the description.
"""

        log.info("Optimizing metadata via SEO agent...")
        structured_llm = llm.with_structured_output(SEOOutput)
        result: SEOOutput = structured_llm.invoke(seo_prompt)

        description_with_tags = result.description
        if result.hashtags:
            description_with_tags += "\n\n" + " ".join(result.hashtags)

        log.info(f"SEO Agent Output → Title: {result.title}")
        emit_progress(5, "✅ SEO metadata optimization completed.", "INFO", run_id)

        return {
            "seo_title": result.title,
            "seo_description": description_with_tags,
            "seo_tags": result.tags,
            "seo_optimized": True,
            "script": {**script, "metadata": {
                "title": result.title,
                "description": result.description,
                "tags": result.tags
            }},
            "last_failed_node": ""
        }

    except Exception as exc:
        log.warning(f"SEO Agent failed: {exc}. Using original script metadata.")
        emit_progress(5, f"⚠️ SEO Agent failed: {exc}. Using original script metadata.", "WARNING", run_id)
        return {
            "seo_title": current_title,
            "seo_description": current_desc,
            "seo_tags": current_tags,
            "seo_optimized": False,
            "last_failed_node": ""
        }
