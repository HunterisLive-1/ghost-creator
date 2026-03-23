"""
modules/scripter.py — Gemini AI Script Generator
=================================================
Sends a structured prompt to Gemini and parses its JSON response into:
  {
    "voiceover_text": str,
    "image_prompts": [str x5-6],
    "metadata": {
      "title": str,
      "description": str,
      "tags": [str]
    }
  }
"""

import json
import re

from google import genai
from google.genai import types

from config import get_logger, GEMINI_MODEL, VOICEOVER_LANG
from core.config_manager import config

log = get_logger("scripter")

# ISO 639-1 code → (Gemini display name, script instruction for voiceover/title)
VOICEOVER_LANG_META: dict[str, tuple[str, str]] = {
    "hi": ("Hindi", "Use Devanagari script for Hindi."),
    "en": ("English", "Use Latin script (English) only."),
    "mr": ("Marathi", "Use Devanagari script for Marathi."),
    "bn": ("Bengali", "Use Bengali script."),
    "gu": ("Gujarati", "Use Gujarati script."),
    "ta": ("Tamil", "Use Tamil script."),
}


def _lang_display_and_script(lang: str) -> tuple[str, str]:
    code = (lang or "hi").lower().strip()
    if code in VOICEOVER_LANG_META:
        return VOICEOVER_LANG_META[code]
    return (code.upper(), "Use the correct native writing system for this language.")


# ── Prompt Template ───────────────────────────────────────────────────────────
def _build_prompt(
    topic: str,
    lang: str,
    *,
    target_duration: int,
    num_scenes: int,
    target_words: int,
    video_type: str,
    composition_hint: str,
) -> str:
    """
    Build the full Gemini prompt for the given topic and voiceover language.
    voiceover_text  → in `lang`  (Hindi, English, Hinglish, etc.)
    image_prompts   → ALWAYS in English (for best Stable Diffusion results)
    metadata.title  → in `lang`
    metadata.description / tags → in English (for YouTube SEO)
    """
    lang_display, script_rule = _lang_display_and_script(lang)
    duration_guidance = (
        "Keep it short, concise, and high-energy."
        if target_duration <= 90
        else "Create an engaging in-depth explainer."
    )
    return f"""You are a viral YouTube Shorts scriptwriter for AI and Technology content.

IMPORTANT LANGUAGE RULES:
- "voiceover_text" MUST be written in {lang_display}. {script_rule}
- "english_subtitle_text" MUST be in plain English, no emojis, no special characters.
- "image_prompts" MUST always be in English (for Stable Diffusion quality).
- "title" MUST be in {lang_display}.
- "description" and "tags" MUST be in English (for YouTube SEO).

Output ONLY a valid JSON object. No markdown fences, no extra text.

Video requirements:
- Target duration: {target_duration} seconds
- Video type: {video_type}
- Voiceover length: approximately {target_words} words
- Generate exactly {num_scenes} scenes/image prompts
- {duration_guidance}

JSON schema:
{{
  "voiceover_text": "<{lang_display} narration — match the target duration and target word count>",
  "english_subtitle_text": "<exact English translation of voiceover_text — plain text only, no emojis, no symbols>",
  "image_prompts": [
    "<English Stable Diffusion prompt, scene 1 — cinematic, photorealistic, 8K>",
    "<scene 2>",
    "<scene 3>",
    "<scene 4>",
    "<scene 5>",
    "<scene {num_scenes}>"
  ],
  "metadata": {{
    "title": "<viral {lang_display} {video_type} title, max 70 chars>",
    "description": "<compelling English description with SEO keywords, ~200 words>",
    "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10"]
  }}
}}

Rules for voiceover_text:
- First sentence: shocking hook question/statement
- Short punchy sentences throughout
- Build to a mind-blowing fact or tip
- End: short YouTube-style CTA in {lang_display} (subscribe / bell / follow) — match how local Shorts creators close
- Target: approximately {target_words} words

Rules for english_subtitle_text:
- Direct English translation of voiceover_text
- Plain ASCII text only — no emojis, no Indic/other scripts, no special characters
- Same energy and structure as the voiceover

Rules for image_prompts:
- One cinematic scene per prompt, English only
- Always include: "ultra-realistic, 8K, cinematic lighting, DreamshaperXL style"
- Each image prompt should be optimized for {composition_hint} composition
- No text, UI, or watermarks in prompts

Topic: "{topic}"

Generate the JSON now:"""



def _extract_json(raw: str) -> dict:
    """
    Extract the first valid JSON object from `raw`, regardless of surrounding
    prose or markdown fences.  Uses json.JSONDecoder.raw_decode() which
    correctly handles all escape sequences.
    """
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().replace("```", "")

    # Scan forward to the first '{' then let the stdlib decoder handle the rest
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No JSON object found in Gemini response.")

    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(cleaned, start)
    return obj  # type: ignore[return-value]


def generate_script(
    topic: str,
    lang: str | None = None,
    target_duration: int = 60,
    aspect_ratio: str = "9:16",
    image_count: int | None = None,
) -> dict:
    """
    Call Gemini with the given topic and return the parsed script dict.
    lang: voiceover language (defaults to VOICEOVER_LANG from config).
    Image prompts are always generated in English.
    ``image_count`` overrides ``config image.image_count`` when set (clamped 4–40).
    """
    language = (lang or VOICEOVER_LANG).lower()
    ic = image_count if image_count is not None else int(config.get("image.image_count", 6))
    num_scenes = max(4, min(ic, 40))
    target_words = int((target_duration / 60) * 130)
    video_type = "YouTube Short" if target_duration <= 90 else "YouTube video"
    composition_hint = "vertical portrait" if aspect_ratio == "9:16" else "wide cinematic landscape"
    log.info(f"Generating script: topic={topic!r}  lang={language!r}")
    
    api_key = config.get("api_keys.gemini", "").strip()
    if not api_key:
        raise ValueError("No Gemini API key was provided. Please add it in Settings.")
        
    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(
        topic,
        language,
        target_duration=target_duration,
        num_scenes=num_scenes,
        target_words=target_words,
        video_type=video_type,
        composition_hint=composition_hint,
    )

    for attempt in range(1, 3):
        log.debug(f"Gemini API call (attempt {attempt}) …")
        try:
            max_out = 4096 if num_scenes > 12 else 2048
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    max_output_tokens=max_out,
                ),
            )
            raw_text = response.text
            log.debug(f"Raw Gemini response (first 200 chars): {raw_text[:200]}")

            script = _extract_json(raw_text)

            # ── Validate required keys ─────────────────────────────────────
            required = {"voiceover_text", "image_prompts", "metadata"}
            missing = required - script.keys()
            if missing:
                raise KeyError(f"Missing keys in script JSON: {missing}")

            if len(script["image_prompts"]) < num_scenes:
                raise ValueError(
                    f"Expected at least {num_scenes} image_prompts, got {len(script['image_prompts'])}."
                )

            # Fallback: if Gemini didn't return english_subtitle_text, use voiceover_text
            if "english_subtitle_text" not in script:
                log.warning("english_subtitle_text missing from Gemini response — falling back to voiceover_text")
                script["english_subtitle_text"] = script["voiceover_text"]

            script["num_scenes"] = num_scenes

            log.info(f"Script generated → title: {script['metadata']['title']!r}")
            return script

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            log.warning(f"Attempt {attempt} failed to parse script: {exc}")
            if attempt == 2:
                raise RuntimeError(
                    f"Gemini returned unparseable JSON after 2 attempts: {exc}"
                ) from exc

    # Should never reach here
    raise RuntimeError("generate_script: unexpected exit")


if __name__ == "__main__":
    # Quick smoke-test
    import pprint
    topic = "OpenAI releases GPT-5 with real-time reasoning"
    pprint.pprint(generate_script(topic))
