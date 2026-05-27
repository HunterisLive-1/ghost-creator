"""Unit tests for Groq JSON repair/salvage in modules.scripter."""

import json

import pytest

from modules.scripter import _parse_groq_script, _repair_groq_json_text

# Malformed failed_generation from Groq json_validate_failed (tags inside description)
MALFORMED_GROQ_JSON = (
    '{\n'
    '  "voiceover_text": "test voiceover",\n'
    '  "english_subtitle_text": "test subtitle",\n'
    '  "image_prompts": ["scene 1", "scene 2", "scene 3", "scene 4"],\n'
    '  "metadata": {\n'
    '    "title": "Test Title",\n'
    '    "description": "DuckDuckGo installs have increased by thirty percent. '
    'Aapko pata hai ki DuckDuckGo kyu popular ho raha hai? '
    'Dekho yeh video aur jaano ki kya hai wajah,\n'
    '       tags": ["DuckDuckGo", "Google AI Search", "Search Engine", "Online Privacy", "hindi story", "full explain"]\n'
    '  }\n'
    '}'
)


def test_malformed_groq_json_is_invalid_before_repair():
    with pytest.raises(json.JSONDecodeError):
        json.loads(MALFORMED_GROQ_JSON)


def test_repair_groq_json_text_fixes_tags_inside_description():
    repaired = _repair_groq_json_text(MALFORMED_GROQ_JSON)
    parsed = json.loads(repaired)
    assert isinstance(parsed["metadata"]["description"], str)
    assert isinstance(parsed["metadata"]["tags"], list)
    assert "DuckDuckGo" in parsed["metadata"]["tags"]


def test_parse_groq_script_salvages_malformed_json():
    script = _parse_groq_script(MALFORMED_GROQ_JSON, num_scenes=4)
    assert script["voiceover_text"]
    assert len(script["image_prompts"]) >= 4
    assert isinstance(script["metadata"]["description"], str)
    assert isinstance(script["metadata"]["tags"], list)
    assert script["metadata"]["tags"][0] == "DuckDuckGo"
