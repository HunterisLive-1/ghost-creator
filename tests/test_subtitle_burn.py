"""Tests for subtitle burn-in gating."""

from unittest.mock import MagicMock

from modules.documentary_assembler import wants_burned_subtitles


def test_burn_subtitles_enabled_for_short_mode():
    cfg = MagicMock()
    cfg.get.side_effect = lambda key, default=None: {
        "documentary.burn_subtitles": True,
        "documentary.length_mode": "short",
    }.get(key, default)
    assert wants_burned_subtitles(cfg) is True


def test_burn_subtitles_respects_disabled_flag():
    cfg = MagicMock()
    cfg.get.side_effect = lambda key, default=None: {
        "documentary.burn_subtitles": False,
        "documentary.length_mode": "long",
    }.get(key, default)
    assert wants_burned_subtitles(cfg) is False
