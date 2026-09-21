#!/bin/bash

set -u

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STOP_AT="${1:-20:30}"
RETRY_SECONDS=5
# Legacy landscape-only helper. Prefer app.capture.obs_session for new setups.
: "${CBM_DATA_ROOT:?Set CBM_DATA_ROOT to your existing external data directory}"
SNAPSHOT_PATH="${CBM_DATA_ROOT}/snapshots/live/camera01_latest.jpg"

cd "$PROJECT_ROOT" || exit 1

stop_epoch="$(date -j -f "%Y-%m-%d %H:%M" "$(date +%Y-%m-%d) $STOP_AT" +%s 2>/dev/null)"
if [ -z "$stop_epoch" ] || [ "$stop_epoch" -le "$(date +%s)" ]; then
  echo "结束时间无效或已经过期：$STOP_AT"
  exit 2
fi

run_stamp="$(date +%Y%m%d_%H%M%S)"
worker_log="logs/obs-virtual-snapshot-until-dark-${run_stamp}.log"
exec > >(tee -a "$worker_log") 2>&1

echo "OBS虚拟摄像头快照开始，计划结束时间：$(date -r "$stop_epoch" '+%F %T %Z')"
echo "日志：$worker_log"

device_index="$(
  .venv/bin/cbm devices |
    .venv/bin/python -c \
      'import json,sys; data=json.load(sys.stdin); print(next(item["index"] for item in data["video_devices"] if item["name"] == "OBS Virtual Camera"))'
)"
echo "$(date '+%F %T') 使用OBS虚拟摄像头设备 ${device_index}"

while [ "$(date +%s)" -lt "$stop_epoch" ]; do
  status=0
  ffmpeg -y -hide_banner -nostdin -loglevel error \
    -f avfoundation -framerate 60 -video_size 1920x1080 -pixel_format uyvy422 \
    -i "${device_index}:none" -an -frames:v 1 -q:v 3 -update 1 -atomic_writing 1 \
    -f image2 "$SNAPSHOT_PATH" || status=$?

  if [ "$status" -eq 0 ]; then
    sleep 1
  else
    echo "$(date '+%F %T') OBS快照失败，状态码：${status}，${RETRY_SECONDS} 秒后重试"
    sleep "$RETRY_SECONDS"
    device_index="$(
      .venv/bin/cbm devices |
        .venv/bin/python -c \
          'import json,sys; data=json.load(sys.stdin); print(next(item["index"] for item in data["video_devices"] if item["name"] == "OBS Virtual Camera"))'
    )"
  fi
done

echo "$(date '+%F %T') 已到计划结束时间，OBS快照停止"
