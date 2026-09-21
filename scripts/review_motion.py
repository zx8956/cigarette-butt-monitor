"""Read real video frames and produce motion-review candidates, not object labels."""

import argparse
from collections import Counter
import json
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--start", type=float, default=0)
    p.add_argument("--end", type=float)
    p.add_argument("--top", type=int, default=80)
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--transient", action="store_true")
    p.add_argument("--sequence-only", action="store_true")
    p.add_argument("--crop", default="650,1200,430,600")
    p.add_argument("--rerank-json", type=Path)
    p.add_argument("--exclude", help="Review-only exclusion interval in source seconds: start,end")
    args = p.parse_args()
    if not 0 < args.scale <= 1 or args.top < 1:
        p.error("scale must be in (0, 1], top must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError("Cannot open real video")
    fps = cap.get(cv2.CAP_PROP_FPS)
    origin = datetime.strptime(args.video.stem, "%Y-%m-%d %H-%M-%S")
    cap.set(cv2.CAP_PROP_POS_MSEC, args.start * 1000)
    if args.sequence_only:
        tiles = []
        for i in range(12):
            ok, frame = cap.read()
            if not ok:
                break
            sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            stamp = (origin + timedelta(seconds=sec)).strftime("%H:%M:%S.%f")[:-3]
            cv2.imwrite(str(args.output / f"frame_{i:02d}.png"), frame)
            x, y, w, h = [int(v) for v in args.crop.split(",")]
            crop = frame[y : y + h, x : x + w].copy()
            cv2.putText(crop, stamp, (5, 25), 0, 0.65, (0, 0, 255), 2)
            tiles.append(crop)
        cap.release()
        if len(tiles) == 12:
            cv2.imwrite(
                str(args.output / "sequence.jpg"),
                np.vstack([np.hstack(tiles[i : i + 4]) for i in range(0, 12, 4)]),
            )
        return
    prev = None
    prevprev = None
    candidates = {}
    rows = []
    sampled = []
    last_second = -1
    n = 0
    if args.rerank_json:
        prior = json.loads(args.rerank_json.read_text())
        rows = prior["frames"]
        n = prior["decoded_frames"]
        frequencies = Counter(
            (int((x + w / 2) // 32), int((y + h / 2) // 32))
            for row in rows
            for x, y, w, h, area in row["components"]
        )
        rare = {}
        for row in rows:
            if args.exclude:
                low, high = map(float, args.exclude.split(","))
                if low <= row["seconds"] <= high:
                    continue
            if row["changed_pixels"] > 25000:
                continue
            boxes = [
                box
                for box in row["components"]
                if box[4] >= 8
                and frequencies[
                    (int((box[0] + box[2] / 2) // 32), int((box[1] + box[3] / 2) // 32))
                ]
                <= 30
            ]
            if boxes:
                bucket = int(row["seconds"] * 2)
                score = max(b[4] for b in boxes)
                if bucket not in rare or score > rare[bucket][0]:
                    rare[bucket] = (score, row["seconds"], boxes)
        for score, sec, boxes in sorted(rare.values(), reverse=True)[: args.top]:
            cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
            ok, frame = cap.read()
            if ok:
                candidates[int(sec * 2)] = (score, sec, boxes, frame)
    while not args.rerank_json:
        ok, frame = cap.read()
        if not ok:
            break
        sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if args.end is not None and sec >= args.end:
            break
        stamp = (origin + timedelta(seconds=sec)).strftime("%H:%M:%S.%f")[:-3]
        analysis_frame = (
            cv2.resize(frame, None, fx=args.scale, fy=args.scale) if args.scale != 1 else frame
        )
        gray = cv2.cvtColor(analysis_frame, cv2.COLOR_BGR2GRAY)
        if int(sec) != last_second:
            thumb = cv2.resize(frame, (216, 384))
            cv2.putText(thumb, stamp, (4, 20), 0, 0.48, (0, 0, 255), 1)
            sampled.append(thumb)
            last_second = int(sec)
        if prev is not None:
            diff = cv2.absdiff(gray, prev)
            mask = (diff > 22).astype(np.uint8)
            if args.transient and prevprev is not None:
                edges = cv2.Canny(prevprev, 60, 140)
                edges = cv2.dilate(edges, np.ones((5, 5), np.uint8))
                mask = ((diff > 12) & (cv2.absdiff(gray, prevprev) > 12) & (edges == 0)).astype(
                    np.uint8
                )
            count, labels, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
            components = []
            for x, y, w, h, area in stats[1:]:
                if (
                    3 <= area <= 3000 * args.scale**2
                    and w < 160 * args.scale
                    and h < 160 * args.scale
                ):
                    components.append(
                        [
                            round(x / args.scale),
                            round(y / args.scale),
                            round(w / args.scale),
                            round(h / args.scale),
                            round(area / args.scale**2),
                        ]
                    )
            if components:
                components.sort(key=lambda b: b[4], reverse=True)
                score = components[0][4]
                bucket = int(sec * 2)
                if bucket not in candidates or score > candidates[bucket][0]:
                    candidates[bucket] = (score, sec, components[:12], frame.copy())
                    if len(candidates) > args.top:
                        worst = min(candidates, key=lambda key: candidates[key][0])
                        del candidates[worst]
            rows.append(
                {
                    "seconds": sec,
                    "time_approx": stamp,
                    "changed_pixels": int(mask.sum()),
                    "components": components[:12],
                }
            )
        prevprev, prev = prev, gray
        n += 1
        if n % 900 == 0:
            print(f"decoded={n} time={stamp}", flush=True)
    cap.release()
    for offset in range(0, len(sampled), 20):
        batch = sampled[offset : offset + 20]
        batch += [np.zeros_like(sampled[0])] * (20 - len(batch))
        sheet = np.vstack([np.hstack(batch[i : i + 5]) for i in range(0, 20, 5)])
        cv2.imwrite(str(args.output / f"overview_{offset:03d}.jpg"), sheet)
    top = sorted(candidates.values(), key=lambda r: r[0], reverse=True)[: args.top]
    thumbs = []
    summary = []
    for i, (score, sec, boxes, frame) in enumerate(top):
        x, y, w, h, _ = boxes[0]
        cx, cy = x + w // 2, y + h // 2
        left, up = (
            max(0, min(cx - 120, frame.shape[1] - 240)),
            max(0, min(cy - 120, frame.shape[0] - 240)),
        )
        crop = frame[up : up + 240, left : left + 240].copy()
        cv2.rectangle(crop, (x - left, y - up), (x + w - left, y + h - up), (0, 0, 255), 1)
        stamp = (origin + timedelta(seconds=sec)).strftime("%H:%M:%S.%f")[:-3]
        cv2.putText(crop, f"{i} {stamp}", (2, 18), 0, 0.43, (0, 0, 255), 1)
        thumbs.append(crop)
        cv2.imwrite(str(args.output / f"candidate_{i:03d}.jpg"), frame)
        summary.append(
            {"index": i, "seconds": sec, "time_approx": stamp, "score": score, "boxes": boxes}
        )
    for offset in range(0, len(thumbs), 20):
        batch = thumbs[offset : offset + 20]
        batch += [np.zeros((240, 240, 3), np.uint8)] * (20 - len(batch))
        cv2.imwrite(
            str(args.output / f"motion_{offset:03d}.jpg"),
            np.vstack([np.hstack(batch[i : i + 5]) for i in range(0, 20, 5)]),
        )
    (args.output / "motion.json").write_text(
        json.dumps(
            {
                "source": str(args.video),
                "decoded_frames": n,
                "fps": fps,
                "start_seconds": args.start,
                "spatial_scale": args.scale,
                "reranked_from": str(args.rerank_json) if args.rerank_json else None,
                "method": "adjacent-frame absolute difference; NOT cigarette classification",
                "transient_edge_suppression": args.transient,
                "excluded_review_interval": args.exclude,
                "time_note": "Approximate wall time from filename plus media PTS",
                "candidates": summary,
                "frames": rows,
            },
            indent=2,
        )
    )
    print(json.dumps({"frames": n, "candidates": len(summary), "output": str(args.output)}))


if __name__ == "__main__":
    main()
