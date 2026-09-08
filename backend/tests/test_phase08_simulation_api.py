from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.models as _models  # noqa: F401
from app.db import init_db
from app.main import app
from app.config import settings
from app.models import EmergencyResource, Incident, TimelineEvent
from sqlalchemy import select


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_simulation_controls_are_disabled_by_default(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "simulation_controls_enabled", False)

    response = client.get("/api/v1/simulation/status")

    assert response.status_code == 403
    assert "SIMULATION_CONTROLS_DISABLED" in response.json()["detail"]


def test_simulation_load_event_and_reset_are_gated_and_deterministic(
    client,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "simulation_controls_enabled", True)

    loaded = client.post("/api/v1/simulation/load/T01_urgent_activation")
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["mode"] == "SIMULATED"
    assert body["scope"] == "DEMO_ONLY"
    assert body["incident"]["id"] == "simulation-T01_urgent_activation"
    assert body["incident"]["status"] == "ACTIVE_UNCONFIRMED"
    assert len(body["resource_ids"]) > 0

    status = client.get("/api/v1/simulation/status")
    assert status.status_code == 200
    assert status.json()["scenario_id"] == "T01_urgent_activation"
    assert status.json()["scheduler"] == "NONE"

    # T01 has no events; loading a scenario with a deterministic event checks
    # manifest-order application and explicit second-incident creation.
    loaded_events = client.post("/api/v1/simulation/load/T15_competing_incident")
    assert loaded_events.status_code == 200
    event = client.post("/api/v1/simulation/events", json={"next": True})
    assert event.status_code == 200
    assert event.json()["event_type"] == "SECOND_INCIDENT"
    assert event.json()["created_incident_id"] == (
        "simulation-T15_competing_incident-event-0"
    )

    db_session.expire_all()
    assert db_session.scalar(
        select(Incident).where(
            Incident.id == "simulation-T15_competing_incident-event-0"
        )
    ) is not None
    assert db_session.scalar(select(EmergencyResource)) is not None
    assert db_session.scalar(select(TimelineEvent)) is not None

    reset = client.post("/api/v1/simulation/reset")
    assert reset.status_code == 200
    assert reset.json()["status"] == "RESET"
    db_session.expire_all()
    assert db_session.scalar(select(Incident)) is None
    assert db_session.scalar(select(EmergencyResource)) is None
