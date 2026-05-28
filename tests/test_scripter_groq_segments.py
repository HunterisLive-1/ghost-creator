"""Tests for Groq-safe documentary segment capping."""

from modules.scripter import _resolve_documentary_segments


def test_short_video_caps_segment_override():
    assert _resolve_documentary_segments(30, n_segments=8, provider="gemini") == 3


def test_groq_30s_caps_to_three_segments():
    assert _resolve_documentary_segments(30, n_segments=8, provider="groq") == 3


def test_groq_60s_caps_segments():
    assert _resolve_documentary_segments(60, n_segments=8, provider="groq") == 4
