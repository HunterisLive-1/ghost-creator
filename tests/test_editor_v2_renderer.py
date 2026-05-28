from pathlib import Path

from api.services.editor_v2_renderer import validate_editor_v2


def test_validate_editor_v2_accepts_basic_project(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00" * 6000)
    project = {
        "schema_version": 2,
        "assets": [{"id": "a1", "type": "video", "name": "clip.mp4", "path": str(clip)}],
        "tracks": [{"id": "video-main", "type": "video", "name": "Main Video"}],
        "items": [{"id": "i1", "trackId": "video-main", "kind": "video", "assetId": "a1", "start": 0, "end": 3}],
    }
    assert validate_editor_v2(project, tmp_path) == []


def test_validate_editor_v2_reports_missing_asset_file(tmp_path):
    project = {
        "schema_version": 2,
        "assets": [{"id": "a1", "type": "video", "name": "missing.mp4", "path": str(tmp_path / "missing.mp4")}],
        "tracks": [{"id": "video-main", "type": "video", "name": "Main Video"}],
        "items": [{"id": "i1", "trackId": "video-main", "kind": "video", "assetId": "a1", "start": 0, "end": 3}],
    }
    errors = validate_editor_v2(project, tmp_path)
    assert errors
    assert "asset file not found" in errors[0]


def test_validate_editor_v2_reports_bad_duration(tmp_path):
    project = {
        "schema_version": 2,
        "assets": [],
        "tracks": [{"id": "overlay-1", "type": "overlay", "name": "Overlay"}],
        "items": [{"id": "txt", "trackId": "overlay-1", "kind": "text", "text": "Hello", "start": 5, "end": 5}],
    }
    errors = validate_editor_v2(project, tmp_path)
    assert any("end time" in err for err in errors)
