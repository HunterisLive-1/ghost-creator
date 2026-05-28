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


def test_list_clips_separates_edit_and_stock(tmp_path):
    from api.routes.history import list_clips

    run_dir = tmp_path / "run_clips"
    cfe = run_dir / "clips_for_edit"
    stock = run_dir / "clips"
    cfe.mkdir(parents=True)
    stock.mkdir(parents=True)
    (cfe / "e_00.mp4").write_bytes(b"\x00" * 100)
    (cfe / "e_01.mp4").write_bytes(b"\x00" * 100)
    (stock / "clip_00.mp4").write_bytes(b"\x00" * 100)

    res = list_clips(str(run_dir))
    assert len(res["edit_clips"]) == 2
    assert len(res["stock_clips"]) == 1
    assert res["clips"] == res["edit_clips"]
    assert all(c["role"] == "edit" for c in res["edit_clips"])
    assert res["stock_clips"][0]["role"] == "stock"
