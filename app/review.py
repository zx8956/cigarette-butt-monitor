"""Human-triggered retrospective motion review; candidates are never accusations."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    duration = float(data["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Video duration must be finite and positive; close the recording first")
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return {"duration": duration, "width": video["width"], "height": video["height"]}


def recording_time(path: Path) -> datetime:
    """Only explicit supported filename conventions; never infer from mtime."""
    for name, fmt in [
        (path.stem, "%Y-%m-%d %H-%M-%S"),
        (path.stem.split("_", 1)[-1], "%Y-%m-%d_%H-%M-%S"),
    ]:
        try:
            return datetime.strptime(name, fmt)
        except ValueError:
            pass
    raise ValueError("Unsupported timestamp filename")


def overlap(start: datetime, duration: float, begin: datetime, end: datetime):
    lo = max(0.0, (begin - start).total_seconds())
    hi = min(duration, (end - start).total_seconds())
    return (lo, hi) if hi > lo else None


def gaps(intervals, begin, end):
    cursor = begin
    result = []
    for lo, hi in sorted(intervals):
        lo, hi = max(begin, lo), min(end, hi)
        if hi <= lo:
            continue
        if lo > cursor:
            result.append([cursor.isoformat(), lo.isoformat()])
        cursor = max(cursor, hi)
    if cursor < end:
        result.append([cursor.isoformat(), end.isoformat()])
    return result


def export_candidate(source: Path, output: Path, start: float, end: float) -> dict:
    source = source.resolve()
    info = probe(source)
    if not all(math.isfinite(v) for v in [start, end]) or not 0 <= start < end <= info["duration"]:
        raise ValueError("Clip must be within video duration: 0 <= start < end <= duration")
    output.mkdir(parents=True, exist_ok=False)
    cap = cv2.VideoCapture(str(source))
    tiles, samples = [], []
    try:
        # Keep last sample away from the end-of-file boundary.
        for i, sec in enumerate(
            np.linspace(start, max(start, end - min(0.1, (end - start) / 10)), 9)
        ):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(sec) * 1000)
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(
                    f"Cannot decode grid frame at {sec:.3f}s; no placeholder emitted"
                )
            measured = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            h, w = frame.shape[:2]
            scale = min(480 / w, 300 / h)
            resized = cv2.resize(frame, (max(1, round(w * scale)), max(1, round(h * scale))))
            tile = np.zeros((330, 480, 3), np.uint8)
            rh, rw = resized.shape[:2]
            tile[(300 - rh) // 2 : (300 - rh) // 2 + rh, (480 - rw) // 2 : (480 - rw) // 2 + rw] = (
                resized
            )
            cv2.putText(
                tile,
                f"{i + 1} | source ~{measured:.3f}s",
                (8, 320),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            tiles.append(tile)
            samples.append({"requested_seconds": float(sec), "decoder_seconds_approx": measured})
    finally:
        cap.release()
    grid = np.vstack([np.hstack(tiles[i : i + 3]) for i in range(0, 9, 3)])
    if not cv2.imwrite(str(output / "grid_3x3.jpg"), grid):
        raise RuntimeError("Grid could not be written")
    length = end - start
    # Input duration is bounded BEFORE setpts; never synthesize intermediate motion.
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-n",
            "-ss",
            str(start),
            "-t",
            str(length),
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            "setpts=6*(PTS-STARTPTS),fps=30,pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output / "slow_6x.mp4"),
        ],
        check=True,
    )
    slow = probe(output / "slow_6x.mp4")
    if abs(slow["duration"] - length * 6) > max(0.6, length * 0.06):
        raise RuntimeError("Slow video duration differs from expected 6x; inspect output")
    hashes = {}
    for path in [output / "grid_3x3.jpg", output / "slow_6x.mp4"]:
        with path.open("rb") as handle:
            hashes[path.name] = hashlib.file_digest(handle, "sha256").hexdigest()
    metadata = {
        "source": str(source),
        "source_size": source.stat().st_size,
        "source_mtime_ns": source.stat().st_mtime_ns,
        "start_seconds": start,
        "end_seconds": end,
        "source_duration": info["duration"],
        "speed": "1/6 (six times longer)",
        "slow_duration": slow["duration"],
        "grid_samples": samples,
        "human_review_required": True,
        "classification": "unconfirmed motion candidate; no floor attribution",
        "note": "Derived review media, no audio, repeated frames without AI interpolation; retain original",
        "sha256": hashes,
    }
    (output / "review.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    return metadata


def review_recent(
    recordings: Path,
    output: Path,
    discovered: datetime,
    hours: float,
    max_candidates: int,
    chunk_seconds: float = 300,
) -> dict:
    if discovered.tzinfo is not None:
        raise ValueError(
            "Use camera filename local time without timezone suffix; correct clock offsets first"
        )
    if not math.isfinite(hours) or hours <= 0 or max_candidates < 1:
        raise ValueError("hours and max-candidates must be positive")
    if not recordings.is_dir():
        raise ValueError("Recordings directory does not exist")
    begin = discovered - timedelta(hours=hours)
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "window_start": begin.isoformat(),
        "discovered_at": discovered.isoformat(),
        "hours": hours,
        "scanned": [],
        "skipped": [],
        "errors": [],
        "exports": [],
        "human_review_required": True,
        "method": "motion ranking only; absence of a candidate does not exclude an event or floor",
    }
    candidates, intervals = [], []

    def save():
        report["unreviewed_intervals"] = gaps(intervals, begin, discovered)
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))

    save()
    for source in sorted(recordings.rglob("*")):
        if source.suffix.lower() not in {".mkv", ".mp4", ".mov"} or not source.is_file():
            continue
        try:
            origin = recording_time(source)
            if origin >= discovered:
                continue
            before = source.stat()
            duration = probe(source)["duration"]
            window = overlap(origin, duration, begin, discovered)
            if window is None:
                continue
        except Exception as exc:
            report["skipped"].append({"source": str(source), "reason": str(exc)})
            save()
            continue
        lo, hi = window
        while lo < hi:
            end = min(hi, lo + chunk_seconds)
            scan = output / "scans" / f"{len(report['scanned']) + len(report['errors']):05d}"
            scan.parent.mkdir(exist_ok=True)
            try:
                # Bounded chunks keep the existing frame-review script's memory use limited.
                with (scan.parent / f"{scan.name}.log").open("w") as log:
                    subprocess.run(
                        [
                            sys.executable,
                            str(ROOT / "scripts/review_motion.py"),
                            str(source.resolve()),
                            str(scan),
                            "--start",
                            str(lo),
                            "--end",
                            str(end),
                            "--scale",
                            ".5",
                            "--top",
                            str(max_candidates),
                        ],
                        check=True,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
                after = source.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError("Recording changed during review; close segment and retry")
                data = json.loads((scan / "motion.json").read_text())
                if data["decoded_frames"] <= 0:
                    raise RuntimeError("No frames decoded in requested interval")
                decoded_end = min(end, data["last_decoded_seconds"] + 1 / data["fps"])
                if decoded_end < end - 0.1:
                    raise RuntimeError(
                        f"Incomplete decode: stopped at {decoded_end:.3f}s, expected {end:.3f}s"
                    )
                report["scanned"].append(
                    {
                        "source": str(source),
                        "start": lo,
                        "end": end,
                        "decoded_frames": data["decoded_frames"],
                    }
                )
                intervals.append((origin + timedelta(seconds=lo), origin + timedelta(seconds=end)))
                candidates.extend(
                    {
                        **c,
                        "source": str(source.resolve()),
                        "duration": duration,
                        "window_lo": window[0],
                        "window_hi": window[1],
                    }
                    for c in data["candidates"]
                )
            except Exception as exc:
                report["errors"].append(
                    {"source": str(source), "start": lo, "end": end, "reason": str(exc)}
                )
            lo = end
            save()
    selected = []
    for candidate in sorted(candidates, key=lambda c: c["score"], reverse=True):
        if any(
            c["source"] == candidate["source"] and abs(c["seconds"] - candidate["seconds"]) < 3
            for c in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= max_candidates:
            break
    for i, c in enumerate(selected):
        try:
            clip = export_candidate(
                Path(c["source"]),
                output / "candidates" / f"{i + 1:03d}",
                max(c["window_lo"], c["seconds"] - 1),
                min(c["window_hi"], c["seconds"] + 2),
            )
            report["exports"].append({"candidate": c, "review": clip})
        except Exception as exc:
            report["errors"].append({"candidate": c, "reason": str(exc)})
        save()
    report["candidate_count_before_limit"] = len(candidates)
    report["export_limit"] = max_candidates
    report["status"] = (
        "review_complete"
        if not report["errors"] and not report["unreviewed_intervals"]
        else "partial_review"
    )
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser(
        "export", help="Export one real-video interval as nine-grid and 6x slow video"
    )
    export.add_argument("source", type=Path)
    export.add_argument("output", type=Path)
    export.add_argument("--start", type=float, required=True)
    export.add_argument("--end", type=float, required=True)
    recent = sub.add_parser(
        "recent", help="Human-triggered retrospective review of closed recording segments"
    )
    recent.add_argument("recordings", type=Path)
    recent.add_argument("output", type=Path)
    recent.add_argument("--discovered-at", type=datetime.fromisoformat, required=True)
    recent.add_argument("--hours", type=float, default=3)
    recent.add_argument("--max-candidates", type=int, default=12)
    args = parser.parse_args()
    if args.command == "export":
        result = export_candidate(args.source, args.output, args.start, args.end)
    else:
        result = review_recent(
            args.recordings, args.output, args.discovered_at, args.hours, args.max_candidates
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") == "partial_review" else 0


if __name__ == "__main__":
    raise SystemExit(main())
