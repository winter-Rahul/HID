import numpy as np
import pytest
from src.pad.liveness_detector import LivenessDetector


def test_demo_preprocessing_and_live_class():
    class Session:
        def run(self, outputs, feeds):
            assert feeds["input"].max() == 255
            return [np.array([[0., 5., 0.]], dtype=np.float32)]
    class Texture:
        def analyze(self, crop):
            return {"texture_live_score": .9, "moire_detected": False, "glare_detected": False, "peak_ratio": 1}
    detector = LivenessDetector.__new__(LivenessDetector)
    detector.session, detector.input_name, detector.texture_analyzer = Session(), "input", Texture()
    result = detector.predict_frame(np.full((100, 100, 3), 255, dtype=np.uint8), [20, 20, 50, 50])
    assert result["p_live_deep"] > .98


@pytest.mark.parametrize("logits", [
    np.array([[float('nan'), 0., 0.]], dtype=np.float32),
    np.array([[float('inf'), 0., 0.]], dtype=np.float32),
    np.array([[0., 1.]], dtype=np.float32),
])
def test_invalid_model_outputs_fail_closed(logits):
    class Session:
        def run(self, outputs, feeds):
            return [logits]
    detector = LivenessDetector.__new__(LivenessDetector)
    detector.session, detector.input_name = Session(), "input"
    with pytest.raises(ValueError, match="invalid logits"):
        detector.predict_frame(np.full((100, 100, 3), 128, dtype=np.uint8), [20, 20, 50, 50])


def test_real_model_is_executable():
    detector = LivenessDetector()
    frame = np.full((100, 100, 3), 128, dtype=np.uint8)
    result = detector.predict_frame(frame, [20, 20, 50, 50])
    assert np.isfinite(result["p_live_deep"])
    assert 0.0 <= result["p_live_deep"] <= 1.0


def test_class_two_is_not_used_as_live_score():
    class Session:
        def run(self, outputs, feeds):
            return [np.array([[0., 0., 8.]], dtype=np.float32)]
    class Texture:
        def analyze(self, crop):
            return {"texture_live_score": .9, "moire_detected": False, "glare_detected": False, "peak_ratio": 1}
    detector = LivenessDetector.__new__(LivenessDetector)
    detector.session, detector.input_name, detector.texture_analyzer = Session(), "input", Texture()
    result = detector.predict_frame(np.full((100, 100, 3), 128, dtype=np.uint8), [20, 20, 50, 50])
    assert result["p_live_deep"] < .01
