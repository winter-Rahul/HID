import numpy as np
from src.detector.face_detector import framing_issue


def face():
    return np.array([100, 60, 100, 120, 125, 100, 175, 100, 150, 125, 130, 150, 170, 150, .99])


def test_centered_frontal_face_is_accepted():
    assert framing_issue({"raw_face": face()}, (240, 320, 3)) is None


def test_partial_or_turned_face_gets_guidance():
    partial = face()
    partial[0] = -1
    assert "whole face" in framing_issue({"raw_face": partial}, (240, 320, 3))
    turned = face()
    turned[8] = 126
    assert "Turn toward" in framing_issue({"raw_face": turned}, (240, 320, 3))


def test_missing_landmarks_do_not_pass():
    assert framing_issue({"raw_face": None}, (240, 320, 3)) is not None
