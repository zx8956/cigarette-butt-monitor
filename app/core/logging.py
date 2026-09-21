from __future__ import annotations

import logging
from pathlib import Path

LOG_NAMES = ("application", "capture", "inference", "events", "storage")


def setup_logging(log_root: Path, level: str = "INFO") -> None:
    log_root.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%S%z"
    )
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    for name in LOG_NAMES:
        logger = logging.getLogger(name)
        logger.setLevel(numeric_level)
        logger.propagate = False
        if not logger.handlers:
            handler = logging.FileHandler(log_root / f"{name}.log", encoding="utf-8")
            handler.setFormatter(formatter)
            logger.addHandler(handler)

    root = logging.getLogger()
    root.setLevel(numeric_level)
    if not any(getattr(handler, "baseFilename", "").endswith("errors.log") for handler in root.handlers):
        errors = logging.FileHandler(log_root / "errors.log", encoding="utf-8")
        errors.setLevel(logging.ERROR)
        errors.setFormatter(formatter)
        root.addHandler(errors)

