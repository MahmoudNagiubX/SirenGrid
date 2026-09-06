from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from typing import Any, Iterable

import networkx as nx
from pyproj import Transformer
from shapely import wkt
from shapely.errors import ShapelyError
from shapely.geometry import LineString, Point
from shapely.ops import transform

from app.config import settings
from app.traffic.models import (
    EdgeKey,
    TrafficEdgeMatch,
    TrafficMatchStatus,
    TrafficObservation,
    TrafficOverlay,
    TrafficOverlayEntry,
)


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stable_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]
    if isinstance(value, set):
        return sorted(_stable_value(item) for item in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def graph_fingerprint(graph: nx.Graph) -> str:
    """Hash graph truth deterministically without altering graph state."""
    nodes = [
        (str(node), _stable_value(attrs))
        for node, attrs in graph.nodes(data=True)
    ]
    nodes.sort(key=lambda item: item[0])
    if graph.is_multigraph():
        edges = [
            (str(u), str(v), str(key), _stable_value(attrs))
            for u, v, key, attrs in graph.edges(keys=True, data=True)
        ]
    else:
        edges = [
            (str(u), str(v), "0", _stable_value(attrs))
            for u, v, attrs in graph.edges(data=True)
        ]
    edges.sort(key=lambda item: (item[0], item[1], item[2]))
    payload = {
        "directed": graph.is_directed(),
        "multigraph": graph.is_multigraph(),
        "graph": _stable_value(dict(graph.graph)),
        "nodes": nodes,
        "edges": edges,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _iter_edges(graph: nx.Graph) -> Iterable[tuple[Any, Any, Any, dict[str, Any]]]:
    if graph.is_multigraph():
        yield from graph.edges(keys=True, data=True)
        return
    for u, v, attrs in graph.edges(data=True):
        yield u, v, 0, attrs


def _edge_key(u: Any, v: Any, key: Any) -> EdgeKey:
    return str(u), str(v), str(key)


def select_corridor_edges(
    graph: nx.Graph,
    corridor_names: tuple[str, ...],
) -> frozenset[EdgeKey]:
    """Select only edges whose OSM name belongs to the approved corridor."""
    normalized_names = tuple(
        name.strip().casefold() for name in corridor_names if name.strip()
    )
    selected = {
        _edge_key(u, v, key)
        for u, v, key, attrs in _iter_edges(graph)
        if any(
            name in str(attrs.get("name", "")).casefold()
            for name in normalized_names
        )
    }
    return frozenset(selected)


def _node_coords(graph: nx.Graph, node: Any) -> tuple[float, float]:
    attrs = graph.nodes[node]
    if "x" in attrs and "y" in attrs:
        return float(attrs["x"]), float(attrs["y"])
    if "lon" in attrs and "lat" in attrs:
        return float(attrs["lon"]), float(attrs["lat"])
    raise ValueError(f"Node {node} has no WGS84 coordinates")


def _edge_line(
    graph: nx.Graph,
    u: Any,
    v: Any,
    attrs: dict[str, Any],
) -> LineString:
    raw_geometry = attrs.get("geometry")
    if isinstance(raw_geometry, LineString):
        line = raw_geometry
    elif isinstance(raw_geometry, str):
        parsed = wkt.loads(raw_geometry)
        if isinstance(parsed, LineString):
            line = parsed
        else:
            line = LineString((_node_coords(graph, u), _node_coords(graph, v)))
    else:
        line = LineString((_node_coords(graph, u), _node_coords(graph, v)))

    u_lon, u_lat = _node_coords(graph, u)
    v_lon, v_lat = _node_coords(graph, v)
    start_lon, start_lat = line.coords[0]
    end_lon, end_lat = line.coords[-1]
    forward_distance = (
        (start_lon - u_lon) ** 2
        + (start_lat - u_lat) ** 2
        + (end_lon - v_lon) ** 2
        + (end_lat - v_lat) ** 2
    )
    reverse_distance = (
        (end_lon - u_lon) ** 2
        + (end_lat - u_lat) ** 2
        + (start_lon - v_lon) ** 2
        + (start_lat - v_lat) ** 2
    )
    return LineString(reversed(line.coords)) if reverse_distance < forward_distance else line


def _metric_transformer(observation: TrafficObservation) -> tuple[Transformer, str]:
    average_lon = sum(point[0] for point in observation.coordinates) / len(observation.coordinates)
    average_lat = sum(point[1] for point in observation.coordinates) / len(observation.coordinates)
    zone = max(1, min(60, int((average_lon + 180) // 6) + 1))
    epsg = (32600 if average_lat >= 0 else 32700) + zone
    return Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True), f"EPSG:{epsg}"


def _bearing(line: LineString) -> float:
    start_x, start_y = line.coords[0]
    end_x, end_y = line.coords[-1]
    if start_x == end_x and start_y == end_y:
        raise ValueError("Cannot calculate direction for zero-length line")
    return math.degrees(math.atan2(end_x - start_x, end_y - start_y)) % 360


def _direction_difference(first: float, second: float) -> float:
    difference = abs(first - second) % 360
    return min(difference, 360 - difference)


def _max_vertex_separation(edge: LineString, observation: LineString) -> float:
    return max(Point(coordinate).distance(observation) for coordinate in edge.coords)


def _lookup_allowed_edges(
    graph: nx.Graph,
    allowed_edges: frozenset[EdgeKey],
) -> list[tuple[Any, Any, Any, dict[str, Any]]]:
    return [
        (u, v, key, attrs)
        for u, v, key, attrs in _iter_edges(graph)
        if _edge_key(u, v, key) in allowed_edges
    ]


def _unmatched(
    observation: TrafficObservation,
    reason: str,
    *,
    status: TrafficMatchStatus = TrafficMatchStatus.UNMATCHED,
    metric_crs: str | None = None,
) -> TrafficEdgeMatch:
    return TrafficEdgeMatch(
        observation_id=observation.observation_id,
        status=status,
        reason=reason,
        metric_crs=metric_crs,
    )


def match_observation(
    graph: nx.Graph,
    observation: TrafficObservation,
    allowed_edges: frozenset[EdgeKey],
) -> TrafficEdgeMatch:
    """Apply locked gates, then accept only one structural directed chain."""
    if observation.confidence < settings.TOMTOM_MIN_PROVIDER_CONFIDENCE:
        return _unmatched(observation, "LOW_PROVIDER_CONFIDENCE")

    transformer, metric_crs = _metric_transformer(observation)
    observation_line = transform(
        transformer.transform,
        LineString(observation.coordinates),
    )
    observation_bearing = _bearing(observation_line)

    geometry_candidates: list[tuple[Any, Any, Any, float, float]] = []
    passing_candidates: list[tuple[Any, Any, Any, float, float]] = []
    for u, v, key, attrs in _lookup_allowed_edges(graph, allowed_edges):
        try:
            edge_line = transform(
                transformer.transform,
                _edge_line(graph, u, v, attrs),
            )
            separation = _max_vertex_separation(edge_line, observation_line)
            if separation > settings.TOMTOM_MAX_GEOMETRY_SEPARATION_M:
                continue
            direction = _direction_difference(_bearing(edge_line), observation_bearing)
        except (KeyError, ShapelyError, TypeError, ValueError):
            continue
        geometry_candidates.append((u, v, key, separation, direction))
        if direction <= settings.TOMTOM_MAX_DIRECTION_DIFFERENCE_DEGREES:
            passing_candidates.append((u, v, key, separation, direction))

    if not geometry_candidates:
        return _unmatched(observation, "GEOMETRY_SEPARATION", metric_crs=metric_crs)
    if not passing_candidates:
        return _unmatched(observation, "DIRECTION_DIFFERENCE", metric_crs=metric_crs)

    endpoint_counts = Counter((str(u), str(v)) for u, v, *_ in passing_candidates)
    if any(count > 1 for count in endpoint_counts.values()):
        return _unmatched(
            observation,
            "PARALLEL_CANDIDATES",
            status=TrafficMatchStatus.AMBIGUOUS,
            metric_crs=metric_crs,
        )

    candidates = nx.DiGraph()
    metrics: dict[tuple[str, str], tuple[EdgeKey, float, float]] = {}
    for u, v, key, separation, direction in passing_candidates:
        normalized_u, normalized_v = str(u), str(v)
        candidates.add_edge(normalized_u, normalized_v)
        metrics[(normalized_u, normalized_v)] = (
            _edge_key(u, v, key),
            separation,
            direction,
        )

    if nx.number_weakly_connected_components(candidates) != 1:
        return _unmatched(
            observation,
            "MULTIPLE_CANDIDATE_CHAINS",
            status=TrafficMatchStatus.AMBIGUOUS,
            metric_crs=metric_crs,
        )
    if any(candidates.in_degree(node) > 1 or candidates.out_degree(node) > 1 for node in candidates):
        return _unmatched(
            observation,
            "BRANCHING_CANDIDATES",
            status=TrafficMatchStatus.AMBIGUOUS,
            metric_crs=metric_crs,
        )

    starts = [node for node in candidates if candidates.in_degree(node) == 0]
    if len(starts) != 1:
        return _unmatched(
            observation,
            "NON_CHAIN_CANDIDATES",
            status=TrafficMatchStatus.AMBIGUOUS,
            metric_crs=metric_crs,
        )

    ordered: list[tuple[EdgeKey, float, float]] = []
    current = starts[0]
    while candidates.out_degree(current) == 1:
        following = next(iter(candidates.successors(current)))
        ordered.append(metrics[(current, following)])
        current = following
    if len(ordered) != candidates.number_of_edges():
        return _unmatched(
            observation,
            "NON_CHAIN_CANDIDATES",
            status=TrafficMatchStatus.AMBIGUOUS,
            metric_crs=metric_crs,
        )

    return TrafficEdgeMatch(
        observation_id=observation.observation_id,
        status=TrafficMatchStatus.MATCHED,
        reason="ALL_SAFETY_GATES_PASSED",
        edge_keys=tuple(item[0] for item in ordered),
        max_geometry_separation_m=max(item[1] for item in ordered),
        max_direction_difference_degrees=max(item[2] for item in ordered),
        metric_crs=metric_crs,
    )


def build_overlay(
    graph: nx.Graph,
    *,
    snapshot_id: str,
    observations: tuple[TrafficObservation, ...],
    allowed_edges: frozenset[EdgeKey],
) -> tuple[tuple[TrafficEdgeMatch, ...], TrafficOverlay]:
    """Build a graph-bound overlay; competing observations are all rejected."""
    matches = [match_observation(graph, item, allowed_edges) for item in observations]
    edge_claims: dict[EdgeKey, set[str]] = defaultdict(set)
    for match in matches:
        if match.status is TrafficMatchStatus.MATCHED:
            for edge_key in match.edge_keys:
                edge_claims[edge_key].add(match.observation_id)
    competing_ids = {
        observation_id
        for claimants in edge_claims.values()
        if len(claimants) > 1
        for observation_id in claimants
    }

    resolved_matches: list[TrafficEdgeMatch] = []
    observations_by_id = {item.observation_id: item for item in observations}
    entries: list[TrafficOverlayEntry] = []
    for match in matches:
        if match.observation_id in competing_ids:
            resolved_matches.append(
                TrafficEdgeMatch(
                    observation_id=match.observation_id,
                    status=TrafficMatchStatus.AMBIGUOUS,
                    reason="COMPETING_OBSERVATIONS",
                    metric_crs=match.metric_crs,
                )
            )
            continue
        resolved_matches.append(match)
        if match.status is not TrafficMatchStatus.MATCHED:
            continue
        observation = observations_by_id[match.observation_id]
        factor = None
        if not observation.road_closure:
            factor = (
                observation.current_travel_time_s
                / observation.free_flow_travel_time_s
            )
        entries.extend(
            TrafficOverlayEntry(
                edge_key=edge_key,
                observation_id=match.observation_id,
                traffic_factor=factor,
                road_closure=observation.road_closure,
            )
            for edge_key in match.edge_keys
        )

    entries.sort(key=lambda item: item.edge_key)
    overlay = TrafficOverlay(
        snapshot_id=snapshot_id,
        graph_fingerprint=graph_fingerprint(graph),
        entries=tuple(entries),
    )
    return tuple(resolved_matches), overlay


def validate_overlay_for_graph(graph: nx.Graph, overlay: TrafficOverlay) -> bool:
    return graph_fingerprint(graph) == overlay.graph_fingerprint
