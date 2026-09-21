from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class TrackSummary:
    track_id: int
    first_seen_seconds: float
    last_seen_seconds: float
    max_confidence: float
    observed_frames: int = 1
    trail: list[tuple[int, int]] = field(default_factory=list)
    smoking_or_cigarette_detected: bool = False

    @property
    def dwell_seconds(self) -> float:
        return max(0.0, self.last_seen_seconds - self.first_seen_seconds)

    def update(self, timestamp: float, confidence: float, center: tuple[int, int]) -> None:
        self.last_seen_seconds = timestamp
        self.max_confidence = max(self.max_confidence, confidence)
        self.observed_frames += 1
        self.trail.append(center)
        self.trail = self.trail[-50:]

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["dwell_seconds"] = self.dwell_seconds
        return result
