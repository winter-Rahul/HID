from types import SimpleNamespace
import numpy as np
from src.decision.decision_engine import DecisionEngine
from src.pipeline import KioskPipeline
from src.telemetry.logger import TelemetryLogger


def make_pipeline(scores, *, online=True, features=None):
    pipeline = KioskPipeline.__new__(KioskPipeline)
    frames = [np.full((4, 4, 3), i, dtype=np.uint8) for i in range(len(scores))]
    pipeline.burst_size = 8
    pipeline.camera = SimpleNamespace(get_burst=lambda n: list(enumerate(frames)), get_latest_frame=lambda: None)
    pipeline.detector = SimpleNamespace(detect=lambda frame: {"n_faces": 1, "laplacian_var": 100, "brightness": 100, "bbox": [0, 0, 100, 100], "raw_face": None})
    pipeline.pad = SimpleNamespace(predict_frame=lambda frame, bbox: {"score": scores[int(frame[0, 0, 0])]}, aggregate_burst=lambda rows: {"p_live": min(r["score"] for r in rows), "uncertainty": 0., "strong_attack_cue": False, "attack_reason": None, "moire_hits": 0})
    vectors = features or [np.array([1., 0.]) for _ in frames]
    pipeline.recognizer = SimpleNamespace(extract_feature=lambda frame, face: vectors[int(frame[0, 0, 0])], cosine_threshold_high=.45, match=lambda feat: {"name": "Alice", "matched": True, "score": .9, "margin": .9})
    pipeline.schedule_mgr = SimpleNamespace(check_access=lambda *args, **kwargs: {"allowed": True})
    pipeline.decision_engine = DecisionEngine()
    pipeline.offline_mgr = SimpleNamespace(is_online=lambda: online, queue_offline_decision=lambda *args: None)
    pipeline.telemetry = SimpleNamespace(record_decision=lambda *args: None)
    return pipeline


def test_one_frame_cannot_allow():
    result = make_pipeline([.95]).process_burst()
    assert result["reason_code"] == "INCONSISTENT_BURST"
    assert result["decision"] == "STEP_UP_VERIFICATION"


def test_multiple_people_are_not_matched():
    pipeline = make_pipeline([.95] * 3)
    original_detect = pipeline.detector.detect
    pipeline.detector.detect = lambda frame: {**original_detect(frame), "n_faces": 2}
    def fail_if_called(*args):
        raise AssertionError("Identity matching must not run with multiple people")
    pipeline.recognizer.extract_feature = fail_if_called
    result = pipeline.process_burst()
    assert result["reason_code"] == "MULTIPLE_FACES"
    assert "clear the background" in result["message"].lower()


def test_identity_change_cannot_allow():
    vectors = [np.array([1., 0.]), np.array([1., 0.]), np.array([0., 1.])]
    assert make_pipeline([.95] * 3, features=vectors).process_burst()["reason_code"] == "INCONSISTENT_BURST"


def test_consistent_probe_matches_normalized_mean():
    vectors = [np.array([1., 0.]), np.array([.8, .6]), np.array([.8, .6])]
    pipeline = make_pipeline([.95] * 3, features=vectors)
    seen = []
    pipeline.recognizer.match = lambda feat: (seen.append(feat.copy()) or {"name": "Alice", "matched": True, "score": .9, "margin": .9})
    assert pipeline.process_burst()["decision"] == "ALLOW"
    expected = np.mean(vectors, axis=0)
    np.testing.assert_allclose(seen[0], expected / np.linalg.norm(expected), rtol=1e-6)


def test_blurry_frame_does_not_contaminate_probe():
    vectors = [np.array([1., 0.]), np.array([1., 0.]), np.array([1., 0.]), np.array([.5, np.sqrt(.75)])]
    pipeline = make_pipeline([.95] * 4, features=vectors)
    pipeline.detector.detect = lambda frame: {"n_faces": 1, "laplacian_var": 5 if frame[0, 0, 0] == 3 else 100, "brightness": 100, "bbox": [0, 0, 100, 100], "raw_face": None}
    seen = []
    pipeline.recognizer.match = lambda feat: (seen.append(feat.copy()) or {"name": "Alice", "matched": True, "score": .9, "margin": .9})
    assert pipeline.process_burst()["decision"] == "ALLOW"
    np.testing.assert_allclose(seen[0], [1., 0.])


def test_slow_spoof_stays_denied(monkeypatch):
    import src.pipeline as pipeline_module
    times = iter(range(100))
    monkeypatch.setattr(pipeline_module.time, "monotonic", lambda: next(times))
    result = make_pipeline([.1] * 3).process_burst()
    assert result["reason_code"] == "SPOOF_DETECTED"
    assert result["decision"] == "DENY"


def test_offline_high_score_and_emergency_cannot_allow():
    result = make_pipeline([.95] * 3, online=False).process_burst()
    assert result["reason_code"] == "OFFLINE_VERIFICATION_REQUIRED"
    evidence = {"n_faces": 1, "bbox": [0, 0, 100, 100], "p_live": .95, "id_matched": True,
                "id_name": "Alice", "id_score": .99, "online_mode": False,
                "schedule_check": {"allowed": True, "emergency_override": True}}
    assert DecisionEngine().decide(evidence)["decision"] != "ALLOW"


def test_telemetry_unknown_does_not_pollute_genuine(tmp_path):
    logger = TelemetryLogger(str(tmp_path / "metrics.json"))
    logger.record_decision("schedule_violation", "DENY", 10, {})
    logger.record_decision("unknown-label", "DENY", 10, {})
    assert logger.scenarios["genuine_live"]["presentations"] == 0
    assert logger.scenarios["schedule_violation"]["presentations"] == 1
    assert logger.scenarios["other"]["presentations"] == 1
