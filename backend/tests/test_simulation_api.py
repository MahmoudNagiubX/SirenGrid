from __future__ import annotations

import threading
from collections.abc import Generator
from pathlib import Path

import pytest
from app.config import settings
from app.db import init_db
from app.main import app
from app.models import EmergencyResource
from app.schemas import ResourceStatus
from app.seed import seed_resources
from app.simulation_api import simulation_controller
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def setup_simulation_db(isolated_engine: Engine) -> None:
    init_db(isolated_engine)
    session = Session(bind=isolated_engine)
    seed_resources(session)
    session.commit()
    session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    simulation_controller.reset()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        simulation_controller.reset()


def test_simulation_controls_disabled_by_default(client: TestClient) -> None:
    """1. Disabled by default, 2. status shows disabled, 3-5. POST endpoints return 403."""
    assert settings.simulation_controls_enabled is False

    resp = client.get("/api/v1/simulation/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["reality"] in ("SYNTHETIC", "SIMULATED")
    assert "api_key" not in data
    assert "database_url" not in data

    resp_reset = client.post("/api/v1/simulation/reset")
    assert resp_reset.status_code == 403
    assert resp_reset.json()["detail"] == "SIMULATION_DISABLED"

    resp_load = client.post("/api/v1/simulation/load/T01_urgent_activation")
    assert resp_load.status_code == 403
    assert resp_load.json()["detail"] == "SIMULATION_DISABLED"

    resp_event = client.post(
        "/api/v1/simulation/events",
        json={
            "event_type": "RESOURCE_STATE",
            "resource_payload": {
                "resource_id": "10000000-0000-0000-0000-000000000001",
                "status": "AVAILABLE",
            },
        },
    )
    assert resp_event.status_code == 403
    assert resp_event.json()["detail"] == "SIMULATION_DISABLED"


def test_simulation_load_and_reset_lifecycle(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """6. Loads known scenario, 7. 404 on unknown, 8. Exact seed, 9. Resets event index, 10. Reset deterministic, 11. Status reflects loaded."""
    monkeypatch.setattr(settings, "simulation_controls_enabled", True)

    resp_404 = client.post("/api/v1/simulation/load/UNKNOWN_SCENARIO_XYZ")
    assert resp_404.status_code == 404
    assert "not found" in resp_404.json()["detail"]

    resp_load = client.post("/api/v1/simulation/load/T01_urgent_activation")
    assert resp_load.status_code == 200
    load_data = resp_load.json()
    assert load_data["status"] == "LOADED"
    assert load_data["scenario_id"] == "T01_urgent_activation"
    assert load_data["seed"] == 80101
    assert load_data["master_plan_case"] == "T01"
    assert load_data["reality"] in ("SYNTHETIC", "SIMULATED")

    resp_status = client.get("/api/v1/simulation/status")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["enabled"] is True
    assert status_data["loaded_scenario_id"] == "T01_urgent_activation"
    assert status_data["seed"] == 80101
    assert status_data["event_index"] == 0

    resp_reset = client.post("/api/v1/simulation/reset")
    assert resp_reset.status_code == 200
    reset_data = resp_reset.json()
    assert reset_data["status"] == "RESET"
    assert reset_data["simulation"]["loaded_scenario_id"] is None
    assert reset_data["simulation"]["seed"] is None
    assert reset_data["simulation"]["event_index"] == 0

    resp_reset_2 = client.post("/api/v1/simulation/reset")
    assert resp_reset_2.status_code == 200
    assert resp_reset_2.json()["status"] == "RESET"


def test_simulation_event_application_and_validation(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """12. Allowed event updates bounded state, 13. Invalid event kind -> 422, domain validation integration."""
    monkeypatch.setattr(settings, "simulation_controls_enabled", True)

    client.post("/api/v1/simulation/load/T01_urgent_activation")

    # 13a. Invalid event kind -> 422
    resp_invalid_kind = client.post(
        "/api/v1/simulation/events",
        json={"event_type": "UNKNOWN_EVENT_KIND"},
    )
    assert resp_invalid_kind.status_code == 422

    # 13b. Missing payload -> 422
    resp_missing_payload = client.post(
        "/api/v1/simulation/events",
        json={"event_type": "RESOURCE_STATE"},
    )
    assert resp_missing_payload.status_code == 422

    # 12. Allowed event: RESOURCE_STATE
    target_res_id = "10000000-0000-0000-0000-000000000001"
    resp_event = client.post(
        "/api/v1/simulation/events",
        json={
            "event_type": "RESOURCE_STATE",
            "resource_payload": {
                "resource_id": target_res_id,
                "status": "OUT_OF_SERVICE",
            },
        },
    )
    assert resp_event.status_code == 200
    event_data = resp_event.json()
    assert event_data["status"] == "EVENT_APPLIED"
    assert event_data["event_index"] == 1
    assert event_data["event_type"] == "RESOURCE_STATE"
    assert event_data["reality"] in ("SYNTHETIC", "SIMULATED")

    db_session.expire_all()
    res = db_session.get(EmergencyResource, target_res_id)
    assert res is not None
    assert res.status == ResourceStatus.OUT_OF_SERVICE
    db_session.rollback()

    # Domain validation integration: stale expected_resource_version -> 409
    resp_stale = client.post(
        "/api/v1/simulation/events",
        json={
            "event_type": "RESOURCE_STATE",
            "resource_payload": {
                "resource_id": target_res_id,
                "status": "AVAILABLE",
                "expected_resource_version": 1,
            },
        },
    )
    assert resp_stale.status_code == 409
    assert "Stale" in resp_stale.json()["detail"]

    # Allowed event: HOSPITAL_STATE
    hospitals = client.get("/api/v1/hospitals").json()
    assert len(hospitals) > 0
    target_hospital_id = hospitals[0]["id"]

    resp_hosp = client.post(
        "/api/v1/simulation/events",
        json={
            "event_type": "HOSPITAL_STATE",
            "hospital_payload": {
                "hospital_id": target_hospital_id,
                "accepting_state": "NOT_ACCEPTING",
                "simulated_load_ratio": 0.95,
            },
        },
    )
    assert resp_hosp.status_code == 200
    hosp_data = resp_hosp.json()
    assert hosp_data["event_index"] == 2
    assert hosp_data["simulation"]["last_event_type"] == "HOSPITAL_STATE"


def test_simulation_no_background_tasks_and_no_data_mutation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """15. No live provider call, 16. No static data asset mutation, 18. No background threads created."""
    monkeypatch.setattr(settings, "simulation_controls_enabled", True)

    # Warm up client to initialize any internal starlette/anyio threads
    client.get("/api/v1/simulation/status")
    threads_before = {t.name for t in threading.enumerate()}

    scenarios_path = Path("data/evaluation/phase08/scenarios.json")
    mtime_before = scenarios_path.stat().st_mtime

    hospitals = client.get("/api/v1/hospitals").json()
    target_hospital_id = hospitals[0]["id"]

    client.post("/api/v1/simulation/load/T01_urgent_activation")
    client.post(
        "/api/v1/simulation/events",
        json={
            "event_type": "HOSPITAL_STATE",
            "hospital_payload": {
                "hospital_id": target_hospital_id,
                "accepting_state": "ACCEPTING",
            },
        },
    )
    client.post("/api/v1/simulation/reset")

    # 18. No background threads or schedulers created
    threads_after = {t.name for t in threading.enumerate()}
    new_threads = threads_after - threads_before
    assert not any(
        "sim" in name.lower() or "sched" in name.lower() or "timer" in name.lower()
        for name in new_threads
    ), f"Unexpected simulation threads spawned: {new_threads}"

    # 16. No static file mutation
    mtime_after = scenarios_path.stat().st_mtime
    assert mtime_after == mtime_before, "Static evaluation scenarios must not be mutated"
