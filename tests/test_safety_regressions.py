from src.context.schedule import ScheduleManager
from src.decision.decision_engine import DecisionEngine
from src.offline.fail_safe import OfflineFailSafe


def test_missing_schedule_never_grants_access(tmp_path):
    manager = ScheduleManager(str(tmp_path / "schedules.json"))
    assert not manager.check_access("Unknown", simulated_hour=12, simulated_day="Mon")["allowed"]
    evidence = {"n_faces": 1, "bbox": [0, 0, 100, 100], "p_live": .9,
                "id_matched": True, "id_name": "Unknown", "id_score": .9}
    assert DecisionEngine().decide(evidence)["decision"] == "DENY"


def test_overnight_shift_uses_start_day(tmp_path):
    manager = ScheduleManager(str(tmp_path / "schedules.json"))
    manager.set_user_schedule("Night", 22, 4, ["Fri"])
    assert manager.check_access("Night", simulated_hour=2, simulated_day="Sat")["allowed"]
    assert not manager.check_access("Night", simulated_hour=2, simulated_day="Fri")["allowed"]


def test_offline_events_remain_pending_without_server(tmp_path):
    manager = OfflineFailSafe(str(tmp_path / "queue.json"))
    manager.set_online_status(False)
    manager.queue_offline_decision("DENY", None, "NO_FACE", 12)
    manager.set_online_status(True)
    assert manager.get_queue_status()["pending_sync_count"] == 1
    assert OfflineFailSafe(str(tmp_path / "queue.json")).get_queue_status()["pending_sync_count"] == 1


def test_nonfinite_measurements_cannot_grant_access():
    evidence = {"n_faces": 1, "bbox": [0, 0, 100, 100], "p_live": float("nan"),
                "id_matched": True, "id_name": "Alice", "id_score": .9,
                "schedule_check": {"allowed": True}}
    assert not DecisionEngine().decide(evidence)["allow"]
