from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiskState:
    total_bytes: int
    used_bytes: int
    free_bytes: int

    @property
    def free_percent(self) -> float:
        return self.free_bytes / self.total_bytes * 100 if self.total_bytes else 0.0


def disk_state(path: Path) -> DiskState:
    usage = shutil.disk_usage(path)
    return DiskState(usage.total, usage.used, usage.free)


def classify_capacity(free_percent: float, warning: float = 15, cleanup: float = 10) -> str:
    if free_percent < cleanup:
        return "cleanup_required"
    if free_percent < warning:
        return "warning"
    return "ok"


def assert_project_recording(path: Path, data_root: Path) -> Path:
    candidate = path.resolve()
    recordings_root = (data_root / "recordings").resolve()
    events_root = (data_root / "events").resolve()
    if candidate == events_root or events_root in candidate.parents:
        raise ValueError("event evidence is never eligible for automatic deletion")
    if candidate == recordings_root or recordings_root not in candidate.parents:
        raise ValueError("automatic deletion is restricted to files inside recordings")
    return candidate


def delete_recording(path: Path, data_root: Path) -> None:
    safe_path = assert_project_recording(path, data_root)
    if not safe_path.is_file():
        raise ValueError("only regular recording files can be deleted")
    safe_path.unlink()
