from types import SimpleNamespace

from app.detection.cigarette import EVENT_CANDIDATE_LABELS, detections_from_result


class _Scalar:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value


class _Coordinates:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, _index):
        return self

    def tolist(self):
        return self.values


def test_ultralytics_result_is_converted_to_explainable_detection():
    box = SimpleNamespace(
        cls=_Scalar(0),
        conf=_Scalar(0.81234),
        xyxy=_Coordinates([10.123, 20.456, 30.789, 40.987]),
    )
    detections = detections_from_result(SimpleNamespace(boxes=[box]), {0: "cigarette butt"})

    assert detections == [
        {
            "class_id": 0,
            "label": "cigarette butt",
            "confidence": 0.81234,
            "box_xyxy": [10.12, 20.46, 30.79, 40.99],
        }
    ]


def test_empty_model_result_is_not_turned_into_a_fake_detection():
    assert detections_from_result(SimpleNamespace(boxes=None), {}) == []


def test_person_is_context_not_a_cigarette_event():
    assert "person" not in EVENT_CANDIDATE_LABELS
    assert "cigarette butt" in EVENT_CANDIDATE_LABELS
