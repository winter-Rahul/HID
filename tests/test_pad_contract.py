import numpy as np
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
