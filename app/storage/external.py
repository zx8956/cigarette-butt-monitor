from __future__ import annotations

import os
from pathlib import Path

LAYOUT = ("recordings", "events", "snapshots", "database-backups", "archived-logs")


def validate_external_root(path: Path) -> Path:
    root = path.expanduser().resolve()
    volumes = Path("/Volumes").resolve()
    if volumes not in root.parents:
        raise ValueError("formal data root must be an explicitly configured path under /Volumes")
    if not root.exists():
        raise FileNotFoundError(f"configured external data root is offline: {root}")
    if not root.is_dir() or not os.access(root, os.W_OK):
        raise PermissionError(f"configured external data root is not writable: {root}")
    return root


def initialize_layout(path: Path) -> dict[str, Path]:
    root = validate_external_root(path)
    layout = {name: root / name for name in LAYOUT}
    for directory in layout.values():
        directory.mkdir(parents=True, exist_ok=True)
    return layout
