from pathlib import Path

import pytest

from app.detection.cigarette import freeze_snapshot, monitor_live_snapshot


def test_freeze_rejects_stale_input(tmp_path):
    import os

    source = tmp_path / "old.jpg"
    source.write_bytes(b"test fixture, not model output")
    os.utime(source, (1, 1))
    with pytest.raises(ValueError, match="stale snapshot"):
        freeze_snapshot(source, tmp_path / "frozen.jpg")
    assert not (tmp_path / "frozen.jpg").exists()


def test_frozen_evidence_does_not_change_when_publisher_replaces_source(tmp_path):
    import hashlib

    source, frozen = tmp_path / "source.jpg", tmp_path / "frozen.jpg"
    source.write_bytes(b"frame A fixture")
    metadata = freeze_snapshot(source, frozen)
    source.write_bytes(b"frame B fixture")
    assert frozen.read_bytes() == b"frame A fixture"
    assert metadata["source_sha256"] == hashlib.sha256(frozen.read_bytes()).hexdigest()


def test_live_monitor_rejects_unbounded_zero_duration(tmp_path: Path):
    with pytest.raises(ValueError, match="greater than zero"):
        monitor_live_snapshot(
            tmp_path / "latest.jpg",
            tmp_path / "output",
            tmp_path / "events",
            config=None,  # type: ignore[arg-type]
            duration_seconds=0,
        )
