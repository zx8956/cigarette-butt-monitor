from pathlib import Path

import pytest

from app.storage.policy import assert_project_recording, classify_capacity, delete_recording


def test_capacity_thresholds():
    assert classify_capacity(20) == "ok"
    assert classify_capacity(12) == "warning"
    assert classify_capacity(9) == "cleanup_required"


def test_deletion_is_restricted_to_recordings(tmp_path: Path):
    recording = tmp_path / "recordings" / "camera01" / "clip.mkv"
    recording.parent.mkdir(parents=True)
    recording.write_bytes(b"real-test-bytes")
    assert assert_project_recording(recording, tmp_path) == recording.resolve()
    delete_recording(recording, tmp_path)
    assert not recording.exists()


@pytest.mark.parametrize("relative", ["events/a/event.mkv", "database/app.db", "outside.mkv"])
def test_automatic_deletion_rejects_non_recordings(tmp_path: Path, relative: str):
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"evidence")
    with pytest.raises(ValueError):
        delete_recording(target, tmp_path)
    assert target.exists()
