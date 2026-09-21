from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import cv2
import torch
from ultralytics import YOLO, __version__ as ultralytics_version

from app.capture.video_file import probe_video, validate_video_path
from app.core.config import PROJECT_ROOT, AppConfig
from app.tracking.summary import TrackSummary


def _device() -> str:
    return "mps" if torch.backends.mps.is_available() else "cpu"


def _model_path(model_name: str) -> Path:
    configured = Path(model_name)
    if configured.is_absolute():
        return configured
    return PROJECT_ROOT / "models" / configured.name


def analyze_people(
    source: Path,
    output_dir: Path,
    config: AppConfig,
    max_seconds: float | None = None,
) -> dict[str, Any]:
    source = validate_video_path(source)
    metadata = probe_video(source)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open real video: {source}")

    source_fps = capture.get(cv2.CAP_PROP_FPS)
    if source_fps <= 0:
        capture.release()
        raise RuntimeError("source video does not report a valid frame rate")
    stride = max(1, round(source_fps / config.analysis.fps))
    analysis_fps = source_fps / stride
    source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    output_width = min(source_width, config.analysis.input_width)
    output_height = round(source_height * output_width / source_width)

    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / f"{source.stem}_people_tracked.mp4"
    report_path = output_dir / f"{source.stem}_people_tracks.json"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        analysis_fps,
        (output_width, output_height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"could not create annotated video: {video_path}")

    model_path = _model_path(config.analysis.person_model)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(model_path))
    tracks: dict[int, TrackSummary] = {}
    frame_index = 0
    analyzed_frames = 0
    started = time.perf_counter()
    device = _device()

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = frame_index / source_fps
            frame_index += 1
            if max_seconds is not None and timestamp > max_seconds:
                break
            if (frame_index - 1) % stride:
                continue
            resized = cv2.resize(frame, (output_width, output_height))
            result = model.track(
                resized,
                persist=True,
                tracker="bytetrack.yaml",
                classes=[0],
                conf=config.analysis.person_confidence,
                device=device,
                verbose=False,
            )[0]
            annotated = result.plot()
            if result.boxes is not None and result.boxes.id is not None:
                ids = result.boxes.id.int().cpu().tolist()
                confidences = result.boxes.conf.cpu().tolist()
                boxes = result.boxes.xyxy.cpu().tolist()
                for track_id, confidence, box in zip(ids, confidences, boxes, strict=True):
                    center = (round((box[0] + box[2]) / 2), round((box[1] + box[3]) / 2))
                    if track_id in tracks:
                        tracks[track_id].update(timestamp, confidence, center)
                    else:
                        tracks[track_id] = TrackSummary(
                            track_id=track_id,
                            first_seen_seconds=timestamp,
                            last_seen_seconds=timestamp,
                            max_confidence=confidence,
                            trail=[center],
                        )
                    trail = tracks[track_id].trail
                    for start, end in zip(trail, trail[1:]):
                        cv2.line(annotated, start, end, (0, 255, 255), 2)
            writer.write(annotated)
            analyzed_frames += 1
    finally:
        capture.release()
        writer.release()

    elapsed = time.perf_counter() - started
    report: dict[str, Any] = {
        "source": str(source),
        "source_probe": metadata,
        "output_video": str(video_path),
        "person_model": str(model_path),
        "ultralytics_version": ultralytics_version,
        "device": device,
        "tracker": "ByteTrack",
        "person_class_only": True,
        "source_fps": source_fps,
        "analysis_fps": analysis_fps,
        "analyzed_frames": analyzed_frames,
        "elapsed_seconds": elapsed,
        "throughput_analyzed_fps": analyzed_frames / elapsed if elapsed else 0,
        "track_count": len(tracks),
        "tracks": [track.to_dict() for track in sorted(tracks.values(), key=lambda item: item.track_id)],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
