from __future__ import annotations

import os
import shutil

import networkx as nx
import pytest

from app.config import settings
from app.routing import (
    RouteNotFoundError,
    RouteResult,
    RoutingPointOutsideGraphError,
    clear_routing_graph_cache,
    compute_route_on_graph,
    haversine_distance_m,
    load_routing_graph,
    snap_coordinate_to_graph,
)
from app.schemas import Coordinate
from app.traffic.matching import clear_graph_fingerprint_cache, graph_fingerprint


def test_haversine_distance_m_basic():
    # Same point returns zero
    assert haversine_distance_m(31.33, 30.06, 31.33, 30.06) == 0.0

    # Known distance test (approx 13-14 meters in Cairo)
    dist = haversine_distance_m(31.3263282, 30.0840694, 31.3263191, 30.0839447)
    assert 13.0 < dist < 15.0


def test_synthetic_graph_chooses_lower_travel_time_path():
    """Verify that NetworkX shortest path weights exclusively by numeric OSM travel_time,

    preferring the lower-travel-time path even if its distance is greater.
    """
    g = nx.MultiDiGraph()
    # Node 1: (lon=31.300, lat=30.000)
    # Node 2: (lon=31.305, lat=30.005)
    # Node 3: (lon=31.310, lat=30.010)
    g.add_node(1, x="31.300", y="30.000")
    g.add_node(2, x="31.305", y="30.005")
    g.add_node(3, x="31.310", y="30.010")

    # Path A: Direct 1 -> 3, shorter distance (500m), but high travel time (120s)
    g.add_edge(1, 3, key=0, length="500.0", travel_time="120.0")

    # Path B: Indirect 1 -> 2 -> 3, longer distance (400 + 400 = 800m), but lower travel time (20 + 20 = 40s)
    g.add_edge(1, 2, key=0, length="400.0", travel_time="20.0")
    g.add_edge(2, 3, key=0, length="400.0", travel_time="20.0")

    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.010, lon=31.310)

    result = compute_route_on_graph(g, origin, destination)

    assert result.nodes == [1, 2, 3]
    assert result.distance_m == 800.0
    assert result.eta_seconds == 40.0
    assert result.routing_source == "OSM_BASE_TRAVEL_TIME"


def test_synthetic_multigraph_deterministic_minimum_travel_time_edge():
    """For multiedges between two nodes, deterministic minimum travel_time edge is selected."""
    g = nx.MultiDiGraph()
    g.add_node("A", x=31.300, y=30.000)
    g.add_node("B", x=31.305, y=30.005)

    # Edge 0: travel_time 60s, length 100m
    g.add_edge("A", "B", key=0, length=100.0, travel_time=60.0)
    # Edge 1: travel_time 25s, length 110m (preferred)
    g.add_edge("A", "B", key=1, length=110.0, travel_time=25.0)

    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.005, lon=31.305)

    result = compute_route_on_graph(g, origin, destination)

    assert result.nodes == ["A", "B"]
    assert result.distance_m == 110.0
    assert result.eta_seconds == 25.0


def test_distance_and_eta_sums_are_exact():
    """Distance and ETA sums must be exact arithmetic sums without fabricated values."""
    g = nx.DiGraph()
    g.add_node(1, x=31.300, y=30.000)
    g.add_node(2, x=31.305, y=30.005)
    g.add_node(3, x=31.310, y=30.010)

    g.add_edge(1, 2, length=150.5, travel_time=32.25)
    g.add_edge(2, 3, length=249.5, travel_time=47.75)

    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.010, lon=31.310)

    result = compute_route_on_graph(g, origin, destination)

    assert result.distance_m == 400.0
    assert result.eta_seconds == 80.0


def test_wkt_edge_geometry_direction_and_fallback():
    """WKT edge geometry is parsed in the travel direction; edges without geometry fallback to node line."""
    g = nx.DiGraph()
    g.add_node(1, x=31.300, y=30.000)
    g.add_node(2, x=31.305, y=30.005)
    g.add_node(3, x=31.310, y=30.010)

    # Edge 1 -> 2 has WKT reversed in storage (from 2 down to 1)
    g.add_edge(
        1,
        2,
        length=100.0,
        travel_time=10.0,
        geometry="LINESTRING (31.305 30.005, 31.302 30.002, 31.300 30.000)",
    )
    # Edge 2 -> 3 has NO geometry attribute (must fallback to [2 coords, 3 coords])
    g.add_edge(2, 3, length=100.0, travel_time=10.0)

    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.010, lon=31.310)

    result = compute_route_on_graph(g, origin, destination)

    coords = result.geometry["coordinates"]
    assert result.geometry["type"] == "LineString"
    assert len(coords) >= 3
    # Starts at node 1 (31.300, 30.000)
    assert coords[0] == [31.300, 30.000]
    # Traverses the intermediate point in correct direction
    assert coords[1] == [31.302, 30.002]
    # Ends at node 3 (31.310, 30.010)
    assert coords[-1] == [31.310, 30.010]


def test_no_path_raises_route_not_found_error():
    g = nx.DiGraph()
    g.add_node(1, x=31.300, y=30.000)
    g.add_node(2, x=31.305, y=30.005)
    # No edge between 1 and 2

    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.005, lon=31.305)

    with pytest.raises(RouteNotFoundError, match="No path"):
        compute_route_on_graph(g, origin, destination)


def test_same_snapped_node_yields_a_valid_zero_travel_route():
    """A responder already at the destination is the ideal dispatch outcome.

    It must produce a real zero route rather than an error that would drop the
    closest responder from planning.
    """
    g = nx.DiGraph()
    g.add_node(1, x=31.300, y=30.000)
    g.add_node(2, x=31.310, y=30.010)
    g.add_edge(1, 2, length=100.0, travel_time=10.0)

    # Origin and destination both snap to node 1.
    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.0001, lon=31.3001)

    result = compute_route_on_graph(g, origin, destination)

    assert result.distance_m == 0.0
    assert result.eta_seconds == 0.0
    assert result.nodes == [1]
    assert result.routing_source == "OSM_BASE_TRAVEL_TIME"

    # Geometry stays a structurally valid LineString at the node itself; no
    # straight-line travel is fabricated.
    assert result.geometry["type"] == "LineString"
    assert result.geometry["coordinates"] == [[31.300, 30.000], [31.300, 30.000]]

    # Serialization round-trips for map and plan consumers.
    as_dict = result.to_dict()
    assert as_dict["distance_m"] == 0.0
    assert as_dict["eta_seconds"] == 0.0


def test_same_snapped_node_traffic_aware_route_is_unaffected_by_overlay():
    """No overlay or closure can change a route that traverses no edge."""
    from app.routing import compute_traffic_aware_route

    g = nx.MultiDiGraph()
    g.add_node(1, x=31.300, y=30.000)
    g.add_node(2, x=31.310, y=30.010)
    g.add_edge(1, 2, key="0", length=100.0, travel_time=10.0, base_travel_time_s=10.0)

    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.0001, lon=31.3001)

    result = compute_traffic_aware_route(g, origin, destination, None)

    assert result.distance_m == 0.0
    assert result.eta_seconds == 0.0
    assert result.base_eta == 0.0
    assert result.effective_eta == 0.0
    assert result.edge_keys == []
    assert result.total_traversed_edge_count == 0
    assert result.matched_traversed_edge_count == 0
    assert result.traffic_coverage_ratio == 0.0
    assert result.routing_source == "OSM_BASE_TRAVEL_TIME"
    assert result.traffic_weight_affected_path_selection is False
    assert result.traffic_closure_affected_path_selection is False


def test_too_far_coordinate_raises_routing_point_outside_graph_error():
    g = nx.DiGraph()
    g.add_node(1, x=31.300, y=30.000)
    g.add_node(2, x=31.310, y=30.010)
    g.add_edge(1, 2, length=100.0, travel_time=10.0)

    # Coordinate is 0, 0 (thousands of km away)
    far_coord = Coordinate(lat=0.0, lon=0.0)
    valid_coord = Coordinate(lat=30.000, lon=31.300)

    with pytest.raises(RoutingPointOutsideGraphError, match="exceed"):
        snap_coordinate_to_graph(g, far_coord, max_distance_m=1500.0)

    with pytest.raises(RoutingPointOutsideGraphError, match="exceed"):
        compute_route_on_graph(g, far_coord, valid_coord)

    with pytest.raises(RoutingPointOutsideGraphError, match="exceed"):
        compute_route_on_graph(g, valid_coord, far_coord)


def test_missing_graphml_raises_file_not_found_error(tmp_path):
    missing_path = tmp_path / "nonexistent_graph.graphml"
    with pytest.raises(FileNotFoundError, match="Routing graph file not found"):
        load_routing_graph(missing_path)

    # Also verify with settings fallback when configured file does not exist
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "nasr_city_data_dir", empty_dir)
        with pytest.raises(FileNotFoundError, match="Routing graph file not found"):
            load_routing_graph()


def test_real_pinned_nasr_city_graphml_loads():
    graph = load_routing_graph()
    assert isinstance(graph, nx.MultiDiGraph)
    assert graph.number_of_nodes() > 0
    assert graph.number_of_edges() > 0


def test_real_nasr_city_route_computes_with_exact_spec():
    graph = load_routing_graph()

    # Real Nasr City locations: Police station and Hospital
    origin = Coordinate(lat=30.0687969, lon=31.3411596)
    destination = Coordinate(lat=30.0642054, lon=31.3455818)

    result = compute_route_on_graph(graph, origin, destination)

    assert isinstance(result, RouteResult)
    assert len(result.nodes) >= 2
    assert result.distance_m > 0
    assert result.eta_seconds > 0
    assert result.origin_snap_distance_m >= 0
    assert result.destination_snap_distance_m >= 0
    assert result.routing_source == "OSM_BASE_TRAVEL_TIME"

    # GeoJSON LineString geometry
    geometry = result.geometry
    assert isinstance(geometry, dict)
    assert geometry.get("type") == "LineString"
    coordinates = geometry.get("coordinates")
    assert isinstance(coordinates, list)
    assert len(coordinates) >= 2
    for pt in coordinates:
        assert isinstance(pt, list)
        assert len(pt) == 2
        assert isinstance(pt[0], float)
        assert isinstance(pt[1], float)

    # Serialization path
    as_dict = result.to_dict()
    assert isinstance(as_dict, dict)
    assert as_dict["routing_source"] == "OSM_BASE_TRAVEL_TIME"
    assert as_dict["distance_m"] == result.distance_m
    assert as_dict["eta_seconds"] == result.eta_seconds
    assert as_dict["geometry"] == geometry


def test_load_routing_graph_reuses_the_immutable_graph_and_refreshes_on_change(
    tmp_path,
) -> None:
    """The base graph is cached per file identity but must follow a refresh.

    Reusing one object keeps the fingerprint memo effective across requests.
    A republished asset must still be picked up rather than served stale.
    """
    clear_routing_graph_cache()
    source = settings.NASR_CITY_DATA_DIR / "nasr_city_graph.graphml"
    target = tmp_path / "graph.graphml"
    shutil.copy2(source, target)

    first = load_routing_graph(target)
    second = load_routing_graph(target)
    assert first is second, "unchanged graph asset should not be re-parsed"

    # Republish with different content and a distinct modification time.
    rewritten = first.copy()
    rewritten.remove_node(next(iter(rewritten.nodes())))
    nx.write_graphml(rewritten, target)
    stats = target.stat()
    os.utime(target, ns=(stats.st_atime_ns, stats.st_mtime_ns + 1_000_000_000))

    third = load_routing_graph(target)
    assert third is not first, "refreshed graph asset must invalidate the cache"
    assert third.number_of_nodes() == first.number_of_nodes() - 1
    clear_routing_graph_cache()


def test_graph_fingerprint_is_memoized_without_serving_a_stale_hash() -> None:
    """Memoization must never hide a structural change to a graph."""
    clear_graph_fingerprint_cache()
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=31.30, y=30.00)
    graph.add_node("b", x=31.31, y=30.00)
    graph.add_edge("a", "b", key="0", length=100.0, travel_time=10.0)

    first = graph_fingerprint(graph)
    assert graph_fingerprint(graph) == first, "repeat call must be stable"

    graph.add_node("c", x=31.32, y=30.00)
    assert graph_fingerprint(graph) != first, "added node must change the hash"

    graph.add_edge("b", "c", key="0", length=100.0, travel_time=10.0)
    with_edge = graph_fingerprint(graph)
    assert with_edge != first

    # An independently built but identical graph hashes the same, proving the
    # memo is keyed on content rather than object identity alone.
    twin = nx.MultiDiGraph()
    twin.add_node("a", x=31.30, y=30.00)
    twin.add_node("b", x=31.31, y=30.00)
    twin.add_node("c", x=31.32, y=30.00)
    twin.add_edge("a", "b", key="0", length=100.0, travel_time=10.0)
    twin.add_edge("b", "c", key="0", length=100.0, travel_time=10.0)
    assert graph_fingerprint(twin) == with_edge
    clear_graph_fingerprint_cache()


def test_snap_coordinate_to_graph_memoizes_repeated_calls() -> None:
    """Repeated calls with same graph and coordinate return identical results and use cache."""
    clear_routing_graph_cache()
    from app.routing import _GRAPH_SNAP_CACHE

    graph = nx.MultiDiGraph()
    graph.add_node("A", x=31.300, y=30.000)
    coord = Coordinate(lat=30.000, lon=31.300)

    first_node, first_dist = snap_coordinate_to_graph(graph, coord, max_distance_m=500.0)
    assert first_node == "A"
    assert first_dist == pytest.approx(0.0)

    # Check that cache has been populated for this graph
    cache_key = (float(coord.lat), float(coord.lon), 500.0)
    assert graph in _GRAPH_SNAP_CACHE
    assert _GRAPH_SNAP_CACHE[graph][cache_key] == (first_node, first_dist)

    # Second call returns identical result
    second_node, second_dist = snap_coordinate_to_graph(graph, coord, max_distance_m=500.0)
    assert second_node == first_node
    assert second_dist == first_dist
    clear_routing_graph_cache()


def test_snap_coordinate_cache_key_includes_max_distance() -> None:
    """Cache key includes max_distance_m so permissive snaps don't leak into strict ones."""
    clear_routing_graph_cache()
    graph = nx.MultiDiGraph()
    graph.add_node("A", x=31.300, y=30.000)
    # Coordinate ~111m away
    coord = Coordinate(lat=30.001, lon=31.300)

    node, dist = snap_coordinate_to_graph(graph, coord, max_distance_m=500.0)
    assert node == "A"
    assert dist > 10.0

    # A subsequent call with a tighter threshold that dist exceeds MUST raise
    with pytest.raises(RoutingPointOutsideGraphError, match="exceeding max snap distance"):
        snap_coordinate_to_graph(graph, coord, max_distance_m=10.0)
    clear_routing_graph_cache()


def test_snap_coordinate_cache_isolated_per_graph_instance() -> None:
    """Two different graph objects cannot share a snap result."""
    clear_routing_graph_cache()
    from app.routing import _GRAPH_SNAP_CACHE

    g1 = nx.MultiDiGraph()
    g1.add_node("N1", x=31.300, y=30.000)

    g2 = nx.MultiDiGraph()
    g2.add_node("N2", x=31.300, y=30.000)

    coord = Coordinate(lat=30.000, lon=31.300)

    node1, _ = snap_coordinate_to_graph(g1, coord, max_distance_m=500.0)
    assert node1 == "N1"

    node2, _ = snap_coordinate_to_graph(g2, coord, max_distance_m=500.0)
    assert node2 == "N2"

    assert g1 in _GRAPH_SNAP_CACHE
    assert g2 in _GRAPH_SNAP_CACHE
    assert _GRAPH_SNAP_CACHE[g1] != _GRAPH_SNAP_CACHE[g2]
    clear_routing_graph_cache()


def test_clear_routing_graph_cache_drops_snap_cache() -> None:
    """Explicit cache clear removes cached snaps."""
    clear_routing_graph_cache()
    from app.routing import _GRAPH_SNAP_CACHE

    graph = nx.MultiDiGraph()
    graph.add_node("A", x=31.300, y=30.000)
    coord = Coordinate(lat=30.000, lon=31.300)

    snap_coordinate_to_graph(graph, coord, max_distance_m=500.0)
    assert graph in _GRAPH_SNAP_CACHE
    assert len(_GRAPH_SNAP_CACHE[graph]) > 0

    clear_routing_graph_cache()
    assert graph not in _GRAPH_SNAP_CACHE
    assert len(_GRAPH_SNAP_CACHE) == 0


def test_same_node_route_remains_zero_distance_and_valid_with_snap_cache() -> None:
    """Same-node route remains zero-distance/zero-ETA and valid with coordinate snapping."""
    clear_routing_graph_cache()
    graph = nx.MultiDiGraph()
    graph.add_node("A", x=31.300, y=30.000)
    graph.add_node("B", x=31.310, y=30.010)
    graph.add_edge("A", "B", key="0", length=1000.0, travel_time=60.0)

    # Both coords snap to node "A"
    origin = Coordinate(lat=30.00001, lon=31.30001)
    destination = Coordinate(lat=30.00002, lon=31.30002)

    result = compute_route_on_graph(graph, origin, destination)
    assert result.nodes == ["A"]
    assert result.distance_m == 0.0
    assert result.eta_seconds == 0.0
    assert result.geometry["type"] == "LineString"
    assert len(result.geometry["coordinates"]) == 2
    assert result.geometry["coordinates"][0] == result.geometry["coordinates"][1]

    # Repeat call exercises cached coordinate snaps
    repeat_result = compute_route_on_graph(graph, origin, destination)
    assert repeat_result.nodes == ["A"]
    assert repeat_result.distance_m == 0.0
    assert repeat_result.eta_seconds == 0.0
    clear_routing_graph_cache()


def test_compute_traffic_aware_route_calculates_alternatives_by_default() -> None:
    """Default call to compute_traffic_aware_route calculates alternatives."""
    from app.routing import compute_traffic_aware_route

    graph = nx.MultiDiGraph()
    graph.add_node("A", x=31.300, y=30.000)
    graph.add_node("B", x=31.305, y=30.005)
    graph.add_node("C", x=31.305, y=29.995)
    graph.add_node("D", x=31.310, y=30.000)
    graph.add_edge("A", "B", key="0", length=100.0, travel_time=10.0, base_travel_time_s=10.0)
    graph.add_edge("B", "D", key="0", length=100.0, travel_time=10.0, base_travel_time_s=10.0)
    graph.add_edge("A", "C", key="0", length=120.0, travel_time=15.0, base_travel_time_s=15.0)
    graph.add_edge("C", "D", key="0", length=120.0, travel_time=15.0, base_travel_time_s=15.0)

    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.000, lon=31.310)

    result = compute_traffic_aware_route(graph, origin, destination, None)
    assert len(result.alternatives) == 1
    assert result.alternatives[0].nodes == ["A", "C", "D"]


def test_compute_traffic_aware_route_skips_alternatives_when_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """When include_alternatives=False, skip _edge_disjoint_alternative and return empty alternatives."""
    from app import routing
    from app.routing import compute_traffic_aware_route

    graph = nx.MultiDiGraph()
    graph.add_node("A", x=31.300, y=30.000)
    graph.add_node("B", x=31.305, y=30.005)
    graph.add_node("C", x=31.305, y=29.995)
    graph.add_node("D", x=31.310, y=30.000)
    graph.add_edge("A", "B", key="0", length=100.0, travel_time=10.0, base_travel_time_s=10.0)
    graph.add_edge("B", "D", key="0", length=100.0, travel_time=10.0, base_travel_time_s=10.0)
    graph.add_edge("A", "C", key="0", length=120.0, travel_time=15.0, base_travel_time_s=15.0)
    graph.add_edge("C", "D", key="0", length=120.0, travel_time=15.0, base_travel_time_s=15.0)

    called = False

    def fail_if_called(*_args: object, **_kwargs: object):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(routing, "_edge_disjoint_alternative", fail_if_called)

    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.000, lon=31.310)

    result = compute_traffic_aware_route(graph, origin, destination, None, include_alternatives=False)
    assert result.alternatives == []
    assert not called


def test_compute_traffic_aware_route_primary_route_facts_match() -> None:
    """Primary route facts match identically whether include_alternatives is True or False."""
    from app.routing import compute_traffic_aware_route

    graph = nx.MultiDiGraph()
    graph.add_node("A", x=31.300, y=30.000)
    graph.add_node("B", x=31.305, y=30.005)
    graph.add_node("C", x=31.305, y=29.995)
    graph.add_node("D", x=31.310, y=30.000)
    graph.add_edge("A", "B", key="0", length=100.0, travel_time=10.0, base_travel_time_s=10.0)
    graph.add_edge("B", "D", key="0", length=100.0, travel_time=10.0, base_travel_time_s=10.0)
    graph.add_edge("A", "C", key="0", length=120.0, travel_time=15.0, base_travel_time_s=15.0)
    graph.add_edge("C", "D", key="0", length=120.0, travel_time=15.0, base_travel_time_s=15.0)

    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.000, lon=31.310)

    with_alt = compute_traffic_aware_route(graph, origin, destination, None, include_alternatives=True)
    without_alt = compute_traffic_aware_route(graph, origin, destination, None, include_alternatives=False)

    assert without_alt.nodes == with_alt.nodes
    assert without_alt.edge_keys == with_alt.edge_keys
    assert without_alt.geometry == with_alt.geometry
    assert without_alt.distance_m == with_alt.distance_m
    assert without_alt.eta_seconds == with_alt.eta_seconds
    assert without_alt.base_eta == with_alt.base_eta
    assert without_alt.effective_eta == with_alt.effective_eta
    assert without_alt.traffic_selected_path_base_eta == with_alt.traffic_selected_path_base_eta
    assert without_alt.origin_snap_distance_m == with_alt.origin_snap_distance_m
    assert without_alt.destination_snap_distance_m == with_alt.destination_snap_distance_m
    assert without_alt.routing_source == with_alt.routing_source
    assert without_alt.traffic_snapshot_id == with_alt.traffic_snapshot_id
    assert without_alt.traffic_snapshot_version == with_alt.traffic_snapshot_version
    assert without_alt.traffic_freshness_status == with_alt.traffic_freshness_status
    assert without_alt.matched_traversed_edge_count == with_alt.matched_traversed_edge_count
    assert without_alt.total_traversed_edge_count == with_alt.total_traversed_edge_count
    assert without_alt.traffic_coverage_ratio == with_alt.traffic_coverage_ratio
    assert without_alt.traffic_weight_affected_path_selection == with_alt.traffic_weight_affected_path_selection
    assert without_alt.traffic_closure_affected_path_selection == with_alt.traffic_closure_affected_path_selection
    assert without_alt.traffic_fallback_reason == with_alt.traffic_fallback_reason
    assert without_alt.alternatives == []
    assert len(with_alt.alternatives) > 0


def test_compute_traffic_aware_route_same_node_works_with_default_and_false() -> None:
    """Same-node route works identically with default (True) and include_alternatives=False."""
    from app.routing import compute_traffic_aware_route

    graph = nx.MultiDiGraph()
    graph.add_node("A", x=31.300, y=30.000)
    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.0001, lon=31.3001)

    default_result = compute_traffic_aware_route(graph, origin, destination, None)
    assert default_result.distance_m == 0.0
    assert default_result.eta_seconds == 0.0
    assert default_result.alternatives == []

    false_result = compute_traffic_aware_route(graph, origin, destination, None, include_alternatives=False)
    assert false_result.distance_m == 0.0
    assert false_result.eta_seconds == 0.0
    assert false_result.alternatives == []
    assert false_result.nodes == default_result.nodes
