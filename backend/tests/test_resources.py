from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
import json
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import init_db
from app.main import app
from app.models import EmergencyResource, Incident, ResponsePlan, TimelineEvent
from app.routing import load_routing_graph, snap_coordinate_to_graph
from app.schemas import (
    ConfidenceLevel,
    Coordinate,
    DataReality,
    FreshnessStatus,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)
from app.resources import interpolate_route_progress, is_planner_eligible
from app.seed import DEFAULT_SCENARIO_PATH, main as seed_main, seed_resources
from app.websocket import operations_manager, reset_operations_stream


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    """Initialize all model tables on the isolated test engine."""
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_is_planner_eligible_pure_helper() -> None:
    """Verify is_planner_eligible returns True only for AVAILABLE and unassigned resources."""
    # Available with no assigned incident -> eligible
    available_resource = EmergencyResource(
        id="res-avail-01",
        name="Ambulance 01",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        latitude=30.06,
        longitude=31.33,
        assigned_incident_id=None,
    )
    assert is_planner_eligible(available_resource) is True

    # Available but assigned to an incident -> NOT eligible
    assigned_available = EmergencyResource(
        id="res-avail-02",
        name="Ambulance 02",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        latitude=30.06,
        longitude=31.33,
        assigned_incident_id="inc-123",
    )
    assert is_planner_eligible(assigned_available) is False

    # Status ASSIGNED -> NOT eligible
    assigned_status = EmergencyResource(
        id="res-assigned-01",
        name="Ambulance 03",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.ASSIGNED,
        latitude=30.06,
        longitude=31.33,
        assigned_incident_id="inc-123",
    )
    assert is_planner_eligible(assigned_status) is False

    # Out of service -> NOT eligible
    oos_resource = EmergencyResource(
        id="res-oos-01",
        name="Ambulance 04",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.OUT_OF_SERVICE,
        latitude=30.06,
        longitude=31.33,
        assigned_incident_id=None,
    )
    assert is_planner_eligible(oos_resource) is False

    # Dict input support
    assert is_planner_eligible({"status": "AVAILABLE", "assigned_incident_id": None}) is True
    assert is_planner_eligible({"status": "AVAILABLE", "assigned_incident_id": "inc-456"}) is False
    assert is_planner_eligible({"status": "OUT_OF_SERVICE", "assigned_incident_id": None}) is False


def test_seed_resources_creates_expected_counts(db_session: Session) -> None:
    """Verify seed populates DB with >=3 ambulances and >=2 fire/rescue resources."""
    seeded = seed_resources(db=db_session)
    assert len(seeded) >= 5

    resources = db_session.scalars(select(EmergencyResource)).all()
    ambulances = [r for r in resources if r.resource_type == ResourceType.AMBULANCE]
    fire_rescue = [r for r in resources if r.resource_type == ResourceType.FIRE_RESCUE]

    assert len(ambulances) >= 3, f"Expected at least 3 ambulances, found {len(ambulances)}"
    assert len(fire_rescue) >= 2, f"Expected at least 2 fire rescue units, found {len(fire_rescue)}"


def test_seed_resources_is_idempotent(db_session: Session) -> None:
    """Verify running seed twice leaves count, IDs, and existing user changes unchanged."""
    seed_resources(db=db_session)
    initial_resources = db_session.scalars(select(EmergencyResource)).all()
    initial_count = len(initial_resources)
    initial_ids = {r.id for r in initial_resources}

    # Simulate an operational modification by a user
    target_res = initial_resources[0]
    target_id = target_res.id
    target_res.name = "Renamed By Operator"
    db_session.commit()

    # Second seed run
    second_run_result = seed_resources(db=db_session)
    # No new resources added on second run
    assert len(second_run_result) == 0

    after_resources = db_session.scalars(select(EmergencyResource)).all()
    assert len(after_resources) == initial_count
    assert {r.id for r in after_resources} == initial_ids

    # User change was preserved
    re_queried = db_session.get(EmergencyResource, target_id)
    assert re_queried is not None
    assert re_queried.name == "Renamed By Operator"


def test_seed_resources_provenance_labels_are_simulated(db_session: Session) -> None:
    """Verify all seeded resources carry SIMULATED data reality and valid provenance."""
    seed_resources(db=db_session)
    resources = db_session.scalars(select(EmergencyResource)).all()

    for res in resources:
        provenance = res.provenance_json
        assert isinstance(provenance, dict), f"Resource {res.id} missing provenance_json dict"
        assert provenance.get("data_reality") == DataReality.SIMULATED.value
        assert provenance.get("freshness_status") in (
            FreshnessStatus.FRESH.value,
            FreshnessStatus.STATIC.value,
        )
        assert "source" in provenance
        assert "source_reference" in provenance


def test_scenario_coordinates_snap_within_threshold() -> None:
    """Verify all scenario coordinates snap within settings.MAX_ROUTE_SNAP_DISTANCE_M."""
    assert DEFAULT_SCENARIO_PATH.exists(), f"Scenario file not found at {DEFAULT_SCENARIO_PATH}"
    with open(DEFAULT_SCENARIO_PATH, encoding="utf-8") as f:
        scenario_data = json.load(f)

    resources_list = scenario_data.get("resources", scenario_data)
    assert isinstance(resources_list, list) and len(resources_list) >= 5

    graph = load_routing_graph()
    for res_dict in resources_list:
        lat = res_dict.get("latitude", res_dict.get("location", {}).get("lat"))
        lon = res_dict.get("longitude", res_dict.get("location", {}).get("lon"))
        assert lat is not None and lon is not None

        coord = Coordinate(lat=lat, lon=lon)
        node, snap_dist = snap_coordinate_to_graph(
            graph,
            coord,
            max_distance_m=settings.MAX_ROUTE_SNAP_DISTANCE_M,
        )
        assert node is not None
        assert snap_dist <= settings.MAX_ROUTE_SNAP_DISTANCE_M, (
            f"Resource {res_dict.get('id')} snap distance {snap_dist}m exceeds "
            f"threshold {settings.MAX_ROUTE_SNAP_DISTANCE_M}m"
        )


def test_api_get_resources_list(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/resources returns full list with required fields and filter support."""
    seed_resources(db=db_session)

    # 1. Unfiltered list
    response = client.get("/api/v1/resources")
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 5

    for item in data:
        assert "id" in item
        assert "version" in item
        assert "name" in item
        assert "resource_type" in item
        assert "capabilities" in item or "capability_tags" in item
        assert "status" in item
        assert "latitude" in item
        assert "longitude" in item
        assert "home_zone" in item
        assert "assigned_incident_id" in item
        assert "last_updated" in item
        assert "provenance" in item
        assert item["provenance"]["data_reality"] == DataReality.SIMULATED.value
        assert "is_planner_eligible" in item

    # 2. Filter by resource_type=AMBULANCE
    amb_resp = client.get("/api/v1/resources?resource_type=AMBULANCE")
    assert amb_resp.status_code == 200
    amb_data = amb_resp.json()
    assert len(amb_data) >= 3
    assert all(item["resource_type"] == "AMBULANCE" for item in amb_data)

    # 3. Filter by resource_type=FIRE_RESCUE
    fire_resp = client.get("/api/v1/resources?resource_type=FIRE_RESCUE")
    assert fire_resp.status_code == 200
    fire_data = fire_resp.json()
    assert len(fire_data) >= 2
    assert all(item["resource_type"] == "FIRE_RESCUE" for item in fire_data)


def test_api_get_resource_detail(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/resources/{resource_id} returns exact resource details."""
    seed_resources(db=db_session)
    first_res = db_session.scalars(select(EmergencyResource)).first()
    assert first_res is not None

    response = client.get(f"/api/v1/resources/{first_res.id}")
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["id"] == first_res.id
    assert item["name"] == first_res.name
    assert item["resource_type"] == first_res.resource_type.value
    assert item["status"] == first_res.status.value
    assert item["latitude"] == first_res.latitude
    assert item["longitude"] == first_res.longitude
    assert item["provenance"]["data_reality"] == DataReality.SIMULATED.value


def test_api_get_resource_not_found_returns_404(client: TestClient) -> None:
    """Verify GET /api/v1/resources/{resource_id} for a non-existent ID returns 404."""
    response = client.get("/api/v1/resources/non-existent-resource-id")
    assert response.status_code == 404
    assert "not found" in response.json().get("detail", "").lower()


def test_unavailable_and_assigned_units_not_planner_eligible(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify unavailable/assigned units are visible in API but marked not planner eligible."""
    seed_resources(db=db_session)
    response = client.get("/api/v1/resources")
    assert response.status_code == 200
    resources = response.json()

    # Find assigned unit
    assigned_units = [r for r in resources if r.get("assigned_incident_id")]
    assert len(assigned_units) >= 1, "Expected at least one assigned resource fixture"
    for unit in assigned_units:
        assert unit["is_planner_eligible"] is False

    # Find non-available unit (e.g. OUT_OF_SERVICE)
    non_avail_units = [r for r in resources if r.get("status") != ResourceStatus.AVAILABLE.value]
    assert len(non_avail_units) >= 1, "Expected at least one non-available resource fixture"
    for unit in non_avail_units:
        assert unit["is_planner_eligible"] is False

    # Available and unassigned units
    avail_units = [
        r
        for r in resources
        if r.get("status") == ResourceStatus.AVAILABLE.value and not r.get("assigned_incident_id")
    ]
    assert len(avail_units) >= 1
    for unit in avail_units:
        assert unit["is_planner_eligible"] is True


def test_seed_main_cli_execution(capsys: pytest.CaptureFixture[str], db_session: Session) -> None:
    """Verify seed_main() executes cleanly, seeds records, and prints completion message."""
    seed_main()
    captured = capsys.readouterr().out
    assert "SirenGrid seed completed" in captured
    assert "new resource(s) inserted" in captured

    resources = db_session.scalars(select(EmergencyResource)).all()
    assert len(resources) >= 5

    # Run seed_main() again to verify idempotent output
    seed_main()
    captured_second = capsys.readouterr().out
    assert "0 new resource(s) inserted" in captured_second


def _create_test_incident(
    db: Session,
    incident_id: str | None = None,
    version: int = 1,
    status: IncidentStatus = IncidentStatus.ACTIVE_UNCONFIRMED,
) -> Incident:
    if incident_id is None:
        incident_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)
    inc = Incident(
        id=incident_id,
        version=version,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=status,
        latitude=30.0561,
        longitude=31.3452,
        location_text="Nasr City test incident",
        casualty_count=1,
        casualty_range="1",
        trapped_person=False,
        road_blockage=False,
        required_resources_json=[
            {"resource_type": "AMBULANCE", "count": 1},
        ],
        current_plan_id=None,
        created_at=now_utc,
        updated_at=now_utc,
        provenance_json={
            "source": "operator_manual_entry",
            "data_reality": DataReality.SIMULATED.value,
            "freshness_status": FreshnessStatus.FRESH.value,
            "last_updated": now_utc.isoformat(),
            "source_reference": "test-op",
        },
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return inc


def _create_test_resource(
    db: Session,
    resource_id: str = "res-test-01",
    version: int = 1,
    status: ResourceStatus = ResourceStatus.AVAILABLE,
    assigned_incident_id: str | None = None,
    resource_type: ResourceType = ResourceType.AMBULANCE,
) -> EmergencyResource:
    now_utc = datetime.now(timezone.utc)
    res = EmergencyResource(
        id=resource_id,
        version=version,
        name="Test Unit 01",
        resource_type=resource_type,
        capability_tags_json=["basic_life_support"],
        status=status,
        latitude=30.0565,
        longitude=31.3450,
        home_zone="Nasr City",
        assigned_incident_id=assigned_incident_id,
        last_updated=now_utc,
        provenance_json={
            "source": "operator_manual_entry",
            "data_reality": DataReality.SIMULATED.value,
            "freshness_status": FreshnessStatus.FRESH.value,
            "last_updated": now_utc.isoformat(),
            "source_reference": "initial_seed",
        },
    )
    db.add(res)
    db.commit()
    db.refresh(res)
    return res


def test_resource_assign_success(client: TestClient, db_session: Session) -> None:
    """Verify POST /api/v1/resources/{resource_id}/assign atomically assigns resource and appends timeline event."""
    inc = _create_test_incident(db_session)
    res = _create_test_resource(db_session, "res-assign-01", version=1)

    payload = {
        "incident_id": inc.id,
        "expected_resource_version": 1,
        "operator_reference": "disp-assign-01",
    }
    response = client.post(f"/api/v1/resources/{res.id}/assign", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == res.id
    assert data["version"] == 2
    assert data["status"] == ResourceStatus.ASSIGNED.value
    assert data["operational_status"] == ResourceStatus.ASSIGNED.value
    assert data["assigned_incident_id"] == inc.id
    assert data["assignment"] == inc.id
    assert data["is_planner_eligible"] is False
    assert data["provenance"]["data_reality"] == DataReality.SIMULATED.value
    assert data["provenance"]["freshness_status"] == FreshnessStatus.FRESH.value
    assert data["provenance"]["source_reference"] == "disp-assign-01"
    assert data["provenance"]["last_updated"] is not None

    # Check persisted DB record
    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 2
    assert persisted.status == ResourceStatus.ASSIGNED
    assert persisted.assigned_incident_id == inc.id

    # Check incident timeline event
    events = db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.incident_id == inc.id)
    ).all()
    assert len(events) == 1
    assert events[0].event_type == "RESOURCE_ASSIGNED"
    assert events[0].details_json["resource_id"] == res.id
    assert events[0].details_json["resource_version"] == 2
    assert events[0].details_json["incident_id"] == inc.id
    assert events[0].details_json["operator_reference"] == "disp-assign-01"


def test_resource_assign_stale_conflict_no_mutation(client: TestClient, db_session: Session) -> None:
    """Verify assign with stale expected version returns 409 with zero mutation."""
    inc = _create_test_incident(db_session)
    res = _create_test_resource(db_session, "res-stale-01", version=1)

    payload = {
        "incident_id": inc.id,
        "expected_resource_version": 99,
        "operator_reference": "disp-stale-01",
    }
    response = client.post(f"/api/v1/resources/{res.id}/assign", json=payload)
    assert response.status_code == 409
    assert "stale" in response.json().get("detail", "").lower()

    # Zero mutation in DB
    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 1
    assert persisted.status == ResourceStatus.AVAILABLE
    assert persisted.assigned_incident_id is None

    # Zero timeline events
    events = db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.incident_id == inc.id)
    ).all()
    assert len(events) == 0


def test_resource_assign_already_assigned_rejection(client: TestClient, db_session: Session) -> None:
    """Verify assigning an already assigned resource returns 409 with zero mutation."""
    inc1 = _create_test_incident(db_session)
    inc2 = _create_test_incident(db_session)
    res = _create_test_resource(
        db_session,
        "res-already-assigned",
        version=2,
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=inc1.id,
    )

    payload = {
        "incident_id": inc2.id,
        "expected_resource_version": 2,
        "operator_reference": "disp-dup-01",
    }
    response = client.post(f"/api/v1/resources/{res.id}/assign", json=payload)
    assert response.status_code == 409
    assert "already assigned" in response.json().get("detail", "").lower()

    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 2
    assert persisted.assigned_incident_id == inc1.id

    events = db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.incident_id == inc2.id)
    ).all()
    assert len(events) == 0


def test_resource_assign_unavailable_rejection(client: TestClient, db_session: Session) -> None:
    """Verify assigning an unavailable (OUT_OF_SERVICE) resource returns 409 with zero mutation."""
    inc = _create_test_incident(db_session)
    res = _create_test_resource(
        db_session,
        "res-oos-assign",
        version=1,
        status=ResourceStatus.OUT_OF_SERVICE,
    )

    payload = {
        "incident_id": inc.id,
        "expected_resource_version": 1,
        "operator_reference": "disp-oos-01",
    }
    response = client.post(f"/api/v1/resources/{res.id}/assign", json=payload)
    assert response.status_code == 409
    assert "available" in response.json().get("detail", "").lower()

    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 1
    assert persisted.status == ResourceStatus.OUT_OF_SERVICE
    assert persisted.assigned_incident_id is None


def test_resource_assign_missing_incident_returns_409(client: TestClient, db_session: Session) -> None:
    """Verify assign with non-existent incident returns 409 conflict with zero mutation."""
    res = _create_test_resource(db_session, "res-missing-inc", version=1)

    payload = {
        "incident_id": "nonexistent-inc-id",
        "expected_resource_version": 1,
        "operator_reference": "disp-missing-inc",
    }
    response = client.post(f"/api/v1/resources/{res.id}/assign", json=payload)
    assert response.status_code == 409
    assert "not found" in response.json().get("detail", "").lower()

    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 1
    assert persisted.status == ResourceStatus.AVAILABLE


def test_resource_assign_missing_resource_returns_404(client: TestClient, db_session: Session) -> None:
    """Verify assign for non-existent resource returns 404."""
    inc = _create_test_incident(db_session)
    payload = {
        "incident_id": inc.id,
        "expected_resource_version": 1,
        "operator_reference": "disp-missing-res",
    }
    response = client.post("/api/v1/resources/nonexistent-resource-id/assign", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json().get("detail", "").lower()


def test_resource_state_patch_unassigned_available_and_out_of_service(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify PATCH /api/v1/resources/{resource_id}/state transitions unassigned unit to OUT_OF_SERVICE and back to AVAILABLE."""
    res = _create_test_resource(db_session, "res-state-unassigned", version=1)

    # Transition AVAILABLE -> OUT_OF_SERVICE
    payload1 = {
        "status": ResourceStatus.OUT_OF_SERVICE.value,
        "expected_resource_version": 1,
        "operator_reference": "disp-oos",
    }
    resp1 = client.patch(f"/api/v1/resources/{res.id}/state", json=payload1)
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert data1["version"] == 2
    assert data1["status"] == ResourceStatus.OUT_OF_SERVICE.value
    assert data1["is_planner_eligible"] is False
    assert data1["assigned_incident_id"] is None

    # Transition OUT_OF_SERVICE -> AVAILABLE
    payload2 = {
        "status": ResourceStatus.AVAILABLE.value,
        "expected_resource_version": 2,
        "operator_reference": "disp-avail",
    }
    resp2 = client.patch(f"/api/v1/resources/{res.id}/state", json=payload2)
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["version"] == 3
    assert data2["status"] == ResourceStatus.AVAILABLE.value
    assert data2["is_planner_eligible"] is True
    assert data2["assigned_incident_id"] is None

    # Verify no dummy timeline events were created
    events = db_session.scalars(select(TimelineEvent)).all()
    assert len(events) == 0


def test_resource_state_patch_unassigned_rejects_assignment_or_invalid_status(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify PATCH /state on unassigned unit rejects status ASSIGNED, EN_ROUTE, or providing incident_id."""
    res = _create_test_resource(db_session, "res-unassigned-reject", version=1)

    # Attempt to assign via state patch
    resp1 = client.patch(
        f"/api/v1/resources/{res.id}/state",
        json={
            "status": ResourceStatus.ASSIGNED.value,
            "expected_resource_version": 1,
            "operator_reference": "disp-bad",
        },
    )
    assert resp1.status_code == 409

    # Attempt to pass incident_id on unassigned unit
    resp2 = client.patch(
        f"/api/v1/resources/{res.id}/state",
        json={
            "status": ResourceStatus.AVAILABLE.value,
            "expected_resource_version": 1,
            "operator_reference": "disp-bad",
            "incident_id": "inc-some-id",
        },
    )
    assert resp2.status_code == 409

    # Attempt EN_ROUTE on unassigned unit
    resp3 = client.patch(
        f"/api/v1/resources/{res.id}/state",
        json={
            "status": ResourceStatus.EN_ROUTE.value,
            "expected_resource_version": 1,
            "operator_reference": "disp-bad",
        },
    )
    assert resp3.status_code == 409

    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 1
    assert persisted.status == ResourceStatus.AVAILABLE


def test_resource_state_patch_assigned_valid_progression(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify PATCH /state on assigned unit progression: ASSIGNED -> EN_ROUTE -> ON_SCENE -> TRANSPORTING."""
    inc = _create_test_incident(db_session)
    res = _create_test_resource(
        db_session,
        "res-assigned-prog",
        version=2,
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=inc.id,
    )

    # 1. ASSIGNED -> EN_ROUTE
    p1 = {
        "status": ResourceStatus.EN_ROUTE.value,
        "expected_resource_version": 2,
        "operator_reference": "disp-enroute",
        "incident_id": inc.id,
    }
    r1 = client.patch(f"/api/v1/resources/{res.id}/state", json=p1)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["version"] == 3
    assert d1["status"] == ResourceStatus.EN_ROUTE.value

    # 2. EN_ROUTE -> ON_SCENE
    p2 = {
        "status": ResourceStatus.ON_SCENE.value,
        "expected_resource_version": 3,
        "operator_reference": "disp-onscene",
        "incident_id": inc.id,
    }
    r2 = client.patch(f"/api/v1/resources/{res.id}/state", json=p2)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["version"] == 4
    assert d2["status"] == ResourceStatus.ON_SCENE.value

    # 3. ON_SCENE -> TRANSPORTING
    p3 = {
        "status": ResourceStatus.TRANSPORTING.value,
        "expected_resource_version": 4,
        "operator_reference": "disp-transport",
        "incident_id": inc.id,
    }
    r3 = client.patch(f"/api/v1/resources/{res.id}/state", json=p3)
    assert r3.status_code == 200, r3.text
    d3 = r3.json()
    assert d3["version"] == 5
    assert d3["status"] == ResourceStatus.TRANSPORTING.value

    # Verify timeline events
    events = db_session.scalars(
        select(TimelineEvent)
        .where(TimelineEvent.incident_id == inc.id)
        .order_by(TimelineEvent.created_at.asc(), TimelineEvent.id.asc())
    ).all()
    assert len(events) == 3
    assert all(e.event_type == "RESOURCE_STATUS_CHANGED" for e in events)
    assert events[0].details_json["status"] == ResourceStatus.EN_ROUTE.value
    assert events[1].details_json["status"] == ResourceStatus.ON_SCENE.value
    assert events[2].details_json["status"] == ResourceStatus.TRANSPORTING.value


def test_resource_state_patch_assigned_rejects_cross_incident(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify PATCH /state on assigned unit rejects cross-incident mutation or missing incident_id."""
    inc1 = _create_test_incident(db_session)
    inc2 = _create_test_incident(db_session)
    res = _create_test_resource(
        db_session,
        "res-cross-inc",
        version=2,
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=inc1.id,
    )

    # Missing incident_id
    resp1 = client.patch(
        f"/api/v1/resources/{res.id}/state",
        json={
            "status": ResourceStatus.EN_ROUTE.value,
            "expected_resource_version": 2,
            "operator_reference": "disp-bad",
        },
    )
    assert resp1.status_code == 409
    assert "owning incident_id is required" in resp1.json().get("detail", "").lower()

    # Wrong incident_id
    resp2 = client.patch(
        f"/api/v1/resources/{res.id}/state",
        json={
            "status": ResourceStatus.EN_ROUTE.value,
            "expected_resource_version": 2,
            "operator_reference": "disp-bad",
            "incident_id": inc2.id,
        },
    )
    assert resp2.status_code == 409
    assert "cross-incident" in resp2.json().get("detail", "").lower()

    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 2
    assert persisted.status == ResourceStatus.ASSIGNED


def test_resource_state_patch_assigned_rejects_available_without_release(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify PATCH /state on assigned unit rejects status AVAILABLE (must use release endpoint)."""
    inc = _create_test_incident(db_session)
    res = _create_test_resource(
        db_session,
        "res-no-avail-patch",
        version=2,
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=inc.id,
    )

    resp = client.patch(
        f"/api/v1/resources/{res.id}/state",
        json={
            "status": ResourceStatus.AVAILABLE.value,
            "expected_resource_version": 2,
            "operator_reference": "disp-bad",
            "incident_id": inc.id,
        },
    )
    assert resp.status_code == 409
    assert "release" in resp.json().get("detail", "").lower()

    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 2
    assert persisted.status == ResourceStatus.ASSIGNED


def test_resource_state_patch_stale_conflict(client: TestClient, db_session: Session) -> None:
    """Verify PATCH /state with stale expected version returns 409 with zero mutation."""
    inc = _create_test_incident(db_session)
    res = _create_test_resource(
        db_session,
        "res-stale-patch",
        version=2,
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=inc.id,
    )

    resp = client.patch(
        f"/api/v1/resources/{res.id}/state",
        json={
            "status": ResourceStatus.EN_ROUTE.value,
            "expected_resource_version": 1,
            "operator_reference": "disp-stale",
            "incident_id": inc.id,
        },
    )
    assert resp.status_code == 409
    assert "stale" in resp.json().get("detail", "").lower()

    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 2
    assert persisted.status == ResourceStatus.ASSIGNED


def test_resource_release_success(client: TestClient, db_session: Session) -> None:
    """Verify POST /api/v1/resources/{resource_id}/release atomically clears assignment, sets AVAILABLE, increments version, and records timeline event."""
    inc = _create_test_incident(db_session)
    res = _create_test_resource(
        db_session,
        "res-release-ok",
        version=2,
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=inc.id,
    )

    payload = {
        "incident_id": inc.id,
        "expected_resource_version": 2,
        "operator_reference": "disp-rel-01",
    }
    response = client.post(f"/api/v1/resources/{res.id}/release", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == res.id
    assert data["version"] == 3
    assert data["status"] == ResourceStatus.AVAILABLE.value
    assert data["operational_status"] == ResourceStatus.AVAILABLE.value
    assert data["assigned_incident_id"] is None
    assert data["assignment"] is None
    assert data["is_planner_eligible"] is True
    assert data["provenance"]["data_reality"] == DataReality.SIMULATED.value
    assert data["provenance"]["freshness_status"] == FreshnessStatus.FRESH.value
    assert data["provenance"]["source_reference"] == "disp-rel-01"

    # Verify DB
    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 3
    assert persisted.status == ResourceStatus.AVAILABLE
    assert persisted.assigned_incident_id is None

    # Verify timeline event
    events = db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.incident_id == inc.id)
    ).all()
    assert len(events) == 1
    assert events[0].event_type == "RESOURCE_RELEASED"
    assert events[0].details_json["resource_id"] == res.id
    assert events[0].details_json["resource_version"] == 3
    assert events[0].details_json["status"] == ResourceStatus.AVAILABLE.value


def test_resource_release_wrong_incident_rejection(client: TestClient, db_session: Session) -> None:
    """Verify release requested by wrong incident returns 409 with zero mutation."""
    inc1 = _create_test_incident(db_session)
    inc2 = _create_test_incident(db_session)
    res = _create_test_resource(
        db_session,
        "res-wrong-rel",
        version=2,
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=inc1.id,
    )

    payload = {
        "incident_id": inc2.id,
        "expected_resource_version": 2,
        "operator_reference": "disp-wrong",
    }
    response = client.post(f"/api/v1/resources/{res.id}/release", json=payload)
    assert response.status_code == 409
    assert "wrong incident" in response.json().get("detail", "").lower()

    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 2
    assert persisted.assigned_incident_id == inc1.id


def test_resource_release_already_unassigned_rejection(client: TestClient, db_session: Session) -> None:
    """Verify release of already unassigned resource returns 409 with zero mutation."""
    inc = _create_test_incident(db_session)
    res = _create_test_resource(db_session, "res-unassigned-rel", version=1)

    payload = {
        "incident_id": inc.id,
        "expected_resource_version": 1,
        "operator_reference": "disp-unassigned",
    }
    response = client.post(f"/api/v1/resources/{res.id}/release", json=payload)
    assert response.status_code == 409
    assert "already unassigned" in response.json().get("detail", "").lower()

    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 1
    assert persisted.status == ResourceStatus.AVAILABLE


def test_resource_release_stale_version_rejection(client: TestClient, db_session: Session) -> None:
    """Verify release with stale version returns 409 with zero mutation."""
    inc = _create_test_incident(db_session)
    res = _create_test_resource(
        db_session,
        "res-stale-rel",
        version=2,
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=inc.id,
    )

    payload = {
        "incident_id": inc.id,
        "expected_resource_version": 1,
        "operator_reference": "disp-stale",
    }
    response = client.post(f"/api/v1/resources/{res.id}/release", json=payload)
    assert response.status_code == 409
    assert "stale" in response.json().get("detail", "").lower()

    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, res.id)
    assert persisted is not None
    assert persisted.version == 2
    assert persisted.status == ResourceStatus.ASSIGNED


def test_concurrent_resource_assignment_yields_one_winner(
    db_session: Session,
) -> None:
    """Concurrency regression: two simultaneous assignment attempts for one resource to different incidents yield exactly one success, exactly one owning incident, and no duplicate assignment/timeline mutation."""
    inc_a = _create_test_incident(db_session)
    inc_b = _create_test_incident(db_session)
    res = _create_test_resource(db_session, "res-concurrent-lock", version=1)

    def attempt_assignment(target_inc_id: str, op_ref: str) -> tuple[int, dict]:
        # Using a dedicated client per thread
        thread_client = TestClient(app)
        resp = thread_client.post(
            f"/api/v1/resources/{res.id}/assign",
            json={
                "incident_id": target_inc_id,
                "expected_resource_version": 1,
                "operator_reference": op_ref,
            },
        )
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {"detail": resp.text}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_assignment, inc_a.id, "op-a")
        f2 = executor.submit(attempt_assignment, inc_b.id, "op-b")
        status1, data1 = f1.result(timeout=10.0)
        status2, data2 = f2.result(timeout=10.0)

    statuses = [status1, status2]
    assert statuses.count(200) == 1, f"Expected exactly one 200, got {statuses}. Data: {data1}, {data2}"
    assert statuses.count(409) == 1, f"Expected exactly one 409, got {statuses}. Data: {data1}, {data2}"

    # Verify persisted DB state
    db_session.expire_all()
    final_res = db_session.get(EmergencyResource, res.id)
    assert final_res is not None
    assert final_res.version == 2
    assert final_res.status == ResourceStatus.ASSIGNED
    assert final_res.assigned_incident_id in (inc_a.id, inc_b.id)

    # Verify exactly one timeline event across both incidents
    all_events = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id.in_([inc_a.id, inc_b.id]),
            TimelineEvent.event_type == "RESOURCE_ASSIGNED",
        )
    ).all()
    assert len(all_events) == 1
    assert all_events[0].incident_id == final_res.assigned_incident_id
    assert all_events[0].details_json["resource_id"] == res.id
    assert all_events[0].details_json["resource_version"] == 2


def test_no_unavailable_resource_fallback_in_planning(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify that taking the last eligible ambulance OUT_OF_SERVICE causes planning to reject with 409 rather than falling back to unavailable resources."""
    seed_resources(db=db_session)
    ambulances = db_session.scalars(
        select(EmergencyResource).where(
            EmergencyResource.resource_type == ResourceType.AMBULANCE
        )
    ).all()
    assert len(ambulances) >= 3

    # Mark all ambulances except the first one as ASSIGNED to dummy incidents
    dummy_inc = _create_test_incident(db_session)
    for amb in ambulances[1:]:
        amb.status = ResourceStatus.ASSIGNED
        amb.assigned_incident_id = dummy_inc.id
        amb.version = amb.version + 1
    db_session.commit()

    # The first ambulance is the only AVAILABLE one
    last_amb = ambulances[0]
    assert last_amb.status == ResourceStatus.AVAILABLE

    # Now transition the last ambulance to OUT_OF_SERVICE via PATCH /state
    patch_resp = client.patch(
        f"/api/v1/resources/{last_amb.id}/state",
        json={
            "status": ResourceStatus.OUT_OF_SERVICE.value,
            "expected_resource_version": last_amb.version,
            "operator_reference": "disp-oos-test",
        },
    )
    assert patch_resp.status_code == 200

    # Create an incident requiring 1 AMBULANCE at AWAITING_APPROVAL (ready for plan generation)
    target_inc = _create_test_incident(
        db_session,
        status=IncidentStatus.AWAITING_APPROVAL,
    )
    target_inc.required_resources_json = [{"resource_type": "AMBULANCE", "count": 1}]
    db_session.commit()

    # Attempt candidate response planning
    plan_resp = client.post(f"/api/v1/incidents/{target_inc.id}/plans/generate")
    assert plan_resp.status_code == 409
    assert "insufficient eligible" in plan_resp.json().get("detail", "").lower()


def _create_test_approved_plan(
    db: Session,
    incident: Incident,
    resource: EmergencyResource,
    coordinates: list[list[float]] | None = None,
    plan_id: str = "plan-mov-test-01",
) -> ResponsePlan:
    if coordinates is None:
        coordinates = [
            [31.3400, 30.0500],
            [31.3450, 30.0550],
            [31.3500, 30.0600],
        ]
    plan = ResponsePlan(
        id=plan_id,
        incident_id=incident.id,
        incident_version=incident.version,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=[resource.id],
        routes_json=[
            {
                "resource_id": resource.id,
                "route_id": f"{plan_id}:{resource.id}",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
                "distance_m": 1500.0,
                "eta_seconds": 180.0,
                "routing_source": "OSM_BASE_TRAVEL_TIME",
            }
        ],
        metrics_json={"routing_source": "OSM_BASE_TRAVEL_TIME"},
        score_breakdown_json={"algorithm": "MIN_BASE_ROUTE_ETA"},
        created_at=datetime.now(timezone.utc),
    )
    incident.current_plan_id = plan.id
    incident.status = IncidentStatus.RESPONSE_ACTIVE
    resource.assigned_incident_id = incident.id
    resource.status = ResourceStatus.ASSIGNED
    db.add(plan)
    db.commit()
    db.refresh(plan)
    db.refresh(incident)
    db.refresh(resource)
    return plan


def test_interpolate_route_progress_pure_helper() -> None:
    """Verify interpolate_route_progress correctly handles endpoints, uneven segments, and boundaries."""
    coords = [
        [31.3400, 30.0500],
        [31.3450, 30.0550],
        [31.3500, 30.0600],
    ]
    # 0.0 -> first coordinate
    p0 = interpolate_route_progress(coords, 0.0)
    assert p0 == (31.3400, 30.0500)

    # 1.0 -> final coordinate
    p1 = interpolate_route_progress(coords, 1.0)
    assert p1 == (31.3500, 30.0600)

    # The helper enforces the same closed interval as the API contract.
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        interpolate_route_progress(coords, -0.2)
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        interpolate_route_progress(coords, 1.5)

    # Unevenly spaced multi-segment geometry proving cumulative distance vs vertex count
    # Segment 0->1 is ~1110m (0.01 deg lat), Segment 1->2 is ~11m (0.0001 deg lat)
    uneven_coords = [
        [31.3400, 30.0500],
        [31.3400, 30.0600],
        [31.3400, 30.0601],
    ]
    mid = interpolate_route_progress(uneven_coords, 0.5)
    # Total distance is ~1121m, 50% is ~560m, so latitude must be halfway along segment 1 (~30.0550)
    # NOT near vertex 1 (30.0600) which would happen under vertex-count interpolation!
    assert abs(mid[0] - 31.3400) < 1e-6
    assert abs(mid[1] - 30.0550) < 0.001
    assert abs(mid[1] - 30.0600) > 0.004

    # Fewer than 2 coordinates raises ValueError
    with pytest.raises(ValueError, match="at least 2 points"):
        interpolate_route_progress([[31.34, 30.05]], 0.5)

    assert interpolate_route_progress(
        [[31.34, 30.05], [31.34, 30.05]],
        0.5,
    ) == (31.34, 30.05)


def test_resource_movement_success_full_lifecycle(client: TestClient, db_session: Session) -> None:
    """Verify successful 0.0, intermediate, and 1.0 movement along an approved route with all provenance and event requirements."""
    reset_operations_stream()

    inc = _create_test_incident(db_session, incident_id="inc-mov-01")
    res = _create_test_resource(db_session, resource_id="res-mov-01", status=ResourceStatus.AVAILABLE)
    coords = [
        [31.3400, 30.0500],
        [31.3450, 30.0550],
        [31.3500, 30.0600],
    ]
    plan = _create_test_approved_plan(db_session, inc, res, coordinates=coords)

    # Step 1: Initial movement at 0.0
    r0 = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": 0.0,
            "operator_reference": "disp-mov-01",
        },
    )
    assert r0.status_code == 200, r0.text
    d0 = r0.json()
    assert d0["version"] == 2
    assert d0["route_progress"] == 0.0
    assert d0["longitude"] == 31.3400
    assert d0["latitude"] == 30.0500
    assert d0["location"] == {"lat": 30.0500, "lon": 31.3400}
    assert d0["status"] == ResourceStatus.ASSIGNED.value  # Lifecycle status unchanged
    assert d0["provenance"]["data_reality"] == DataReality.SIMULATED.value
    assert d0["provenance"]["freshness_status"] == FreshnessStatus.FRESH.value
    assert d0["provenance"]["source_reference"] == "disp-mov-01"
    assert "speed" not in d0
    assert "eta" not in d0

    # Verify TimelineEvent in DB
    ev0 = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == inc.id,
            TimelineEvent.event_type == "RESOURCE_MOVED",
        )
    ).all()
    assert len(ev0) == 1
    assert ev0[0].details_json["resource_id"] == res.id
    assert ev0[0].details_json["incident_id"] == inc.id
    assert ev0[0].details_json["plan_id"] == plan.id
    assert ev0[0].details_json["previous_progress"] is None
    assert ev0[0].details_json["route_progress"] == 0.0
    assert ev0[0].details_json["coordinates"]["latitude"] == 30.0500
    assert ev0[0].details_json["coordinates"]["longitude"] == 31.3400
    assert ev0[0].details_json["operator_reference"] == "disp-mov-01"
    assert ev0[0].details_json["resource_version"] == 2
    assert ev0[0].details_json["source"] == "operator_movement_command"
    assert ev0[0].details_json["data_reality"] == DataReality.SIMULATED.value
    assert ev0[0].details_json["freshness_status"] == FreshnessStatus.FRESH.value

    # Step 2: Intermediate movement to 0.5
    r1 = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 2,
            "route_progress": 0.5,
            "operator_reference": "disp-mov-01",
        },
    )
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["version"] == 3
    assert d1["route_progress"] == 0.5
    assert abs(d1["longitude"] - 31.3450) < 1e-4
    assert abs(d1["latitude"] - 30.0550) < 1e-4

    ev1 = db_session.scalars(
        select(TimelineEvent)
        .where(
            TimelineEvent.incident_id == inc.id,
            TimelineEvent.event_type == "RESOURCE_MOVED",
        )
        .order_by(TimelineEvent.created_at.asc())
    ).all()
    assert len(ev1) == 2
    assert ev1[1].details_json["previous_progress"] == 0.0
    assert ev1[1].details_json["route_progress"] == 0.5
    assert ev1[1].details_json["resource_version"] == 3

    # Step 3: Movement to 1.0 (destination)
    r2 = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 3,
            "route_progress": 1.0,
            "operator_reference": "disp-mov-01",
        },
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["version"] == 4
    assert d2["route_progress"] == 1.0
    assert d2["longitude"] == 31.3500
    assert d2["latitude"] == 30.0600

    # Step 4: Verify canonical GET /resources/{id} persistence
    get_res = client.get(f"/api/v1/resources/{res.id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["version"] == 4
    assert get_data["route_progress"] == 1.0
    assert get_data["longitude"] == 31.3500
    assert get_data["latitude"] == 30.0600


def test_resource_movement_idempotency_no_mutation(client: TestClient, db_session: Session) -> None:
    """Verify repeated identical progress is idempotent: unchanged version, no timeline event, and no live event."""
    inc = _create_test_incident(db_session, incident_id="inc-idem-01")
    res = _create_test_resource(db_session, resource_id="res-idem-01")
    _create_test_approved_plan(db_session, inc, res)

    # Initial movement to 0.4
    r1 = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": 0.4,
            "operator_reference": "op-idem",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["version"] == 2
    assert r1.json()["route_progress"] == 0.4

    event_count_before = len(
        db_session.scalars(
            select(TimelineEvent).where(TimelineEvent.incident_id == inc.id)
        ).all()
    )
    seq_before = operations_manager.current_sequence

    # Repeat identical progress 0.4 with expected_resource_version = 2
    r2 = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 2,
            "route_progress": 0.4,
            "operator_reference": "op-idem",
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["version"] == 2
    assert d2["route_progress"] == 0.4

    # Verify zero mutation in DB and operations stream
    db_session.expire_all()
    event_count_after = len(
        db_session.scalars(
            select(TimelineEvent).where(TimelineEvent.incident_id == inc.id)
        ).all()
    )
    assert event_count_after == event_count_before
    assert operations_manager.current_sequence == seq_before


def test_resource_movement_rejects_backwards_progress(client: TestClient, db_session: Session) -> None:
    """Verify backwards movement progress is rejected with 409 and zero mutation."""
    inc = _create_test_incident(db_session, incident_id="inc-back-01")
    res = _create_test_resource(db_session, resource_id="res-back-01")
    _create_test_approved_plan(db_session, inc, res)

    # Move forward to 0.6
    r1 = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": 0.6,
            "operator_reference": "op-back",
        },
    )
    assert r1.status_code == 200
    lat_at_06 = r1.json()["latitude"]
    lon_at_06 = r1.json()["longitude"]

    event_count_before = len(
        db_session.scalars(
            select(TimelineEvent).where(TimelineEvent.incident_id == inc.id)
        ).all()
    )

    # Attempt backwards movement to 0.3
    r_back = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 2,
            "route_progress": 0.3,
            "operator_reference": "op-back",
        },
    )
    assert r_back.status_code == 409
    assert "backwards" in r_back.json().get("detail", "").lower()

    # Verify zero mutation
    db_session.expire_all()
    reloaded = db_session.get(EmergencyResource, res.id)
    assert reloaded is not None
    assert reloaded.version == 2
    assert reloaded.latitude == lat_at_06
    assert reloaded.longitude == lon_at_06

    event_count_after = len(
        db_session.scalars(
            select(TimelineEvent).where(TimelineEvent.incident_id == inc.id)
        ).all()
    )
    assert event_count_after == event_count_before


def test_resource_movement_bounds_and_input_validation(client: TestClient, db_session: Session) -> None:
    """Verify route_progress bounds [0.0, 1.0] and required string fields enforce 422 Unprocessable Entity."""
    inc = _create_test_incident(db_session, incident_id="inc-val-01")
    res = _create_test_resource(db_session, resource_id="res-val-01")
    _create_test_approved_plan(db_session, inc, res)

    # Negative progress -> 422
    r_neg = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": -0.05,
            "operator_reference": "op-val",
        },
    )
    assert r_neg.status_code == 422

    # Progress > 1.0 -> 422
    r_over = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": 1.05,
            "operator_reference": "op-val",
        },
    )
    assert r_over.status_code == 422

    # Boolean progress is not a numeric route-progress command.
    r_bool = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": True,
            "operator_reference": "op-val",
        },
    )
    assert r_bool.status_code == 422

    # Empty operator_reference -> 422
    r_no_op = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "   ",
        },
    )
    assert r_no_op.status_code == 422

    # Empty incident_id -> 422
    r_no_inc = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": "",
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "op-val",
        },
    )
    assert r_no_inc.status_code == 422


def test_resource_movement_conflict_safeguards_zero_mutation(client: TestClient, db_session: Session) -> None:
    """Verify absent entities return 404, while stale versions, unassigned status, cross-incident, and missing routes return 409 with zero mutation."""
    inc = _create_test_incident(db_session, incident_id="inc-safe-01")
    res = _create_test_resource(db_session, resource_id="res-safe-01")
    _create_test_approved_plan(db_session, inc, res)

    initial_lat = res.latitude
    initial_lon = res.longitude

    # 1. Absent resource -> 404
    r_no_res = client.patch(
        "/api/v1/resources/res-nonexistent-999/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "op-test",
        },
    )
    assert r_no_res.status_code == 404

    # 2. Absent incident -> 404
    r_no_inc = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": "inc-nonexistent-999",
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "op-test",
        },
    )
    assert r_no_inc.status_code == 404

    # 3. Stale resource version -> 409
    r_stale = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 99,
            "route_progress": 0.5,
            "operator_reference": "op-test",
        },
    )
    assert r_stale.status_code == 409
    assert "stale" in r_stale.json().get("detail", "").lower()

    # 4. Cross-incident mutation: resource assigned to inc-safe-01, requested for inc-other -> 409
    inc_other = _create_test_incident(db_session, incident_id="inc-other-01")
    r_cross = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc_other.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "op-test",
        },
    )
    assert r_cross.status_code == 409
    assert "cross-incident" in r_cross.json().get("detail", "").lower() or "assigned" in r_cross.json().get("detail", "").lower()

    # 5. Unassigned resource -> 409
    res_unassigned = _create_test_resource(db_session, resource_id="res-unassigned-01")
    r_unassigned = client.patch(
        f"/api/v1/resources/{res_unassigned.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "op-test",
        },
    )
    assert r_unassigned.status_code == 409
    assert "not assigned" in r_unassigned.json().get("detail", "").lower()

    # 6. Incident with no approved plan -> 409
    inc_unapproved = _create_test_incident(db_session, incident_id="inc-unapproved-01")
    res_in_unapproved = _create_test_resource(
        db_session,
        resource_id="res-in-unapproved-01",
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=inc_unapproved.id,
    )
    r_unapp = client.patch(
        f"/api/v1/resources/{res_in_unapproved.id}/movement",
        json={
            "incident_id": inc_unapproved.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "op-test",
        },
    )
    assert r_unapp.status_code == 409

    # 7. Approved plan does not contain route for requested resource -> 409
    res_no_route = _create_test_resource(
        db_session,
        resource_id="res-no-route-01",
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=inc.id,
    )
    r_no_route = client.patch(
        f"/api/v1/resources/{res_no_route.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "op-test",
        },
    )
    assert r_no_route.status_code == 409

    # Assert zero mutation on res
    db_session.expire_all()
    reloaded = db_session.get(EmergencyResource, res.id)
    assert reloaded is not None
    assert reloaded.version == 1
    assert reloaded.latitude == initial_lat
    assert reloaded.longitude == initial_lon


def test_resource_movement_uneven_multisegment_via_api(client: TestClient, db_session: Session) -> None:
    """Verify cumulative-distance interpolation along an uneven multi-segment route via real API call."""
    inc = _create_test_incident(db_session, incident_id="inc-uneven-01")
    res = _create_test_resource(db_session, resource_id="res-uneven-01")
    # Segment 1 is ~1110m (0.01 lat diff); Segment 2 is ~11m (0.0001 lat diff)
    uneven_coords = [
        [31.3400, 30.0500],
        [31.3400, 30.0600],
        [31.3400, 30.0601],
    ]
    _create_test_approved_plan(db_session, inc, res, coordinates=uneven_coords)

    resp = client.patch(
        f"/api/v1/resources/{res.id}/movement",
        json={
            "incident_id": inc.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "op-uneven",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert abs(data["longitude"] - 31.3400) < 1e-6
    # Halfway in distance lands on segment 1 (~30.0550), proving cumulative distance interpolation
    assert abs(data["latitude"] - 30.0550) < 0.001
    assert abs(data["latitude"] - 30.0600) > 0.004


def test_resource_movement_publishes_websocket_resource_updated(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify that a successful movement command delivers an authoritative resource.updated WebSocket event."""
    inc = _create_test_incident(db_session, incident_id="inc-ws-mov-01")
    res = _create_test_resource(db_session, resource_id="res-ws-mov-01")
    _create_test_approved_plan(db_session, inc, res)

    with client.websocket_connect("/api/v1/ws/operations") as ws:
        resp = client.patch(
            f"/api/v1/resources/{res.id}/movement",
            json={
                "incident_id": inc.id,
                "expected_resource_version": 1,
                "route_progress": 0.5,
                "operator_reference": "op-ws-mov",
            },
        )
        assert resp.status_code == 200

        msg = ws.receive_json()
        assert msg["event"] == "resource.updated"
        assert msg["incident_id"] == inc.id
        assert msg["version"] >= 1
        assert msg["payload"]["id"] == res.id
        assert msg["payload"]["version"] == 2
        assert msg["payload"]["route_progress"] == 0.5
        assert abs(msg["payload"]["latitude"] - 30.0550) < 1e-4
        assert abs(msg["payload"]["longitude"] - 31.3450) < 1e-4


def test_resource_movement_rejects_foreign_current_plan(
    client: TestClient,
    db_session: Session,
) -> None:
    """The current plan must belong to the requested incident, even if its route names the resource."""
    incident = _create_test_incident(db_session, incident_id="inc-own-route")
    foreign_incident = _create_test_incident(db_session, incident_id="inc-foreign-route")
    resource = _create_test_resource(
        db_session,
        resource_id="res-own-route",
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id=incident.id,
    )
    foreign_plan = ResponsePlan(
        id="plan-foreign-route",
        incident_id=foreign_incident.id,
        incident_version=foreign_incident.version,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=[resource.id],
        routes_json=[
            {
                "resource_id": resource.id,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[31.34, 30.05], [31.35, 30.06]],
                },
            }
        ],
        metrics_json={},
        score_breakdown_json={},
        created_at=datetime.now(timezone.utc),
    )
    incident.current_plan_id = foreign_plan.id
    db_session.add(foreign_plan)
    db_session.commit()

    response = client.patch(
        f"/api/v1/resources/{resource.id}/movement",
        json={
            "incident_id": incident.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "operator-foreign-plan",
        },
    )

    assert response.status_code == 409
    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, resource.id)
    assert persisted is not None
    assert persisted.version == 1
    assert persisted.provenance_json.get("movement") is None


def test_distinct_forward_progress_is_not_treated_as_idempotent(
    client: TestClient,
    db_session: Session,
) -> None:
    """Only an exactly repeated progress value is idempotent; no epsilon policy is invented."""
    incident = _create_test_incident(db_session, incident_id="inc-distinct-progress")
    resource = _create_test_resource(db_session, resource_id="res-distinct-progress")
    _create_test_approved_plan(db_session, incident, resource)

    first = client.patch(
        f"/api/v1/resources/{resource.id}/movement",
        json={
            "incident_id": incident.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "operator-progress",
        },
    )
    assert first.status_code == 200

    second = client.patch(
        f"/api/v1/resources/{resource.id}/movement",
        json={
            "incident_id": incident.id,
            "expected_resource_version": 2,
            "route_progress": 0.5000000005,
            "operator_reference": "operator-progress",
        },
    )

    assert second.status_code == 200
    assert second.json()["version"] == 3
    assert second.json()["route_progress"] == 0.5000000005
    events = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "RESOURCE_MOVED",
        )
    ).all()
    assert len(events) == 2


def test_release_and_reassignment_clear_previous_movement_state(
    client: TestClient,
    db_session: Session,
) -> None:
    """Movement progress is current assignment state and must not leak into a later assignment."""
    first_incident = _create_test_incident(db_session, incident_id="inc-first-assignment")
    second_incident = _create_test_incident(db_session, incident_id="inc-second-assignment")
    resource = _create_test_resource(db_session, resource_id="res-reassignment")
    _create_test_approved_plan(db_session, first_incident, resource)

    moved = client.patch(
        f"/api/v1/resources/{resource.id}/movement",
        json={
            "incident_id": first_incident.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "operator-move",
        },
    )
    assert moved.status_code == 200

    released = client.post(
        f"/api/v1/resources/{resource.id}/release",
        json={
            "incident_id": first_incident.id,
            "expected_resource_version": 2,
            "operator_reference": "operator-release",
        },
    )
    assert released.status_code == 200
    assert released.json()["route_progress"] is None
    assert "movement" not in released.json()["provenance"]
    assert "route_progress" not in released.json()["provenance"]

    reassigned = client.post(
        f"/api/v1/resources/{resource.id}/assign",
        json={
            "incident_id": second_incident.id,
            "expected_resource_version": 3,
            "operator_reference": "operator-reassign",
        },
    )
    assert reassigned.status_code == 200
    assert reassigned.json()["route_progress"] is None
    assert "movement" not in reassigned.json()["provenance"]


@pytest.mark.parametrize(
    "coordinates",
    [
        [[31.34, 30.05], [31.34, 30.05]],
        [[31.34, 30.05], ["invalid", 30.06]],
        [[31.34, 30.05], [181.0, 30.06]],
    ],
)
def test_resource_movement_rejects_invalid_stored_route_geometry(
    client: TestClient,
    db_session: Session,
    coordinates: list[list[object]],
) -> None:
    """Malformed or degenerate persisted route geometry fails visibly without fabricating movement."""
    suffix = str(uuid.uuid4())
    incident = _create_test_incident(db_session, incident_id=f"inc-bad-geometry-{suffix}")
    resource = _create_test_resource(db_session, resource_id=f"res-bad-geometry-{suffix}")
    _create_test_approved_plan(db_session, incident, resource, coordinates=coordinates)  # type: ignore[arg-type]

    response = client.patch(
        f"/api/v1/resources/{resource.id}/movement",
        json={
            "incident_id": incident.id,
            "expected_resource_version": 1,
            "route_progress": 0.5,
            "operator_reference": "operator-invalid-route",
        },
    )

    assert response.status_code == 409
    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, resource.id)
    assert persisted is not None
    assert persisted.version == 1
    assert persisted.provenance_json.get("movement") is None


def test_concurrent_resource_movement_yields_one_winner(
    db_session: Session,
) -> None:
    """Two movement commands using one resource version produce one commit and one conflict."""
    incident = _create_test_incident(db_session, incident_id="inc-concurrent-movement")
    resource = _create_test_resource(db_session, resource_id="res-concurrent-movement")
    _create_test_approved_plan(db_session, incident, resource)

    def move(progress: float) -> int:
        thread_client = TestClient(app)
        response = thread_client.patch(
            f"/api/v1/resources/{resource.id}/movement",
            json={
                "incident_id": incident.id,
                "expected_resource_version": 1,
                "route_progress": progress,
                "operator_reference": f"operator-{progress}",
            },
        )
        return response.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(move, [0.25, 0.75]))

    assert sorted(statuses) == [200, 409]
    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, resource.id)
    assert persisted is not None
    assert persisted.version == 2
    assert persisted.provenance_json["movement"]["route_progress"] in {0.25, 0.75}
    events = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "RESOURCE_MOVED",
        )
    ).all()
    assert len(events) == 1
