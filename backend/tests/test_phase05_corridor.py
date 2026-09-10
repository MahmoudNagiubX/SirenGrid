from __future__ import annotations

from datetime import datetime, timezone
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.corridor import extract_corridor_signals
from app.db import init_db
from app.main import app
from app.schemas import CorridorSignalState
from app.traffic_signal_gateway import TrafficSignalGateway
from test_phase05_hospital_api import _create_approved_transport_plan


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _route_through_real_signals() -> dict[str, object]:
    with open("data/processed/nasr_city/nasr_city_traffic_signals.geojson", encoding="utf-8") as handle:
        first = json.load(handle)["features"]
    coordinates = [
        first[0]["geometry"]["coordinates"],
        first[1]["geometry"]["coordinates"],
        first[2]["geometry"]["coordinates"],
    ]
    return {"type": "LineString", "coordinates": coordinates}


def test_corridor_extraction_uses_real_osm_signals_and_approved_timing() -> None:
    route = _route_through_real_signals()
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)

    signals = extract_corridor_signals(route, 180.0, now_iso=now.isoformat())

    assert len(signals) >= 2
    assert signals == sorted(signals, key=lambda item: (item.distance_along_route_m, item.signal_id))
    assert all(item.provenance["data_reality"] == "REAL_PUBLIC" for item in signals)
    assert all(item.provenance["matching_tolerance_m"] == 50 for item in signals)
    assert all(item.request_time for item in signals)
    assert signals[0].request_time != now.isoformat()


def test_zero_distance_approved_route_has_no_corridor_signals() -> None:
    route = {"type": "LineString", "coordinates": [[31.3304, 30.0571], [31.3304, 30.0571]]}

    assert extract_corridor_signals(route, 0.0, now_iso="2026-09-07T12:00:00+00:00") == []


def test_traffic_signal_gateway_exposes_only_simulated_forward_states() -> None:
    gateway = TrafficSignalGateway()
    assert gateway.transition("NORMAL", CorridorSignalState.REQUESTED).data_reality == "SIMULATED"
    with pytest.raises(ValueError, match="Illegal corridor priority transition"):
        gateway.transition("NORMAL", CorridorSignalState.PASSED)


def test_corridor_api_preserves_route_eta_and_priority_is_simulated(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, _, plan = _create_approved_transport_plan(db_session)
    route = _route_through_real_signals()
    routes = list(plan.routes_json)
    routes[0] = {**routes[0], "route_geometry": route, "geometry": route, "eta_seconds": 180.0}
    plan.routes_json = routes
    db_session.commit()

    generated = client.post(
        f"/api/v1/incidents/{incident.id}/corridor",
        json={"resource_id": "phase05-amb-01"},
    )
    assert generated.status_code == 200, generated.text
    data = generated.json()
    assert data["data_reality"] == "REAL_DERIVED"
    assert data["safety_lead_time_seconds"] == 30
    assert len(data["signals"]) >= 2
    assert all(signal["provenance"]["data_reality"] == "REAL_PUBLIC" for signal in data["signals"])
    original_geometry = data["route_geometry"]

    state = data
    for target in (
        CorridorSignalState.REQUESTED.value,
        CorridorSignalState.PREPARING.value,
        CorridorSignalState.PRIORITY_ACTIVE.value,
        CorridorSignalState.PASSED.value,
    ):
        response = client.post(
            f"/api/v1/incidents/{incident.id}/corridor/priority",
            json={
                "expected_incident_version": 4,
                "expected_plan_version": 1,
                "operator_reference": "operator-corridor",
                "state": target,
            },
        )
        assert response.status_code == 200, response.text
        state = response.json()
        assert state["state"] == target
        assert state["route_geometry"] == original_geometry
        assert all(signal["state"] == target for signal in state["signals"])

    assert state["provenance"]["priority_reality"] == "SIMULATED"
    assert state["plan_id"] == plan.id
