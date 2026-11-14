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
    response = api.post("/api/authenticate", json={"scenario": "schedule_violation", "simulated_hour": 12})
    assert response.status_code == 200
    assert pipeline.calls == [{"scenario": "schedule_violation"}]
    assert api.get("/health?offline=true").status_code == 200
    assert pipeline.calls == [{"scenario": "schedule_violation"}]
    assert api.post("/health?offline=true").status_code == 405
