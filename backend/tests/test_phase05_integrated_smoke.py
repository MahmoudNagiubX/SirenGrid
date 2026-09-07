from __future__ import annotations

from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.db import init_db
from app.main import app
from app.seed import seed_resources


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_phase05_integrated_one_worker_smoke(client: TestClient, db_session: Session) -> None:
    """Exercise the real asset-backed Phase 05 path without external integrations."""
    seeded = seed_resources(db_session)
    assert seeded

    with patch("urllib.request.urlopen") as urlopen:
        created = client.post(
            "/api/v1/intake/manual",
            json={
                "incident_type": "traffic_collision",
                "severity": "HIGH",
                "confidence_level": "HIGH",
                "location": {"lat": 30.0561, "lon": 31.3452},
                "location_text": "Nasr City Phase 05 smoke",
                "casualty_count": 1,
                "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
                "operator_reference": "phase05-smoke",
            },
        )
        assert created.status_code == 201, created.text
        incident_id = created.json()["id"]
        generated = client.post(f"/api/v1/incidents/{incident_id}/plans/generate")
        assert generated.status_code == 201, generated.text
        plan = generated.json()
        ambulance_id = next(item["resource_id"] for item in plan["routes"] if item["resource_type"] == "AMBULANCE")
        approved = client.post(
            f"/api/v1/plans/{plan['id']}/approve",
            json={
                "expected_incident_version": plan["incident_version"],
                "expected_plan_version": plan["plan_version"],
                "operator_reference": "phase05-smoke",
            },
        )
        assert approved.status_code == 200, approved.text
        assert urlopen.call_count == 0

    corrected = client.patch(
        f"/api/v1/incidents/{incident_id}/facts",
        json={
            "expected_incident_version": approved.json()["incident"]["version"],
            "operator_reference": "phase05-smoke",
            "transport_required": True,
        },
    )
    assert corrected.status_code == 200, corrected.text
    current_incident_version = corrected.json()["incident"]["version"]

    options = client.post(f"/api/v1/incidents/{incident_id}/hospital-options")
    assert options.status_code == 200, options.text
    options_data = options.json()
    assert options_data["options"]
    hospital_id = options_data["options"][0]["hospital"]["id"]
    selected = client.post(
        f"/api/v1/incidents/{incident_id}/hospital-destination/select",
        json={
            "expected_incident_version": current_incident_version,
            "expected_plan_version": 1,
            "expected_option_set_version": options_data["option_set_version"],
            "hospital_id": hospital_id,
            "operator_reference": "phase05-smoke",
        },
    )
    assert selected.status_code == 200, selected.text
    prealert = client.post(
        f"/api/v1/incidents/{incident_id}/hospital-prealert",
        json={
            "expected_incident_version": current_incident_version + 1,
            "expected_plan_version": 1,
            "operator_reference": "phase05-smoke",
        },
    )
    assert prealert.status_code == 200, prealert.text
    assert prealert.json()["status"] == "ACKNOWLEDGED"

    route = next(item for item in plan["routes"] if item["resource_id"] == ambulance_id)
    corridor = client.post(
        f"/api/v1/incidents/{incident_id}/corridor",
        json={"resource_id": ambulance_id},
    )
    assert corridor.status_code == 200, corridor.text
    priority = client.post(
        f"/api/v1/incidents/{incident_id}/corridor/priority",
        json={
            "expected_incident_version": current_incident_version + 1,
            "expected_plan_version": 1,
            "operator_reference": "phase05-smoke",
            "state": "REQUESTED",
        },
    )
    assert priority.status_code == 200, priority.text
    assert priority.json()["route_geometry"] == route["route_geometry"]

    resource = client.get(f"/api/v1/resources/{ambulance_id}")
    assert resource.status_code == 200, resource.text
    moved = client.patch(
        f"/api/v1/resources/{ambulance_id}/movement",
        json={
            "incident_id": incident_id,
            "expected_resource_version": resource.json()["version"],
            "route_progress": 0.25,
            "operator_reference": "phase05-smoke",
        },
    )
    assert moved.status_code == 200, moved.text
    driver_alert = client.get(f"/api/v1/incidents/{incident_id}/resources/{ambulance_id}/driver-alert")
    assert driver_alert.status_code == 200, driver_alert.text
    assert driver_alert.json()["data_reality"] == "SIMULATED"

    aggregate = client.get(f"/api/v1/incidents/{incident_id}/operational-state")
    assert aggregate.status_code == 200, aggregate.text
    state: dict[str, Any] = aggregate.json()
    assert state["hospital_pre_alert"]["status"] == "ACKNOWLEDGED"
    assert state["corridor"]["state"] == "REQUESTED"
    assert state["driver_alert"]["route_progress"] == 0.25
