#!/bin/bash

set -u

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKER="${1:-}"
STOP_AT="${2:-20:30}"
RETRY_SECONDS=5

if [ "$WORKER" != "recording" ] && [ "$WORKER" != "ai" ]; then
  echo "用法：$0 recording|ai HH:MM"
  exit 2
fi

cd "$PROJECT_ROOT" || exit 1

stop_epoch="$(date -j -f "%Y-%m-%d %H:%M" "$(date +%Y-%m-%d) $STOP_AT" +%s 2>/dev/null)"
if [ -z "$stop_epoch" ]; then
  echo "结束时间格式错误，请使用 HH:MM，例如 20:30"
  exit 2
fi
if [ "$stop_epoch" -le "$(date +%s)" ]; then
  echo "结束时间 $STOP_AT 已经过期"
  exit 2
fi

run_stamp="$(date +%Y%m%d_%H%M%S)"
worker_log="logs/${WORKER}-until-dark-${run_stamp}.log"
exec > >(tee -a "$worker_log") 2>&1

echo "${WORKER} 开始运行，计划结束时间：$(date -r "$stop_epoch" '+%F %T %Z')"
echo "日志：$worker_log"

while [ "$(date +%s)" -lt "$stop_epoch" ]; do
  remaining_seconds=$((stop_epoch - $(date +%s)))
  echo "$(date '+%F %T') 启动 ${WORKER}，剩余 ${remaining_seconds} 秒"

  status=0
  if [ "$WORKER" = "recording" ]; then
    caffeinate -dimsu .venv/bin/cbm record-camera \
      --duration-seconds "$remaining_seconds" || status=$?
  else
    .venv/bin/cbm monitor-cigarette-butts \
      --duration-seconds "$remaining_seconds" || status=$?
  fi

  echo "$(date '+%F %T') ${WORKER} 进程退出，状态码：${status}"
  if [ "$(date +%s)" -lt "$stop_epoch" ]; then
    echo "$(date '+%F %T') ${RETRY_SECONDS} 秒后自动重启 ${WORKER}"
    sleep "$RETRY_SECONDS"
  fi
done

echo "$(date '+%F %T') 已到计划结束时间，${WORKER} 停止"
