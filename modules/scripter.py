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
import math
import re
import shutil

import requests

from google import genai
from google.genai import types

from config import get_logger, GEMINI_MODEL, VOICEOVER_LANG
from core.config_manager import config
from modules.tts_number_normalize import normalize_documentary_script_numbers

log = get_logger("scripter")

# Documentary: auto segment count = round(target_sec / DOC_AUTO_SEG_EVERY_S); clamped 3..DOC_SEG_MAX
DOC_AUTO_SEG_EVERY_S = 12.0
DOC_SEG_MAX = 100

# ISO 639-1 code → (Gemini display name, script instruction for voiceover/title)
VOICEOVER_LANG_META: dict[str, tuple[str, str]] = {
    "hi": (
        "Hindi",
        (
            "Write in pure Hindi using Devanagari script only. "
            "NEVER use Hinglish, Roman Hindi, or English spellings for Hindi words. "
            "Example: 'क्या आप जानते हैं कि यह एक कमाल की चीज़ है?'"
            "always use hindi slangs/words which are commonly used in daily conversations"
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
    "te": ("Telugu", "Use Telugu script."),
    "or": ("Odia", "Use Odia (Oriya) script for Odisha — standard Odia orthography."),
}


def _lang_display_and_script(lang: str) -> tuple[str, str]:
    code = (lang or "hi").lower().strip()
    if code in VOICEOVER_LANG_META:
        return VOICEOVER_LANG_META[code]
    return (code.upper(), "Use the correct native writing system for this language.")


def _voiceover_plain_format_rules() -> str:
    """
    Force Gemini (and any provider using this prompt) to output TTS-friendly voiceover:
    continuous prose, no [emotion] flags or markup — matches how creators actually speak in shorts.
    """
    return (
        '\nVOICEOVER — PLAIN SPOKEN FORMAT (MANDATORY for "voiceover_text" and each segment "voiceover"):\n'
        "- Write a continuous, natural monologue: short–medium sentences; end each thought with a full stop or question mark, "
        "then a single space before the next sentence (standard typing).\n"
        "- Style: like a YouTube/Instagram/shorts host explaining the topic in plain language — flow from hook to details to CTA, "
        "same spirit as: informal but clear sentences in a row, no list formatting in the speech.\n"
        "- Do NOT use emotion tags, square brackets, hashtags, emojis, asterisks, bullet symbols, or stage directions in the spoken text.\n"
        "- Do NOT prefix lines with [neutral], [excited], or any [label]. No SFX:/MUSIC: lines.\n"
        "- Avoid decorative typing: no repeated !!!, ellipsis spam ………, or ALL CAPS for fake emphasis; convey energy with words only.\n"
        "- NUMBERS / YEARS / DATES: NEVER use Arabic digits (0–9) in spoken voiceover. "
        "Always write every number, year, count, date, and statistic as **full words** in the same script as the voiceover "
        "(e.g. Hindi: समझिए उन्नीस सौ निन्यानवे में …; English: In nineteen ninety-nine …; "
        "Telugu/Tamil/Bengali/Odia: use native script words for those languages). "
        "TTS will misread digits; words must be spelled out.\n"
    )


def _hindi_cinematic_monologue_block(lang: str) -> str:
    """
    When pipeline language is Hindi: match introspective, staccato monologue style and honor
    user-supplied story appended after the main topic (after a separator in the topic string).
    """
    if (lang or "hi").lower().strip() != "hi":
        return ""
    return (
        "\nHINDI CINEMATIC MONOLOGUE STYLE (only when writing Hindi voiceover — apply on top of rules above):\n"
        "- Open with a **provocative hook**: e.g. what 'they' said vs what is really true; flip a common belief about the subject.\n"
        "- **Short, spoken lines**: often one clear idea per sentence; full stop; then the next. Inner voice / hypnotic monologue, not long essay paragraphs.\n"
        "- You may use **tight anaphora** in a run (e.g. several short sentences starting the same way) for emphasis, then pivot to a new beat.\n"
        "- **Closing image**: end with a concrete, visual moment (e.g. someone doing something) rather than only abstract morals.\n"
        "- **User story at end of topic**: If the TOPIC string contains extra material after a **separator** "
        "(blank line, `---`, or a line starting with `कहानी:`, `कहानी -`, or `Story:`), treat the text **before** the first separator as the main subject "
        "and the text **after** as the user's **mandatory** story/beat. Work that material into the **latter part** of the script in this same rhythm; do not drop or replace it with generic text.\n"
        "- If there is no such appended story, still use this **tone and line-break rhythm** (provocative, intimate, staccato Devanagari).\n"
        "- Do not use [संगीत] or any square-bracket music/SFX — TTS would read them aloud; use words for mood only.\n"
    )


def _youtube_metadata_rules(lang: str, lang_display: str) -> str:
    """
    YouTube title / description / tag instructions. Hindi voiceover uses Devanagari in
    voiceover_text, but upload titles work better as Hinglish (English + Roman Hindi) for
    SEO and readability — so we do not ask for the same script style as the title.
    """
    code = (lang or "en").lower().strip()
    if code == "hi":
        return (
            "YOUTUBE METADATA (title / description / tags — for upload ONLY; do NOT use this for voiceover):\n"
            '- "title" (and metadata "title") MUST be **Hinglish** — a natural mix of **English** (searchable words: topic, format: e.g. Shocking, Facts, Full Story, Explained) '
            "and **Roman Hindi** in **Latin script only** (aap, kya, nahi, sabse, sach, dekho). "
            "Sound like a real Indian YouTuber: **clickable, human, SEO-friendly**. "
            "You may use `|`, `·`, or `—` to pair an English half with a Hinglish hook. "
            "**Do not** use Devanagari in the title. **Do not** use full formal Hindi book-phrasing only; mix English for discoverability.\n"
            "- metadata **description** MUST be mostly **plain English** (2–4 short paragraphs, natural SEO keywords, line breaks, readable). "
            "Optional: **1–2 opening lines in Roman Hinglish** for vibe, then the rest English. No stiff machine-translation tone.\n"
            "- metadata **tags** MUST include strong **English** search terms; add 1–3 Roman/Hinglish-style tags that Indian users type (e.g. \"hindi story\", \"full explain\"), no duplicates.\n"
        )
    if code == "hinglish":
        return (
            "YOUTUBE METADATA (for upload ONLY):\n"
            '- "title" and metadata "title": **Hinglish** in **Latin script**; put the **strongest English SEO keywords in the first 50 characters**. '
            "Catchy, like mobile search — not random Roman strings. Max ~100 characters.\n"
            "- metadata **description** — **English** for SEO (2–4 paragraphs) + optional short Roman Hinglish intro; **tags** — English + Hinglish search phrases as needed.\n"
        )
    if code == "en":
        return (
            "YOUTUBE METADATA (for upload ONLY):\n"
            '- "title" and metadata "title": **English** — clear, **keyword-rich**, human, max ~100 characters (best ~50–70 for Shorts), no clickbait spam, no all-caps.\n'
            "- metadata **description** and **tags**: **English** for SEO, conversational, natural keywords, 2–4 short paragraphs in description.\n"
        )
    return (
        f"YOUTUBE METADATA (for upload ONLY):\n"
        f'- "title" and metadata "title" MUST be in {lang_display} but **readable**; add **English topic keywords** in the title when it helps YouTube search (mix is OK).\n'
        "- metadata **description** and **tags** MUST be in **English** (YouTube SEO).\n"
    )


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
    metadata.title  → Hinglish (hi/hinglish) or per _youtube_metadata_rules; description/tags per same
    """
    lang_display, script_rule = _lang_display_and_script(lang)
    voiceover_plain_rules = _voiceover_plain_format_rules()
    hindi_style = _hindi_cinematic_monologue_block(lang)
    youtube_meta_rules = _youtube_metadata_rules(lang, lang_display)
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
{youtube_meta_rules}
{voiceover_plain_rules}{hindi_style}

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
    "title": "<YouTube title per YOUTUBE METADATA rules above — for Hindi: Hinglish Latin script, English SEO + Roman Hindi, max ~100 chars, about '{topic}'>",
    "description": "<per YOUTUBE METADATA: mostly English SEO text about '{topic}', ~150-300 words, readable>",
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
- Follow VOICEOVER — PLAIN SPOKEN FORMAT above: no bracket tags, no emojis, no extra symbols in the spoken line

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
                    safety_settings=[
                        types.SafetySetting(
                            category="HARM_CATEGORY_HARASSMENT",
                            threshold="BLOCK_ONLY_HIGH",
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_HATE_SPEECH",
                            threshold="BLOCK_ONLY_HIGH",
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                            threshold="BLOCK_ONLY_HIGH",
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_DANGEROUS_CONTENT",
                            threshold="BLOCK_ONLY_HIGH",
                        ),
                    ],
                ),
            )
            raw_text = response.text
            if raw_text is None:
                # Safety filter blocked the response — collect reason if available
                block_reason = "unknown"
                try:
                    fb = response.prompt_feedback
                    if fb and hasattr(fb, "block_reason"):
                        block_reason = str(fb.block_reason)
                except Exception:
                    pass
                try:
                    if response.candidates:
                        finish = response.candidates[0].finish_reason
                        block_reason = f"{block_reason} / finish_reason={finish}"
                except Exception:
                    pass
                raise ValueError(
                    f"Gemini returned no text (likely blocked by safety filters). "
                    f"Reason: {block_reason}. Try rephrasing the topic to be less graphic."
                )
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


# ── Documentary Mode ──────────────────────────────────────────────────────────

# Max seconds per single Gemini call — stays within reliable output length
_DOC_CHUNK_MAX_S = 720   # 12 minutes per chunk


def _default_narration_style_block() -> str:
    """Injected when no Idea Workshop tone/style was agreed."""
    return (
        "\n════════════════════════════════════════════════════════\n"
        "DEFAULT NARRATION STYLE (apply when no creative brief given):\n"
        "- Open with a SHOCKING HOOK — a provocative question or little-known fact that\n"
        "  immediately challenges the viewer's assumption about this topic.\n"
        "- Tone: AUTHORITATIVE yet CONVERSATIONAL — like a National Geographic narrator\n"
        "  who speaks like a real person, not a textbook.\n"
        "- Vary sentence length: short punchy lines for impact, longer ones for depth.\n"
        "- Use SPECIFIC details: real names, dates, numbers, case studies — no vague generalities.\n"
        "- Build natural tension across segments: hook → context → revelation → implication → CTA.\n"
        "════════════════════════════════════════════════════════\n"
    )


def _build_documentary_prompt(
    topic: str,
    lang: str,
    target_duration: int,
    num_segments: int,
    *,
    tone_hint: str = "",
    style_hint: str = "",
    chapter_num: int = 0,
    total_chapters: int = 1,
    prev_ending: str = "",
) -> str:
    """
    Build the Gemini prompt for one documentary chunk.
    chapter_num / total_chapters: used when chunked (0 = single call = no chapter label).
    prev_ending: last ~200 chars of previous chunk's voiceover for continuity.
    """
    lang_display, script_rule = _lang_display_and_script(lang)
    voiceover_plain = _voiceover_plain_format_rules()
    hindi_style = _hindi_cinematic_monologue_block(lang)
    youtube_meta_rules = _youtube_metadata_rules(lang, lang_display)
    _min = target_duration // 60
    _sec = target_duration % 60
    duration_label = (f"{_min} min" if not _sec else f"{_min}m {_sec}s")
    target_words = int((target_duration / 60) * 130)
    per_seg_words = max(80, target_words // max(1, num_segments))

    # ── Creative brief block ──────────────────────────────────────────────────
    if tone_hint or style_hint:
        _brief = (
            "\n════════════════════════════════════════════════════════\n"
            "CREATIVE BRIEF (agreed with user):\n"
        )
        if style_hint:
            _brief += f"- Visual style  : {style_hint}\n"
        if tone_hint:
            _brief += (
                f"- Voiceover tone: {tone_hint}\n"
                "  Apply this tone consistently across EVERY segment.\n"
            )
        _brief += "════════════════════════════════════════════════════════\n"
    else:
        _brief = _default_narration_style_block()

    # ── Chapter context (chunked mode only) ───────────────────────────────────
    _chapter_block = ""
    if total_chapters > 1 and chapter_num > 0:
        _chapter_block = (
            f"\n════════════════════════════════════════════════════════\n"
            f"CHAPTER {chapter_num} of {total_chapters} of the full documentary.\n"
            f"- Do NOT add an intro or repeat what was covered in earlier chapters.\n"
            f"- Continue naturally from where the last chapter ended.\n"
        )
        if prev_ending:
            _chapter_block += f"- Previous chapter ended with: \"{prev_ending[-200:].strip()}\"\n"
        if chapter_num == total_chapters:
            _chapter_block += "- This is the FINAL chapter — conclude the documentary and add the CTA.\n"
        _chapter_block += "════════════════════════════════════════════════════════\n"

    return f"""You are a professional documentary scriptwriter.

════════════════════════════════════════════════════════
TOPIC (MANDATORY — DO NOT DEVIATE): "{topic}"
════════════════════════════════════════════════════════
Every sentence of narration, every video query, the title, and all metadata
MUST be directly and specifically about: "{topic}".
Do NOT drift to generic facts, unrelated topics, or padding.
════════════════════════════════════════════════════════
{_brief}{_chapter_block}
LANGUAGE RULES:
- "voiceover" fields MUST be in {lang_display}. {script_rule}
- "video_query" fields MUST be in English (for YouTube search).
{youtube_meta_rules}
{voiceover_plain}{hindi_style}
Output ONLY valid JSON. No markdown fences, no extra text.

════════════════════════════════════════════════════════
⚠️  WORD COUNT — THIS IS THE MOST CRITICAL RULE ⚠️
════════════════════════════════════════════════════════
- Chunk duration   : {target_duration} seconds ({duration_label})
- MINIMUM words    : {target_words} words across ALL voiceover fields combined
- Per-segment min  : ~{per_seg_words} words each (NEVER less than {per_seg_words // 2})
- Speaking rate    : 130 words / minute in {lang_display}
- DO NOT STOP EARLY. If you reach a natural end before {target_words} words:
    → Expand with: historical context, expert viewpoints, real case studies,
      statistics, societal impact, future outlook, comparisons, viewer anecdotes.
    → NEVER repeat sentences you already wrote; always add NEW content.
- Count your words before finishing. If total < {target_words - 100}, KEEP WRITING.
════════════════════════════════════════════════════════

VIDEO QUERY RULES:
- Each "video_query" = a specific YouTube search string for matching REAL footage.
- Be visual: "NASA rocket launch slow motion", "coral reef 4K underwater"
- NOT generic: "documentary", "facts", "history"
- 3–7 words, English only, no quotes inside.

JSON schema — produce EXACTLY:
{{
  "title": "<YouTube title — for Hindi: Hinglish Latin, English keywords, max 100 chars>",
  "voiceover_text": "<ALL segments' voiceover joined — MINIMUM {target_words} words in {lang_display}>",
  "segments": [
    {{
      "voiceover": "<{lang_display} narration — MINIMUM {per_seg_words} words, full sentences>",
      "video_query": "<English YouTube search query>",
      "duration_hint": <integer seconds>
    }}
  ],
  "metadata": {{
    "title": "<same as top-level title>",
    "description": "<English SEO, 2-4 paragraphs about '{topic}'>",
    "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10"]
  }}
}}

SEGMENT RULES:
- Produce exactly {num_segments} segments.
- Flow: hook → background → detail → depth → implication{' → CTA' if chapter_num == total_chapters or total_chapters == 1 else ''}.
- Every "voiceover" ≥ {per_seg_words} words. Every sentence counts toward the total.
- Sum of all duration_hint values MUST equal {target_duration}.
- Spoken prose only — no [tags], no emojis, no bullet symbols in voiceover.

Generate the JSON now:"""



def _validate_documentary_script(script: dict, num_segments: int) -> dict:
    """Validate and normalise a documentary script dict."""
    for key in ("title", "voiceover_text", "segments", "metadata"):
        if key not in script:
            raise KeyError(f"Missing key in documentary script: {key!r}")
    segs = script["segments"]
    if not isinstance(segs, list) or len(segs) < 1:
        raise ValueError("'segments' must be a non-empty list")
    for i, s in enumerate(segs):
        if "voiceover" not in s:
            raise KeyError(f"Segment {i} missing 'voiceover'")
        if "video_query" not in s:
            s["video_query"] = s.get("voiceover", "")[:50]
        if "duration_hint" not in s:
            s["duration_hint"] = 20
    # Stitch full voiceover_text if missing or empty
    if not script.get("voiceover_text", "").strip():
        script["voiceover_text"] = " ".join(s["voiceover"] for s in segs)
    return script


def _generate_documentary_chunked(
    topic: str,
    language: str,
    target_duration: int,
    total_segments: int,
    cfg: dict,
    provider: str,
    tone_hint: str,
    style_hint: str,
) -> dict:
    """
    For long videos (> _DOC_CHUNK_MAX_S), split into N chunks of ≤12 min each,
    call the AI for every chunk independently, then stitch the segments together.
    This guarantees word-count compliance for 40–120 min videos.
    """
    n_chunks = math.ceil(target_duration / _DOC_CHUNK_MAX_S)
    # Distribute duration evenly; last chunk gets the remainder
    base_dur = target_duration // n_chunks
    remainders = target_duration - base_dur * n_chunks
    chunk_durations = [base_dur + (1 if i < remainders else 0) for i in range(n_chunks)]

    # Segments per chunk (proportional)
    segs_per_chunk = max(3, total_segments // n_chunks)

    log.info(
        "Chunked documentary: %s chunks × ~%ss each, %s segs/chunk",
        n_chunks, base_dur, segs_per_chunk,
    )

    all_segments: list[dict] = []
    first_title: str = ""
    first_metadata: dict = {}
    prev_ending: str = ""

    for i, chunk_dur in enumerate(chunk_durations):
        chunk_num = i + 1
        # Last chunk: adjust segment count to account for rounding
        if chunk_num == n_chunks:
            remaining_segs = max(3, total_segments - len(all_segments))
            cur_segs = remaining_segs
        else:
            cur_segs = segs_per_chunk

        log.info("  Chunk %s/%s: %ss, %s segments …", chunk_num, n_chunks, chunk_dur, cur_segs)

        prompt = _build_documentary_prompt(
            topic, language, chunk_dur, cur_segs,
            tone_hint=tone_hint, style_hint=style_hint,
            chapter_num=chunk_num, total_chapters=n_chunks,
            prev_ending=prev_ending,
        )

        if provider == "openai":
            raw = _generate_raw_openai(prompt, cfg)
        elif provider == "ollama":
            raw = _generate_raw_ollama(prompt, cfg)
        else:
            raw = _generate_raw_gemini(prompt, cfg)

        chunk_script = _extract_json(raw)
        chunk_script = _validate_documentary_script(chunk_script, cur_segs)

        if not first_title:
            first_title    = chunk_script.get("title", topic)
            first_metadata = chunk_script.get("metadata", {})

        segs = chunk_script["segments"]
        all_segments.extend(segs)
        # Pass the tail of this chunk's narration to the next chunk for continuity
        if segs:
            prev_ending = segs[-1].get("voiceover", "")[-300:]

    log.info(
        "Chunked script stitched: %s total segments, ~%s words",
        len(all_segments), len(full_voiceover.split()),
    )
    out = {
        "title":          first_title,
        "voiceover_text": full_voiceover,
        "segments":       all_segments,
        "metadata":       first_metadata,
    }
    return normalize_documentary_script_numbers(out, language)


def generate_documentary_script(
    topic: str,
    lang: str | None = None,
    target_duration: int = 180,
    script_config: dict | None = None,
    n_segments: int = 0,
) -> dict:
    """
    Generate a documentary script (narration + footage queries per segment).
    Videos longer than _DOC_CHUNK_MAX_S (12 min) are generated in chunks to
    guarantee full word-count coverage for 40–120 min targets.
    """
    cfg = script_config or {}
    language = (lang or "hi").lower().strip()

    if n_segments and n_segments > 0:
        num_segments = max(3, min(DOC_SEG_MAX, n_segments))
    else:
        num_segments = max(
            3, min(DOC_SEG_MAX, round(target_duration / DOC_AUTO_SEG_EVERY_S))
        )

    provider   = cfg.get("script_provider") or config.get("script_provider", "gemini")
    tone_hint  = cfg.get("voiceover_tone", "") or config.get("documentary.voiceover_tone", "")
    style_hint = cfg.get("video_style",    "") or config.get("documentary.video_style",    "")

    log.info(
        "Documentary script: topic=%r  lang=%r  dur=%ss  segs=%s  provider=%r  tone=%r",
        topic, language, target_duration, num_segments, provider, tone_hint,
    )

    # ── Long videos: chunked generation ──────────────────────────────────────
    if target_duration > _DOC_CHUNK_MAX_S:
        return _generate_documentary_chunked(
            topic, language, target_duration, num_segments,
            cfg, provider, tone_hint, style_hint,
        )

    # ── Short/medium videos: single call ─────────────────────────────────────
    prompt = _build_documentary_prompt(
        topic, language, target_duration, num_segments,
        tone_hint=tone_hint, style_hint=style_hint,
    )

    if provider == "openai":
        raw = _generate_raw_openai(prompt, cfg)
    elif provider == "ollama":
        raw = _generate_raw_ollama(prompt, cfg)
    else:
        raw = _generate_raw_gemini(prompt, cfg)

    script = _extract_json(raw)
    script = _validate_documentary_script(script, num_segments)
    script = normalize_documentary_script_numbers(script, language)
    log.info("Script ready: %s segments, title=%r", len(script["segments"]), script["title"])
    return script



def _generate_raw_gemini(prompt: str, script_config: dict) -> str:
    """Call Gemini and return raw response text (no parsing)."""
    api_key = (script_config.get("api_keys.gemini") or config.get("api_keys.gemini", "")).strip()
    if not api_key:
        raise ValueError("No Gemini API key was provided. Please add it in Settings.")
    gemini_model = script_config.get("gemini_model") or config.get("gemini_model", GEMINI_MODEL)

    for attempt in range(1, 4):
        log.debug("Gemini API call (attempt %s, model=%r) …", attempt, gemini_model)
        try:
            client = _gemini_client(api_key, gemini_model)
            response = client.models.generate_content(
                model=gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7 if attempt == 1 else 0.4,
                    max_output_tokens=24576,
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH"),
                        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_ONLY_HIGH"),
                        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
                    ],
                ),
            )
            raw = response.text
            if raw is None:
                raise ValueError("Gemini returned no text (safety filter).")
            return raw
        except (json.JSONDecodeError, KeyError, ValueError):
            if attempt == 3:
                raise
        except Exception as api_exc:
            err = str(api_exc)
            if "404" in err or "NOT_FOUND" in err:
                next_m = None
                try:
                    idx = _GEMINI_FALLBACK_CHAIN.index(gemini_model)
                    if idx + 1 < len(_GEMINI_FALLBACK_CHAIN):
                        next_m = _GEMINI_FALLBACK_CHAIN[idx + 1]
                except ValueError:
                    if gemini_model != _GEMINI_FINAL_FALLBACK:
                        next_m = _GEMINI_FINAL_FALLBACK
                if next_m:
                    log.warning("Model %r not available — switching to %r", gemini_model, next_m)
                    gemini_model = next_m
                    continue
            raise RuntimeError(f"Gemini API error: {api_exc}") from api_exc
    raise RuntimeError("_generate_raw_gemini: unexpected exit")


def _generate_raw_openai(prompt: str, script_config: dict) -> str:
    """Call OpenAI and return raw response text."""
    from openai import OpenAI
    api_key = (script_config.get("openai_api_key") or config.get("openai_api_key", "")).strip()
    if not api_key:
        raise ValueError("OpenAI API key is not set.")
    model = script_config.get("openai_model") or config.get("openai_model", "gpt-4o")
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a documentary scriptwriter. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
        max_tokens=24576,
    )
    return response.choices[0].message.content


def _generate_raw_ollama(prompt: str, script_config: dict) -> str:
    """Call Ollama and return raw response text."""
    url = (script_config.get("ollama_url") or config.get("ollama_url", "http://localhost:11434")).rstrip("/")
    model = script_config.get("ollama_model") or config.get("ollama_model", "llama3")
    resp = requests.post(
        f"{url}/v1/chat/completions",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a documentary scriptwriter. Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 24576,
            "stream": False,
        },
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]



# ── Idea Workshop Chat ────────────────────────────────────────────────────────

_CONSULTANT_SYSTEM = """
You are Ghost Agent inside Ghost Creator AI — an expert documentary creative consultant.

LANGUAGE RULE (MOST IMPORTANT):
- Detect the language the user is writing in.
- If the user writes in English → reply ENTIRELY in English.
- If the user writes in Hindi / Hinglish → reply in Hindi/Hinglish.
- If the user writes in any other language → match that language.
- The <<PLAN_START>>..<<PLAN_END>> block field VALUES (TOPIC, META_TITLE, META_TAGS) must ALWAYS be written in English regardless of conversation language — they are used for YouTube metadata and search.

HOW VIDEOS START (no rigid questionnaire):
- Do NOT run a fixed wizard (topic → style → format → tone). Treat the chat as one natural flowing conversation.
- Your goal is to be a creative partner — explore the idea, suggest angles, ask about audience or tone if relevant.
- When generation should begin, you emit <<PLAN_START>>...<<PLAN_END>> (see below). That block IS the "start video" action.

WHEN TO EMIT THE PLAN:
1) User clearly says a start command — "start", "okay go", "generate", "make the video", "banao", "chalo banao",
   "lets go", "roll it", "I'm happy", "create now", "yes do it", "ab banao" etc. → emit the plan IMMEDIATELY in the same reply.
2) Only if the conversation has had AT LEAST 3–4 meaningful exchanges AND the idea is clearly concrete (topic, rough tone, length are understood) → you MAY gently suggest starting and offer to proceed. Do NOT auto-start silently; instead say something like "Sounds like a solid plan — should I go ahead and start?"
3) If the topic is vague or missing, ask ONE short clarifying question first.

DO NOT emit the plan after only 1–2 exchanges unless the user explicitly commands it (rule 1 above).
Enjoy the conversation — discuss angles, hook ideas, audience targeting, trending relevance before jumping to creation.

SMART DEFAULTS (fill any field the user didn't explicitly specify):
- STYLE: cinematic | shocking | educational | inspirational | fun  → default cinematic
- FORMAT: short = under ~60s | long = 1+ minutes  → default long
  "3 minutes / 10 min episode / full video" → long. "shorts / reel / under a minute" → short.
- TONE: energetic | calm | dramatic | casual | authoritative → default authoritative

CONVERSATION STYLE:
- Keep replies concise (2–4 sentences). No bullet checklists unless asked.
- Do not demand ✓ confirmations on every field before generating.
- NEVER say you cannot create — emitting the plan starts the pipeline.
- NEVER ask the user to click any button.
- NEVER write the full script, shot list, or narration — only the plan block when starting.

OUTPUT WHEN STARTING (end your reply with EXACTLY this block, nothing after <<PLAN_END>>):
<<PLAN_START>>
TOPIC: <specific English topic/angle>
STYLE: <one word>
FORMAT: <short or long>
TONE: <one word>
META_TITLE: <catchy English YouTube title>
META_TAGS: <comma-separated 6-10 English tags>
<<PLAN_END>>
"""

# Key to extract from PLAN block
_PLAN_KEYS = ("TOPIC", "STYLE", "FORMAT", "TONE", "META_TITLE", "META_TAGS")


def parse_plan_block(text: str) -> dict | None:
    """
    Extract the agreed creative plan from an AI reply.
    Returns a dict with keys: topic, style, format, tone, meta_title, meta_tags
    or None if no complete plan block is present.
    """
    if "<<PLAN_START>>" not in text or "<<PLAN_END>>" not in text:
        return None
    block_start = text.index("<<PLAN_START>>") + len("<<PLAN_START>>")
    block_end   = text.index("<<PLAN_END>>")
    block = text[block_start:block_end]
    plan: dict = {}
    for line in block.splitlines():
        line = line.strip()
        for key in _PLAN_KEYS:
            if line.upper().startswith(f"{key}:"):
                plan[key.lower().replace("meta_", "")] = line.split(":", 1)[1].strip()
                break
    # Require the four core keys
    if all(k in plan for k in ("topic", "style", "format", "tone")):
        return plan
    return None


def chat_with_consultant(
    history: list[dict],
    user_message: str,
    script_config: dict | None = None,
) -> str:
    """
    Multi-turn Gemini chat for the documentary Idea Workshop.

    Parameters
    ----------
    history       : list of {role: 'user'|'model', text: str} dicts
    user_message  : latest user input
    script_config : optional config slice (same shape as generate_script uses)

    Returns
    -------
    str — the model's reply text
    """
    cfg = script_config or {}
    api_key = (cfg.get("api_keys.gemini") or config.get("api_keys.gemini", "")).strip()
    if not api_key:
        return "⚠ No Gemini API key found. Please add it in Settings → API Keys."

    gemini_model = cfg.get("gemini_model") or config.get("gemini_model", GEMINI_MODEL)

    # Build contents list: system turn first, then history, then new user turn
    contents = []
    
    # ALWAYS inject the system prompt at the very start so the AI never forgets its rules.
    contents.append({"role": "user",  "parts": [{"text": _CONSULTANT_SYSTEM}]})
    contents.append({"role": "model", "parts": [{"text": "Understood. I reply in the user's language (plan block values always in English). I chat naturally, enjoy the discussion, and only emit <<PLAN_START>> when explicitly commanded OR after 3-4 meaningful exchanges. I never write the full script."}]})

    for turn in history:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn.get("text", "")}]})

    contents.append({"role": "user", "parts": [{"text": user_message}]})

    try:
        client = _gemini_client(api_key, gemini_model)
        response = client.models.generate_content(
            model=gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=2048,
                safety_settings=[
                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT",        threshold="BLOCK_ONLY_HIGH"),
                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH",       threshold="BLOCK_ONLY_HIGH"),
                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_ONLY_HIGH"),
                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
                ],
            ),
        )
        return response.text or "⚠ No response from Gemini."
    except Exception as exc:
        log.warning("chat_with_consultant error: %s", exc)
        return f"⚠ Gemini error: {exc}"


if __name__ == "__main__":
    # Quick smoke-test
    import pprint
    topic = "OpenAI releases GPT-5 with real-time reasoning"
    pprint.pprint(generate_script(topic))

