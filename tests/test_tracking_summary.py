from app.tracking.summary import TrackSummary


def test_track_summary_keeps_time_confidence_and_trail():
    track = TrackSummary(3, 1.0, 1.0, 0.4, trail=[(1, 1)])
    track.update(4.5, 0.8, (2, 3))
    result = track.to_dict()
    assert result["dwell_seconds"] == 3.5
    assert result["max_confidence"] == 0.8
    assert result["observed_frames"] == 2
    assert result["smoking_or_cigarette_detected"] is False

