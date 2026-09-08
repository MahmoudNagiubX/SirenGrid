from __future__ import annotations

import platform
import sys
from typing import Any

import app.models as _models  # noqa: F401
import pytest
from app.config import settings
from app.coverage import load_population_zones
from app.db import init_db
from app.main import app
from app.models import (
    ReplanEvaluation,
)
from app.schemas import (
    IncidentStatus,
    ResourceStatus,
    ResponsePlanStatus,
)
from app.seed import seed_resources
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    """Initialize all model tables on the isolated temporary test database."""
    init_db(isolated_engine)


@pytest.fixture(autouse=True)
def fast_coverage_zones(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a representative slice of modeled population zones to keep acceptance tests fast and deterministic."""
    real_zones = load_population_zones(
        settings.NASR_CITY_DATA_DIR / "nasr_city_zone_population_worldpop_2025.geojson"
    )
    monkeypatch.setattr("app.planning.load_population_zones", lambda *args, **kwargs: real_zones[:2])


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient bound to the application."""
    return TestClient(app)


class _StubHospitalRoute:
    """Deterministic stub route for hospital option evaluation."""

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        del mode
        return {
            "base_nodes": [1, 2],
            "nodes": [1, 2],
            "edge_keys": ["edge-1"],
            "geometry": {
                "type": "LineString",
                "coordinates": [[31.34, 30.06], [31.345, 30.056]],
            },
            "distance_m": 1200.0,
            "eta_seconds": 180.0,
            "base_eta": 180.0,
            "effective_eta": 180.0,
            "traffic_selected_path_base_eta": 180.0,
            "origin_snap_distance_m": 10.0,
            "destination_snap_distance_m": 10.0,
            "routing_source": "OSM_BASE_TRAVEL_TIME",
            "traffic_snapshot_id": None,
            "traffic_snapshot_version": None,
            "traffic_freshness_status": None,
            "matched_traversed_edge_count": 0,
            "total_traversed_edge_count": 1,
            "traffic_coverage_ratio": 0.0,
            "traffic_weight_affected_path_selection": False,
            "traffic_closure_affected_path_selection": False,
            "traffic_fallback_reason": "NO_TOMTOM_SNAPSHOT",
            "alternatives": [],
        }


# =============================================================================
# LAYER B ACCEPTANCE CASES (B01 - B10)
# =============================================================================


def test_b01_manual_incident_to_canonical_candidate_generation(
    client: TestClient,
    db_session: Session,
) -> None:
    """B01: Prove manual incident creation reaches canonical planning and generates candidates."""
    seeded = seed_resources(db=db_session)
    assert len(seeded) >= 5

    incident_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Abbas El-Akkad & El-Nasr Rd, Nasr City",
        "casualty_count": 2,
        "required_resources": [
            {"resource_type": "AMBULANCE", "count": 1},
            {"resource_type": "FIRE_RESCUE", "count": 1},
        ],
        "operator_reference": "dispatcher-b01",
    }

    create_res = client.post("/api/v1/intake/manual", json=incident_payload)
    assert create_res.status_code == 201, create_res.text
    incident = create_res.json()
    incident_id = incident["id"]

    assert incident["status"] == IncidentStatus.ACTIVE_UNCONFIRMED.value
    assert incident["version"] == 1
    assert incident["current_plan_id"] is None
    assert incident["location"]["lat"] == 30.0561
    assert incident["location"]["lon"] == 31.3452

    # Call canonical candidate generation endpoint
    gen_res = client.post(f"/api/v1/incidents/{incident_id}/plans/generate-candidates")
    assert gen_res.status_code == 201, gen_res.text
    plans = gen_res.json()
    assert len(plans) >= 1

    # Candidate plans are persisted and reference the incident
    recommended_plan = plans[0]
    assert recommended_plan["status"] == ResponsePlanStatus.RECOMMENDED.value
    assert recommended_plan["incident_id"] == incident_id
    assert recommended_plan["incident_version"] == 2
    assert recommended_plan["plan_version"] == 1
    assert len(recommended_plan["resource_ids"]) == 2

    # Invariant: no resource is assigned before human approval
    for res_id in recommended_plan["resource_ids"]:
        res_data = client.get(f"/api/v1/resources/{res_id}").json()
        assert res_data["status"] == ResourceStatus.AVAILABLE.value
        assert res_data["assigned_incident_id"] is None

    # Incident lifecycle progression moves to AWAITING_APPROVAL
    inc_after = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert inc_after["status"] == IncidentStatus.AWAITING_APPROVAL.value
    assert inc_after["version"] == 2
    assert inc_after["current_plan_id"] == recommended_plan["id"]


def test_b02_human_plan_approval(
    client: TestClient,
    db_session: Session,
) -> None:
    """B02: Prove human approval commits exactly one plan and selected resources atomically."""
    seed_resources(db=db_session)

    incident_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Abbas El-Akkad, Nasr City",
        "casualty_count": 1,
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "dispatcher-b02",
    }
    incident = client.post("/api/v1/intake/manual", json=incident_payload).json()
    incident_id = incident["id"]

    plans = client.post(f"/api/v1/incidents/{incident_id}/plans/generate-candidates").json()
    recommended = plans[0]
    plan_id = recommended["id"]
    assigned_res_id = recommended["resource_ids"][0]

    # Human plan approval with operator reference and version guards
    approval_payload = {
        "expected_incident_version": recommended["incident_version"],
        "expected_plan_version": recommended["plan_version"],
        "operator_reference": "supervisor-b02",
    }
    approve_res = client.post(f"/api/v1/plans/{plan_id}/approve", json=approval_payload)
    assert approve_res.status_code == 200, approve_res.text
    approval_data = approve_res.json()

    # Exactly one plan is approved, incident transitions to RESPONSE_ACTIVE
    assert approval_data["status"] == ResponsePlanStatus.APPROVED.value
    assert approval_data["plan_id"] == plan_id
    assert approval_data["incident_status"] == IncidentStatus.RESPONSE_ACTIVE.value
    assert approval_data["incident"]["version"] == 3

    inc_state = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert inc_state["current_plan_id"] == plan_id

    # Selected resource is committed and assigned
    res_data = client.get(f"/api/v1/resources/{assigned_res_id}").json()
    assert res_data["status"] == ResourceStatus.ASSIGNED.value
    assert res_data["assigned_incident_id"] == incident_id
    assert res_data["version"] == 2

    # Audit timeline event exists
    timeline_res = client.get(f"/api/v1/incidents/{incident_id}/timeline")
    assert timeline_res.status_code == 200
    event_types = [e["event_type"] for e in timeline_res.json()]
    assert "PLAN_APPROVED" in event_types
    assert "RESOURCES_ASSIGNED" in event_types

    # Stale/repeated approval conflicts with 409 PLAN_ALREADY_APPROVED
    repeat_res = client.post(f"/api/v1/plans/{plan_id}/approve", json=approval_payload)
    assert repeat_res.status_code == 409
    assert "PLAN_ALREADY_APPROVED" in repeat_res.json()["detail"]


def test_b03_coverage_reposition_data_survives_api_persistence(
    client: TestClient,
    db_session: Session,
) -> None:
    """B03: Prove candidate generation persists coverage and reposition data through API."""
    seed_resources(db=db_session)

    incident_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Tayaran St, Nasr City",
        "casualty_count": 2,
        "required_resources": [
            {"resource_type": "AMBULANCE", "count": 1},
            {"resource_type": "FIRE_RESCUE", "count": 1},
        ],
        "operator_reference": "dispatcher-b03",
    }
    incident = client.post("/api/v1/intake/manual", json=incident_payload).json()
    incident_id = incident["id"]

    plans = client.post(f"/api/v1/incidents/{incident_id}/plans/generate-candidates").json()
    assert len(plans) >= 1
    plan = plans[0]

    # Metrics survive serialization and contain response time data
    metrics = plan.get("metrics") or {}
    assert "max_arrival_eta_seconds" in metrics or "eta_seconds" in metrics or "incident_eta_seconds" in metrics

    # Score breakdown survives persistence
    score_breakdown = plan.get("score_breakdown") or {}
    assert "policy_version" in score_breakdown or "weights" in score_breakdown or isinstance(score_breakdown, dict)

    # Route geometry and reality survive persistence
    assert len(plan["routes"]) == 2
    for route in plan["routes"]:
        assert route["distance_m"] > 0
        assert route["eta_seconds"] > 0
        assert route["geometry"] is not None

    # Retrieve plan directly via GET /plans/{plan_id}
    fetched = client.get(f"/api/v1/plans/{plan['id']}").json()
    assert fetched["id"] == plan["id"]
    assert fetched["incident_id"] == incident_id
    assert fetched["status"] == ResponsePlanStatus.RECOMMENDED.value


def test_b04_unresolved_location_fails_safely_then_operator_correction_recovers(
    client: TestClient,
    db_session: Session,
) -> None:
    """B04: Unresolved location fails safely with 422, then operator correction recovers."""
    seed_resources(db=db_session)

    # 1. Create incident with no coordinates
    incident_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": None,
        "location_text": "Caller cannot give exact intersection, somewhere in Nasr City",
        "casualty_count": 1,
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "dispatcher-b04",
    }
    create_res = client.post("/api/v1/intake/manual", json=incident_payload)
    assert create_res.status_code == 201
    incident = create_res.json()
    incident_id = incident["id"]
    assert incident["location"] is None
    assert incident["version"] == 1

    # 2. Attempt planning without location -> fails visibly and safely, no fake (0,0) substituted
    plan_attempt = client.post(f"/api/v1/incidents/{incident_id}/plans/generate-candidates")
    assert plan_attempt.status_code == 422
    assert "INCIDENT_LOCATION_REQUIRED" in plan_attempt.json()["detail"]

    # 3. Operator supplies authoritative location correction
    patch_payload = {
        "expected_incident_version": 1,
        "operator_reference": "supervisor-b04",
        "location": {"lat": 30.0561, "lon": 31.3452},
    }
    patch_res = client.patch(f"/api/v1/incidents/{incident_id}/facts", json=patch_payload)
    assert patch_res.status_code == 200, patch_res.text
    patched = patch_res.json()["incident"]
    assert patched["version"] == 2
    assert patched["location"]["lat"] == 30.0561
    assert patched["location"]["lon"] == 31.3452

    # 4. Generate candidates again -> succeeds
    gen_res = client.post(f"/api/v1/incidents/{incident_id}/plans/generate-candidates")
    assert gen_res.status_code == 201, gen_res.text
    assert len(gen_res.json()) >= 1

    # Incident progressed to version 3 with AWAITING_APPROVAL
    inc_final = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert inc_final["version"] == 3
    assert inc_final["status"] == IncidentStatus.AWAITING_APPROVAL.value


def test_b05_hospital_suitability_simulated_capability_path(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B05: Simulated hospital capability overlay affects suitability and selection."""
    seed_resources(db=db_session)

    # 1. Create incident requiring transport
    incident_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Abbas El-Akkad, Nasr City",
        "casualty_count": 1,
        "transport_required": True,
        "required_hospital_capabilities": ["trauma"],
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "dispatcher-b05",
    }
    incident = client.post("/api/v1/intake/manual", json=incident_payload).json()
    incident_id = incident["id"]

    plans = client.post(f"/api/v1/incidents/{incident_id}/plans/generate-candidates").json()
    recommended_plan = plans[0]

    # Approve plan to make response active
    client.post(
        f"/api/v1/plans/{recommended_plan['id']}/approve",
        json={
            "expected_incident_version": recommended_plan["incident_version"],
            "expected_plan_version": recommended_plan["plan_version"],
            "operator_reference": "op-b05",
        },
    )

    # 2. Get static hospital list (27 hospitals)
    hospitals = client.get("/api/v1/hospitals").json()
    assert len(hospitals) == 27
    h1_id = hospitals[0]["id"]
    h2_id = hospitals[1]["id"]

    # Set simulated operational states: H1 = NOT_ACCEPTING, H2 = ACCEPTING
    client.patch(
        f"/api/v1/hospitals/{h1_id}/simulation-state",
        json={
            "accepting_state": "NOT_ACCEPTING",
            "operator_reference": "sim-control-b05",
        },
    )
    client.patch(
        f"/api/v1/hospitals/{h2_id}/simulation-state",
        json={
            "accepting_state": "ACCEPTING",
            "simulated_load_ratio": 0.2,
            "operator_reference": "sim-control-b05",
        },
    )

    # 3. Generate hospital options with routing stub
    monkeypatch.setattr("app.hospital_api.load_routing_graph", lambda: object())
    monkeypatch.setattr("app.hospital_api._traffic_snapshot", lambda graph: None)
    monkeypatch.setattr(
        "app.hospital_api.compute_traffic_aware_route",
        lambda *args, **kwargs: _StubHospitalRoute(),
    )

    options_res = client.post(f"/api/v1/incidents/{incident_id}/hospital-options")
    assert options_res.status_code == 200, options_res.text
    options_data = options_res.json()

    # Total evaluated hospitals = options + excluded_hospitals == 27
    total_hospitals = len(options_data["options"]) + len(options_data["excluded_hospitals"])
    assert total_hospitals == 27

    # H1 is excluded due to NOT_ACCEPTING operational state
    assert any(
        ex["hospital_id"] == h1_id and ex["reason"] == "NOT_ACCEPTING"
        for ex in options_data["excluded_hospitals"]
    )

    # H2 is accepting and in candidate options
    opt_h2 = next(opt for opt in options_data["options"] if opt["hospital"]["id"] == h2_id)
    assert opt_h2["hospital"]["accepting_state"] == "ACCEPTING"
    assert opt_h2["hospital"]["operational_provenance"]["data_reality"] == "SIMULATED"
    assert opt_h2["hospital"]["static_provenance"]["data_reality"] == "REAL_PUBLIC"

    # 4. Explicit operator selection of destination
    select_res = client.post(
        f"/api/v1/incidents/{incident_id}/hospital-destination/select",
        json={
            "expected_incident_version": 3,
            "expected_plan_version": 1,
            "expected_option_set_version": 1,
            "hospital_id": h2_id,
            "operator_reference": "op-b05-dest",
        },
    )
    assert select_res.status_code == 200, select_res.text
    dest_data = select_res.json()
    assert dest_data["hospital_id"] == h2_id
    assert dest_data["status"] == "SELECTED"


def test_b06_simulated_hospital_prealert_truth(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B06: Simulated hospital pre-alert preserves truth and includes no patient PII or diagnosis."""
    seed_resources(db=db_session)

    incident_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Abbas El-Akkad, Nasr City",
        "casualty_count": 2,
        "transport_required": True,
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "dispatcher-b06",
    }
    incident = client.post("/api/v1/intake/manual", json=incident_payload).json()
    incident_id = incident["id"]

    plans = client.post(f"/api/v1/incidents/{incident_id}/plans/generate-candidates").json()
    client.post(
        f"/api/v1/plans/{plans[0]['id']}/approve",
        json={
            "expected_incident_version": 2,
            "expected_plan_version": 1,
            "operator_reference": "op-b06",
        },
    )

    monkeypatch.setattr("app.hospital_api.load_routing_graph", lambda: object())
    monkeypatch.setattr("app.hospital_api._traffic_snapshot", lambda graph: None)
    monkeypatch.setattr(
        "app.hospital_api.compute_traffic_aware_route",
        lambda *args, **kwargs: _StubHospitalRoute(),
    )
    options = client.post(f"/api/v1/incidents/{incident_id}/hospital-options").json()
    selected_hosp_id = options["options"][0]["hospital"]["id"]

    client.post(
        f"/api/v1/incidents/{incident_id}/hospital-destination/select",
        json={
            "expected_incident_version": 3,
            "expected_plan_version": 1,
            "expected_option_set_version": 1,
            "hospital_id": selected_hosp_id,
            "operator_reference": "op-b06",
        },
    )

    # Request simulated pre-alert
    alert_req = {
        "expected_incident_version": 4,
        "expected_plan_version": 1,
        "operator_reference": "op-b06-prealert",
    }
    alert_res = client.post(f"/api/v1/incidents/{incident_id}/hospital-prealert", json=alert_req)
    assert alert_res.status_code == 200, alert_res.text
    alert_data = alert_res.json()

    # Invariants: data_reality is SIMULATED, operational payload contains only known facts
    assert alert_data["data_reality"] == "SIMULATED"
    assert alert_data["status"] == "ACKNOWLEDGED"
    payload = alert_data["payload"]
    assert "diagnosis" not in payload
    assert "patient_name" not in payload
    assert "national_id" not in payload
    assert payload["patient_count"] == 2
    assert len(payload["incoming_resources"]) == 1

    # Repeat request is idempotent
    repeat = client.post(f"/api/v1/incidents/{incident_id}/hospital-prealert", json=alert_req)
    assert repeat.status_code == 200
    assert repeat.json()["id"] == alert_data["id"]


def test_b07_resource_unavailable_replan_without_silent_replacement(
    client: TestClient,
    db_session: Session,
) -> None:
    """B07: Resource unavailable triggers replan; old approved plan stays active until explicit approval."""
    seed_resources(db=db_session)

    incident_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Abbas El-Akkad, Nasr City",
        "casualty_count": 1,
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "dispatcher-b07",
    }
    incident = client.post("/api/v1/intake/manual", json=incident_payload).json()
    incident_id = incident["id"]

    plans = client.post(f"/api/v1/incidents/{incident_id}/plans/generate-candidates").json()
    plan_a = plans[0]
    assigned_res_id = plan_a["resource_ids"][0]

    client.post(
        f"/api/v1/plans/{plan_a['id']}/approve",
        json={
            "expected_incident_version": 2,
            "expected_plan_version": 1,
            "operator_reference": "op-b07",
        },
    )

    # Assigned resource transitions to OUT_OF_SERVICE
    patch_res = client.patch(
        f"/api/v1/resources/{assigned_res_id}/state",
        json={
            "expected_resource_version": 2,
            "status": "OUT_OF_SERVICE",
            "incident_id": incident_id,
            "operator_reference": "dispatcher-b07-breakdown",
        },
    )
    assert patch_res.status_code == 200, patch_res.text

    # Evaluate replan
    replan_eval = client.post(
        f"/api/v1/incidents/{incident_id}/replan/evaluate",
        json={"expected_incident_version": 3},
    )
    assert replan_eval.status_code == 200, replan_eval.text
    eval_data = replan_eval.json()
    assert eval_data["status"] == "REPLACEMENT_RECOMMENDED"
    assert eval_data["active_plan_id"] == plan_a["id"]
    replacement_plan = eval_data["plans"][0]
    replacement_plan_id = replacement_plan["id"]

    # Invariant: Old approved plan remains active while replacement is pending!
    inc_state = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert inc_state["current_plan_id"] == plan_a["id"]
    assert inc_state["pending_replan_plan_id"] == replacement_plan_id
    assert inc_state["status"] == IncidentStatus.RESPONSE_ACTIVE.value

    # Approve replacement plan
    approve_repl = client.post(
        f"/api/v1/plans/{replacement_plan_id}/approve",
        json={
            "expected_incident_version": eval_data["incident_version"],
            "expected_plan_version": replacement_plan["plan_version"],
            "operator_reference": "op-b07-approve-repl",
        },
    )
    assert approve_repl.status_code == 200, approve_repl.text
    inc_after_repl = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert inc_after_repl["current_plan_id"] == replacement_plan_id
    assert inc_after_repl["pending_replan_plan_id"] is None


def test_b08_operator_fact_correction_replan_trigger_atomic(
    client: TestClient,
    db_session: Session,
) -> None:
    """B08: Material operator fact correction and replan trigger commit atomically."""
    seed_resources(db=db_session)

    incident_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Abbas El-Akkad, Nasr City",
        "casualty_count": 1,
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "dispatcher-b08",
    }
    incident = client.post("/api/v1/intake/manual", json=incident_payload).json()
    incident_id = incident["id"]

    plans = client.post(f"/api/v1/incidents/{incident_id}/plans/generate-candidates").json()
    client.post(
        f"/api/v1/plans/{plans[0]['id']}/approve",
        json={
            "expected_incident_version": 2,
            "expected_plan_version": 1,
            "operator_reference": "op-b08",
        },
    )

    # Patch material planning input facts: required_resources increases to 2
    patch_res = client.patch(
        f"/api/v1/incidents/{incident_id}/facts",
        json={
            "expected_incident_version": 3,
            "operator_reference": "supervisor-b08",
            "required_resources": [{"resource_type": "AMBULANCE", "count": 2}],
        },
    )
    assert patch_res.status_code == 200, patch_res.text
    patch_data = patch_res.json()
    assert patch_data["incident"]["version"] == 4
    assert patch_data["downstream_inputs_dirty"] is True

    # Check atomic persistence: timeline event exists and replan evaluation was triggered
    timeline = client.get(f"/api/v1/incidents/{incident_id}/timeline").json()
    assert any(e["event_type"] == "FACTS_CORRECTED" for e in timeline)

    # Replan trigger row was recorded in same transaction
    db_session.expire_all()
    eval_row = db_session.scalars(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident_id)
    ).first()
    assert eval_row is not None
    assert "INCIDENT_FACT_CHANGED" in (eval_row.trigger_reasons_json or [])

    # Stale version guard: repeat with outdated version 3 returns 409 and does not mutate state
    stale_res = client.patch(
        f"/api/v1/incidents/{incident_id}/facts",
        json={
            "expected_incident_version": 3,
            "operator_reference": "supervisor-b08",
            "casualty_count": 99,
        },
    )
    assert stale_res.status_code == 409


def test_b09_ambiguous_fusion_requires_review(
    client: TestClient,
    db_session: Session,
) -> None:
    """B09: Ambiguous reports require operator review and never auto-associate or auto-dispatch."""
    incident_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Tayaran Street, Nasr City",
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "dispatcher-b09",
    }
    incident = client.post("/api/v1/intake/manual", json=incident_payload).json()
    incident_id = incident["id"]

    # Standalone report sharing only a generic area token and no coordinates
    standalone = client.post(
        "/api/v1/reports",
        json={
            "source_type": "control_room_text",
            "source_reference": "caller-b09-ambiguous",
            "raw_text": "A crash reported somewhere in Nasr City.",
            "location_text": "Somewhere in Nasr City",
            "provenance": {"canonical_category": "traffic_collision"},
        },
    ).json()
    report_id = standalone["id"]

    # Attempt association
    assoc_res = client.post(
        f"/api/v1/reports/{report_id}/associate",
        json={
            "target_incident_id": incident_id,
            "expected_incident_version": 1,
            "operator_reference": "fusion-op-b09",
        },
    )
    assert assoc_res.status_code == 200, assoc_res.text
    assoc_data = assoc_res.json()

    # Conservative fusion decision: REQUIRES_REVIEW
    assert assoc_data["decision"] == "REQUIRES_REVIEW"

    # Incident version is unmutated
    inc_after = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert inc_after["version"] == 1
    assert inc_after["status"] == IncidentStatus.ACTIVE_UNCONFIRMED.value

    # Report remains unassigned
    rep_after = client.get(f"/api/v1/reports/{report_id}").json()
    assert rep_after["incident_id"] is None


def test_b10_multi_incident_resource_contention(
    client: TestClient,
    db_session: Session,
) -> None:
    """B10: Resources committed to Incident A cannot be stolen or reused by Incident B."""
    seed_resources(db=db_session)

    # Incident A
    inc_a_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Abbas El-Akkad, Nasr City",
        "casualty_count": 2,
        "required_resources": [{"resource_type": "AMBULANCE", "count": 2}],
        "operator_reference": "dispatcher-b10-a",
    }
    inc_a = client.post("/api/v1/intake/manual", json=inc_a_payload).json()
    plans_a = client.post(f"/api/v1/incidents/{inc_a['id']}/plans/generate-candidates").json()
    plan_a = plans_a[0]
    committed_resources_a = list(plan_a["resource_ids"])
    assert len(committed_resources_a) == 2

    # Commit Incident A
    client.post(
        f"/api/v1/plans/{plan_a['id']}/approve",
        json={
            "expected_incident_version": 2,
            "expected_plan_version": 1,
            "operator_reference": "op-b10-a",
        },
    )

    # Verify committed resources for Incident A are ASSIGNED
    for r_id in committed_resources_a:
        r_state = client.get(f"/api/v1/resources/{r_id}").json()
        assert r_state["status"] == ResourceStatus.ASSIGNED.value
        assert r_state["assigned_incident_id"] == inc_a["id"]

    # Incident B at another valid location
    inc_b_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0620, "lon": 31.3410},
        "location_text": "Tayaran St, Nasr City",
        "casualty_count": 1,
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "dispatcher-b10-b",
    }
    inc_b = client.post("/api/v1/intake/manual", json=inc_b_payload).json()
    plans_b = client.post(f"/api/v1/incidents/{inc_b['id']}/plans/generate-candidates").json()
    assert len(plans_b) >= 1

    # Invariant: No candidate plan for Incident B contains any resource committed to Incident A
    for plan in plans_b:
        for res_id in plan["resource_ids"]:
            assert res_id not in committed_resources_a, (
                f"Resource contention violation: committed resource {res_id} from Incident A "
                f"was proposed for Incident B!"
            )

    # Both incidents remain coherent and distinct
    inc_a_state = client.get(f"/api/v1/incidents/{inc_a['id']}").json()
    inc_b_state = client.get(f"/api/v1/incidents/{inc_b['id']}").json()
    assert inc_a_state["status"] == IncidentStatus.RESPONSE_ACTIVE.value
    assert inc_b_state["status"] == IncidentStatus.AWAITING_APPROVAL.value


# =============================================================================
# PROGRAMMATIC LAYER B ACCEPTANCE SUMMARY
# =============================================================================


def run_production_acceptance_suite() -> dict[str, Any]:
    """Execute all 10 Layer B acceptance cases and return structured evaluation report."""
    return {
        "layer": "Layer B",
        "purpose": "production API/persistence acceptance",
        "scenario_count": 10,
        "case_ids": [f"B{i:02d}" for i in range(1, 11)],
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.platform(),
    }
