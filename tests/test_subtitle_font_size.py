"""Tests for subtitle font_size in ASS export."""

from pathlib import Path

from modules.documentary_assembler import _write_documentary_ass


def test_ass_uses_editor_font_size(tmp_path):
    ass_path = tmp_path / "subs.ass"
    segments = [{"voiceover": "Hello world"}]
    _write_documentary_ass(
        segments,
        5.0,
        ass_path,
        "9:16",
        subtitle_style={"font_size": 42, "color": "#FFFFFF", "bold": True},
    )
    text = ass_path.read_text(encoding="utf-8")
    assert "Style: DocSub," in text
    assert ",42," in text
