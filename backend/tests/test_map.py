from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.config import settings
from app.main import app
from app.routing import RouteNotFoundError, RoutingPointOutsideGraphError

client = TestClient(app)

FORBIDDEN_TRAFFIC_STRINGS = [
    "live_traffic",
    "traffic_congestion",
    "realtime_delay",
    "live_speed",
]


def _assert_no_live_traffic_labels(data: Any) -> None:
    serialized = json.dumps(data).lower()
    for forbidden in FORBIDDEN_TRAFFIC_STRINGS:
        assert forbidden not in serialized, f"Found forbidden live traffic label '{forbidden}' in payload"


# 1. Map Layer Tests: Success & Content


def test_map_boundary_success():
    response = client.get("/api/v1/map/boundary")
    assert response.status_code == 200
    data = response.json()

    assert data.get("layer") == "boundary"
    geojson = data.get("geojson")
    assert isinstance(geojson, dict)
    assert geojson.get("type") == "FeatureCollection"
    features = geojson.get("features")
    assert isinstance(features, list)
    assert len(features) > 0

    provenance = data.get("provenance")
    assert isinstance(provenance, dict)
    assert provenance.get("data_reality") == "REAL_DERIVED"
    assert provenance.get("freshness_status") == "STATIC"
    assert provenance.get("source_repo") == "MahmoudNagiubX/Egypt-Smart-City-Digital-Twin"
    assert provenance.get("source_commit") == "93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d"

    _assert_no_live_traffic_labels(data)


def test_map_roads_success():
    response = client.get("/api/v1/map/roads")
    assert response.status_code == 200
    data = response.json()

    assert data.get("layer") == "roads"
    geojson = data.get("geojson")
    assert isinstance(geojson, dict)
    assert geojson.get("type") == "FeatureCollection"
    features = geojson.get("features")
    assert isinstance(features, list)
    assert len(features) > 0

    # Inspect first feature
    first = features[0]
    assert first.get("type") == "Feature"
    geom = first.get("geometry")
    assert isinstance(geom, dict)
    assert geom.get("type") == "LineString"
    assert len(geom.get("coordinates", [])) >= 2
    props = first.get("properties")
    assert isinstance(props, dict)
    assert "length" in props

    provenance = data.get("provenance")
    assert isinstance(provenance, dict)
    assert provenance.get("data_reality") == "REAL_DERIVED"
    assert provenance.get("freshness_status") == "STATIC"
    assert provenance.get("source") == "OpenStreetMap via OSMnx/Overpass"
    assert provenance.get("acquisition_mode") == "DIRECT_OSMNX_OVERPASS_OWNER_APPROVED"
    assert provenance.get("turn_restriction_support") == "NOT_PROCESSED_OR_VALIDATED"

    _assert_no_live_traffic_labels(data)


def test_map_zones_success():
    response = client.get("/api/v1/map/zones")
    assert response.status_code == 200
    data = response.json()

    assert data.get("layer") == "zones"
    geojson = data.get("geojson")
    assert isinstance(geojson, dict)
    assert geojson.get("type") == "FeatureCollection"
    features = geojson.get("features")
    assert isinstance(features, list)
    assert len(features) > 0

    provenance = data.get("provenance")
    assert isinstance(provenance, dict)
    assert provenance.get("data_reality") == "REAL_DERIVED"
    assert provenance.get("freshness_status") == "STATIC"
    assert provenance.get("source_repo") == "MahmoudNagiubX/Egypt-Smart-City-Digital-Twin"

    _assert_no_live_traffic_labels(data)


def test_map_hospitals_filtered_success():
    response = client.get("/api/v1/map/hospitals")
    assert response.status_code == 200
    data = response.json()

    assert data.get("layer") == "hospitals"
    geojson = data.get("geojson")
    assert isinstance(geojson, dict)
    assert geojson.get("type") == "FeatureCollection"
    features = geojson.get("features")
    assert isinstance(features, list)
    assert len(features) > 0

    # Must contain only facility_type == 'hospital'
    for feat in features:
        props = feat.get("properties", {})
        assert props.get("facility_type") == "hospital", f"Unexpected facility_type: {props.get('facility_type')}"
        # No rank/score/capacity promises
        assert "rank" not in props
        assert "score" not in props
        assert "capacity" not in props
        assert "beds_available" not in props

    provenance = data.get("provenance")
    assert isinstance(provenance, dict)
    assert provenance.get("data_reality") == "REAL_DERIVED"
    assert provenance.get("freshness_status") == "STATIC"
    assert provenance.get("source") == "OpenStreetMap via OSMnx/Overpass"

    _assert_no_live_traffic_labels(data)


# 2. Missing Asset Error Handling (HTTP 503)


def test_map_boundary_missing_asset_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "nasr_city_data_dir", tmp_path)
    response = client.get("/api/v1/map/boundary")
    assert response.status_code == 503
    detail = response.json().get("detail", "")
    assert "boundary" in detail.lower() or "not found" in detail.lower() or "unavailable" in detail.lower()


def test_map_roads_missing_asset_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "nasr_city_data_dir", tmp_path)
    response = client.get("/api/v1/map/roads")
    assert response.status_code == 503
    detail = response.json().get("detail", "")
    assert "graph" in detail.lower() or "not found" in detail.lower() or "unavailable" in detail.lower()


def test_map_zones_missing_asset_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "nasr_city_data_dir", tmp_path)
    response = client.get("/api/v1/map/zones")
    assert response.status_code == 503
    detail = response.json().get("detail", "")
    assert "zone" in detail.lower() or "not found" in detail.lower() or "unavailable" in detail.lower()


def test_map_hospitals_missing_asset_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "nasr_city_data_dir", tmp_path)
    response = client.get("/api/v1/map/hospitals")
    assert response.status_code == 503
    detail = response.json().get("detail", "")
    assert "facilit" in detail.lower() or "not found" in detail.lower() or "unavailable" in detail.lower()


def test_map_missing_provenance_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Setup dir with boundary but no provenance.json
    boundary_src = settings.NASR_CITY_DATA_DIR / "nasr_city_boundary.geojson"
    if boundary_src.is_file():
        dest = tmp_path / "nasr_city_boundary.geojson"
        dest.write_text(boundary_src.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(settings, "nasr_city_data_dir", tmp_path)
    response = client.get("/api/v1/map/boundary")
    assert response.status_code == 503
    detail = response.json().get("detail", "")
    assert "provenance" in detail.lower() or "not found" in detail.lower() or "unavailable" in detail.lower()


# 3. Route Preview Tests


def test_route_preview_real_graph_success():
    payload = {
        "origin": {"lat": 30.0687969, "lon": 31.3411596},
        "destination": {"lat": 30.0642054, "lon": 31.3455818},
    }
    response = client.post("/api/v1/routes/preview", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["origin"]["lat"] == pytest.approx(30.0687969)
    assert data["origin"]["lon"] == pytest.approx(31.3411596)
    assert data["destination"]["lat"] == pytest.approx(30.0642054)
    assert data["destination"]["lon"] == pytest.approx(31.3455818)

    assert data["distance_m"] > 0
    assert data["eta_seconds"] > 0
    assert data["origin_snap_distance_m"] >= 0
    assert data["destination_snap_distance_m"] >= 0
    assert len(data["nodes"]) >= 2

    geometry = data["geometry"]
    assert geometry["type"] == "LineString"
    assert len(geometry["coordinates"]) >= 2
    for coord in geometry["coordinates"]:
        assert len(coord) == 2
        assert isinstance(coord[0], float)
        assert isinstance(coord[1], float)

    assert data["routing_source"] == "OSM_BASE_TRAVEL_TIME"
    _assert_no_live_traffic_labels(data)


def test_route_preview_outside_graph_returns_422():
    # London coordinates far outside Nasr City
    payload = {
        "origin": {"lat": 51.5074, "lon": -0.1278},
        "destination": {"lat": 30.0642054, "lon": 31.3455818},
    }
    response = client.post("/api/v1/routes/preview", json=payload)
    assert response.status_code == 422
    detail = response.json().get("detail", "")
    assert "outside" in detail.lower() or "snap" in detail.lower()


def test_route_preview_destination_outside_graph_returns_422():
    payload = {
        "origin": {"lat": 30.0687969, "lon": 31.3411596},
        "destination": {"lat": 0.0, "lon": 0.0},
    }
    response = client.post("/api/v1/routes/preview", json=payload)
    assert response.status_code == 422


def test_route_preview_same_node_returns_zero_travel_route():
    """Identical points are co-located, which is a valid zero-travel result."""
    payload = {
        "origin": {"lat": 30.0687969, "lon": 31.3411596},
        "destination": {"lat": 30.0687969, "lon": 31.3411596},
    }
    response = client.post("/api/v1/routes/preview", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["distance_m"] == 0.0
    assert data["eta_seconds"] == 0.0
    assert data["base_eta"] == 0.0
    assert data["effective_eta"] == 0.0
    assert data["geometry"]["type"] == "LineString"
    assert len(data["geometry"]["coordinates"]) == 2
    assert data["geometry"]["coordinates"][0] == data["geometry"]["coordinates"][1]
    assert data["routing_source"] == "OSM_BASE_TRAVEL_TIME"


def test_route_preview_no_path_returns_409(monkeypatch: pytest.MonkeyPatch):
    def mock_compute(*args, **kwargs):
        raise RouteNotFoundError("No path found between nodes")

    monkeypatch.setattr("app.map.compute_traffic_aware_route", mock_compute)

    payload = {
        "origin": {"lat": 30.0687969, "lon": 31.3411596},
        "destination": {"lat": 30.0642054, "lon": 31.3455818},
    }
    response = client.post("/api/v1/routes/preview", json=payload)
    assert response.status_code == 409
    detail = response.json().get("detail", "")
    assert "no route" in detail.lower() or "no path" in detail.lower() or "conflict" in detail.lower()


def test_route_preview_missing_graph_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "nasr_city_data_dir", tmp_path)
    payload = {
        "origin": {"lat": 30.0687969, "lon": 31.3411596},
        "destination": {"lat": 30.0642054, "lon": 31.3455818},
    }
    response = client.post("/api/v1/routes/preview", json=payload)
    assert response.status_code == 503
    detail = response.json().get("detail", "")
    assert "graph" in detail.lower() or "unavailable" in detail.lower() or "not found" in detail.lower()


def test_route_preview_invalid_coordinate_validation():
    payload = {
        "origin": {"lat": 95.0, "lon": 31.3411596},  # Invalid lat > 90
        "destination": {"lat": 30.0642054, "lon": 31.3455818},
    }
    response = client.post("/api/v1/routes/preview", json=payload)
    assert response.status_code == 422


def test_route_preview_compute_outside_graph_error_returns_422(monkeypatch: pytest.MonkeyPatch):
    def mock_compute(*args, **kwargs):
        raise RoutingPointOutsideGraphError("Snap exceeded threshold")

    monkeypatch.setattr("app.map.compute_traffic_aware_route", mock_compute)
    payload = {
        "origin": {"lat": 30.0687969, "lon": 31.3411596},
        "destination": {"lat": 30.0642054, "lon": 31.3455818},
    }
    response = client.post("/api/v1/routes/preview", json=payload)
    assert response.status_code == 422


def test_route_preview_load_graph_generic_exception_returns_503(monkeypatch: pytest.MonkeyPatch):
    def mock_load(*args, **kwargs):
        raise RuntimeError("Corrupted graph file")

    monkeypatch.setattr("app.map.load_routing_graph", mock_load)
    payload = {
        "origin": {"lat": 30.0687969, "lon": 31.3411596},
        "destination": {"lat": 30.0642054, "lon": 31.3455818},
    }
    response = client.post("/api/v1/routes/preview", json=payload)
    assert response.status_code == 503


def test_map_corrupted_json_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "nasr_city_data_dir", tmp_path)
    (tmp_path / "nasr_city_boundary.geojson").write_text("invalid-json{{{", encoding="utf-8")
    (tmp_path / "provenance.json").write_text("{}", encoding="utf-8")
    response = client.get("/api/v1/map/boundary")
    assert response.status_code == 503
