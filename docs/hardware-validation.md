# Hardware validation

## Connected hardware

- Camera: Hikvision DS-UVC-U168R, exposed by macOS as `4K USB Camera`
- UVC identifier: `VendorID_11231 ProductID_680`
- Storage: external USB disk (local volume name omitted)
- Storage filesystem: NTFS through the installed iBoysoft driver

## 2026-07-28 checks

The external disk had approximately 749 GB free. A disposable 256 MiB file written inside
the project data root measured approximately 83 MB/s. The test file was removed immediately
after the measurement.

AVFoundation reported support for 3840x2160 at both 30 fps and 25 fps. Supported pixel
formats were UYVY422, YUYV422, NV12, 0RGB and BGR0.

### 4K30 UYVY422

Result: failed.

The camera initially produced valid 4K frames, then returned 4,177,920-byte buffers while
FFmpeg expected 16,588,800-byte 4K UYVY frames. The safely finalized evidence file contains
48.233 seconds and 1,447 HEVC frames. This mode is not suitable for continued testing.

### 4K30 NV12

Result: completed with timing-quality warning.

- Duration: 60.000 seconds
- Frames: 1,800
- Codec: HEVC through `hevc_videotoolbox`
- Average bitrate: 12.81 Mbps
- File size: 96,067,831 bytes
- FFmpeg speed: 0.998x
- Duplicated frames: 97
- Dropped frames: 87
- Wall timeout: not triggered

The recording is complete and decodable, but the amount of CFR timestamp correction is too
high to approve a one-hour stability test. The next required mode is 4K25 NV12.

### 4K25 NV12

Result: failed.

The device returned 1,385,280-byte buffers, which match 1280x720 NV12 rather than the
requested 3840x2160 NV12 frame size. No valid frame was encoded. The program wall timeout
stopped FFmpeg after 80 seconds. This mode is not suitable for continued testing.

### 2560x1440 30 fps NV12 input probe

Result: passed for a 15-second input-only test.

- Frames: 451
- Measured rate: 29.93 fps
- Duplicated frames: 0
- Dropped frames: 0
- FFmpeg speed: 0.995x
- Wall timeout: not triggered

This is the next mode approved for a one-minute HEVC recording test.

### 2560x1440 30 fps NV12 HEVC recording

Result: passed for a one-minute recording test.

- Duration: 60.000 seconds
- Frames: 1,800
- Measured rate: 29.96 fps
- Codec: HEVC through `hevc_videotoolbox`
- Average bitrate: 12.37 Mbps
- File size: 92,808,194 bytes
- Duplicated frames: 4
- Dropped frames: 0
- FFmpeg speed: 0.998x
- Wall timeout: not triggered
- SHA-256: `4b1e7b1104aa8aefbf0105dd11bf8b693ddcf2a74e683f18427db8627277f3c0`

This mode is approved for the one-hour stability test. The 4K modes remain disabled.
