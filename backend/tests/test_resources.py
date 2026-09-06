from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import init_db
from app.main import app
from app.models import EmergencyResource
from app.routing import load_routing_graph, snap_coordinate_to_graph
from app.schemas import Coordinate, DataReality, FreshnessStatus, ResourceStatus, ResourceType
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
