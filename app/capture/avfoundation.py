from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AVDevice:
    index: int
    name: str
    kind: str

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


def parse_device_listing(output: str) -> list[AVDevice]:
    devices: list[AVDevice] = []
    kind: str | None = None
    device_pattern = re.compile(r"\[(\d+)\]\s+(.+)$")
    for line in output.splitlines():
        if "AVFoundation video devices:" in line:
            kind = "video"
            continue
        if "AVFoundation audio devices:" in line:
            kind = "audio"
            continue
        if kind is None:
            continue
        match = device_pattern.search(line)
        if match:
            devices.append(AVDevice(int(match.group(1)), match.group(2).strip(), kind))
    return devices


def list_devices(ffmpeg: str = "ffmpeg") -> list[AVDevice]:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return parse_device_listing(result.stderr + result.stdout)


def find_target(devices: list[AVDevice], name_contains: str) -> AVDevice | None:
    needle = name_contains.casefold()
    return next(
        (device for device in devices if device.kind == "video" and needle in device.name.casefold()),
        None,
    )
