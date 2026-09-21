"""Rank real motion components by displacement, for manual review only."""

import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta

import cv2
import numpy as np


def center(box):
    x, y, w, h, _ = box
    return np.array([x + w / 2, y + h / 2])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("motion", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.motion.read_text())
    tracks, active = [], []
    for row in data["frames"]:
        sec = row["seconds"]
        expired = [t for t in active if sec - t[-1][0] > 0.24]
        tracks.extend(expired)
        active = [t for t in active if sec - t[-1][0] <= 0.24]
        if row["changed_pixels"] / data.get("spatial_scale", 1) ** 2 > 20000:
            continue
        boxes = [b for b in row["components"] if 8 <= b[4] <= 2000]
        used = set()
        for box in sorted(boxes, key=lambda b: b[4], reverse=True):
            point = center(box)
            options = []
            for i, track in enumerate(active):
                if i in used:
                    continue
                dt = sec - track[-1][0]
                if dt <= 0:
                    continue
                last = center(track[-1][1])
                distance = np.linalg.norm(point - last)
                if distance > 35 + dt * 1000:
                    continue
                if len(track) >= 2:
                    prev_dt = track[-1][0] - track[-2][0]
                    velocity = (last - center(track[-2][1])) / max(prev_dt, 0.033)
                    predicted = last + velocity * dt
                    distance = 0.4 * distance + 0.6 * np.linalg.norm(point - predicted)
                options.append((float(distance), i))
            if options:
                _, i = min(options)
                active[i].append((sec, box))
                used.add(i)
            else:
                active.append([(sec, box)])
                used.add(len(active) - 1)
    tracks.extend(active)
    ranked = []
    for track in tracks:
        if len(track) < 3:
            continue
        points = np.array([center(b) for _, b in track])
        dy = points[-1, 1] - points[0, 1]
        duration = track[-1][0] - track[0][0]
        if dy < 70 or duration > 6:
            continue
        span = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
        ranked.append((float(dy + span / 4), track))
    selected, times = [], []
    for score, track in sorted(ranked, key=lambda item: item[0], reverse=True):
        t = track[0][0]
        if any(abs(t - other) < 1.2 for other in times):
            continue
        selected.append((score, track))
        times.append(t)
        if len(selected) >= 40:
            break
    args.output.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(data["source"])
    origin = datetime.strptime(Path(data["source"]).stem, "%Y-%m-%d %H-%M-%S")
    rows, summary = [], []
    for index, (score, track) in enumerate(selected):
        tiles = []
        picks = np.linspace(0, len(track) - 1, 6).round().astype(int)
        for pick in picks:
            sec, box = track[pick]
            cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
            ok, frame = cap.read()
            if not ok:
                tiles.append(np.zeros((180, 180, 3), np.uint8))
                continue
            x, y = center(box)
            left = max(0, min(round(x) - 90, frame.shape[1] - 180))
            top = max(0, min(round(y) - 90, frame.shape[0] - 180))
            crop = frame[top : top + 180, left : left + 180].copy()
            stamp = (origin + timedelta(seconds=sec)).strftime("%H:%M:%S.%f")[:-3]
            cv2.putText(crop, f"{index} {stamp}", (2, 14), 0, 0.35, (0, 0, 255), 1)
            tiles.append(crop)
        rows.append(np.hstack(tiles))
        summary.append(
            {
                "index": index,
                "score": score,
                "start": track[0][0],
                "end": track[-1][0],
                "points": track,
                "time_approx": (origin + timedelta(seconds=track[0][0])).isoformat(),
            }
        )
    cap.release()
    for start in range(0, len(rows), 6):
        cv2.imwrite(str(args.output / f"paths_{start:03d}.jpg"), np.vstack(rows[start : start + 6]))
    (args.output / "paths.json").write_text(
        json.dumps(
            {
                "source": data["source"],
                "method": "heuristic association, not validated object tracks or labels",
                "candidates": summary,
            },
            indent=2,
        )
    )
    print(args.output, len(summary))


if __name__ == "__main__":
    main()
