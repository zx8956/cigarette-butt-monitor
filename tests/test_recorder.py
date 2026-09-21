from pathlib import Path

import pytest

from app.capture.recorder import (
    CaptureState,
    CaptureStatus,
    parse_ffmpeg_progress,
    recording_command,
    run_bounded_process,
)


def test_disconnect_is_explicit_and_counted():
    status = CaptureStatus()
    status.device_found()
    status.recording_started()
    status.device_lost("USB disconnected")
    assert status.state == CaptureState.DISCONNECTED
    assert status.failures == 1
    assert status.last_error == "USB disconnected"


def test_recording_requires_ready_state():
    with pytest.raises(RuntimeError):
        CaptureStatus().recording_started()


def test_segment_command_uses_mkv_hardware_encoder_and_timestamp(tmp_path: Path):
    command = recording_command(
        device_index=3,
        camera_id="camera01",
        output_root=tmp_path,
        width=3840,
        height=2160,
        fps=30,
        segment_minutes=30,
        encoder="hevc_videotoolbox",
    )
    assert "hevc_videotoolbox" in command
    assert "1800" in command
    assert command[-1].endswith("camera01_%Y-%m-%d_%H-%M-%S.mkv")


def test_bounded_recording_command_and_progress(tmp_path: Path):
    command = recording_command(
        device_index=1,
        camera_id="camera01",
        output_root=tmp_path,
        width=3840,
        height=2160,
        fps=30,
        segment_minutes=30,
        encoder="hevc_videotoolbox",
        duration_seconds=60,
    )
    assert command[-3:-1] == ["-t", "60"]
    progress = parse_ffmpeg_progress(
        "frame=1800\nfps=30.0\ndup_frames=0\ndrop_frames=0\nspeed=0.999x\nprogress=end\n"
    )
    assert progress == {
        "frame": 1800,
        "fps": 30.0,
        "dup_frames": 0,
        "drop_frames": 0,
        "speed": 0.999,
        "progress": "end",
    }


def test_recording_can_publish_atomic_live_snapshot_without_model_backpressure(tmp_path: Path):
    snapshot = tmp_path / "snapshots" / "camera01_latest.jpg"
    command = recording_command(
        device_index=1,
        camera_id="camera01",
        output_root=tmp_path,
        width=2560,
        height=1440,
        fps=30,
        segment_minutes=30,
        encoder="hevc_videotoolbox",
        duration_seconds=60,
        snapshot_path=snapshot,
        snapshot_fps=1,
    )

    assert command.count("-map") == 2
    assert "fps=1" in command
    assert "-atomic_writing" in command
    assert command[-1] == str(snapshot)
    assert command.count("-t") == 2


def test_process_wall_timeout_stops_stuck_process():
    import sys

    result = run_bounded_process(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        wall_timeout_seconds=0.1,
        graceful_stop_seconds=1,
    )
    assert result.wall_timeout_triggered is True
    assert result.returncode != 0
