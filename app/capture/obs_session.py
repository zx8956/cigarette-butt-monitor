"""Local OBS snapshot + experimental AI supervisor; never starts/stops OBS recording.

Runs until interrupted or the specified OBS PID exits. No cloud calls or deletion.
"""

import argparse
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from app.core.config import PROJECT_ROOT, load_config
from app.storage.external import initialize_layout


def storage_ready(root: Path) -> bool:
    mount = Path(*root.parts[:3])
    return (
        mount.is_mount()
        and root.is_dir()
        and os.access(root, os.W_OK)
        and shutil.disk_usage(root).free / shutil.disk_usage(root).total >= 0.10
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--obs-pid", type=int, required=True)
    args = parser.parse_args()
    lock = (PROJECT_ROOT / "logs" / "obs-ai-session.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("An OBS AI supervisor is already running") from None

    def stop(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    config = load_config()
    root = config.storage.external_data_root
    if root is None or not storage_ready(root):
        raise RuntimeError("Confirmed external disk unavailable or below 10% free")
    layout = initialize_layout(root)
    snapshot = layout["snapshots"] / "live" / f"{config.camera.id}_latest.jpg"
    snapshot.parent.mkdir(exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-f",
        "avfoundation",
        "-framerate",
        "60",
        "-video_size",
        "1920x1080",
        "-pixel_format",
        "uyvy422",
        "-i",
        "OBS Virtual Camera:none",
        "-an",
        "-frames:v",
        "1",
        "-q:v",
        "3",
        "-update",
        "1",
        "-atomic_writing",
        "1",
        "-f",
        "image2",
        str(snapshot),
    ]
    worker = None
    keep_awake = subprocess.Popen(["caffeinate", "-di", "-w", str(args.obs_pid)])
    try:
        with (PROJECT_ROOT / "logs" / "obs-ai-session.log").open("a") as log:
            while True:
                try:
                    os.kill(args.obs_pid, 0)
                except ProcessLookupError:
                    break
                if not storage_ready(root):
                    print(
                        "ALERT: external disk offline/low; AI stopped, no system-disk fallback",
                        flush=True,
                    )
                    break
                if worker is None or worker.poll() is not None:
                    if worker is not None:
                        print(
                            f"AI worker exit={worker.returncode}; retrying in 5 seconds", flush=True
                        )
                        time.sleep(5)
                    worker = subprocess.Popen(
                        [
                            str(PROJECT_ROOT / ".venv/bin/cbm"),
                            "monitor-cigarette-butts",
                            "--duration-seconds",
                            "3600",
                        ],
                        stdout=log,
                        stderr=log,
                    )
                try:
                    subprocess.run(command, timeout=12, check=True, stdout=log, stderr=log)
                except (subprocess.SubprocessError, OSError) as error:
                    print(f"Snapshot error: {error}", flush=True)
                    time.sleep(5)
                time.sleep(1)
    finally:
        if worker is not None and worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()
        keep_awake.terminate()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
