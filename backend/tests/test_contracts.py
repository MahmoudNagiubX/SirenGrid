from __future__ import annotations

import datetime
from typing import Any
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401 - ensure all ORM models are registered
from app.db import init_db
from app.main import app
from app.models import EmergencyResource, Incident, ResponsePlan
from app.schemas import (
    ConfidenceLevel,
    DataReality,
    FreshnessStatus,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    """Initialize all model tables on the isolated test engine."""
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_openapi_schema_contains_required_paths_and_models(client: TestClient) -> None:
    """Verify /openapi.json exposes all Phase 01 contract paths, schemas, and honest examples."""
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    openapi = response.json()

    # 1. Verify all required endpoint paths are registered
    paths = openapi.get("paths", {})
    expected_paths = [
        ("/api/v1/intake/manual", "post"),
        ("/api/v1/incidents", "get"),
        ("/api/v1/incidents/{incident_id}", "get"),
        ("/api/v1/resources", "get"),
        ("/api/v1/resources/{resource_id}", "get"),
        ("/api/v1/incidents/{incident_id}/plans/generate", "post"),
        ("/api/v1/incidents/{incident_id}/plans", "get"),
        ("/api/v1/plans/{plan_id}", "get"),
        ("/api/v1/plans/{plan_id}/approve", "post"),
        ("/api/v1/map/boundary", "get"),
        ("/api/v1/map/roads", "get"),
        ("/api/v1/map/zones", "get"),
        ("/api/v1/map/hospitals", "get"),
        ("/api/v1/routes/preview", "post"),
    ]
    for path, method in expected_paths:
        assert path in paths, f"Path '{path}' missing from openapi.json"
        assert method in paths[path], f"Method '{method.upper()}' for '{path}' missing from openapi.json"

    # 2. Verify all required component schemas exist
    schemas = openapi.get("components", {}).get("schemas", {})
    expected_schemas = [
        "ManualIncidentCreate",
        "IncidentRead",
        "ResourceRead",
        "ResponsePlanRead",
        "ApprovePlanRequest",
        "ApprovalResult",
        "MapLayerResponse",
        "RoutePreviewRequest",
        "RoutePreviewResponse",
    ]
    for schema_name in expected_schemas:
        assert schema_name in schemas, f"Schema '{schema_name}' missing from components.schemas"
        schema_obj = schemas[schema_name]
        # Must have example or examples defined
        has_example = "example" in schema_obj or "examples" in schema_obj
        assert has_example, f"Schema '{schema_name}' must expose example or examples in JSON schema"

    # 3. Assert honest labels and no live traffic / TomTom claims anywhere in schemas
    schema_dump = str(schemas)
    assert "TomTom" not in schema_dump, "Forbidden provider 'TomTom' found in schema examples"
    assert "live traffic" not in schema_dump.lower(), "Live traffic claim found in schema examples"

    # Check specific reality labels in schema examples
    resource_example = schemas["ResourceRead"].get("example") or schemas["ResourceRead"]["examples"][0]
    res_provenance = resource_example.get("provenance", {})
    assert res_provenance.get("data_reality") == DataReality.SIMULATED.value

    incident_example = schemas["IncidentRead"].get("example") or schemas["IncidentRead"]["examples"][0]
    inc_provenance = incident_example.get("provenance", {})
    assert inc_provenance.get("data_reality") == DataReality.SIMULATED.value

    map_example = schemas["MapLayerResponse"].get("example") or schemas["MapLayerResponse"]["examples"][0]
    map_provenance = map_example.get("provenance", {})
    assert map_provenance.get("data_reality") == DataReality.REAL_DERIVED.value
    assert map_provenance.get("freshness_status") == FreshnessStatus.STATIC.value

    plan_example = schemas["ResponsePlanRead"].get("example") or schemas["ResponsePlanRead"]["examples"][0]
    assert plan_example.get("metrics", {}).get("routing_source") == "OSM_BASE_TRAVEL_TIME"


def test_incident_read_endpoints_and_null_unknown_preservation(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify GET /api/v1/incidents and GET /api/v1/incidents/{incident_id} return persisted

    incidents ordered deterministically, preserve null unknowns, and return 404 for missing ID.
    """
    # 1. 404 on non-existent incident
    missing_resp = client.get("/api/v1/incidents/non-existent-uuid")
    assert missing_resp.status_code == 404
    assert "not found" in missing_resp.json().get("detail", "").lower()

    # 2. Empty list when no incidents exist
    empty_list_resp = client.get("/api/v1/incidents")
    assert empty_list_resp.status_code == 200
    assert empty_list_resp.json() == []

    # 3. Create incident with null optional fields via intake
    payload_minimal: dict[str, Any] = {
        "incident_type": "medical_emergency",
        "severity": "MODERATE",
        "confidence_level": "MEDIUM",
        "location": {"lat": 30.0510, "lon": 31.3410},
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "op-min",
    }
    create_resp1 = client.post("/api/v1/intake/manual", json=payload_minimal)
    assert create_resp1.status_code == 201
    inc1_id = create_resp1.json()["id"]

    # Create second incident with full optional fields
    payload_full: dict[str, Any] = {
        "incident_type": "structure_fire",
        "severity": "CRITICAL",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0600, "lon": 31.3500},
        "location_text": "Abbas El-Akkad commercial area",
        "casualty_count": 3,
        "casualty_range": "3-5",
        "trapped_person": True,
        "road_blockage": True,
        "required_resources": [{"resource_type": "FIRE_RESCUE", "count": 2}],
        "operator_reference": "op-full",
    }
    create_resp2 = client.post("/api/v1/intake/manual", json=payload_full)
    assert create_resp2.status_code == 201
    inc2_id = create_resp2.json()["id"]

    # 4. Detail endpoint for inc1 preserves null unknowns
    detail_resp1 = client.get(f"/api/v1/incidents/{inc1_id}")
    assert detail_resp1.status_code == 200
    inc1_data = detail_resp1.json()
    assert inc1_data["id"] == inc1_id
    assert inc1_data["incident_type"] == "medical_emergency"
    assert inc1_data["severity"] == "MODERATE"
    assert inc1_data["confidence_level"] == "MEDIUM"
    assert inc1_data["status"] == IncidentStatus.ACTIVE_UNCONFIRMED.value
    assert inc1_data["location"] == {"lat": 30.0510, "lon": 31.3410}
    assert inc1_data["latitude"] == 30.0510
    assert inc1_data["longitude"] == 31.3410
    assert inc1_data["location_text"] is None
    assert inc1_data["casualty_count"] is None
    assert inc1_data["casualty_range"] is None
    assert inc1_data["trapped_person"] is None
    assert inc1_data["road_blockage"] is None
    assert inc1_data["current_plan_id"] is None
    assert inc1_data["provenance"]["data_reality"] == DataReality.SIMULATED.value
    assert inc1_data["provenance"]["source_reference"] == "op-min"

    # Detail endpoint for inc2 has full populated fields
    detail_resp2 = client.get(f"/api/v1/incidents/{inc2_id}")
    assert detail_resp2.status_code == 200
    inc2_data = detail_resp2.json()
    assert inc2_data["id"] == inc2_id
    assert inc2_data["casualty_count"] == 3
    assert inc2_data["casualty_range"] == "3-5"
    assert inc2_data["trapped_person"] is True
    assert inc2_data["road_blockage"] is True
    assert inc2_data["location_text"] == "Abbas El-Akkad commercial area"

    # 5. List endpoint returns both incidents deterministically ordered (most recent first)
    list_resp = client.get("/api/v1/incidents")
    assert list_resp.status_code == 200
    incidents_list = list_resp.json()
    assert len(incidents_list) == 2
    # inc2 was created after inc1
    assert incidents_list[0]["id"] == inc2_id
    assert incidents_list[1]["id"] == inc1_id


def test_incident_plans_read_and_plan_detail_endpoints(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify GET /api/v1/incidents/{incident_id}/plans and GET /api/v1/plans/{plan_id}

    return persisted plans, return 404 for missing incident or plan, and maintain deterministic order.
    """
    # 1. 404 on missing incident for plans list
    resp_missing_inc = client.get("/api/v1/incidents/missing-incident-id/plans")
    assert resp_missing_inc.status_code == 404
    assert "not found" in resp_missing_inc.json().get("detail", "").lower()

    # 2. 404 on missing plan for plan detail
    resp_missing_plan = client.get("/api/v1/plans/missing-plan-id")
    assert resp_missing_plan.status_code == 404
    assert "not found" in resp_missing_plan.json().get("detail", "").lower()

    # 3. Create an incident in DB
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    incident = Incident(
        id=str(uuid.uuid4()),
        version=1,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=30.0561,
        longitude=31.3452,
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
        created_at=now_utc,
        updated_at=now_utc,
        provenance_json={"data_reality": "SIMULATED"},
    )
    db_session.add(incident)
    db_session.commit()

    # Incident with no plans yet returns empty list
    empty_plans_resp = client.get(f"/api/v1/incidents/{incident.id}/plans")
    assert empty_plans_resp.status_code == 200
    assert empty_plans_resp.json() == []

    # 4. Insert two plans for this incident with distinct plan_versions
    plan1 = ResponsePlan(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        incident_version=1,
        plan_version=1,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids_json=["res-amb-01"],
        routes_json=[
            {
                "resource_id": "res-amb-01",
                "distance_m": 1500.0,
                "eta_seconds": 210.0,
                "routing_source": "OSM_BASE_TRAVEL_TIME",
            }
        ],
        metrics_json={
            "max_arrival_eta_seconds": 210.0,
            "mean_arrival_eta_seconds": 210.0,
            "selected_resource_count": 1,
            "routing_source": "OSM_BASE_TRAVEL_TIME",
        },
        score_breakdown_json={
            "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
            "traffic_source": "OSM_BASE_TRAVEL_TIME",
        },
        created_at=now_utc,
    )
    plan2 = ResponsePlan(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        incident_version=2,
        plan_version=2,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids_json=["res-amb-02"],
        routes_json=[
            {
                "resource_id": "res-amb-02",
                "distance_m": 1200.0,
                "eta_seconds": 180.0,
                "routing_source": "OSM_BASE_TRAVEL_TIME",
            }
        ],
        metrics_json={
            "max_arrival_eta_seconds": 180.0,
            "mean_arrival_eta_seconds": 180.0,
            "selected_resource_count": 1,
            "routing_source": "OSM_BASE_TRAVEL_TIME",
        },
        score_breakdown_json={
            "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
            "traffic_source": "OSM_BASE_TRAVEL_TIME",
        },
        created_at=now_utc + datetime.timedelta(seconds=10),
    )
    db_session.add(plan1)
    db_session.add(plan2)
    db_session.commit()

    # 5. List incident plans: should return both plans ordered deterministically by plan_version asc
    plans_resp = client.get(f"/api/v1/incidents/{incident.id}/plans")
    assert plans_resp.status_code == 200
    plans_list = plans_resp.json()
    assert len(plans_list) == 2
    assert plans_list[0]["id"] == plan1.id
    assert plans_list[0]["plan_version"] == 1
    assert plans_list[0]["metrics"]["routing_source"] == "OSM_BASE_TRAVEL_TIME"
    assert plans_list[1]["id"] == plan2.id
    assert plans_list[1]["plan_version"] == 2

    # 6. GET /api/v1/plans/{plan_id} returns exact serialized plan
    plan1_detail_resp = client.get(f"/api/v1/plans/{plan1.id}")
    assert plan1_detail_resp.status_code == 200
    p1_data = plan1_detail_resp.json()
    assert p1_data["id"] == plan1.id
    assert p1_data["plan_id"] == plan1.id
    assert p1_data["incident_id"] == incident.id
    assert p1_data["incident_version"] == 1
    assert p1_data["plan_version"] == 1
    assert p1_data["version"] == 1
    assert p1_data["status"] == "RECOMMENDED"
    assert p1_data["resource_ids"] == ["res-amb-01"]
    assert p1_data["metrics"]["max_arrival_eta_seconds"] == 210.0
    assert p1_data["score_breakdown"]["algorithm"] == "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS"
    assert p1_data["score_breakdown"]["traffic_source"] == "OSM_BASE_TRAVEL_TIME"


def test_read_endpoints_do_not_mutate_state(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify that multiple GET calls across read endpoints never mutate database state."""
    # Seed an incident and a resource
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    inc = Incident(
        id="inc-read-only-test",
        version=1,
        incident_type="traffic_collision",
        severity=Severity.LOW,
        confidence_level=ConfidenceLevel.LOW,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=30.05,
        longitude=31.34,
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
        created_at=now_utc,
        updated_at=now_utc,
        provenance_json={"data_reality": "SIMULATED"},
    )
    res = EmergencyResource(
        id="res-read-only-test",
        version=1,
        name="Ambulance Test",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        latitude=30.06,
        longitude=31.33,
        capability_tags_json=["BLS"],
        provenance_json={"data_reality": "SIMULATED"},
        last_updated=now_utc,
    )
    db_session.add(inc)
    db_session.add(res)
    db_session.commit()

    # Call GET repeatedly
    for _ in range(3):
        r_inc = client.get("/api/v1/incidents")
        assert r_inc.status_code == 200
        r_inc_detail = client.get(f"/api/v1/incidents/{inc.id}")
        assert r_inc_detail.status_code == 200
        r_plans = client.get(f"/api/v1/incidents/{inc.id}/plans")
        assert r_plans.status_code == 200
        r_res = client.get("/api/v1/resources")
        assert r_res.status_code == 200
        r_res_detail = client.get(f"/api/v1/resources/{res.id}")
        assert r_res_detail.status_code == 200

    # Ensure DB records are completely untouched
    db_session.expire_all()
    reloaded_inc = db_session.get(Incident, inc.id)
    assert reloaded_inc is not None
    assert reloaded_inc.version == 1
    assert reloaded_inc.status == IncidentStatus.ACTIVE_UNCONFIRMED

    reloaded_res = db_session.get(EmergencyResource, res.id)
    assert reloaded_res is not None
    assert reloaded_res.version == 1
    assert reloaded_res.status == ResourceStatus.AVAILABLE


def test_resource_schema_and_examples_preserve_simulated(client: TestClient) -> None:
    """Verify resource schema and live GET /resources endpoint preserve SIMULATED provenance."""
    response = client.get("/openapi.json")
    openapi = response.json()
    schemas = openapi.get("components", {}).get("schemas", {})
    assert "ResourceRead" in schemas

    schema = schemas["ResourceRead"]
    example = schema.get("example") or schema.get("examples", [{}])[0]
    assert example["provenance"]["data_reality"] == "SIMULATED"
    assert "capabilities" in example
    assert "status" in example
    assert "is_planner_eligible" in example

    # Check live GET /resources schema compliance via client
    res_resp = client.get("/api/v1/resources")
    assert res_resp.status_code == 200
    assert isinstance(res_resp.json(), list)


def test_plan_and_approval_contracts_preserve_osm_and_version_fields(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify plan and approval contracts preserve OSM_BASE_TRAVEL_TIME, versions, and honest schemas."""
    response = client.get("/openapi.json")
    openapi = response.json()
    schemas = openapi.get("components", {}).get("schemas", {})

    assert "ResponsePlanRead" in schemas
    plan_schema = schemas["ResponsePlanRead"]
    plan_example = plan_schema.get("example") or plan_schema.get("examples", [{}])[0]
    assert plan_example["metrics"]["routing_source"] == "OSM_BASE_TRAVEL_TIME"
    assert plan_example["score_breakdown"]["traffic_source"] == "OSM_BASE_TRAVEL_TIME"
    assert "plan_version" in plan_example
    assert "incident_version" in plan_example

    assert "ApprovalResult" in schemas
    appr_schema = schemas["ApprovalResult"]
    appr_example = appr_schema.get("example") or appr_schema.get("examples", [{}])[0]
    assert appr_example["incident_status"] in ("RESPONSE_ACTIVE", "ACTIVE_UNCONFIRMED")
    assert "approval" in appr_example
    assert "expected_incident_version" in appr_example["approval"]
    assert "expected_plan_version" in appr_example["approval"]


def test_map_route_contracts_exposed_without_live_labels(client: TestClient) -> None:
    """Verify map layer and route preview schemas remain exposed without live/TomTom labels."""
    response = client.get("/openapi.json")
    openapi = response.json()
    schemas = openapi.get("components", {}).get("schemas", {})

    assert "MapLayerResponse" in schemas
    map_schema = schemas["MapLayerResponse"]
    map_example = map_schema.get("example") or map_schema.get("examples", [{}])[0]
    assert map_example["provenance"]["data_reality"] == "REAL_DERIVED"
    assert map_example["provenance"]["freshness_status"] == "STATIC"

    assert "RoutePreviewResponse" in schemas
    route_schema = schemas["RoutePreviewResponse"]
    route_example = route_schema.get("example") or route_schema.get("examples", [{}])[0]
    assert route_example["routing_source"] == "OSM_BASE_TRAVEL_TIME"
    assert "TomTom" not in str(route_example)
    assert "live traffic" not in str(route_example).lower()

