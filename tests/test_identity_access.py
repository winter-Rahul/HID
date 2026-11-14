import numpy as np
from src.decision.decision_engine import DecisionEngine
from src.detector.face_detector import FaceDetector


def evidence(**changes):
    result = {"n_faces": 1, "bbox": [0, 0, 100, 100], "laplacian_var": 100.,
              "brightness": 120., "p_live": .95, "uncertainty": .01,
              "id_matched": True, "id_name": "Alice", "id_score": .9,
              "schedule_check": {"allowed": True}, "online_mode": True}
    result.update(changes)
    return result


def test_unknown_and_borderline_identities_are_denied():
    engine = DecisionEngine()
    for sample in (evidence(id_name=None, id_matched=False),
                   evidence(id_name="Alice", id_matched=False, id_score=.4),
                   evidence(id_name=None, id_matched=False, p_live=.6)):
        result = engine.decide(sample)
        assert result["decision"] == "DENY"
        assert result["reason_code"] == "IDENTITY_NOT_RECOGNIZED"


def test_multiple_people_are_asked_to_clear_background():
    result = DecisionEngine().decide(evidence(n_faces=2))
    assert result["decision"] != "ALLOW"
    assert "clear the background" in result["message"].lower()


def test_smaller_background_face_counts_as_second_person():
    primary = np.array([10, 10, 120, 120] + [0] * 10 + [.99], dtype=np.float32)
    background = np.array([160, 30, 40, 40] + [0] * 10 + [.99], dtype=np.float32)
    class Detector:
        def detect(self, frame):
            return None, np.array([primary, background])
    detector = FaceDetector.__new__(FaceDetector)
    detector.detector = Detector()
    detector.input_size = (240, 180)
    detector.score_threshold = .7
    result = detector.detect(np.zeros((180, 240, 3), dtype=np.uint8))
    assert result["n_faces"] == 2
