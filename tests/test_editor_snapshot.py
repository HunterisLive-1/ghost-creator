"""Tests for editor snapshot backfill."""

from pathlib import Path

from api.services.editor_snapshot import ensure_editor_json, run_is_editable


def test_run_is_editable_with_clips_for_edit(tmp_path):
    run_dir = tmp_path / "run1"
    cfe = run_dir / "clips_for_edit"
    cfe.mkdir(parents=True)
    (cfe / "e_00.mp4").write_bytes(b"\x00" * 200)
    assert run_is_editable(run_dir) is True


def test_ensure_editor_json_creates_snapshot(tmp_path, monkeypatch):
    run_dir = tmp_path / "custom_script_test"
    cfe = run_dir / "clips_for_edit"
    cfe.mkdir(parents=True)
    (cfe / "e_00.mp4").write_bytes(b"\x00" * 200)
    (cfe / "e_01.mp4").write_bytes(b"\x00" * 200)
    (run_dir / "metadata.json").write_text(
        '{"title": "Test Run", "video_path": ""}', encoding="utf-8"
    )

    from core.clip_manager import get_clip_duration

    monkeypatch.setattr("api.services.editor_snapshot.get_clip_duration", lambda _p: 5.0)

    path = ensure_editor_json(run_dir)
    assert path is not None
    assert path.is_file()
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["title"] == "Test Run"
    assert len(data["segments"]) == 2
    assert data["segments"][0]["clip_name"] == "e_00.mp4"
