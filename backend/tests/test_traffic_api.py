from __future__ import annotations

from datetime import datetime, timezone

import networkx as nx
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.schemas import DataReality, FreshnessStatus
from app.traffic.matching import graph_fingerprint
from app.traffic.models import (
    TrafficOverlay,
    TrafficOverlayEntry,
    TrafficProviderState,
    TrafficSnapshot,
)


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
PAYLOAD = {
    "origin": {"lat": 30.06, "lon": 31.33},
    "destination": {"lat": 30.06, "lon": 31.331},
}


class FakeTrafficRuntime:
    def __init__(self, snapshot: TrafficSnapshot | None) -> None:
        self.snapshot = snapshot
        self.capture_count = 0

    def capture_snapshot(self, graph, **kwargs) -> TrafficSnapshot:
        self.capture_count += 1
        assert graph is not None
        assert "now" in kwargs
        assert "wall_clock" in kwargs
        assert "monotonic" in kwargs
        assert self.snapshot is not None
        return self.snapshot

    def current_snapshot(self, **kwargs) -> TrafficSnapshot | None:
        assert "now" in kwargs
        return self.snapshot


def route_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node("a", x=31.33, y=30.06)
    graph.add_node("b", x=31.3305, y=30.0605)
    graph.add_node("d", x=31.331, y=30.06)
    graph.add_edge("a", "d", key="0", length=100, travel_time=10)
    graph.add_edge("a", "b", key="0", length=450, travel_time=15)
    graph.add_edge("b", "d", key="0", length=450, travel_time=15)
    return graph


def snapshot(
    graph: nx.MultiDiGraph,
    entries: tuple[TrafficOverlayEntry, ...] = (),
    *,
    state: TrafficProviderState = TrafficProviderState.AVAILABLE,
    failure_reason: str | None = None,
) -> TrafficSnapshot:
    snapshot_id = "snapshot-api-1"
    fingerprint = graph_fingerprint(graph)
    retrieved_at = NOW if state is TrafficProviderState.AVAILABLE else None
    return TrafficSnapshot(
        snapshot_id=snapshot_id,
        version=3,
        graph_fingerprint=fingerprint,
        sample_points_fingerprint="samples",
        provider_state=state,
        refresh_attempted_at=NOW,
        retrieved_at=retrieved_at,
        freshness_status=(
            FreshnessStatus.LIVE if retrieved_at else FreshnessStatus.UNKNOWN
        ),
        source="TomTom Traffic Flow Segment Data",
        source_reference=f"traffic-flow-snapshot:{snapshot_id}",
        data_reality=DataReality.REAL_LIVE if retrieved_at else None,
        flow_style="absolute",
        flow_zoom=22,
        units="kmph",
        overlay=(
            TrafficOverlay(
                snapshot_id=snapshot_id,
                graph_fingerprint=fingerprint,
                entries=entries,
            )
            if retrieved_at
            else None
        ),
        failure_reason=failure_reason,
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def install_runtime(monkeypatch: pytest.MonkeyPatch, runtime: FakeTrafficRuntime) -> None:
    monkeypatch.setattr("app.map.traffic_runtime", runtime)
    monkeypatch.setattr("app.traffic.api.traffic_runtime", runtime)


def test_route_preview_visibly_falls_back_when_key_is_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = route_graph()
    runtime = FakeTrafficRuntime(
        snapshot(
            graph,
            state=TrafficProviderState.MISSING_KEY,
            failure_reason="TOMTOM_API_KEY_MISSING",
        )
    )
    install_runtime(monkeypatch, runtime)
    monkeypatch.setattr("app.map.load_routing_graph", lambda: graph)

    response = client.post("/api/v1/routes/preview", json=PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["routing_source"] == "OSM_BASE_TRAVEL_TIME"
    assert body["base_eta"] == body["effective_eta"] == body["eta_seconds"]
    assert body["matched_traversed_edge_count"] == 0
    assert body["traffic_coverage_ratio"] == 0
    assert body["traffic_fallback_reason"] == "TOMTOM_API_KEY_MISSING"
    assert runtime.capture_count == 1


def test_route_preview_exposes_validated_weight_influence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = route_graph()
    runtime = FakeTrafficRuntime(
        snapshot(
            graph,
            (
                TrafficOverlayEntry(
                    edge_key=("a", "d", "0"),
                    observation_id="obs-weight",
                    traffic_factor=4,
                ),
            ),
        )
    )
    install_runtime(monkeypatch, runtime)
    monkeypatch.setattr("app.map.load_routing_graph", lambda: graph)

    body = client.post("/api/v1/routes/preview", json=PAYLOAD).json()

    assert body["routing_source"] == "TOMTOM_TRAFFIC_ADJUSTED"
    assert body["base_eta"] == 10
    assert body["effective_eta"] == 30
    assert body["traffic_selected_path_base_eta"] == 30
    assert body["traffic_weight_affected_path_selection"] is True


def test_route_preview_exposes_validated_closure_influence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = route_graph()
    runtime = FakeTrafficRuntime(
        snapshot(
            graph,
            (
                TrafficOverlayEntry(
                    edge_key=("a", "d", "0"),
                    observation_id="obs-closure",
                    road_closure=True,
                ),
            ),
        )
    )
    install_runtime(monkeypatch, runtime)
    monkeypatch.setattr("app.map.load_routing_graph", lambda: graph)

    body = client.post("/api/v1/routes/preview", json=PAYLOAD).json()

    assert body["routing_source"] == "TOMTOM_TRAFFIC_ADJUSTED"
    assert body["traffic_closure_affected_path_selection"] is True
    assert body["matched_traversed_edge_count"] == 0
    assert body["traffic_coverage_ratio"] == 0


def test_snapshot_endpoint_is_sanitized_and_exposes_locked_policy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = route_graph()
    current = snapshot(graph)
    runtime = FakeTrafficRuntime(current)
    install_runtime(monkeypatch, runtime)

    response = client.get("/api/v1/traffic/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_id"] == "snapshot-api-1"
    assert body["provider_state"] == "AVAILABLE"
    assert body["retrieved_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert body["provider_last_updated"] is None
    assert body["freshness_status"] == "LIVE"
    assert body["flow_style"] == "absolute"
    assert body["flow_zoom"] == 22
    assert body["observation_count"] == 0
    assert body["prototype_policy"] == {
        "refresh_interval_seconds": 60,
        "fresh_max_age_seconds": 120,
        "refresh_timeout_seconds": 10,
        "min_provider_confidence": 0.8,
        "max_geometry_separation_m": 30,
        "max_direction_difference_degrees": 30,
    }
    serialized = response.text.lower()
    assert "apikey" not in serialized
    assert "openlr" not in serialized
