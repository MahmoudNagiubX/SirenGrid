from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import networkx as nx
import pytest

from app.routing import (
    ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME,
    ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED,
    RouteNotFoundError,
    compute_traffic_aware_route,
)
from app.schemas import Coordinate, DataReality, FreshnessStatus
from app.traffic.matching import graph_fingerprint
from app.traffic.models import (
    TrafficOverlay,
    TrafficOverlayEntry,
    TrafficProviderState,
    TrafficSnapshot,
)


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
ORIGIN = Coordinate(lat=30.0600, lon=31.3300)
DESTINATION = Coordinate(lat=30.0600, lon=31.3310)


def add_edge(
    graph: nx.MultiDiGraph,
    u: str,
    v: str,
    *,
    key: str = "0",
    length: float,
    travel_time: float,
) -> None:
    u_lon, u_lat = graph.nodes[u]["x"], graph.nodes[u]["y"]
    v_lon, v_lat = graph.nodes[v]["x"], graph.nodes[v]["y"]
    graph.add_edge(
        u,
        v,
        key=key,
        length=length,
        travel_time=travel_time,
        oneway=True,
        geometry=f"LINESTRING ({u_lon} {u_lat}, {v_lon} {v_lat})",
    )


def two_path_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node("a", x=31.3300, y=30.0600)
    graph.add_node("b", x=31.3305, y=30.0605)
    graph.add_node("d", x=31.3310, y=30.0600)
    add_edge(graph, "a", "d", length=100, travel_time=10)
    add_edge(graph, "a", "b", length=450, travel_time=15)
    add_edge(graph, "b", "d", length=450, travel_time=15)
    return graph


def mixed_path_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node("a", x=31.3300, y=30.0600)
    graph.add_node("b", x=31.33025, y=30.0600)
    graph.add_node("d", x=31.3310, y=30.0600)
    add_edge(graph, "a", "b", length=100, travel_time=10)
    add_edge(graph, "b", "d", length=300, travel_time=10)
    return graph


def make_snapshot(
    graph: nx.MultiDiGraph,
    entries: tuple[TrafficOverlayEntry, ...],
    *,
    freshness: FreshnessStatus = FreshnessStatus.LIVE,
    failure_reason: str | None = None,
) -> TrafficSnapshot:
    snapshot_id = "snapshot-1"
    fingerprint = graph_fingerprint(graph)
    return TrafficSnapshot(
        snapshot_id=snapshot_id,
        version=1,
        graph_fingerprint=fingerprint,
        sample_points_fingerprint="sample-fingerprint",
        provider_state=TrafficProviderState.AVAILABLE,
        refresh_attempted_at=NOW,
        retrieved_at=NOW,
        freshness_status=freshness,
        source="TomTom Traffic Flow Segment Data",
        source_reference=f"traffic-flow-snapshot:{snapshot_id}",
        data_reality=DataReality.REAL_LIVE,
        flow_style="absolute",
        flow_zoom=22,
        units="kmph",
        overlay=TrafficOverlay(
            snapshot_id=snapshot_id,
            graph_fingerprint=fingerprint,
            entries=entries,
        ),
        failure_reason=failure_reason,
    )


def traffic_entry(
    edge_key: tuple[str, str, str],
    *,
    factor: float | None = 2,
    closure: bool = False,
) -> TrafficOverlayEntry:
    return TrafficOverlayEntry(
        edge_key=edge_key,
        observation_id=f"obs-{edge_key[0]}-{edge_key[1]}",
        traffic_factor=None if closure else factor,
        road_closure=closure,
    )


def test_base_and_traffic_routes_are_optimized_independently() -> None:
    graph = two_path_graph()
    snapshot = make_snapshot(
        graph,
        (traffic_entry(("a", "d", "0"), factor=4),),
    )

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)

    assert result.base_nodes == ["a", "d"]
    assert result.nodes == ["a", "b", "d"]
    assert result.base_eta == 10
    assert result.effective_eta == 30
    assert result.eta_seconds == result.effective_eta
    assert result.traffic_selected_path_base_eta == 30
    assert result.routing_source == ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED
    assert result.traffic_weight_affected_path_selection is True


def test_traffic_coverage_is_length_weighted_not_edge_count_weighted() -> None:
    graph = mixed_path_graph()
    snapshot = make_snapshot(
        graph,
        (traffic_entry(("a", "b", "0"), factor=2),),
    )

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)

    assert result.nodes == ["a", "b", "d"]
    assert result.matched_traversed_edge_count == 1
    assert result.total_traversed_edge_count == 2
    assert result.traffic_coverage_ratio == pytest.approx(0.25)
    assert result.base_eta == 20
    assert result.effective_eta == 30
    assert result.routing_source == ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED


def test_validated_closure_changes_path_and_keeps_traffic_label() -> None:
    graph = two_path_graph()
    snapshot = make_snapshot(
        graph,
        (traffic_entry(("a", "d", "0"), closure=True),),
    )

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)

    assert result.base_nodes == ["a", "d"]
    assert result.nodes == ["a", "b", "d"]
    assert ("a", "d", "0") not in result.edge_keys
    assert result.routing_source == ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED
    assert result.traffic_closure_affected_path_selection is True
    assert result.matched_traversed_edge_count == 0
    assert result.traffic_coverage_ratio == 0


def test_closure_outside_base_and_selected_paths_does_not_change_label() -> None:
    graph = two_path_graph()
    graph.add_node("x", x=31.3320, y=30.0610)
    graph.add_node("y", x=31.3330, y=30.0610)
    add_edge(graph, "x", "y", length=100, travel_time=10)
    snapshot = make_snapshot(
        graph,
        (traffic_entry(("x", "y", "0"), closure=True),),
    )

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)

    assert result.nodes == ["a", "d"]
    assert result.routing_source == ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
    assert result.traffic_closure_affected_path_selection is False


def test_stale_snapshot_falls_back_to_independent_base_route() -> None:
    graph = two_path_graph()
    snapshot = make_snapshot(
        graph,
        (traffic_entry(("a", "d", "0"), factor=4),),
        freshness=FreshnessStatus.STALE,
    )

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)

    assert result.nodes == ["a", "d"]
    assert result.base_eta == result.effective_eta == 10
    assert result.routing_source == ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
    assert result.traffic_fallback_reason == "TOMTOM_SNAPSHOT_STALE"
    assert result.matched_traversed_edge_count == 0


def test_future_timestamp_snapshot_cannot_weight_routing() -> None:
    graph = two_path_graph()
    snapshot = make_snapshot(
        graph,
        (traffic_entry(("a", "d", "0"), factor=4),),
        freshness=FreshnessStatus.UNKNOWN,
        failure_reason="TOMTOM_SNAPSHOT_TIMESTAMP_IN_FUTURE",
    )

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)

    assert result.nodes == ["a", "d"]
    assert result.base_eta == result.effective_eta == 10
    assert result.routing_source == ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
    assert result.traffic_freshness_status is FreshnessStatus.UNKNOWN
    assert result.traffic_fallback_reason == "TOMTOM_SNAPSHOT_TIMESTAMP_IN_FUTURE"
    assert result.matched_traversed_edge_count == 0


def test_graph_fingerprint_mismatch_falls_back_without_using_overlay() -> None:
    graph = two_path_graph()
    snapshot = make_snapshot(
        graph,
        (traffic_entry(("a", "d", "0"), factor=4),),
    )
    snapshot = snapshot.model_copy(update={"graph_fingerprint": "different-graph"})

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)

    assert result.nodes == ["a", "d"]
    assert result.routing_source == ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
    assert result.traffic_fallback_reason == "TOMTOM_GRAPH_FINGERPRINT_MISMATCH"


def test_missing_snapshot_falls_back_without_fabricating_traffic() -> None:
    graph = two_path_graph()

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, None)

    assert result.routing_source == ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
    assert result.base_eta == result.effective_eta == 10
    assert result.traffic_fallback_reason == "TOMTOM_SNAPSHOT_UNAVAILABLE"
    assert result.matched_traversed_edge_count == 0


def test_malformed_snapshot_preserves_specific_failure_reason() -> None:
    graph = two_path_graph()
    malformed = make_snapshot(graph, ()).model_copy(
        update={
            "provider_state": TrafficProviderState.MALFORMED,
            "retrieved_at": None,
            "data_reality": None,
            "freshness_status": FreshnessStatus.UNKNOWN,
            "overlay": None,
            "failure_reason": "TOMTOM_MALFORMED_PAYLOAD",
        }
    )

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, malformed)

    assert result.routing_source == ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
    assert result.traffic_fallback_reason == "TOMTOM_MALFORMED_PAYLOAD"
    assert result.matched_traversed_edge_count == 0


def test_fresh_but_unmatched_snapshot_visibly_uses_base_route() -> None:
    graph = two_path_graph()
    unmatched = make_snapshot(graph, ())

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, unmatched)

    assert result.routing_source == ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
    assert result.traffic_fallback_reason == "TOMTOM_NO_MATCHED_TRAFFIC"
    assert result.traffic_freshness_status is FreshnessStatus.LIVE
    assert result.matched_traversed_edge_count == 0


def test_validated_closure_never_routes_through_closed_only_path() -> None:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node("a", x=31.3300, y=30.0600)
    graph.add_node("d", x=31.3310, y=30.0600)
    add_edge(graph, "a", "d", length=100, travel_time=10)
    snapshot = make_snapshot(
        graph,
        (traffic_entry(("a", "d", "0"), closure=True),),
    )

    with pytest.raises(RouteNotFoundError, match="traffic-aware"):
        compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)


def test_traffic_calculation_does_not_mutate_base_graph() -> None:
    graph = two_path_graph()
    before = deepcopy(nx.node_link_data(graph, edges="edges"))
    fingerprint = graph_fingerprint(graph)
    snapshot = make_snapshot(
        graph,
        (traffic_entry(("a", "d", "0"), factor=4),),
    )

    compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)

    assert nx.node_link_data(graph, edges="edges") == before
    assert graph_fingerprint(graph) == fingerprint


def test_optional_alternative_is_edge_disjoint() -> None:
    graph = two_path_graph()
    snapshot = make_snapshot(graph, ())

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)

    assert len(result.alternatives) == 1
    assert set(result.alternatives[0].edge_keys).isdisjoint(result.edge_keys)


def test_no_alternative_is_returned_when_only_shared_edge_paths_exist() -> None:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node("a", x=31.3300, y=30.0600)
    graph.add_node("b", x=31.3304, y=30.0600)
    graph.add_node("c", x=31.3307, y=30.0602)
    graph.add_node("d", x=31.3310, y=30.0600)
    add_edge(graph, "a", "b", length=100, travel_time=10)
    add_edge(graph, "b", "d", length=100, travel_time=10)
    add_edge(graph, "b", "c", length=100, travel_time=11)
    add_edge(graph, "c", "d", length=100, travel_time=11)
    snapshot = make_snapshot(graph, ())

    result = compute_traffic_aware_route(graph, ORIGIN, DESTINATION, snapshot)

    assert result.alternatives == []
