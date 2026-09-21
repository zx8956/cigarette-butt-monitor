from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv"}


def validate_video_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("supported local video formats are MP4, MOV and MKV")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def probe_video(path: Path, ffprobe: str = "ffprobe") -> dict[str, Any]:
    resolved = validate_video_path(path)
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=filename,duration,size,format_name:stream=index,codec_type,codec_name,width,height,avg_frame_rate",
            "-of",
            "json",
            str(resolved),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def probe_video_safely(path: Path, ffprobe: str = "ffprobe") -> dict[str, Any]:
    try:
        return probe_video(path, ffprobe)
    except subprocess.CalledProcessError as error:
        return {
            "filename": str(path),
            "size": path.stat().st_size if path.exists() else None,
            "probe_error": error.stderr.strip() or f"ffprobe exited with code {error.returncode}",
        }
