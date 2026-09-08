from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable
from weakref import WeakKeyDictionary

import networkx as nx
from pydantic import BaseModel, Field

from app.config import settings
from app.schemas import Coordinate, FreshnessStatus
from app.traffic.matching import graph_fingerprint
from app.traffic.models import EdgeKey, TrafficOverlay, TrafficSnapshot

__all__ = [
    "RoutingPointOutsideGraphError",
    "RouteNotFoundError",
    "RouteResult",
    "TrafficAwareRouteResult",
    "SingleSourceTravelTimes",
    "haversine_distance_m",
    "load_routing_graph",
    "clear_routing_graph_cache",
    "snap_coordinate_to_graph",
    "compute_route_on_graph",
    "compute_traffic_aware_route",
    "compute_single_source_travel_times",
]

ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME = "OSM_BASE_TRAVEL_TIME"
ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED = "TOMTOM_TRAFFIC_ADJUSTED"


class RoutingPointOutsideGraphError(ValueError):
    """Raised when a coordinate is too far from the routing graph to snap safely."""


class RouteNotFoundError(ValueError):
    """Raised when no valid route can be calculated between origin and destination."""


class RouteResult(BaseModel):
    """Result of route computation on the road network graph."""

    nodes: list[Any]
    geometry: dict[str, Any]
    # ``ge=0``: a responder already at the destination has a real zero route.
    distance_m: float = Field(ge=0)
    eta_seconds: float = Field(ge=0)
    origin_snap_distance_m: float = Field(ge=0)
    destination_snap_distance_m: float = Field(ge=0)
    routing_source: str = ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class RouteAlternative(BaseModel):
    """Optional edge-disjoint alternative under the same captured routing state."""

    nodes: list[Any]
    edge_keys: list[EdgeKey]
    geometry: dict[str, Any]
    distance_m: float = Field(gt=0)
    effective_eta: float = Field(gt=0)


class TrafficAwareRouteResult(BaseModel):
    """Independent immutable-base and captured-overlay route calculations."""

    base_nodes: list[Any]
    nodes: list[Any]
    edge_keys: list[EdgeKey]
    geometry: dict[str, Any]
    # ``ge=0``: a responder already at the destination traverses no edge, so
    # every travel metric is a real zero rather than a fabricated minimum.
    distance_m: float = Field(ge=0)
    eta_seconds: float = Field(ge=0)
    base_eta: float = Field(ge=0)
    effective_eta: float = Field(ge=0)
    traffic_selected_path_base_eta: float = Field(ge=0)
    origin_snap_distance_m: float = Field(ge=0)
    destination_snap_distance_m: float = Field(ge=0)
    routing_source: str = ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
    traffic_snapshot_id: str | None = None
    traffic_snapshot_version: int | None = None
    traffic_freshness_status: FreshnessStatus | None = None
    matched_traversed_edge_count: int = Field(ge=0)
    total_traversed_edge_count: int = Field(ge=0)
    traffic_coverage_ratio: float = Field(ge=0, le=1)
    traffic_weight_affected_path_selection: bool = False
    traffic_closure_affected_path_selection: bool = False
    traffic_fallback_reason: str | None = None
    alternatives: list[RouteAlternative] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass(frozen=True)
class SingleSourceTravelTimes:
    """Captured base/overlay travel-time trees from one snapped origin."""

    origin_node: Any
    origin_snap_distance_m: float
    base_travel_times: dict[Any, float]
    base_paths: dict[Any, list[Any]]
    effective_travel_times: dict[Any, float]
    effective_paths: dict[Any, list[Any]]
    traffic_snapshot_id: str | None
    traffic_snapshot_version: int | None
    traffic_freshness_status: FreshnessStatus | None
    traffic_overlay_available: bool
    traffic_fallback_reason: str | None


@dataclass(frozen=True)
class _SelectedEdge:
    u: Any
    v: Any
    actual_key: Any
    public_key: EdgeKey
    attrs: dict[str, Any]
    length_m: float
    base_travel_time_s: float
    effective_travel_time_s: float


@dataclass(frozen=True)
class _CalculatedPath:
    nodes: list[Any]
    edges: list[_SelectedEdge]
    geometry: dict[str, Any]
    distance_m: float
    effective_eta: float
    base_eta: float


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


_GRAPH_CACHE_LOCK = RLock()
_GRAPH_CACHE: dict[str, tuple[int, int, nx.MultiDiGraph]] = {}
_GRAPH_SNAP_CACHE: WeakKeyDictionary[
    nx.Graph, dict[tuple[float, float, float], tuple[Any, float]]
] = WeakKeyDictionary()


def clear_routing_graph_cache() -> None:
    """Drop the cached graph and coordinate snaps. Intended for tests and asset refreshes."""
    with _GRAPH_CACHE_LOCK:
        _GRAPH_CACHE.clear()
        _GRAPH_SNAP_CACHE.clear()


def load_routing_graph(graph_path: Path | str | None = None) -> nx.MultiDiGraph:
    """Load the processed road network graph from GraphML.

    Raises FileNotFoundError visibly if the GraphML file is missing.

    The parsed graph is cached per file identity because the base OSM graph is
    immutable runtime truth: routing copies before removing edges and traffic
    is applied as a frozen overlay rather than graph attributes. Reusing one
    object also lets the graph fingerprint memoize across requests. The cache
    is invalidated when the file's modification time or size changes, so a
    published asset refresh is picked up.
    """
    if graph_path is None:
        target_path = settings.NASR_CITY_DATA_DIR / "nasr_city_graph.graphml"
    else:
        target_path = Path(graph_path)

    if not target_path.is_file():
        raise FileNotFoundError(f"Routing graph file not found: {target_path}")

    stats = target_path.stat()
    cache_key = str(target_path.resolve())
    with _GRAPH_CACHE_LOCK:
        cached = _GRAPH_CACHE.get(cache_key)
        if cached is not None:
            mtime_ns, size, graph = cached
            if mtime_ns == stats.st_mtime_ns and size == stats.st_size:
                return graph

    graph = nx.read_graphml(target_path)
    refreshed_stats = target_path.stat()
    with _GRAPH_CACHE_LOCK:
        _GRAPH_CACHE[cache_key] = (
            refreshed_stats.st_mtime_ns,
            refreshed_stats.st_size,
            graph,
        )
    return graph


def snap_coordinate_to_graph(
    graph: nx.Graph,
    coordinate: Coordinate,
    max_distance_m: float = 1500.0,
) -> tuple[Any, float]:
    """Snap a coordinate to the nearest valid node on the road graph.

    Rejects points farther than max_distance_m with RoutingPointOutsideGraphError.
    """
    cache_key = (float(coordinate.lat), float(coordinate.lon), float(max_distance_m))
    with _GRAPH_CACHE_LOCK:
        cached = _GRAPH_SNAP_CACHE.setdefault(graph, {}).get(cache_key)
    if cached is not None:
        return cached

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

    result = (best_node, min_dist)
    with _GRAPH_CACHE_LOCK:
        _GRAPH_SNAP_CACHE.setdefault(graph, {})[cache_key] = result
    return result


def _edge_key(u: Any, v: Any, key: Any) -> EdgeKey:
    return str(u), str(v), str(key)


def _edge_length_m(graph: nx.Graph, u: Any, v: Any, attrs: dict[str, Any]) -> float:
    raw_length = attrs.get("length", attrs.get("length_m"))
    try:
        length = float(raw_length) if raw_length is not None else 0.0
    except (TypeError, ValueError):
        length = 0.0
    if math.isfinite(length) and length > 0:
        return length
    u_lon, u_lat = _get_node_coords(graph, u)
    v_lon, v_lat = _get_node_coords(graph, v)
    return haversine_distance_m(u_lon, u_lat, v_lon, v_lat)


def _iter_edge_candidates(
    graph: nx.Graph, u: Any, v: Any
) -> list[tuple[Any, dict[str, Any]]]:
    edge_data = graph.get_edge_data(u, v)
    if not edge_data:
        return []
    if graph.is_multigraph():
        return [
            (key, edge_data[key])
            for key in sorted(edge_data, key=lambda candidate: str(candidate))
        ]
    return [("0", edge_data)]


def _effective_edge_time(
    base_time: float,
    entry: Any,
) -> float:
    if entry is None:
        return base_time
    if entry.road_closure:
        return float("inf")
    if entry.traffic_factor is None:
        return base_time
    return base_time * entry.traffic_factor


def _path_weight(overlay: TrafficOverlay | None) -> Callable[[Any, Any, Any], float]:
    def weight(u: Any, v: Any, edge_data: Any) -> float:
        if not isinstance(edge_data, dict) or not edge_data:
            return float("inf")
        if all(isinstance(attrs, dict) for attrs in edge_data.values()):
            candidates = edge_data.items()
        else:
            candidates = (("0", edge_data),)
        costs = []
        for key, attrs in candidates:
            base_time = _parse_numeric_travel_time(attrs)
            entry = overlay.entry_for(_edge_key(u, v, key)) if overlay else None
            costs.append(_effective_edge_time(base_time, entry))
        return min(costs, default=float("inf"))

    return weight


def _edge_coordinates(
    graph: nx.Graph, u: Any, v: Any, attrs: dict[str, Any]
) -> list[list[float]]:
    u_lon, u_lat = _get_node_coords(graph, u)
    v_lon, v_lat = _get_node_coords(graph, v)
    geom_raw = attrs.get("geometry")
    edge_coords = (
        _parse_wkt_linestring(geom_raw)
        if isinstance(geom_raw, str) and geom_raw
        else []
    )
    if len(edge_coords) < 2:
        return [[u_lon, u_lat], [v_lon, v_lat]]
    start_lon, start_lat = edge_coords[0]
    end_lon, end_lat = edge_coords[-1]
    forward = haversine_distance_m(
        start_lon, start_lat, u_lon, u_lat
    ) + haversine_distance_m(end_lon, end_lat, v_lon, v_lat)
    reverse = haversine_distance_m(
        end_lon, end_lat, u_lon, u_lat
    ) + haversine_distance_m(start_lon, start_lat, v_lon, v_lat)
    if reverse < forward:
        edge_coords.reverse()
    return edge_coords


def _calculate_path(
    graph: nx.Graph,
    origin_node: Any,
    destination_node: Any,
    overlay: TrafficOverlay | None = None,
) -> _CalculatedPath:
    try:
        path = nx.shortest_path(
            graph,
            source=origin_node,
            target=destination_node,
            weight=_path_weight(overlay),
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise RouteNotFoundError(
            f"No path found between node {origin_node} and {destination_node}"
        ) from exc
    if not path or len(path) < 2:
        raise RouteNotFoundError("Calculated path has fewer than 2 nodes")

    selected_edges: list[_SelectedEdge] = []
    route_coords: list[list[float]] = []
    for u, v in zip(path[:-1], path[1:]):
        ranked: list[tuple[float, float, str, Any, dict[str, Any], float]] = []
        for actual_key, attrs in _iter_edge_candidates(graph, u, v):
            base_time = _parse_numeric_travel_time(attrs)
            entry = (
                overlay.entry_for(_edge_key(u, v, actual_key)) if overlay else None
            )
            effective_time = _effective_edge_time(base_time, entry)
            length = _edge_length_m(graph, u, v, attrs)
            ranked.append(
                (effective_time, length, str(actual_key), actual_key, attrs, base_time)
            )
        usable = [candidate for candidate in ranked if math.isfinite(candidate[0])]
        if not usable:
            raise RouteNotFoundError(
                f"No edge with usable travel_time found between {u} and {v}"
            )
        effective_time, length, _, actual_key, attrs, base_time = min(usable)
        if not math.isfinite(base_time):
            raise RouteNotFoundError(
                f"No edge with usable base travel_time found between {u} and {v}"
            )
        selected_edges.append(
            _SelectedEdge(
                u=u,
                v=v,
                actual_key=actual_key,
                public_key=_edge_key(u, v, actual_key),
                attrs=attrs,
                length_m=length,
                base_travel_time_s=base_time,
                effective_travel_time_s=effective_time,
            )
        )
        edge_coords = _edge_coordinates(graph, u, v, attrs)
        if route_coords and route_coords[-1] == edge_coords[0]:
            route_coords.extend(edge_coords[1:])
        else:
            route_coords.extend(edge_coords)

    distance = sum(edge.length_m for edge in selected_edges)
    effective_eta = sum(edge.effective_travel_time_s for edge in selected_edges)
    base_eta = sum(edge.base_travel_time_s for edge in selected_edges)
    if distance <= 0 or effective_eta <= 0 or base_eta <= 0:
        raise RouteNotFoundError("Route has non-positive distance or travel time")
    if len(route_coords) < 2:
        raise RouteNotFoundError("Route geometry could not be constructed")
    return _CalculatedPath(
        nodes=path,
        edges=selected_edges,
        geometry={"type": "LineString", "coordinates": route_coords},
        distance_m=distance,
        effective_eta=effective_eta,
        base_eta=base_eta,
    )


def _snap_route_endpoints(
    graph: nx.Graph,
    origin: Coordinate,
    destination: Coordinate,
    max_snap_distance_m: float | None,
) -> tuple[Any, Any, float, float]:
    threshold = (
        max_snap_distance_m
        if max_snap_distance_m is not None
        else settings.MAX_ROUTE_SNAP_DISTANCE_M
    )
    origin_node, origin_distance = snap_coordinate_to_graph(graph, origin, threshold)
    destination_node, destination_distance = snap_coordinate_to_graph(
        graph, destination, threshold
    )
    return origin_node, destination_node, origin_distance, destination_distance


def colocated_path(graph: nx.Graph, node: Any) -> _CalculatedPath:
    """Return the zero-travel path for a responder already at the destination.

    Snapping origin and destination to the same routable node means the
    responder is effectively on location. That is a valid, and in fact ideal,
    dispatch outcome, so it yields a real zero-distance, zero-ETA route rather
    than an error that would drop the closest responder from planning.

    The geometry repeats the node coordinate so it stays a structurally valid
    GeoJSON LineString for map and corridor consumers. No travel is fabricated.
    """
    longitude, latitude = _get_node_coords(graph, node)
    point = [longitude, latitude]
    return _CalculatedPath(
        nodes=[node],
        edges=[],
        geometry={"type": "LineString", "coordinates": [list(point), list(point)]},
        distance_m=0.0,
        effective_eta=0.0,
        base_eta=0.0,
    )


def compute_route_on_graph(
    graph: nx.Graph,
    origin: Coordinate,
    destination: Coordinate,
    max_snap_distance_m: float | None = None,
) -> RouteResult:
    """Compute the fastest route using only immutable OSM base travel times."""
    origin_node, destination_node, origin_distance, destination_distance = (
        _snap_route_endpoints(graph, origin, destination, max_snap_distance_m)
    )
    route = (
        colocated_path(graph, origin_node)
        if origin_node == destination_node
        else _calculate_path(graph, origin_node, destination_node)
    )
    return RouteResult(
        nodes=route.nodes,
        geometry=route.geometry,
        distance_m=route.distance_m,
        eta_seconds=route.base_eta,
        origin_snap_distance_m=origin_distance,
        destination_snap_distance_m=destination_distance,
        routing_source=ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME,
    )


def _usable_overlay(
    graph: nx.Graph, snapshot: TrafficSnapshot | None
) -> tuple[TrafficOverlay | None, str | None]:
    if snapshot is None:
        return None, "TOMTOM_SNAPSHOT_UNAVAILABLE"
    if snapshot.graph_fingerprint != graph_fingerprint(graph):
        return None, "TOMTOM_GRAPH_FINGERPRINT_MISMATCH"
    if snapshot.freshness_status is FreshnessStatus.STALE:
        return None, "TOMTOM_SNAPSHOT_STALE"
    if snapshot.freshness_status not in (FreshnessStatus.LIVE, FreshnessStatus.FRESH):
        return None, snapshot.failure_reason or "TOMTOM_SNAPSHOT_NOT_FRESH"
    if snapshot.overlay is None or not snapshot.overlay.entries:
        return None, snapshot.failure_reason or "TOMTOM_NO_MATCHED_TRAFFIC"
    if snapshot.overlay.graph_fingerprint != snapshot.graph_fingerprint:
        return None, "TOMTOM_OVERLAY_GRAPH_FINGERPRINT_MISMATCH"
    return snapshot.overlay, None


def compute_single_source_travel_times(
    graph: nx.Graph,
    origin: Coordinate,
    snapshot: TrafficSnapshot | None,
    max_snap_distance_m: float | None = None,
) -> SingleSourceTravelTimes:
    """Run base and, when valid, overlay-aware Dijkstra from one origin.

    The graph is read-only. Callers receive both trees so they can keep base
    fallback facts visible instead of inventing traffic values.
    """
    threshold = (
        max_snap_distance_m
        if max_snap_distance_m is not None
        else settings.MAX_ROUTE_SNAP_DISTANCE_M
    )
    origin_node, origin_snap_distance = snap_coordinate_to_graph(
        graph, origin, threshold
    )
    base_travel_times, base_paths = nx.single_source_dijkstra(
        graph,
        source=origin_node,
        weight=_path_weight(None),
    )
    overlay, fallback_reason = _usable_overlay(graph, snapshot)
    if overlay is None:
        effective_travel_times = dict(base_travel_times)
        effective_paths = {node: list(path) for node, path in base_paths.items()}
    else:
        effective_travel_times, effective_paths = nx.single_source_dijkstra(
            graph,
            source=origin_node,
            weight=_path_weight(overlay),
        )
    return SingleSourceTravelTimes(
        origin_node=origin_node,
        origin_snap_distance_m=origin_snap_distance,
        base_travel_times={node: float(value) for node, value in base_travel_times.items()},
        base_paths={node: list(path) for node, path in base_paths.items()},
        effective_travel_times={
            node: float(value) for node, value in effective_travel_times.items()
        },
        effective_paths={node: list(path) for node, path in effective_paths.items()},
        traffic_snapshot_id=snapshot.snapshot_id if snapshot else None,
        traffic_snapshot_version=snapshot.version if snapshot else None,
        traffic_freshness_status=snapshot.freshness_status if snapshot else None,
        traffic_overlay_available=overlay is not None,
        traffic_fallback_reason=fallback_reason,
    )


def _edge_disjoint_alternative(
    graph: nx.Graph,
    route: _CalculatedPath,
    origin_node: Any,
    destination_node: Any,
    overlay: TrafficOverlay | None,
) -> list[RouteAlternative]:
    candidate_graph = graph.copy()
    for edge in route.edges:
        if candidate_graph.is_multigraph():
            if candidate_graph.has_edge(edge.u, edge.v, edge.actual_key):
                candidate_graph.remove_edge(edge.u, edge.v, edge.actual_key)
        elif candidate_graph.has_edge(edge.u, edge.v):
            candidate_graph.remove_edge(edge.u, edge.v)
    try:
        alternative = _calculate_path(
            candidate_graph, origin_node, destination_node, overlay
        )
    except RouteNotFoundError:
        return []
    return [
        RouteAlternative(
            nodes=alternative.nodes,
            edge_keys=[edge.public_key for edge in alternative.edges],
            geometry=alternative.geometry,
            distance_m=alternative.distance_m,
            effective_eta=alternative.effective_eta,
        )
    ]


def compute_traffic_aware_route(
    graph: nx.Graph,
    origin: Coordinate,
    destination: Coordinate,
    snapshot: TrafficSnapshot | None,
    max_snap_distance_m: float | None = None,
    include_alternatives: bool = True,
) -> TrafficAwareRouteResult:
    """Compare immutable OSM routing with one captured, validated traffic overlay."""
    origin_node, destination_node, origin_distance, destination_distance = (
        _snap_route_endpoints(graph, origin, destination, max_snap_distance_m)
    )
    if origin_node == destination_node:
        # Already on location: no edge can be traversed, so no overlay or
        # closure can change the outcome.
        base_route = colocated_path(graph, origin_node)
        overlay, fallback_reason = _usable_overlay(graph, snapshot)
        selected_route = base_route
        colocated = True
    else:
        colocated = False
        base_route = _calculate_path(graph, origin_node, destination_node)
        overlay, fallback_reason = _usable_overlay(graph, snapshot)
    if colocated or overlay is None:
        selected_route = base_route
    else:
        try:
            selected_route = _calculate_path(
                graph, origin_node, destination_node, overlay
            )
        except RouteNotFoundError as exc:
            if any(entry.road_closure for entry in overlay.entries):
                raise RouteNotFoundError(
                    "No traffic-aware path remains after validated road closures"
                ) from exc
            raise

    base_keys = {edge.public_key for edge in base_route.edges}
    selected_keys = {edge.public_key for edge in selected_route.edges}
    path_changed = base_keys != selected_keys
    weight_entries = (
        [
            entry
            for entry in overlay.entries
            if not entry.road_closure
            and entry.traffic_factor is not None
            and not math.isclose(entry.traffic_factor, 1.0)
        ]
        if overlay
        else []
    )
    closure_entries = (
        [entry for entry in overlay.entries if entry.road_closure] if overlay else []
    )
    relevant_keys = base_keys | selected_keys
    weight_affected = bool(
        any(entry.edge_key in relevant_keys for entry in weight_entries)
        and (
            path_changed
            or not math.isclose(selected_route.effective_eta, selected_route.base_eta)
        )
    )
    closure_affected = bool(
        path_changed and any(entry.edge_key in base_keys for entry in closure_entries)
    )
    adjusted = weight_affected or closure_affected

    traversed_entries = {
        entry.edge_key: entry
        for entry in overlay.entries
        if overlay is not None and not entry.road_closure
    } if overlay else {}
    covered_edges = [
        edge for edge in selected_route.edges if edge.public_key in traversed_entries
    ]
    covered_length = sum(edge.length_m for edge in covered_edges)
    # A zero-length co-located route traverses nothing, so no traffic can apply.
    coverage = (
        covered_length / selected_route.distance_m
        if selected_route.distance_m > 0
        else 0.0
    )
    active_overlay = overlay if fallback_reason is None else None
    alternatives = (
        _edge_disjoint_alternative(
            graph, selected_route, origin_node, destination_node, active_overlay
        )
        if include_alternatives
        else []
    )

    return TrafficAwareRouteResult(
        base_nodes=base_route.nodes,
        nodes=selected_route.nodes,
        edge_keys=[edge.public_key for edge in selected_route.edges],
        geometry=selected_route.geometry,
        distance_m=selected_route.distance_m,
        eta_seconds=selected_route.effective_eta,
        base_eta=base_route.base_eta,
        effective_eta=selected_route.effective_eta,
        traffic_selected_path_base_eta=selected_route.base_eta,
        origin_snap_distance_m=origin_distance,
        destination_snap_distance_m=destination_distance,
        routing_source=(
            ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED
            if adjusted
            else ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
        ),
        traffic_snapshot_id=snapshot.snapshot_id if snapshot else None,
        traffic_snapshot_version=snapshot.version if snapshot else None,
        traffic_freshness_status=snapshot.freshness_status if snapshot else None,
        matched_traversed_edge_count=len(covered_edges),
        total_traversed_edge_count=len(selected_route.edges),
        traffic_coverage_ratio=coverage,
        traffic_weight_affected_path_selection=weight_affected,
        traffic_closure_affected_path_selection=closure_affected,
        traffic_fallback_reason=fallback_reason,
        alternatives=alternatives,
    )
