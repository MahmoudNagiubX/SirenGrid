from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import networkx as nx

from app.traffic.matching import (
    build_overlay,
    graph_fingerprint,
    match_observation,
    select_corridor_edges,
    validate_overlay_for_graph,
)
from app.traffic.models import (
    TrafficMatchStatus,
    TrafficObservation,
)


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def add_node(graph: nx.MultiDiGraph, node: str, lon: float, lat: float) -> None:
    graph.add_node(node, x=lon, y=lat)


def add_edge(
    graph: nx.MultiDiGraph,
    u: str,
    v: str,
    *,
    key: str = "0",
    name: str = "شارع الطيران",
    coords: tuple[tuple[float, float], ...] | None = None,
) -> None:
    if coords is None:
        coords = (
            (float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])),
            (float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])),
        )
    wkt_coords = ", ".join(f"{lon} {lat}" for lon, lat in coords)
    graph.add_edge(
        u,
        v,
        key=key,
        name=name,
        geometry=f"LINESTRING ({wkt_coords})",
        length=100.0,
        travel_time=10.0,
        oneway=True,
    )


def chain_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    add_node(graph, "a", 31.3300, 30.0600)
    add_node(graph, "b", 31.3305, 30.0600)
    add_node(graph, "c", 31.3310, 30.0600)
    add_edge(graph, "a", "b")
    add_edge(graph, "b", "c")
    return graph


def observation(
    *,
    observation_id: str = "obs-1",
    confidence: float = 0.80,
    coordinates: tuple[tuple[float, float], ...] = (
        (31.3300, 30.06005),
        (31.3310, 30.06005),
    ),
    road_closure: bool = False,
) -> TrafficObservation:
    return TrafficObservation(
        observation_id=observation_id,
        sample_id="tayaran",
        frc="FRC2",
        current_speed_kph=35,
        free_flow_speed_kph=70,
        current_travel_time_s=20,
        free_flow_travel_time_s=10,
        confidence=confidence,
        road_closure=road_closure,
        coordinates=coordinates,
        retrieved_at=NOW,
    )


def all_edges(graph: nx.MultiDiGraph) -> frozenset[tuple[str, str, str]]:
    return frozenset((str(u), str(v), str(key)) for u, v, key in graph.edges(keys=True))


def test_observation_matching_all_gates_produces_one_chain() -> None:
    graph = chain_graph()

    match = match_observation(graph, observation(), all_edges(graph))

    assert match.status is TrafficMatchStatus.MATCHED
    assert match.edge_keys == (("a", "b", "0"), ("b", "c", "0"))
    assert match.max_geometry_separation_m is not None
    assert match.max_geometry_separation_m <= 30
    assert match.max_direction_difference_degrees is not None
    assert match.max_direction_difference_degrees <= 30
    assert match.metric_crs == "EPSG:32636"


def test_reversed_stored_geometry_is_oriented_to_the_directed_edge() -> None:
    graph = chain_graph()
    graph["a"]["b"]["0"]["geometry"] = (
        "LINESTRING (31.3305 30.0600, 31.3300 30.0600)"
    )

    match = match_observation(graph, observation(), all_edges(graph))

    assert match.status is TrafficMatchStatus.MATCHED
    assert match.edge_keys == (("a", "b", "0"), ("b", "c", "0"))


def test_confidence_below_approved_threshold_is_unmatched() -> None:
    graph = chain_graph()

    match = match_observation(
        graph,
        observation(confidence=0.79),
        all_edges(graph),
    )

    assert match.status is TrafficMatchStatus.UNMATCHED
    assert match.reason == "LOW_PROVIDER_CONFIDENCE"
    assert match.edge_keys == ()


def test_geometry_beyond_thirty_meters_is_unmatched() -> None:
    graph = chain_graph()

    match = match_observation(
        graph,
        observation(
            coordinates=((31.3300, 30.0604), (31.3310, 30.0604)),
        ),
        all_edges(graph),
    )

    assert match.status is TrafficMatchStatus.UNMATCHED
    assert match.reason == "GEOMETRY_SEPARATION"


def test_direction_beyond_thirty_degrees_is_unmatched() -> None:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    add_node(graph, "a", 31.3300, 30.0600)
    add_node(graph, "b", 31.3302, 30.0600)
    add_edge(graph, "a", "b")

    match = match_observation(
        graph,
        observation(
            coordinates=((31.3300, 30.05994), (31.3302, 30.06014)),
        ),
        all_edges(graph),
    )

    assert match.status is TrafficMatchStatus.UNMATCHED
    assert match.reason == "DIRECTION_DIFFERENCE"


def test_two_disconnected_passing_chains_are_ambiguous() -> None:
    graph = chain_graph()
    add_node(graph, "d", 31.3300, 30.06015)
    add_node(graph, "e", 31.3305, 30.06015)
    add_node(graph, "f", 31.3310, 30.06015)
    add_edge(graph, "d", "e")
    add_edge(graph, "e", "f")

    match = match_observation(graph, observation(), all_edges(graph))

    assert match.status is TrafficMatchStatus.AMBIGUOUS
    assert match.reason == "MULTIPLE_CANDIDATE_CHAINS"
    assert match.edge_keys == ()


def test_branching_passing_candidates_are_ambiguous() -> None:
    graph = chain_graph()
    add_node(graph, "d", 31.3310, 30.0601)
    add_edge(graph, "b", "d")

    match = match_observation(graph, observation(), all_edges(graph))

    assert match.status is TrafficMatchStatus.AMBIGUOUS
    assert match.reason == "BRANCHING_CANDIDATES"


def test_parallel_passing_candidates_are_ambiguous() -> None:
    graph = chain_graph()
    add_edge(graph, "a", "b", key="1")

    match = match_observation(graph, observation(), all_edges(graph))

    assert match.status is TrafficMatchStatus.AMBIGUOUS
    assert match.reason == "PARALLEL_CANDIDATES"


def test_corridor_selection_is_name_bounded() -> None:
    graph = chain_graph()
    add_node(graph, "x", 31.3320, 30.0600)
    add_edge(graph, "c", "x", name="Unrelated Local Street")

    selected = select_corridor_edges(graph, ("الطيران", "عباس العقاد"))

    assert selected == frozenset({("a", "b", "0"), ("b", "c", "0")})


def test_empty_corridor_name_does_not_select_every_edge() -> None:
    graph = chain_graph()

    assert select_corridor_edges(graph, ("",)) == frozenset()


def test_overlay_is_graph_bound_and_does_not_mutate_base_graph() -> None:
    graph = chain_graph()
    graph_before = deepcopy(nx.node_link_data(graph, edges="edges"))
    fingerprint_before = graph_fingerprint(graph)

    matches, overlay = build_overlay(
        graph,
        snapshot_id="snapshot-1",
        observations=(observation(),),
        allowed_edges=all_edges(graph),
    )

    assert matches[0].status is TrafficMatchStatus.MATCHED
    assert len(overlay.entries) == 2
    assert overlay.entries[0].traffic_factor == 2
    assert overlay.graph_fingerprint == fingerprint_before
    assert validate_overlay_for_graph(graph, overlay) is True
    assert nx.node_link_data(graph, edges="edges") == graph_before
    assert graph_fingerprint(graph) == fingerprint_before

    changed_graph = graph.copy()
    changed_graph.nodes["a"]["x"] = 31.5
    assert validate_overlay_for_graph(changed_graph, overlay) is False


def test_competing_observations_for_the_same_edges_are_not_applied() -> None:
    graph = chain_graph()

    matches, overlay = build_overlay(
        graph,
        snapshot_id="snapshot-1",
        observations=(observation(), observation(observation_id="obs-2")),
        allowed_edges=all_edges(graph),
    )

    assert {match.status for match in matches} == {TrafficMatchStatus.AMBIGUOUS}
    assert {match.reason for match in matches} == {"COMPETING_OBSERVATIONS"}
    assert overlay.entries == ()


def test_closure_overlay_has_no_fabricated_traffic_factor() -> None:
    graph = chain_graph()

    _, overlay = build_overlay(
        graph,
        snapshot_id="snapshot-closure",
        observations=(observation(road_closure=True),),
        allowed_edges=all_edges(graph),
    )

    assert all(entry.road_closure for entry in overlay.entries)
    assert all(entry.traffic_factor is None for entry in overlay.entries)
