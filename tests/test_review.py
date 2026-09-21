"""Generated test-pattern media validates exports, never used as detection evidence."""

from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil
import subprocess

import cv2
import pytest

from app.review import export_candidate, gaps, overlap, recording_time, review_recent


def test_window_includes_segment_starting_before_lookback():
    t = datetime(2026, 1, 1, 12)
    assert overlap(t, 1800, t + timedelta(minutes=10), t + timedelta(minutes=40)) == (600, 1800)
    assert overlap(t, 60, t + timedelta(hours=1), t + timedelta(hours=2)) is None


def test_camera_and_obs_timestamps_never_use_file_mtime():
    t = datetime(2026, 1, 1, 12)
    assert recording_time(Path("2026-01-01 12-00-00.mkv")) == t
    assert recording_time(Path("camera01_2026-01-01_12-00-00.mkv")) == t
    with pytest.raises(ValueError):
        recording_time(Path("unknown.mkv"))


def test_overlapping_recordings_preserve_real_gaps():
    t = datetime(2026, 1, 1, 12)

    def dt(seconds):
        return t + timedelta(seconds=seconds)

    assert gaps([(dt(0), dt(5)), (dt(3), dt(7)), (dt(9), dt(10))], t, dt(12)) == [
        [dt(7).isoformat(), dt(9).isoformat()],
        [dt(10).isoformat(), dt(12).isoformat()],
    ]


@pytest.fixture
def test_pattern(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required for media integration test")
    root = tmp_path / "recordings"
    root.mkdir()
    video = root / "2026-01-01 12-00-00.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=30:duration=2",
            "-c:v",
            "libx264",
            str(video),
        ],
        check=True,
    )
    return video


def test_export_grid_and_sixfold_duration_without_overwriting(test_pattern, tmp_path):
    output = tmp_path / "export"
    result = export_candidate(test_pattern, output, 0.2, 1.7)
    assert abs(result["slow_duration"] - 9) < 0.3
    assert cv2.imread(str(output / "grid_3x3.jpg")).shape == (990, 1440, 3)
    assert len(result["grid_samples"]) == 9
    assert result["human_review_required"] is True
    assert json.loads((output / "review.json").read_text())["sha256"] == result["sha256"]
    with pytest.raises(FileExistsError):
        export_candidate(test_pattern, output, 0.2, 1.7)
    with pytest.raises(ValueError):
        export_candidate(test_pattern, tmp_path / "invalid", 0, 4)


def test_recent_reports_missing_coverage_and_exports_candidate(test_pattern, tmp_path):
    report = review_recent(
        test_pattern.parent, tmp_path / "recent", datetime(2026, 1, 1, 12, 0, 3), 4 / 3600, 1
    )
    assert report["status"] == "partial_review"
    assert len(report["scanned"]) == 1
    assert len(report["exports"]) == 1
    assert report["unreviewed_intervals"] == [
        ["2026-01-01T11:59:59", "2026-01-01T12:00:00"],
        ["2026-01-01T12:00:02", "2026-01-01T12:00:03"],
    ]
    assert report["errors"] == []
