from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine

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


def test_no_ai_path_remains_plannable_and_approvable(client: TestClient, db_session) -> None:
    seed_resources(db_session)
    created = client.post(
        "/api/v1/intake/manual",
        json={
            "incident_type": "traffic_collision",
            "severity": "HIGH",
            "confidence_level": "HIGH",
            "location": {"lat": 30.0561, "lon": 31.3452},
            "location_text": "Phase 06 no-AI smoke",
            "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
            "operator_reference": "phase06-no-ai",
        },
    )
    assert created.status_code == 201, created.text
    incident = created.json()
    report = client.post(
        "/api/v1/reports",
        json={
            "incident_id": incident["id"],
            "source_type": "control_room_text",
            "source_reference": "phase06-no-ai-report",
            "raw_text": "Operator entered a credible urgent report.",
        },
    )
    assert report.status_code == 201, report.text
    processed = client.post(f"/api/v1/reports/{report.json()['id']}/process")
    assert processed.status_code == 200, processed.text
    assert processed.json()["status"] == "DISABLED"

    generated = client.post(f"/api/v1/incidents/{incident['id']}/plans/generate")
    assert generated.status_code == 201, generated.text
    plan = generated.json()
    approved = client.post(
        f"/api/v1/plans/{plan['id']}/approve",
        json={
            "expected_incident_version": plan["incident_version"],
            "expected_plan_version": plan["plan_version"],
            "operator_reference": "phase06-no-ai",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["incident"]["status"] == "RESPONSE_ACTIVE"
