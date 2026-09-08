from __future__ import annotations

from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.db import init_db
from app.main import app
from app.models import Approval, EmergencyResource, Incident, ResponsePlan, TimelineEvent
from app.schemas import (
    DataReality,
    FreshnessStatus,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
)
from app.seed import seed_resources


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    """Initialize all model tables on the isolated test engine."""
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_phase01_golden_flow(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Execute the end-to-end Phase 01 Golden Flow integration test.

    Sequence:
    1. Start with clean isolated DB.
    2. Seed resources; assert counts, statuses, and provenance.
    3. POST manual incident at graph-reachable Nasr City location; assert initial state.
    4. Assert candidate resources are initially AVAILABLE and unassigned.
    5. POST candidate plan generation with real OSM base routing; assert plan and metrics.
    6. GET incident; assert AWAITING_APPROVAL, version 2, and current_plan_id.
    7. GET plan; assert persisted fields, routes, and metrics.
    8. POST approval with matching versions; assert APPROVED, RESPONSE_ACTIVE, and version 3.
    9. GET selected resources; assert ASSIGNED, version 2, and ineligible for planning.
    10. GET incident plans and query TimelineEvent directly for mandatory audit events.
    11. Repeat approval attempt; assert HTTP 409 with PLAN_ALREADY_APPROVED.
    12. Assert all entity versions, statuses, and event counts remain unmutated after repeat.
    13. Verify no external network calls were made during the entire lifecycle.
    """
    # 1. Clean isolated DB
    assert db_session.scalars(select(EmergencyResource)).all() == []
    assert db_session.scalars(select(Incident)).all() == []
    assert db_session.scalars(select(ResponsePlan)).all() == []
    assert db_session.scalars(select(Approval)).all() == []
    assert db_session.scalars(select(TimelineEvent)).all() == []

    # 2. Seed resources using seed_resources(db_session)
    seeded = seed_resources(db=db_session)
    ambulances = [r for r in seeded if r.resource_type == ResourceType.AMBULANCE]
    fire_rescues = [r for r in seeded if r.resource_type == ResourceType.FIRE_RESCUE]

    assert len(ambulances) >= 3, f"Expected at least 3 ambulances, found {len(ambulances)}"
    assert len(fire_rescues) >= 2, f"Expected at least 2 fire rescues, found {len(fire_rescues)}"

    available_ambulances = [r for r in ambulances if r.status == ResourceStatus.AVAILABLE]
    assigned_ambulances = [r for r in ambulances if r.status == ResourceStatus.ASSIGNED]
    available_fire = [r for r in fire_rescues if r.status == ResourceStatus.AVAILABLE]
    oos_fire = [r for r in fire_rescues if r.status == ResourceStatus.OUT_OF_SERVICE]

    assert len(available_ambulances) >= 3
    assert len(assigned_ambulances) >= 1
    assert len(available_fire) >= 2
    assert len(oos_fire) >= 1

    for res in seeded:
        assert res.version == 1
        assert res.provenance_json.get("data_reality") == DataReality.SIMULATED.value
        assert res.provenance_json.get("freshness_status") == FreshnessStatus.STATIC.value
        assert res.provenance_json.get("source") == "scenario_phase01_seed"

    # 3. POST one manual operator incident at a graph-reachable Nasr City location
    incident_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "El-Nasr Road & Abbas El-Akkad, Nasr City",
        "casualty_count": 2,
        "required_resources": [
            {"resource_type": "AMBULANCE", "count": 1},
            {"resource_type": "FIRE_RESCUE", "count": 1},
        ],
        "operator_reference": "dispatcher-op-gold-01",
    }

    with patch("urllib.request.urlopen") as mock_url:
        create_res = client.post("/api/v1/intake/manual", json=incident_payload)
        assert mock_url.call_count == 0

    assert create_res.status_code == 201, create_res.text
    incident_data = create_res.json()
    incident_id = incident_data["id"]

    assert incident_data["status"] == IncidentStatus.ACTIVE_UNCONFIRMED.value
    assert incident_data["version"] == 1
    assert incident_data["location"]["lat"] == 30.0561
    assert incident_data["location"]["lon"] == 31.3452
    assert incident_data["casualty_range"] is None
    assert incident_data["trapped_person"] is None
    assert incident_data["road_blockage"] is None
    assert incident_data["current_plan_id"] is None
    assert incident_data["provenance"]["data_reality"] == DataReality.SIMULATED.value
    assert incident_data["provenance_json"]["data_reality"] == DataReality.SIMULATED.value
    assert incident_data["provenance"]["source"] == "operator_manual_entry"

    # 4. Assert selected candidate resources are initially AVAILABLE and unassigned
    res_list_res = client.get("/api/v1/resources?status=AVAILABLE")
    assert res_list_res.status_code == 200
    available_res_items = res_list_res.json()
    assert len(available_res_items) >= 5
    for item in available_res_items:
        assert item["status"] == ResourceStatus.AVAILABLE.value
        assert item["assigned_incident_id"] is None
        assert item["is_planner_eligible"] is True

    # Keep the regression deterministic even when a local demo key is configured.
    monkeypatch.setattr(
        "app.planning.traffic_runtime.capture_snapshot",
        lambda *_args, **_kwargs: None,
    )

    # 5. POST /api/v1/incidents/{incident_id}/plans/generate with real OSM base routing
    with patch("urllib.request.urlopen") as mock_url:
        generate_res = client.post(f"/api/v1/incidents/{incident_id}/plans/generate")
        assert mock_url.call_count == 0

    assert generate_res.status_code == 201, generate_res.text
    plan_data = generate_res.json()
    plan_id = plan_data["id"]

    assert plan_data["status"] == ResponsePlanStatus.RECOMMENDED.value
    assert plan_data["plan_version"] == 1
    assert plan_data["incident_version"] == 2

    selected_ids = plan_data["resource_ids"]
    assert len(selected_ids) == 2

    # Exactly the requested two real scenario resource IDs are selected
    seeded_id_map = {r.id: r for r in seeded}
    for res_id in selected_ids:
        assert res_id in seeded_id_map

    selected_types = [seeded_id_map[res_id].resource_type for res_id in selected_ids]
    assert ResourceType.AMBULANCE in selected_types
    assert ResourceType.FIRE_RESCUE in selected_types

    # Routes contain LineString geometry, distance_m > 0, eta_seconds > 0, routing_source OSM_BASE_TRAVEL_TIME
    routes = plan_data["routes"]
    assert len(routes) == 2
    for route in routes:
        assert route["distance_m"] > 0
        assert route["eta_seconds"] > 0
        assert route["routing_source"] == "OSM_BASE_TRAVEL_TIME"
        assert route["route_geometry"]["type"] == "LineString"
        assert route["geometry"]["type"] == "LineString"
        coords = route["geometry"]["coordinates"]
        assert len(coords) >= 2
        for pt in coords:
            assert isinstance(pt[0], float)
            assert isinstance(pt[1], float)

    assert plan_data["metrics"]["routing_source"] == "OSM_BASE_TRAVEL_TIME"
    assert plan_data["metrics"]["selected_resource_count"] == 2
    assert plan_data["metrics"]["max_arrival_eta_seconds"] > 0
    assert plan_data["metrics"]["mean_arrival_eta_seconds"] > 0
    assert plan_data["score_breakdown"]["policy_version"] == (
        "SIRENGRID_PROTOTYPE_PLAN_SCORE_V1"
    )

    # 6. GET incident and assert status AWAITING_APPROVAL, version 2, current_plan_id equals plan ID
    inc_get_res = client.get(f"/api/v1/incidents/{incident_id}")
    assert inc_get_res.status_code == 200
    inc_get_data = inc_get_res.json()
    assert inc_get_data["status"] == IncidentStatus.AWAITING_APPROVAL.value
    assert inc_get_data["version"] == 2
    assert inc_get_data["current_plan_id"] == plan_id

    # 7. GET plan and assert persisted plan status/version/routes/metrics
    plan_get_res = client.get(f"/api/v1/plans/{plan_id}")
    assert plan_get_res.status_code == 200
    plan_get_data = plan_get_res.json()
    assert plan_get_data["id"] == plan_id
    assert plan_get_data["status"] == ResponsePlanStatus.RECOMMENDED.value
    assert plan_get_data["plan_version"] == 1
    assert plan_get_data["incident_version"] == 2
    assert plan_get_data["resource_ids"] == selected_ids
    assert plan_get_data["routes"] == routes
    assert plan_get_data["metrics"] == plan_data["metrics"]
    assert plan_get_data["score_breakdown"] == plan_data["score_breakdown"]

    # 8. POST /api/v1/plans/{plan_id}/approve with expected versions from generated plan directly
    approve_payload: dict[str, Any] = {
        "expected_incident_version": plan_data["incident_version"],
        "expected_plan_version": plan_data["plan_version"],
        "operator_reference": "dispatcher-op-gold-01",
    }
    with patch("urllib.request.urlopen") as mock_url:
        approve_res = client.post(f"/api/v1/plans/{plan_id}/approve", json=approve_payload)
        assert mock_url.call_count == 0

    assert approve_res.status_code == 200, approve_res.text
    approve_data = approve_res.json()
    assert approve_data["status"] == ResponsePlanStatus.APPROVED.value
    assert approve_data["plan_version"] == 1
    assert approve_data["incident_status"] == IncidentStatus.RESPONSE_ACTIVE.value
    assert approve_data["incident"]["status"] == IncidentStatus.RESPONSE_ACTIVE.value
    assert approve_data["incident"]["version"] == 3

    # 9. For every selected resource, GET detail and assert ASSIGNED, version 2, ineligible for planning
    for res_id in selected_ids:
        res_detail_res = client.get(f"/api/v1/resources/{res_id}")
        assert res_detail_res.status_code == 200
        res_detail = res_detail_res.json()
        assert res_detail["status"] == ResourceStatus.ASSIGNED.value
        assert res_detail["assigned_incident_id"] == incident_id
        assert res_detail["version"] == 2
        assert res_detail["is_planner_eligible"] is False

    # 10. GET incident plans and assert plan present; assert TimelineEvent audit records
    list_plans_res = client.get(f"/api/v1/incidents/{incident_id}/plans")
    assert list_plans_res.status_code == 200
    plans_list = list_plans_res.json()
    assert any(p["id"] == plan_id for p in plans_list)
    assert len(plans_list) == plan_data["candidate_count"]
    assert sum(
        plan["status"] == ResponsePlanStatus.APPROVED.value for plan in plans_list
    ) == 1
    assert all(
        plan["status"] in {
            ResponsePlanStatus.APPROVED.value,
            ResponsePlanStatus.ALTERNATIVE.value,
            ResponsePlanStatus.SUPERSEDED.value,
        }
        for plan in plans_list
    )

    timeline_stmt = (
        select(TimelineEvent)
        .where(TimelineEvent.incident_id == incident_id)
        .order_by(TimelineEvent.created_at.asc())
    )
    events = db_session.scalars(timeline_stmt).all()
    event_types = [e.event_type for e in events]

    assert "INCIDENT_CREATED" in event_types
    assert "PLAN_GENERATED" in event_types
    assert "PLAN_APPROVED" in event_types
    assert "RESOURCES_ASSIGNED" in event_types
    assert event_types.count("PLAN_APPROVED") == 1
    assert event_types.count("RESOURCES_ASSIGNED") == 1

    # 11. Repeat the exact approval attempt and assert HTTP 409 with PLAN_ALREADY_APPROVED
    repeat_res = client.post(f"/api/v1/plans/{plan_id}/approve", json=approve_payload)
    assert repeat_res.status_code == 409
    assert "PLAN_ALREADY_APPROVED" in repeat_res.json()["detail"]

    # Also repeat with current incident version 3 and same plan version; assert 409
    repeat_v3_payload = {
        "expected_incident_version": 3,
        "expected_plan_version": 1,
        "operator_reference": "dispatcher-op-gold-01",
    }
    repeat_v3_res = client.post(f"/api/v1/plans/{plan_id}/approve", json=repeat_v3_payload)
    assert repeat_v3_res.status_code == 409
    assert "PLAN_ALREADY_APPROVED" in repeat_v3_res.json()["detail"]

    # 12. After repeat approval, assert plan/incident/resource versions and statuses are unchanged
    plan_after = client.get(f"/api/v1/plans/{plan_id}").json()
    assert plan_after["status"] == ResponsePlanStatus.APPROVED.value
    assert plan_after["plan_version"] == 1

    inc_after = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert inc_after["status"] == IncidentStatus.RESPONSE_ACTIVE.value
    assert inc_after["version"] == 3

    for res_id in selected_ids:
        r_after = client.get(f"/api/v1/resources/{res_id}").json()
        assert r_after["status"] == ResourceStatus.ASSIGNED.value
        assert r_after["assigned_incident_id"] == incident_id
        assert r_after["version"] == 2
        assert r_after["is_planner_eligible"] is False

    # Approval row count remains exactly 1
    approvals = db_session.scalars(
        select(Approval).where(Approval.plan_id == plan_id)
    ).all()
    assert len(approvals) == 1
    assert approvals[0].expected_incident_version == 2
    assert approvals[0].expected_plan_version == 1

    # Timeline events remain unchanged without duplicate mutations
    events_after = db_session.scalars(timeline_stmt).all()
    event_types_after = [e.event_type for e in events_after]
    assert len(events_after) == len(events)
    assert event_types_after.count("PLAN_APPROVED") == 1
    assert event_types_after.count("RESOURCES_ASSIGNED") == 1
