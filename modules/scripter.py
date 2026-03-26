"""
modules/scripter.py — AI Script Generator (Gemini / OpenAI / Ollama)
=====================================================================
Sends a structured prompt to the configured AI provider and parses its
JSON response into:
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
import shutil

import requests

from google import genai
from google.genai import types

from config import get_logger, GEMINI_MODEL, VOICEOVER_LANG
from core.config_manager import config

log = get_logger("scripter")

# ISO 639-1 code → (Gemini display name, script instruction for voiceover/title)
VOICEOVER_LANG_META: dict[str, tuple[str, str]] = {
    "hi": (
        "Hinglish",
        (
            "Write in Hinglish — Hindi spoken naturally but typed entirely in Roman/Latin script. "
            "Example: 'Kya aap jaante hain ke yeh ek kamaal ki cheez hai?' "
            "NEVER use Devanagari or any other non-Latin script. "
            "All words must be readable by someone who knows only the English alphabet."
        ),
    ),
    "hinglish": (
        "Hinglish",
        (
            "Write in Hinglish — Hindi spoken naturally but typed entirely in Roman/Latin script. "
            "Example: 'Kya aap jaante hain ke yeh ek kamaal ki cheez hai?' "
            "NEVER use Devanagari or any other non-Latin script. "
            "All words must be readable by someone who knows only the English alphabet."
        ),
    ),
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
        else "Create a detailed, engaging in-depth explainer — do NOT cut short."
    )
    # Compute human-readable time label (e.g. "10 minutes")
    _min = target_duration // 60
    _sec = target_duration % 60
    duration_label = f"{_min} minute{'s' if _min != 1 else ''}" + (f" {_sec}s" if _sec else "")

    return f"""You are a professional YouTube scriptwriter.

════════════════════════════════════════════════════════
TOPIC (MANDATORY — DO NOT DEVIATE):  "{topic}"
════════════════════════════════════════════════════════
CRITICAL RULE: Every single sentence in voiceover_text, every image prompt, the title, description,
and all tags MUST directly and specifically be about this exact topic: "{topic}".
Do NOT talk about generic AI, technology, or unrelated subjects.
Stay 100% on topic throughout the entire script.
════════════════════════════════════════════════════════

IMPORTANT LANGUAGE RULES:
- "voiceover_text" MUST be written in {lang_display}. {script_rule}
- "english_subtitle_text" MUST be in plain English, no emojis, no special characters.
- "image_prompts" MUST always be in English (for Stable Diffusion quality).
- "title" MUST be in {lang_display}.
- "description" and "tags" MUST be in English (for YouTube SEO).

Output ONLY a valid JSON object. No markdown fences, no extra text.

════════════════════════════════════════════════════════
⚠️  WORD COUNT IS MANDATORY — THIS IS THE MOST IMPORTANT RULE ⚠️
════════════════════════════════════════════════════════
- Target video duration  : {target_duration} seconds  ({duration_label})
- REQUIRED word count    : EXACTLY {target_words} words in voiceover_text
- Speaking rate          : ~130 words per minute in natural {lang_display} speech
- DO NOT stop early. Write ALL {target_words} words.
- A short script will make the video too short. The viewer paid for {duration_label}.
- If you reach a natural ending before {target_words} words, ADD more depth:
    examples, stories, statistics, tips, history, comparisons, viewer advice.
- Count your words. Aim for {target_words} ± 50 words. Nothing less.
════════════════════════════════════════════════════════

Video requirements:
- Target duration: {target_duration} seconds  ({duration_label})
- Video type: {video_type}
- Voiceover word count: {target_words} words  (MANDATORY — see above)
- Generate exactly {num_scenes} scenes/image prompts
- {duration_guidance}

JSON schema:
{{
  "voiceover_text": "<{lang_display} narration — MUST be {target_words} words, natural speech rhythm with pauses (use commas and full stops), about '{topic}'>",
  "english_subtitle_text": "<exact English translation of voiceover_text — plain text only, no emojis, no symbols>",
  "image_prompts": [
    "<English Stable Diffusion prompt about '{topic}', scene 1 — cinematic, photorealistic, 8K>",
    "<scene 2 — still about '{topic}'>",
    "<scene 3>",
    "<scene 4>",
    "<scene 5>",
    "<scene {num_scenes}>"
  ],
  "metadata": {{
    "title": "<viral {lang_display} title about '{topic}', max 70 chars>",
    "description": "<compelling English description specifically about '{topic}', ~200 words, with SEO keywords>",
    "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10"]
  }}
}}

Rules for voiceover_text:
- MUST be specifically about: "{topic}" — do not drift to other subjects
- MUST contain {target_words} words (±50) — this is non-negotiable
- First sentence: shocking hook question/statement DIRECTLY related to the topic
- Natural conversational speech — use commas and full stops for pacing and breathing
- Short punchy sentences with natural pauses
- Build to a mind-blowing fact or tip about the topic
- End: short YouTube-style CTA in {lang_display} (subscribe / bell / follow)
- Target: approximately {target_words} words
- Write as if a real {lang_display}-speaking creator is talking — natural rhythm, not robotic

Rules for english_subtitle_text:
- Direct English translation of voiceover_text
- Plain ASCII text only — no emojis, no Indic/other scripts, no special characters
- Same energy and structure as the voiceover

Rules for image_prompts:
- One cinematic scene per prompt, English only, DIRECTLY visualizing the topic "{topic}"
- Always include: "ultra-realistic, 8K, cinematic lighting, DreamshaperXL style"
- Each image prompt should be optimized for {composition_hint} composition
- No text, UI, or watermarks in prompts

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


def _validate_script(script: dict, num_scenes: int) -> dict:
    """Validate required keys and fill in defaults."""
    required = {"voiceover_text", "image_prompts", "metadata"}
    missing = required - script.keys()
    if missing:
        raise KeyError(f"Missing keys in script JSON: {missing}")
    if len(script["image_prompts"]) < num_scenes:
        raise ValueError(
            f"Expected at least {num_scenes} image_prompts, got {len(script['image_prompts'])}."
        )
    if "english_subtitle_text" not in script:
        log.warning("english_subtitle_text missing — falling back to voiceover_text")
        script["english_subtitle_text"] = script["voiceover_text"]
    script["num_scenes"] = num_scenes
    return script


# Ordered fallback chain — tried in sequence when a model returns 404
_GEMINI_FALLBACK_CHAIN = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]
_GEMINI_FINAL_FALLBACK = "gemini-2.0-flash"   # always-available stable model

# All non-1.x Gemini models require v1alpha for generateContent
_V1BETA_PREFIXES = ("gemini-1.",)   # only 1.x models use v1beta


def _gemini_client(api_key: str, model: str) -> "genai.Client":
    """
    Return a Gemini client.
    • gemini-1.x  → v1beta (stable, default)
    • everything else (2.x, 2.5, 3.x, …) → v1alpha (required for newer models)
    """
    use_beta = any(model.startswith(p) for p in _V1BETA_PREFIXES)
    if use_beta:
        return genai.Client(api_key=api_key)
    return genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1alpha"},
    )


def _generate_with_gemini(prompt: str, num_scenes: int, script_config: dict) -> dict:
    """Generate script using Gemini API, with automatic 404 fallback."""
    api_key = script_config.get("api_keys.gemini") or config.get("api_keys.gemini", "")
    if isinstance(api_key, str):
        api_key = api_key.strip()
    if not api_key:
        raise ValueError("No Gemini API key was provided. Please add it in Settings.")

    gemini_model = script_config.get("gemini_model") or config.get("gemini_model", GEMINI_MODEL)

    for attempt in range(1, 4):
        log.debug(f"Gemini API call (attempt {attempt}, model={gemini_model!r}) …")
        max_out     = 24576
        temperature = 0.7 if attempt == 1 else 0.4
        try:
            client = _gemini_client(api_key, gemini_model)
            response = client.models.generate_content(
                model=gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_out,
                ),
            )
            raw_text = response.text
            log.debug(f"Raw Gemini response (first 200 chars): {raw_text[:200]}")
            script = _extract_json(raw_text)
            return _validate_script(script, num_scenes)

        except (json.JSONDecodeError, KeyError, ValueError) as parse_exc:
            # JSON parse / validation failure — retry with lower temperature
            log.warning(f"Attempt {attempt} failed to parse Gemini script: {parse_exc}")
            if attempt == 3:
                raise RuntimeError(
                    f"Gemini returned unparseable JSON after 3 attempts: {parse_exc}"
                ) from parse_exc

        except Exception as api_exc:
            err_str = str(api_exc)
            # 404 NOT_FOUND = model name wrong or needs a different API version
            if "404" in err_str or "NOT_FOUND" in err_str:
                # Walk the fallback chain to find the next available model
                next_model = None
                try:
                    idx = _GEMINI_FALLBACK_CHAIN.index(gemini_model)
                    if idx + 1 < len(_GEMINI_FALLBACK_CHAIN):
                        next_model = _GEMINI_FALLBACK_CHAIN[idx + 1]
                except ValueError:
                    # Current model not in chain → jump straight to final fallback
                    if gemini_model != _GEMINI_FINAL_FALLBACK:
                        next_model = _GEMINI_FINAL_FALLBACK

                if next_model:
                    log.warning(
                        f"Model {gemini_model!r} not available (404). "
                        f"Auto-switching to: {next_model!r}."
                    )
                    gemini_model = next_model
                    continue   # retry immediately with next model
                raise RuntimeError(
                    f"All Gemini fallback models returned 404. "
                    f"Last tried: {gemini_model!r}. Check your API key."
                ) from api_exc
            # Other API errors (rate limit, auth, network) — fail immediately
            raise RuntimeError(f"Gemini API error: {api_exc}") from api_exc

    raise RuntimeError("_generate_with_gemini: unexpected exit")


# ── Ollama helpers ────────────────────────────────────────────────────────────

def check_ollama_status() -> tuple[bool, bool, list[str]]:
    """
    Probe Ollama and return (is_installed, is_running, available_models).

    * is_installed → True when the `ollama` binary is on PATH
    * is_running   → True when the local HTTP server responds at configured URL
    * available_models → list of model name strings pulled in Ollama
    """
    ollama_url = config.get("ollama_url", "http://localhost:11434")
    is_installed = shutil.which("ollama") is not None
    is_running = False
    models: list[str] = []
    try:
        r = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=3)
        if r.status_code == 200:
            is_running = True
            models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return is_installed, is_running, models


def _generate_with_ollama(prompt: str, num_scenes: int, script_config: dict) -> dict:
    """Generate script using a locally running Ollama LLM."""
    url = (script_config.get("ollama_url") or config.get("ollama_url", "http://localhost:11434")).rstrip("/")
    model = script_config.get("ollama_model") or config.get("ollama_model", "llama3")

    # Verify server is up before attempting
    try:
        requests.get(f"{url}/api/tags", timeout=5)
    except Exception:
        raise RuntimeError(
            f"Ollama server is not reachable at {url}. "
            "Make sure Ollama is installed and running (`ollama serve`)."
        )

    # Note: most Ollama models are English-only. We still pass the language
    # instruction but warn the user via the GUI. Multilingual models like
    # qwen2.5 or aya-expanse will honour the language; English-only models
    # (llama3, mistral, phi3 …) will output English regardless.
    system_msg = (
        "You are a YouTube script writer. IMPORTANT: Always respond with valid JSON only. "
        "No markdown fences, no code blocks, no extra explanation. "
        "Output ONLY the raw JSON object — nothing before or after it. "
        "You MUST follow the language instructions in the user message exactly. "
        "If the user asks for Hindi/Devanagari, write voiceover_text in Hindi script. "
        "If the user asks for English, write in English. Respect the language always."
    )

    api_url = f"{url}/v1/chat/completions"

    for attempt in range(1, 3):
        log.debug(f"Ollama API call (attempt {attempt}, model={model!r}) …")
        try:
            resp = requests.post(
                api_url,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user",   "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 24576,
                    "stream": False,
                },
                timeout=600,
            )
            resp.raise_for_status()
            raw_text = resp.json()["choices"][0]["message"]["content"]
            log.debug(f"Raw Ollama response (first 200 chars): {raw_text[:200]}")
            script = _extract_json(raw_text)
            return _validate_script(script, num_scenes)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            log.warning(f"Attempt {attempt} failed to parse Ollama script: {exc}")
            if attempt == 2:
                raise RuntimeError(
                    f"Ollama returned unparseable JSON after 2 attempts: {exc}"
                ) from exc

    raise RuntimeError("_generate_with_ollama: unexpected exit")


def _generate_with_openai(prompt: str, num_scenes: int, script_config: dict) -> dict:
    """Generate script using OpenAI API."""
    from openai import OpenAI

    api_key = script_config.get("openai_api_key") or config.get("openai_api_key", "")
    if isinstance(api_key, str):
        api_key = api_key.strip()
    if not api_key:
        raise ValueError("OpenAI API key is not set. Please add it in Settings.")

    model = script_config.get("openai_model") or config.get("openai_model", "gpt-4o")

    system = (
        "You are a YouTube script writer. Always respond with valid JSON only. "
        "No markdown, no explanation. Just the JSON object."
    )

    client = OpenAI(api_key=api_key)
    log.debug(f"OpenAI API call (model={model!r}) …")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
        max_tokens=24576,
    )
    raw_text = response.choices[0].message.content
    log.debug(f"Raw OpenAI response (first 200 chars): {raw_text[:200]}")
    script = json.loads(raw_text)
    return _validate_script(script, num_scenes)


def generate_script(
    topic: str,
    lang: str | None = None,
    target_duration: int = 60,
    aspect_ratio: str = "9:16",
    image_count: int | None = None,
    script_config: dict | None = None,
) -> dict:
    """
    Generate script using configured AI provider (Gemini or OpenAI).

    Parameters:
        topic: video topic
        lang: voiceover language (defaults to VOICEOVER_LANG from config)
        target_duration: target video length in seconds
        aspect_ratio: "9:16" or "16:9"
        image_count: overrides config image.image_count when set
        script_config: flat config dict slice (from pipeline_runner); falls back to config manager
    """
    cfg = script_config or {}
    language = (lang or VOICEOVER_LANG).lower()
    ic = image_count if image_count is not None else int(config.get("image.image_count", 6))
    num_scenes = max(4, min(ic, 40))
    target_words = int((target_duration / 60) * 130)
    video_type = "YouTube Short" if target_duration <= 90 else "YouTube video"
    composition_hint = "vertical portrait" if aspect_ratio == "9:16" else "wide cinematic landscape"

    provider = cfg.get("script_provider") or config.get("script_provider", "gemini")
    log.info(f"Generating script: topic={topic!r}  lang={language!r}  provider={provider!r}")

    prompt = _build_prompt(
        topic,
        language,
        target_duration=target_duration,
        num_scenes=num_scenes,
        target_words=target_words,
        video_type=video_type,
        composition_hint=composition_hint,
    )

    if provider == "openai":
        script = _generate_with_openai(prompt, num_scenes, cfg)
    elif provider == "ollama":
        if language != "en":
            log.warning(
                f"Ollama provider selected with language='{language}'. "
                "Most Ollama models are English-only and may ignore the language instruction. "
                "Use qwen2.5 or aya-expanse for multilingual output, or switch to Gemini/OpenAI."
            )
        script = _generate_with_ollama(prompt, num_scenes, cfg)
    else:
        script = _generate_with_gemini(prompt, num_scenes, cfg)

    log.info(f"Script generated → title: {script['metadata']['title']!r}")
    return script


if __name__ == "__main__":
    # Quick smoke-test
    import pprint
    topic = "OpenAI releases GPT-5 with real-time reasoning"
    pprint.pprint(generate_script(topic))
