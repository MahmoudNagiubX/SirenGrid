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
from app.models import EmergencyResource, Incident, TimelineEvent
from app.routing import load_routing_graph, snap_coordinate_to_graph
from app.schemas import (
    ConfidenceLevel,
    Coordinate,
    DataReality,
    FreshnessStatus,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    Severity,
)
from app.resources import is_planner_eligible
from app.seed import DEFAULT_SCENARIO_PATH, main as seed_main, seed_resources


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
