# Third-party components

The project source is licensed under AGPL-3.0-only. Dependencies and separately downloaded
weights retain their upstream licenses; this repository does not relicense them.

| Component | Role | Upstream |
| --- | --- | --- |
| Ultralytics | YOLO11 / YOLO-World inference and ByteTrack integration | https://github.com/ultralytics/ultralytics ; https://www.ultralytics.com/license |
| yolo11n.pt | Pretrained person detection | https://docs.ultralytics.com/models/yolo11/ |
| yolov8s-worldv2.pt | Open-vocabulary candidate detection | https://docs.ultralytics.com/models/yolo-world/ |
| CLIP | Text encoding used by YOLO-World | https://github.com/openai/CLIP |
| PyTorch | Local inference, MPS / CPU | https://github.com/pytorch/pytorch |
| OpenCV | Video decoding and image processing | https://github.com/opencv/opencv |
| NumPy, Pydantic, PyYAML, lap | Numeric, configuration and assignment utilities | Installed via pyproject.toml |
| FFmpeg | External capture / encoding tool | https://ffmpeg.org/legal.html |
| OBS Studio | Optional external recording application | https://github.com/obsproject/obs-studio |

Ultralytics provides an AGPL-3.0 option and a separate Enterprise license. This publication
uses the open-source AGPL option. Consult the exact licenses of downloaded versions and
weights before redistribution or deployment. No proprietary or unidentified model weights
are included. No training dataset or original surveillance video is distributed. Two contributor-authorized
real-video contact sheets are included in docs/examples for the README demonstration.

The initialization command in README uses the upstream Ultralytics loader to obtain the
named pretrained models and text encoder. It may require network access on first run.
After initialization, retain the model files and text encoder caches for offline use.
