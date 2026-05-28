"""Tests for history listing of runs without metadata.json."""

import json
from pathlib import Path

from api.routes.history import list_history


def test_history_lists_run_with_mp4_only(tmp_path, monkeypatch):
    run_dir = tmp_path / "custom_script_20260528_210017"
    run_dir.mkdir()
    (run_dir / "short_test.mp4").write_bytes(b"\x00" * 100)
    (run_dir / "voiceover.mp3").write_bytes(b"\x00" * 50)

    from core.config_manager import config

    monkeypatch.setattr(config, "load", lambda: None)
    monkeypatch.setattr(
        "api.routes.history.resolve_output_base",
        lambda fallback=None: tmp_path,
    )

    entries = list_history()["entries"]
    assert len(entries) == 1
    assert entries[0]["video_path"].endswith("short_test.mp4")
    assert (run_dir / "metadata.json").is_file()
