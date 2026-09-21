from __future__ import annotations

import subprocess


def available_encoders(ffmpeg: str = "ffmpeg") -> set[str]:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return {
        name
        for name in ("hevc_videotoolbox", "h264_videotoolbox")
        if name in result.stdout
    }


def select_encoder(preferences: list[str], installed: set[str]) -> str:
    selected = next((encoder for encoder in preferences if encoder in installed), None)
    if selected is None:
        raise RuntimeError("no configured VideoToolbox hardware encoder is available")
    return selected
