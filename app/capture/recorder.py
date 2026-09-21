from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re
import signal
import subprocess


class CaptureState(StrEnum):
    WAITING_FOR_DEVICE = "waiting_for_camera_device"
    READY = "ready"
    RECORDING = "recording"
    DISCONNECTED = "camera_disconnected"
    STORAGE_OFFLINE = "storage_offline"
    STOPPED = "stopped"


@dataclass
class CaptureStatus:
    state: CaptureState = CaptureState.WAITING_FOR_DEVICE
    failures: int = 0
    last_error: str | None = None

    def device_found(self) -> None:
        self.state = CaptureState.READY
        self.last_error = None

    def recording_started(self) -> None:
        if self.state != CaptureState.READY:
            raise RuntimeError("recording can only start from ready state")
        self.state = CaptureState.RECORDING

    def device_lost(self, reason: str) -> None:
        self.state = CaptureState.DISCONNECTED
        self.failures += 1
        self.last_error = reason


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    wall_timeout_triggered: bool

    def storage_lost(self, reason: str) -> None:
        self.state = CaptureState.STORAGE_OFFLINE
        self.failures += 1
        self.last_error = reason


def recording_command(
    *,
    device_index: int,
    camera_id: str,
    output_root: Path,
    width: int,
    height: int,
    fps: int,
    segment_minutes: int,
    encoder: str,
    bitrate: str = "12M",
    pixel_format: str = "uyvy422",
    duration_seconds: float | None = None,
    snapshot_path: Path | None = None,
    snapshot_fps: float = 1,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    output_pattern = output_root / f"{camera_id}_%Y-%m-%d_%H-%M-%S.mkv"
    segment_seconds = segment_minutes * 60
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "warning",
        "-progress",
        "pipe:2",
        "-nostats",
        "-f",
        "avfoundation",
        "-framerate",
        str(fps),
        "-video_size",
        f"{width}x{height}",
        "-pixel_format",
        pixel_format,
        "-i",
        f"{device_index}:none",
        "-map",
        "0:v:0",
        "-an",
        "-r",
        str(fps),
        "-fps_mode",
        "cfr",
        "-c:v",
        encoder,
        "-b:v",
        bitrate,
        "-force_key_frames",
        f"expr:gte(t,n_forced*{segment_seconds})",
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
    ]
    if duration_seconds is not None:
        command.extend(["-t", str(duration_seconds)])
    command.append(str(output_pattern))
    if snapshot_path is not None:
        command.extend(
            [
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                f"fps={snapshot_fps}",
                "-q:v",
                "3",
                "-update",
                "1",
                "-atomic_writing",
                "1",
                "-f",
                "image2",
            ]
        )
        if duration_seconds is not None:
            command.extend(["-t", str(duration_seconds)])
        command.append(str(snapshot_path))
    return command


def parse_ffmpeg_progress(output: str) -> dict[str, int | float | str]:
    progress: dict[str, int | float | str] = {}
    numeric_integer = {"frame", "dup_frames", "drop_frames"}
    numeric_float = {"fps", "bitrate", "speed", "out_time_ms"}
    for line in re.split(r"[\r\n]+", output):
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if key in numeric_integer:
            progress[key] = int(value)
        elif key in numeric_float:
            cleaned = value.removesuffix("x").removesuffix("kbits/s")
            try:
                progress[key] = float(cleaned)
            except ValueError:
                progress[key] = value
        elif key == "progress":
            progress[key] = value
    return progress


def run_bounded_process(
    command: list[str],
    wall_timeout_seconds: float,
    graceful_stop_seconds: float = 10,
) -> ProcessResult:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=wall_timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.send_signal(signal.SIGINT)
        try:
            stdout, stderr = process.communicate(timeout=graceful_stop_seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            stdout, stderr = process.communicate(timeout=graceful_stop_seconds)
    return ProcessResult(process.returncode, stdout, stderr, timed_out)
