from __future__ import annotations

import json
import hashlib
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import torch
from ultralytics import YOLOWorld, __version__ as ultralytics_version

from app.core.config import PROJECT_ROOT, AppConfig
from app.core.logging import setup_logging

DEFAULT_PROMPTS = (
    "cigarette butt",
    "discarded cigarette",
    "cigarette",
    "smoking person",
    "person",
)
EVENT_CANDIDATE_LABELS = {
    "cigarette butt",
    "discarded cigarette",
    "cigarette",
    "smoking person",
}


def freeze_snapshot(source: Path, destination: Path, max_age_seconds: float = 10) -> dict:
    # The publisher replaces the source atomically. Read metadata and bytes from
    # the same open descriptor so inference and evidence always refer to one frame.
    import os

    with source.open("rb") as handle:
        stat = os.fstat(handle.fileno())
        content = handle.read()
    age = time.time() - stat.st_mtime
    if age > max_age_seconds or age < -1:
        raise ValueError(f"stale snapshot: age={age:.2f}s")
    destination.write_bytes(content)
    return {
        "captured_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "snapshot_age_seconds": age,
        "source_sha256": hashlib.sha256(content).hexdigest(),
    }


def _device() -> str:
    return "mps" if torch.backends.mps.is_available() else "cpu"


def _model_path(model_name: str) -> Path:
    configured = Path(model_name)
    if configured.is_absolute():
        return configured
    return PROJECT_ROOT / "models" / configured.name


def _load_image(path: Path, rotation_degrees: int) -> tuple[Path, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"real image does not exist: {resolved}")
    image = cv2.imread(str(resolved))
    if image is None:
        raise ValueError(f"OpenCV could not decode image: {resolved}")
    rotations = {
        0: None,
        90: cv2.ROTATE_90_CLOCKWISE,
        -90: cv2.ROTATE_90_COUNTERCLOCKWISE,
        180: cv2.ROTATE_180,
    }
    rotation = rotations[rotation_degrees]
    return resolved, cv2.rotate(image, rotation) if rotation is not None else image


def detections_from_result(result: Any, names: dict[int, str]) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []
    if result.boxes is None:
        return detections
    for box in result.boxes:
        class_id = int(box.cls.item())
        detections.append(
            {
                "class_id": class_id,
                "label": names[class_id],
                "confidence": float(box.conf.item()),
                "box_xyxy": [round(float(value), 2) for value in box.xyxy[0].tolist()],
            }
        )
    return detections


class CigaretteObjectDetector:
    def __init__(
        self,
        config: AppConfig,
        prompts: tuple[str, ...] = DEFAULT_PROMPTS,
    ) -> None:
        self.config = config
        self.prompts = prompts
        self.model_path = _model_path(config.analysis.open_vocabulary_model)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        self.model = YOLOWorld(str(self.model_path))
        self.model.set_classes(list(prompts))
        self.load_seconds = time.perf_counter() - started
        self.device = _device()

    def detect(self, source: Path, output_dir: Path) -> dict[str, Any]:
        source, image = _load_image(source, self.config.analysis.rotation_degrees)
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        inference_started = time.perf_counter()
        result = self.model.predict(
            image,
            conf=self.config.analysis.butt_confidence,
            imgsz=self.config.analysis.open_vocabulary_image_size,
            device=self.device,
            verbose=False,
        )[0]
        inference_seconds = time.perf_counter() - inference_started

        annotated_path = output_dir / f"{source.stem}_cigarette_detection.jpg"
        report_path = output_dir / f"{source.stem}_cigarette_detection.json"
        result.save(filename=str(annotated_path))
        detections = detections_from_result(result, self.model.names)
        candidate_detections = [
            detection for detection in detections if detection["label"] in EVENT_CANDIDATE_LABELS
        ]
        report: dict[str, Any] = {
            "source": str(source),
            "output_image": str(annotated_path),
            "model": str(self.model_path),
            "model_family": "YOLO-World",
            "ultralytics_version": ultralytics_version,
            "device": self.device,
            "prompts": list(self.prompts),
            "confidence_threshold": self.config.analysis.butt_confidence,
            "image_size": self.config.analysis.open_vocabulary_image_size,
            "rotation_degrees": self.config.analysis.rotation_degrees,
            "model_load_seconds": self.load_seconds,
            "inference_seconds": inference_seconds,
            "detection_count": len(detections),
            "detections": detections,
            "candidate_detection_count": len(candidate_detections),
            "candidate_detections": candidate_detections,
            "decision": "candidate_found" if candidate_detections else "no_candidate_found",
            "human_review_required": True,
            "license_status": (
                "technical validation only; review Ultralytics AGPL-3.0 or enterprise "
                "licensing before commercial deployment"
            ),
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
        return report


def detect_cigarette_objects(
    source: Path,
    output_dir: Path,
    config: AppConfig,
    prompts: tuple[str, ...] = DEFAULT_PROMPTS,
) -> dict[str, Any]:
    return CigaretteObjectDetector(config, prompts).detect(source, output_dir)


def monitor_live_snapshot(
    snapshot_path: Path,
    output_dir: Path,
    event_root: Path,
    config: AppConfig,
    duration_seconds: float,
    poll_seconds: float = 0.2,
) -> dict[str, Any]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than zero")
    snapshot_path = snapshot_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    event_root = event_root.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(PROJECT_ROOT / "logs")
    logger = logging.getLogger("inference")
    detector = CigaretteObjectDetector(config)
    logger.info("model_loaded model=%s device=%s", detector.model_path, detector.device)
    started = time.monotonic()
    last_mtime_ns: int | None = None
    analyzed_snapshots = 0
    candidate_events: list[str] = []
    errors: list[str] = []
    last_status = 0.0
    last_success = None
    last_error = None

    def status(state: str) -> None:
        nonlocal last_status
        last_status = time.monotonic()
        temporary = output_dir / "live_status.json.tmp"
        temporary.write_text(
            json.dumps(
                {
                    "state": state,
                    "updated_at": datetime.now().astimezone().isoformat(),
                    "last_success": last_success,
                    "analyzed_snapshots": analyzed_snapshots,
                    "candidate_events": len(candidate_events),
                    "last_error": last_error,
                    "model": str(detector.model_path),
                    "device": detector.device,
                },
                indent=2,
            )
        )
        temporary.replace(output_dir / "live_status.json")

    while time.monotonic() - started < duration_seconds:
        try:
            mtime_ns = snapshot_path.stat().st_mtime_ns
        except FileNotFoundError:
            if time.monotonic() - last_status > 5:
                logger.warning("snapshot_missing path=%s", snapshot_path)
                status("waiting_for_snapshot")
            time.sleep(poll_seconds)
            continue
        if mtime_ns == last_mtime_ns:
            if time.monotonic() - last_status > 5:
                age = time.time() - mtime_ns / 1e9
                status("stale_snapshot" if age > 10 else "waiting_for_next_frame")
            time.sleep(poll_seconds)
            continue
        last_mtime_ns = mtime_ns
        try:
            frozen = output_dir / f"{snapshot_path.stem}.jpg"
            metadata = freeze_snapshot(snapshot_path, frozen)
            report = detector.detect(frozen, output_dir)
            report.update(metadata)
            analyzed_snapshots += 1
            last_success = datetime.now().astimezone().isoformat()
            last_error = None
            logger.info(
                "inference_complete count=%s seconds=%.3f candidates=%s age=%.3f",
                analyzed_snapshots,
                report["inference_seconds"],
                report["candidate_detection_count"],
                metadata["snapshot_age_seconds"],
            )
            if report["candidate_detection_count"]:
                now = datetime.now().astimezone()
                event_id = f"event_{now:%Y%m%d_%H%M%S_%f}_unassociated"
                event_dir = event_root / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}" / event_id
                event_dir.mkdir(parents=True, exist_ok=False)
                shutil.copy2(frozen, event_dir / "overview.jpg")
                shutil.copy2(Path(report["output_image"]), event_dir / "detection.jpg")
                event_report = {
                    "event_id": event_id,
                    "camera_id": config.camera.id,
                    "created_at": now.isoformat(),
                    "event_type": "suspected_cigarette_object",
                    "association_status": "track_not_associated",
                    "review_status": "unreviewed",
                    "review_note": "",
                    "detection": report,
                }
                (event_dir / "event.json").write_text(
                    json.dumps(event_report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                candidate_events.append(str(event_dir))
            status("running")
        except (OSError, RuntimeError, ValueError) as error:
            last_error = f"{type(error).__name__}: {error}"
            errors.append(last_error)
            errors = errors[-100:]
            logger.exception("inference_failed")
            status("error")
        time.sleep(poll_seconds)

    status("completed")
    return {
        "status": "completed",
        "snapshot_path": str(snapshot_path),
        "duration_seconds": duration_seconds,
        "analyzed_snapshots": analyzed_snapshots,
        "candidate_event_count": len(candidate_events),
        "candidate_events": candidate_events,
        "errors": errors,
        "model": str(detector.model_path),
        "device": detector.device,
    }
