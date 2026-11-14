from src.step_up import StepUp
from src.offline.fail_safe import OfflineFailSafe


def test_pin_hash_challenge_and_single_use(tmp_path):
    path = tmp_path / "pins.json"
    verifier = StepUp(str(path))
    verifier.set_pin("Alice", "314159")
    assert "314159" not in path.read_text()
    token = verifier.issue("Alice")
    assert verifier.verify(token, "314159") == "Alice"
    assert verifier.verify(token, "314159") is None


def test_wrong_pin_locks_identity(tmp_path):
    verifier = StepUp(str(tmp_path / "pins.json"))
    verifier.set_pin("Alice", "314159")
    for _ in range(3):
        token = verifier.issue("Alice")
        assert verifier.verify(token, "000000") is None
    assert verifier.issue("Alice") is None


def test_audit_pseudonyms_are_stable_and_keyed(tmp_path):
    manager = OfflineFailSafe(str(tmp_path / "queue.json"))
    first = manager.hash_identity("Alice")
    assert first == OfflineFailSafe(str(tmp_path / "queue.json")).hash_identity("Alice")
    assert first != manager.hash_identity("Bob")
    assert first != "REDACTED"


def test_trial_report_uses_recorded_values():
    from eval.collect_trials import report
    text = report([
        {"scenario": "printed_photo", "decision": "DENY", "latency_ms": 100},
        {"scenario": "printed_photo", "decision": "ALLOW", "latency_ms": 200},
    ])
    assert "| printed_photo | 2 | 1 | 0 | 1 | 150.0 | 195.0 |" in text
    assert "not PAD-only APCER" in text
