from app.capture.avfoundation import find_target, parse_device_listing

LISTING = """
[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] FaceTime HD Camera
[AVFoundation indev @ 0x1] [1] HIKVISION DS-UVC-U168R
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone
"""


def test_device_listing_and_target_match():
    devices = parse_device_listing(LISTING)
    assert len(devices) == 3
    target = find_target(devices, "DS-UVC-U168R")
    assert target is not None
    assert target.index == 1
    assert target.kind == "video"


def test_missing_camera_returns_none():
    assert find_target(parse_device_listing(LISTING), "not-connected") is None
