from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CameraConfig(BaseModel):
    id: str = "camera01"
    name_contains: str = "DS-UVC-U168R"
    device_index: int | None = None
    preferred_modes: list[tuple[int, int, int]]


class CaptureConfig(BaseModel):
    segment_minutes: Annotated[int, Field(ge=1)] = 30
    container: str = "mkv"
    encoder_preference: list[str]
    pixel_format: str = "uyvy422"
    bitrate: str = "12M"
    reconnect_seconds: Annotated[float, Field(ge=1)] = 5


class StorageConfig(BaseModel):
    external_data_root: Path | None = None
    warning_free_percent: Annotated[float, Field(gt=0, lt=100)] = 15
    cleanup_free_percent: Annotated[float, Field(gt=0, lt=100)] = 10
    stop_free_percent: Annotated[float, Field(gt=0, lt=100)] = 10
    retention_days: Annotated[int, Field(ge=1)] = 7
    max_recordings_gb: Annotated[float | None, Field(gt=0)] = None

    @model_validator(mode="after")
    def validate_thresholds(self) -> "StorageConfig":
        if self.cleanup_free_percent > self.warning_free_percent:
            raise ValueError("cleanup threshold cannot exceed warning threshold")
        return self


class AnalysisConfig(BaseModel):
    fps: Annotated[float, Field(gt=0)] = 5
    live_snapshot_fps: Annotated[float, Field(gt=0, le=5)] = 1
    input_width: Annotated[int, Field(ge=320)] = 960
    person_model: str = "yolo11n.pt"
    open_vocabulary_model: str = "yolov8s-worldv2.pt"
    open_vocabulary_image_size: Annotated[int, Field(ge=320)] = 1280
    rotation_degrees: int = -90
    person_confidence: Annotated[float, Field(ge=0, le=1)] = 0.35
    cigarette_confidence: Annotated[float, Field(ge=0, le=1)] = 0.30
    butt_confidence: Annotated[float, Field(ge=0, le=1)] = 0.25
    draw_output: bool = True
    open_vocabulary_confirmation: bool = False

    @model_validator(mode="after")
    def validate_rotation(self) -> "AnalysisConfig":
        if self.rotation_degrees not in {0, 90, -90, 180}:
            raise ValueError("rotation_degrees must be one of 0, 90, -90 or 180")
        return self


class EventConfig(BaseModel):
    pre_seconds: Annotated[int, Field(ge=0)] = 10
    post_seconds: Annotated[int, Field(ge=0)] = 20
    ground_roi: tuple[int, int, int, int] | None = None


class AppConfig(BaseModel):
    camera: CameraConfig
    capture: CaptureConfig
    storage: StorageConfig
    analysis: AnalysisConfig
    events: EventConfig

    @property
    def development_data_root(self) -> Path:
        return PROJECT_ROOT / "data"

    @property
    def active_data_root(self) -> Path:
        return self.storage.external_data_root or self.development_data_root

    @property
    def long_recording_allowed(self) -> bool:
        return self.storage.external_data_root is not None


def load_config(path: Path | None = None) -> AppConfig:
    configured = os.environ.get("CBM_CONFIG")
    config_path = path or (Path(configured) if configured else PROJECT_ROOT / "config/default.yaml")
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    config = AppConfig.model_validate(raw)
    external_override = os.environ.get("CBM_DATA_ROOT", "").strip()
    if external_override:
        config.storage.external_data_root = Path(external_override).expanduser().resolve()
    return config
