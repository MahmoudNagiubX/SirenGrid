from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import init_db
from app.config import settings
from app.coverage import load_population_zones
from app.main import app
from app.seed import seed_resources


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_phase07_one_worker_replan_and_multi_incident_smoke(
    client: TestClient,
    db_session: Session,
) -> None:
    """Exercise approved-plan preservation, replacement approval, and contention."""
    seeded = seed_resources(db_session)
    assert seeded
    modeled_zones = load_population_zones(
        settings.NASR_CITY_DATA_DIR / "nasr_city_zone_population_worldpop_2025.geojson"
    )[:1]

    incident_payload = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Phase 07 replan smoke",
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "phase07-smoke-a",
    }
    created_a = client.post("/api/v1/intake/manual", json=incident_payload)
    assert created_a.status_code == 201, created_a.text
    incident_a = created_a.json()

    with (
        patch("app.planning.traffic_runtime.capture_snapshot", return_value=None),
        patch("app.planning.load_population_zones", return_value=modeled_zones),
    ):
        generated_a = client.post(
            f"/api/v1/incidents/{incident_a['id']}/plans/generate-candidates"
        )
    assert generated_a.status_code == 201, generated_a.text
    recommendation_a = generated_a.json()[0]
    resource_a_id = recommendation_a["resource_ids"][0]

    approved_a = client.post(
        f"/api/v1/plans/{recommendation_a['id']}/approve",
        json={
            "expected_incident_version": recommendation_a["incident_version"],
            "expected_plan_version": recommendation_a["plan_version"],
            "operator_reference": "phase07-smoke-a",
        },
    )
    assert approved_a.status_code == 200, approved_a.text
    active_plan_id = recommendation_a["id"]
    assert approved_a.json()["incident"]["version"] == 3

    trigger = client.post(
        f"/api/v1/incidents/{incident_a['id']}/replan/triggers",
        json={
            "expected_incident_version": 3,
            "trigger_reasons": ["TRAFFIC_CHANGED"],
            "input_references": {
                "old_eta_seconds": 100,
                "new_eta_seconds": 160,
                "route_edge_overlap_ratio": 1.0,
                "traffic_snapshot_id": "smoke-traffic-fallback",
            },
        },
    )
    assert trigger.status_code == 200, trigger.text

    with (
        patch("app.planning.traffic_runtime.capture_snapshot", return_value=None),
        patch("app.planning.load_population_zones", return_value=modeled_zones),
    ):
        evaluated = client.post(
            f"/api/v1/incidents/{incident_a['id']}/replan/evaluate",
            json={"expected_incident_version": 3},
        )
    assert evaluated.status_code == 200, evaluated.text
    evaluation = evaluated.json()
    assert evaluation["status"] == "REPLACEMENT_RECOMMENDED"
    assert evaluation["active_plan_id"] == active_plan_id
    assert evaluation["pending_plan_id"] is not None
    replacement = evaluation["plans"][0]
    assert replacement["status"] == "RECOMMENDED"

    active_before_approval = client.get(f"/api/v1/incidents/{incident_a['id']}")
    assert active_before_approval.status_code == 200
    assert active_before_approval.json()["current_plan_id"] == active_plan_id
    assert active_before_approval.json()["pending_replan_plan_id"] == replacement["id"]

    approved_replacement = client.post(
        f"/api/v1/plans/{replacement['id']}/approve",
        json={
            "expected_incident_version": evaluation["incident_version"],
            "expected_plan_version": replacement["plan_version"],
            "operator_reference": "phase07-smoke-replan",
        },
    )
    assert approved_replacement.status_code == 200, approved_replacement.text
    assert approved_replacement.json()["incident"]["version"] == 5
    assert approved_replacement.json()["incident"]["status"] == "RESPONSE_ACTIVE"

    resource_after_replan = client.get(f"/api/v1/resources/{resource_a_id}")
    assert resource_after_replan.status_code == 200
    assert resource_after_replan.json()["assigned_incident_id"] == incident_a["id"]

    incident_b_payload = {
        **incident_payload,
        "location_text": "Phase 07 replan smoke B",
        "operator_reference": "phase07-smoke-b",
    }
    created_b = client.post("/api/v1/intake/manual", json=incident_b_payload)
    assert created_b.status_code == 201, created_b.text
    incident_b = created_b.json()

    with (
        patch("app.planning.traffic_runtime.capture_snapshot", return_value=None),
        patch("app.planning.load_population_zones", return_value=modeled_zones),
    ):
        generated_b = client.post(
            f"/api/v1/incidents/{incident_b['id']}/plans/generate-candidates"
        )
    assert generated_b.status_code == 201, generated_b.text
    assert all(
        resource_a_id not in plan["resource_ids"]
        for plan in generated_b.json()
    )
