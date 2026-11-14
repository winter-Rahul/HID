import importlib
import sys
import types

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    class FakePipeline:
        def __init__(self):
            self.calls = []
            self.offline_mgr = types.SimpleNamespace(
                get_queue_status=lambda: {"online_mode": True},
                is_online=lambda: True,
                set_online_status=lambda value: self.calls.append(("online", value)),
            )
            self.recognizer = types.SimpleNamespace(list_users=lambda: ["Alice"])
            self.schedule_mgr = types.SimpleNamespace(schedules={})

        def process_burst(self, **kwargs):
            self.calls.append(kwargs)
            return {"decision": "DENY"}

    module = types.ModuleType("src.pipeline")
    module.KioskPipeline = FakePipeline
    monkeypatch.setitem(sys.modules, "src.pipeline", module)
    monkeypatch.delitem(sys.modules, "src.server", raising=False)
    server = importlib.import_module("src.server")
    yield TestClient(server.app), server.pipeline
    sys.modules.pop("src.server", None)


def test_management_requires_configured_credential(client, monkeypatch):
    api, _ = client
    monkeypatch.delenv("HID_ADMIN_TOKEN", raising=False)
    assert api.get("/api/users").status_code == 503
    monkeypatch.setenv("HID_ADMIN_TOKEN", "test-secret")
    assert api.get("/api/users").status_code == 401
    assert api.get("/api/users", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert api.get("/api/users", headers={"X-Admin-Token": "test-secret"}).json()["users"] == ["Alice"]


def test_client_cannot_override_authentication_time_or_health(client, monkeypatch):
    api, pipeline = client
    monkeypatch.setenv("HID_ADMIN_TOKEN", "secret")
    response = api.post("/api/authenticate", json={"scenario": "genuine_live", "simulated_hour": 12}, headers={"X-Admin-Token": "secret"})
    assert response.status_code == 200
    assert pipeline.calls == [{"scenario": "genuine_live"}]
    assert api.get("/health?offline=true").status_code == 200
    assert pipeline.calls == [{"scenario": "genuine_live"}]
    assert api.post("/health?offline=true").status_code == 405


def test_demo_clock_requires_admin(client, monkeypatch):
    api, pipeline = client
    monkeypatch.setenv("HID_ADMIN_TOKEN", "secret")
    assert api.post("/api/authenticate", json={"scenario": "schedule_violation"}).status_code == 401
    response = api.post("/api/authenticate", json={"scenario": "schedule_violation"}, headers={"X-Admin-Token": "secret"})
    assert response.status_code == 200
    assert pipeline.calls[-1]["simulated_hour"] == 3


def test_normal_scan_needs_no_admin_token(client, monkeypatch):
    api, _ = client
    monkeypatch.delenv("HID_ADMIN_TOKEN", raising=False)
    assert api.post("/api/authenticate", json={"scenario": "genuine_live"}).status_code == 200
    assert api.post("/api/authenticate", json={"scenario": "printed_photo"}).status_code == 503


def test_enrollment_schedule_is_selected_by_admin(client, monkeypatch):
    api, pipeline = client
    monkeypatch.setenv("HID_ADMIN_TOKEN", "secret")
    captured = []
    pipeline.enroll_user = lambda *args: (captured.append(args) or {"success": True})
    response = api.post("/api/enroll", data={"name": "Alice", "start_hour": "8", "end_hour": "18", "days": "Mon,Tue,Wed,Thu,Fri"}, headers={"X-Admin-Token": "secret"})
    assert response.status_code == 200
    assert captured == [("Alice", 8, 18, ["Mon", "Tue", "Wed", "Thu", "Fri"])]
    assert api.post("/api/enroll", data={"name": "Alice", "start_hour": "25"}, headers={"X-Admin-Token": "secret"}).status_code == 400


def test_admin_can_provision_pin_for_existing_user(client, monkeypatch, tmp_path):
    from src.step_up import StepUp
    api, _ = client
    import src.server as server
    verifier = StepUp(str(tmp_path / "pins.json"))
    monkeypatch.setattr(server, "step_up", verifier)
    monkeypatch.setenv("HID_ADMIN_TOKEN", "secret")
    assert api.post("/api/users/Alice/pin", data={"pin": "314159"}).status_code == 401
    assert api.post("/api/users/Alice/pin", data={"pin": "314159"}, headers={"X-Admin-Token": "secret"}).status_code == 200
    assert verifier.verify(verifier.issue("Alice"), "314159") == "Alice"
    assert api.post("/api/users/Unknown/pin", data={"pin": "314159"}, headers={"X-Admin-Token": "secret"}).status_code == 404


def test_step_up_rechecks_schedule_and_is_single_use(client, monkeypatch, tmp_path):
    from src.step_up import StepUp
    api, pipeline = client
    import src.server as server
    verifier = StepUp(str(tmp_path / "pins.json"))
    verifier.set_pin("Alice", "314159")
    monkeypatch.setattr(server, "step_up", verifier)
    pipeline.schedule_mgr.check_access = lambda name: {"allowed": True}
    pipeline.process_burst = lambda **kwargs: {"decision": "STEP_UP_VERIFICATION", "reason_code": "OFFLINE_VERIFICATION_REQUIRED", "matched_user": "Alice", "schedule_allowed": True}
    response = api.post("/api/authenticate", json={"scenario": "genuine_live"})
    token = response.json()["step_up_challenge"]
    assert api.post("/api/step-up", json={"challenge": token, "pin": "314159"}).json()["decision"] == "ALLOW"
    assert api.post("/api/step-up", json={"challenge": token, "pin": "314159"}).json()["decision"] == "DENY"
    token = api.post("/api/authenticate", json={"scenario": "genuine_live"}).json()["step_up_challenge"]
    pipeline.schedule_mgr.check_access = lambda name: {"allowed": False}
    assert api.post("/api/step-up", json={"challenge": token, "pin": "314159"}).json()["decision"] == "DENY"
