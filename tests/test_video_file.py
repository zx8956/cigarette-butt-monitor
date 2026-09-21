from pathlib import Path

import pytest

from app.capture.video_file import probe_video_safely, validate_video_path


def test_local_video_requires_supported_real_file(tmp_path: Path):
    video = tmp_path / "real.mov"
    video.write_bytes(b"not decoded in this path-only test")
    assert validate_video_path(video) == video.resolve()


def test_local_video_rejects_static_image(tmp_path: Path):
    image = tmp_path / "loop.jpg"
    image.write_bytes(b"image")
    with pytest.raises(ValueError):
        validate_video_path(image)


def test_failed_recording_probe_returns_structured_error(tmp_path: Path):
    invalid = tmp_path / "empty.mkv"
    invalid.write_bytes(b"")
    result = probe_video_safely(invalid)
    assert result["filename"] == str(invalid)
    assert result["size"] == 0
    assert "probe_error" in result
