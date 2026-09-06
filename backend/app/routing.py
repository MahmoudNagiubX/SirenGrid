from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import networkx as nx
from pydantic import BaseModel, Field

from app.config import settings
from app.schemas import Coordinate

__all__ = [
    "RoutingPointOutsideGraphError",
    "RouteNotFoundError",
    "RouteResult",
    "haversine_distance_m",
    "load_routing_graph",
    "snap_coordinate_to_graph",
    "compute_route_on_graph",
]

ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME = "OSM_BASE_TRAVEL_TIME"


class RoutingPointOutsideGraphError(ValueError):
    """Raised when a coordinate is too far from the routing graph to snap safely."""


class RouteNotFoundError(ValueError):
    """Raised when no valid route can be calculated between origin and destination."""


class RouteResult(BaseModel):
    """Result of route computation on the road network graph."""

    nodes: list[Any]
    geometry: dict[str, Any]
    distance_m: float = Field(gt=0)
    eta_seconds: float = Field(gt=0)
    origin_snap_distance_m: float = Field(ge=0)
    destination_snap_distance_m: float = Field(ge=0)
    routing_source: str = ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def haversine_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate great-circle distance between two geographic coordinates in meters."""
    r_earth = 6371000.0  # Earth mean radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    a = max(0.0, min(1.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_earth * c


def _get_node_coords(graph: nx.Graph, node: Any) -> tuple[float, float]:
    data = graph.nodes[node]
    if "x" in data and "y" in data:
        return float(data["x"]), float(data["y"])
    if "lon" in data and "lat" in data:
        return float(data["lon"]), float(data["lat"])
    if "longitude" in data and "latitude" in data:
        return float(data["longitude"]), float(data["latitude"])
    raise ValueError(f"Node {node} missing geographic coordinates (x/y or lon/lat)")


def _parse_wkt_linestring(wkt_str: str) -> list[list[float]]:
    start = wkt_str.find("(")
    end = wkt_str.rfind(")")
    if start == -1 or end == -1 or start >= end:
        return []
    coords_content = wkt_str[start + 1 : end].strip()
    coords: list[list[float]] = []
    for pair in coords_content.split(","):
        parts = pair.strip().split()
        if len(parts) >= 2:
            try:
                coords.append([float(parts[0]), float(parts[1])])
            except (ValueError, TypeError):
                continue
    return coords


def _parse_numeric_travel_time(attrs: dict[str, Any]) -> float:
    raw = attrs.get("travel_time")
    if raw is None:
        raw = attrs.get("travel_time_s")
    if raw is None:
        return float("inf")
    try:
        val = float(raw)
        return val if val >= 0 else float("inf")
    except (ValueError, TypeError):
        return float("inf")


def _edge_travel_time_weight(u: Any, v: Any, edge_data: Any) -> float:
    if isinstance(edge_data, dict) and edge_data:
        first_val = next(iter(edge_data.values()))
        if isinstance(first_val, dict):
            # Multigraph dict of {key: attrs}
            times = [_parse_numeric_travel_time(attrs) for attrs in edge_data.values()]
            valid = [t for t in times if t < float("inf")]
            return min(valid) if valid else float("inf")
        else:
            return _parse_numeric_travel_time(edge_data)
    return float("inf")


def load_routing_graph(graph_path: Path | str | None = None) -> nx.MultiDiGraph:
    """Load the processed road network graph from GraphML.

    Raises FileNotFoundError visibly if the GraphML file is missing.
    """
    if graph_path is None:
        target_path = settings.NASR_CITY_DATA_DIR / "nasr_city_graph.graphml"
    else:
        target_path = Path(graph_path)

    if not target_path.is_file():
        raise FileNotFoundError(f"Routing graph file not found: {target_path}")

    return nx.read_graphml(target_path)


def snap_coordinate_to_graph(
    graph: nx.Graph,
    coordinate: Coordinate,
    max_distance_m: float = 1500.0,
) -> tuple[Any, float]:
    """Snap a coordinate to the nearest valid node on the road graph.

    Rejects points farther than max_distance_m with RoutingPointOutsideGraphError.
    """
    if graph.number_of_nodes() == 0:
        raise RoutingPointOutsideGraphError("Routing graph contains no nodes")

    target_lon = coordinate.lon
    target_lat = coordinate.lat

    best_node = None
    min_dist = float("inf")

    for node in graph.nodes():
        try:
            node_lon, node_lat = _get_node_coords(graph, node)
        except ValueError:
            continue

        dist = haversine_distance_m(target_lon, target_lat, node_lon, node_lat)
        if dist < min_dist:
            min_dist = dist
            best_node = node

    if best_node is None:
        raise RoutingPointOutsideGraphError(
            "No nodes with valid coordinates found in routing graph"
        )

    if min_dist > max_distance_m:
        raise RoutingPointOutsideGraphError(
            f"Coordinate ({target_lat}, {target_lon}) is {min_dist:.1f}m from nearest graph node, "
            f"exceeding max snap distance {max_distance_m:.1f}m"
        )

    return best_node, min_dist


def compute_route_on_graph(
    graph: nx.Graph,
    origin: Coordinate,
    destination: Coordinate,
    max_snap_distance_m: float | None = None,
) -> RouteResult:
    """Compute the fastest route between origin and destination on the base road graph.

    Algorithm:
    1. Snap origin and destination to nearest graph nodes; reject points farther than max snap distance.
    2. Reject requests where origin and destination snap to the same node.
    3. Use NetworkX shortest path weighted only by numeric OSM edge travel_time.
    4. For multiedges, deterministically choose the minimum travel_time edge.
    5. Reconstruct route LineString geometry from edge WKT in travel direction, falling back to node points.
    6. Sum exact numeric edge lengths and travel times.
    """
    snap_threshold = (
        max_snap_distance_m
        if max_snap_distance_m is not None
        else settings.MAX_ROUTE_SNAP_DISTANCE_M
    )

    origin_node, origin_snap_dist = snap_coordinate_to_graph(
        graph, origin, max_distance_m=snap_threshold
    )
    dest_node, dest_snap_dist = snap_coordinate_to_graph(
        graph, destination, max_distance_m=snap_threshold
    )

    if origin_node == dest_node:
        raise RouteNotFoundError(
            f"Origin and destination snapped to the same graph node ({origin_node})"
        )

    try:
        path = nx.shortest_path(
            graph,
            source=origin_node,
            target=dest_node,
            weight=_edge_travel_time_weight,
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise RouteNotFoundError(
            f"No path found between node {origin_node} and {dest_node}"
        ) from exc

    if not path or len(path) < 2:
        raise RouteNotFoundError("Calculated path has fewer than 2 nodes")

    total_distance_m = 0.0
    total_eta_seconds = 0.0
    route_coords: list[list[float]] = []

    is_multigraph = graph.is_multigraph()

    for u, v in zip(path[:-1], path[1:]):
        best_travel_time = float("inf")
        best_length = float("inf")
        best_attrs: dict[str, Any] | None = None

        if is_multigraph:
            edges = graph.get_edge_data(u, v)
            if not edges:
                raise RouteNotFoundError(f"No edge found between {u} and {v}")

            # Deterministic ordering of keys for reproducible tie-breaking
            for key in sorted(edges.keys(), key=lambda k: str(k)):
                attrs = edges[key]
                t = _parse_numeric_travel_time(attrs)
                if t == float("inf"):
                    continue
                raw_len = attrs.get("length", attrs.get("length_m"))
                l_val = float(raw_len) if raw_len is not None else 0.0

                if t < best_travel_time:
                    best_travel_time = t
                    best_length = l_val
                    best_attrs = attrs
                elif t == best_travel_time and l_val < best_length:
                    best_length = l_val
                    best_attrs = attrs
        else:
            attrs = graph.get_edge_data(u, v)
            if not attrs:
                raise RouteNotFoundError(f"No edge found between {u} and {v}")
            t = _parse_numeric_travel_time(attrs)
            if t != float("inf"):
                best_travel_time = t
                raw_len = attrs.get("length", attrs.get("length_m"))
                best_length = float(raw_len) if raw_len is not None else 0.0
                best_attrs = attrs

        if best_attrs is None or best_travel_time == float("inf"):
            raise RouteNotFoundError(
                f"No edge with usable travel_time found between {u} and {v}"
            )

        u_lon, u_lat = _get_node_coords(graph, u)
        v_lon, v_lat = _get_node_coords(graph, v)

        if best_length <= 0.0:
            best_length = haversine_distance_m(u_lon, u_lat, v_lon, v_lat)

        total_distance_m += best_length
        total_eta_seconds += best_travel_time

        geom_raw = best_attrs.get("geometry")
        edge_coords: list[list[float]] = []
        if geom_raw and isinstance(geom_raw, str):
            edge_coords = _parse_wkt_linestring(geom_raw)

        if len(edge_coords) < 2:
            edge_coords = [[u_lon, u_lat], [v_lon, v_lat]]
        else:
            start_lon, start_lat = edge_coords[0]
            end_lon, end_lat = edge_coords[-1]
            fwd_dist = haversine_distance_m(
                start_lon, start_lat, u_lon, u_lat
            ) + haversine_distance_m(end_lon, end_lat, v_lon, v_lat)
            rev_dist = haversine_distance_m(
                end_lon, end_lat, u_lon, u_lat
            ) + haversine_distance_m(start_lon, start_lat, v_lon, v_lat)
            if rev_dist < fwd_dist:
                edge_coords.reverse()

        if not route_coords:
            route_coords.extend(edge_coords)
        else:
            if (
                abs(route_coords[-1][0] - edge_coords[0][0]) < 1e-7
                and abs(route_coords[-1][1] - edge_coords[0][1]) < 1e-7
            ):
                route_coords.extend(edge_coords[1:])
            else:
                route_coords.extend(edge_coords)

    if total_distance_m <= 0 or total_eta_seconds <= 0:
        raise RouteNotFoundError("Route has non-positive distance or travel time")

    if len(route_coords) < 2:
        raise RouteNotFoundError("Route geometry could not be constructed")

    return RouteResult(
        nodes=path,
        geometry={"type": "LineString", "coordinates": route_coords},
        distance_m=total_distance_m,
        eta_seconds=total_eta_seconds,
        origin_snap_distance_m=origin_snap_dist,
        destination_snap_distance_m=dest_snap_dist,
        routing_source=ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME,
    )
