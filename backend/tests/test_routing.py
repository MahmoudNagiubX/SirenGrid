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


def test_same_snapped_node_raises_route_not_found_error():
    g = nx.DiGraph()
    g.add_node(1, x=31.300, y=30.000)
    g.add_node(2, x=31.310, y=30.010)
    g.add_edge(1, 2, length=100.0, travel_time=10.0)

    # Origin and destination snap to node 1
    origin = Coordinate(lat=30.000, lon=31.300)
    destination = Coordinate(lat=30.0001, lon=31.3001)

    with pytest.raises(RouteNotFoundError, match="same.*node"):
        compute_route_on_graph(g, origin, destination)


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


def test_load_routing_graph_reuses_unchanged_graph_and_refreshes_after_republish(
    tmp_path,
) -> None:
    """The immutable base graph cache follows a changed GraphML asset."""
    clear_routing_graph_cache()
    source = settings.NASR_CITY_DATA_DIR / "nasr_city_graph.graphml"
    target = tmp_path / "graph.graphml"
    shutil.copy2(source, target)

    first = load_routing_graph(target)
    assert load_routing_graph(target) is first

    rewritten = first.copy()
    rewritten.remove_node(next(iter(rewritten.nodes())))
    nx.write_graphml(rewritten, target)
    stats = target.stat()
    os.utime(target, ns=(stats.st_atime_ns, stats.st_mtime_ns + 1_000_000_000))

    refreshed = load_routing_graph(target)
    assert refreshed is not first
    assert refreshed.number_of_nodes() == first.number_of_nodes() - 1
    clear_routing_graph_cache()


def test_graph_fingerprint_revalidates_structural_changes() -> None:
    """Fingerprint memoization must not hide node or edge changes."""
    clear_graph_fingerprint_cache()
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=31.30, y=30.00)
    graph.add_node("b", x=31.31, y=30.00)
    graph.add_edge("a", "b", key="0", length=100.0, travel_time=10.0)

    first = graph_fingerprint(graph)
    assert graph_fingerprint(graph) == first

    graph.add_node("c", x=31.32, y=30.00)
    assert graph_fingerprint(graph) != first
    graph.add_edge("b", "c", key="0", length=100.0, travel_time=10.0)
    with_edge = graph_fingerprint(graph)
    assert with_edge != first

    twin = nx.MultiDiGraph()
    twin.add_node("a", x=31.30, y=30.00)
    twin.add_node("b", x=31.31, y=30.00)
    twin.add_node("c", x=31.32, y=30.00)
    twin.add_edge("a", "b", key="0", length=100.0, travel_time=10.0)
    twin.add_edge("b", "c", key="0", length=100.0, travel_time=10.0)
    assert graph_fingerprint(twin) == with_edge
    clear_graph_fingerprint_cache()
