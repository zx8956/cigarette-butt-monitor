from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import time

from app.capture.avfoundation import find_target, list_devices
from app.capture.encoder import available_encoders, select_encoder
from app.capture.recorder import parse_ffmpeg_progress, recording_command, run_bounded_process
from app.capture.video_file import probe_video, probe_video_safely
from app.core.config import PROJECT_ROOT, load_config
from app.core.logging import setup_logging
from app.detection.person import analyze_people
from app.detection.cigarette import detect_cigarette_objects, monitor_live_snapshot
from app.storage.external import initialize_layout
from app.storage.policy import classify_capacity, disk_state


def command_devices() -> int:
    config = load_config()
    devices = list_devices()
    target = find_target(devices, config.camera.name_contains)
    result = {
        "status": "camera_detected" if target else "waiting_for_camera_device",
        "expected_name_contains": config.camera.name_contains,
        "target": target.to_dict() if target else None,
        "video_devices": [device.to_dict() for device in devices if device.kind == "video"],
        "audio_devices": [device.to_dict() for device in devices if device.kind == "audio"],
        "permission_note": (
            "If the camera appears but cannot open, grant Camera access to Terminal/Codex "
            "in System Settings > Privacy & Security > Camera."
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if target else 2


def command_probe_video(path: Path) -> int:
    print(json.dumps(probe_video(path), ensure_ascii=False, indent=2))
    return 0


def command_analyze_people(path: Path, output: Path, max_seconds: float | None) -> int:
    result = analyze_people(path, output, load_config(), max_seconds=max_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_detect_cigarette_butts(path: Path, output: Path) -> int:
    result = detect_cigarette_objects(path, output, load_config())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_monitor_cigarette_butts(duration_seconds: float) -> int:
    config = load_config()
    layout = initialize_layout(config.active_data_root)
    snapshot_path = layout["snapshots"] / "live" / f"{config.camera.id}_latest.jpg"
    output_dir = layout["snapshots"] / "detections"
    result = monitor_live_snapshot(
        snapshot_path,
        output_dir,
        layout["events"],
        config,
        duration_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_record_camera(duration_seconds: float) -> int:
    config = load_config()
    if not config.long_recording_allowed or config.storage.external_data_root is None:
        raise RuntimeError("external_data_root must be explicitly configured before camera recording")
    devices = list_devices()
    target = find_target(devices, config.camera.name_contains)
    if target is None:
        raise RuntimeError(f"waiting for camera device containing: {config.camera.name_contains}")

    layout = initialize_layout(config.storage.external_data_root)
    capacity = disk_state(layout["recordings"])
    capacity_status = classify_capacity(
        capacity.free_percent,
        config.storage.warning_free_percent,
        config.storage.cleanup_free_percent,
    )
    if capacity.free_percent < config.storage.stop_free_percent:
        raise RuntimeError(f"recording refused: disk free space is {capacity.free_percent:.2f}%")

    encoder = select_encoder(config.capture.encoder_preference, available_encoders())
    width, height, fps = config.camera.preferred_modes[0]
    camera_output = layout["recordings"] / config.camera.id
    camera_output.mkdir(parents=True, exist_ok=True)
    live_snapshot_root = layout["snapshots"] / "live"
    live_snapshot_root.mkdir(parents=True, exist_ok=True)
    snapshot_path = live_snapshot_root / f"{config.camera.id}_latest.jpg"
    before = set(camera_output.glob("*.mkv"))
    command = recording_command(
        device_index=target.index,
        camera_id=config.camera.id,
        output_root=camera_output,
        width=width,
        height=height,
        fps=fps,
        segment_minutes=config.capture.segment_minutes,
        encoder=encoder,
        bitrate=config.capture.bitrate,
        pixel_format=config.capture.pixel_format,
        duration_seconds=duration_seconds,
        snapshot_path=snapshot_path,
        snapshot_fps=config.analysis.live_snapshot_fps,
    )
    setup_logging(PROJECT_ROOT / "logs")
    logger = logging.getLogger("capture")
    logger.info(
        "recording_start camera=%s device=%s mode=%sx%s@%s encoder=%s duration=%s",
        config.camera.id,
        target.name,
        width,
        height,
        fps,
        encoder,
        duration_seconds,
    )
    started = time.perf_counter()
    result = run_bounded_process(command, wall_timeout_seconds=duration_seconds + 20)
    elapsed = time.perf_counter() - started
    progress = parse_ffmpeg_progress(result.stderr)
    created = sorted(set(camera_output.glob("*.mkv")) - before)
    if result.returncode:
        logger.error("recording_failed exit=%s error=%s", result.returncode, result.stderr[-2000:])
    else:
        logger.info("recording_complete files=%s progress=%s", created, progress)
    report = {
        "status": "completed" if result.returncode == 0 else "failed",
        "camera": target.to_dict(),
        "mode": {"width": width, "height": height, "fps": fps},
        "pixel_format": config.capture.pixel_format,
        "encoder": encoder,
        "configured_bitrate": config.capture.bitrate,
        "elapsed_seconds": elapsed,
        "ffmpeg_exit_code": result.returncode,
        "wall_timeout_triggered": result.wall_timeout_triggered,
        "ffmpeg_progress": progress,
        "disk_free_percent_before": capacity.free_percent,
        "disk_status_before": capacity_status,
        "files": [str(path) for path in created],
        "live_snapshot": str(snapshot_path),
        "file_probes": [probe_video_safely(path) for path in created],
        "ffmpeg_error_tail": result.stderr[-2000:] if result.returncode else "",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cbm")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("devices", help="List AVFoundation devices and find the configured camera")
    video = subparsers.add_parser("probe-video", help="Inspect a real local MP4, MOV or MKV")
    video.add_argument("path", type=Path)
    analysis = subparsers.add_parser("analyze-people", help="Run real YOLO person detection and ByteTrack")
    analysis.add_argument("path", type=Path)
    analysis.add_argument("--output", type=Path, default=Path("outputs"))
    analysis.add_argument("--max-seconds", type=float)
    cigarette = subparsers.add_parser(
        "detect-cigarette-butts",
        help="Run real offline open-vocabulary cigarette and butt detection on an image",
    )
    cigarette.add_argument("path", type=Path)
    cigarette.add_argument("--output", type=Path, default=Path("outputs/cigarette-detection"))
    monitor = subparsers.add_parser(
        "monitor-cigarette-butts",
        help="Continuously analyze the recorder's real live snapshots",
    )
    monitor.add_argument("--duration-seconds", type=float, default=60)
    record = subparsers.add_parser("record-camera", help="Record a bounded camera test to external storage")
    record.add_argument("--duration-seconds", type=float, default=60, choices=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "devices":
        return command_devices()
    if args.command == "probe-video":
        return command_probe_video(args.path)
    if args.command == "analyze-people":
        return command_analyze_people(args.path, args.output, args.max_seconds)
    if args.command == "detect-cigarette-butts":
        return command_detect_cigarette_butts(args.path, args.output)
    if args.command == "monitor-cigarette-butts":
        return command_monitor_cigarette_butts(args.duration_seconds)
    if args.command == "record-camera":
        if args.duration_seconds <= 0:
            raise ValueError("duration must be greater than zero")
        return command_record_camera(args.duration_seconds)
    raise AssertionError("unreachable")
