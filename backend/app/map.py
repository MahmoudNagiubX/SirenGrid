from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

from fastapi import APIRouter, HTTPException, status
import networkx as nx

from app.config import settings
from app.routing import (
    RouteNotFoundError,
    RoutingPointOutsideGraphError,
    compute_traffic_aware_route,
    load_routing_graph,
    snap_coordinate_to_graph,
)
from app.traffic.runtime import traffic_runtime
from app.schemas import (
    MapLayerResponse,
    RoutePreviewRequest,
    RoutePreviewResponse,
)

__all__ = ["router"]

router = APIRouter(tags=["map"])

_roads_cache: tuple[Path, int, dict[str, Any]] | None = None


def _load_provenance() -> dict[str, Any]:
    provenance_path = settings.NASR_CITY_DATA_DIR / "provenance.json"
    if not provenance_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Configured provenance asset not found: {provenance_path.name}",
        )
    try:
        with open(provenance_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to read provenance asset: {exc}",
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configured provenance asset must be a JSON object",
        )
    return data


def _layer_provenance(filename: str) -> dict[str, Any]:
    manifest = _load_provenance()
    refreshed = manifest.get("artifacts", {})
    retained = manifest.get("retained_artifacts", {})
    record = refreshed.get(filename) or retained.get(filename)
    if record is None:
        # Phase 01 provenance files predate per-artifact records.
        return manifest
    result = dict(record)
    for key in (
        "acquisition_mode",
        "approved_fallback",
        "fallback_used",
        "turn_restriction_support",
    ):
        if key in manifest:
            result[key] = manifest[key]
    return result


def _load_geojson(filename: str) -> dict[str, Any]:
    asset_path = settings.NASR_CITY_DATA_DIR / filename
    if not asset_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Configured map asset not found: {filename}",
        )
    try:
        with open(asset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to read map asset {filename}: {exc}",
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Configured map asset {filename} must be a JSON object",
        )
    return data


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


def _convert_graph_to_roads_geojson(graph: nx.Graph) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    if graph.is_multigraph():
        raw_edges = list(graph.edges(keys=True, data=True))
        raw_edges.sort(key=lambda e: (str(e[0]), str(e[1]), str(e[2])))
    else:
        raw_edges = [(u, v, 0, d) for u, v, d in graph.edges(data=True)]
        raw_edges.sort(key=lambda e: (str(e[0]), str(e[1]), str(e[2])))

    for u, v, _k, data in raw_edges:
        coords: list[list[float]] = []
        geom_wkt = data.get("geometry")
        if geom_wkt and isinstance(geom_wkt, str):
            coords = _parse_wkt_linestring(geom_wkt)

        if len(coords) < 2:
            try:
                u_lon, u_lat = _get_node_coords(graph, u)
                v_lon, v_lat = _get_node_coords(graph, v)
                coords = [[u_lon, u_lat], [v_lon, v_lat]]
            except (ValueError, KeyError):
                continue

        props: dict[str, Any] = {}
        if "length" in data:
            try:
                props["length"] = float(data["length"])
            except (ValueError, TypeError):
                props["length"] = data["length"]
        elif "length_m" in data:
            try:
                props["length"] = float(data["length_m"])
            except (ValueError, TypeError):
                props["length"] = data["length_m"]

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
                "properties": props,
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


@router.get("/map/boundary", response_model=MapLayerResponse)
def get_map_boundary() -> MapLayerResponse:
    provenance = _layer_provenance("nasr_city_boundary.geojson")
    geojson = _load_geojson("nasr_city_boundary.geojson")
    return MapLayerResponse(
        layer="boundary",
        geojson=geojson,
        provenance=provenance,
    )


@router.get("/map/roads", response_model=MapLayerResponse)
def get_map_roads() -> MapLayerResponse:
    provenance = _layer_provenance("nasr_city_graph.graphml")
    graph_path = settings.NASR_CITY_DATA_DIR / "nasr_city_graph.graphml"
    if not graph_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Configured graph asset not found: {graph_path.name}",
        )

    global _roads_cache
    mtime = graph_path.stat().st_mtime_ns
    if (
        _roads_cache is not None
        and _roads_cache[0] == graph_path
        and _roads_cache[1] == mtime
    ):
        geojson = _roads_cache[2]
    else:
        try:
            graph = load_routing_graph(graph_path)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Configured graph asset not found: {exc}",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to load routing graph: {exc}",
            ) from exc

        geojson = _convert_graph_to_roads_geojson(graph)
        _roads_cache = (graph_path, mtime, geojson)

    return MapLayerResponse(
        layer="roads",
        geojson=geojson,
        provenance=provenance,
    )


@router.get("/map/zones", response_model=MapLayerResponse)
def get_map_zones() -> MapLayerResponse:
    provenance = _layer_provenance("nasr_city_grid_500m.geojson")
    geojson = _load_geojson("nasr_city_grid_500m.geojson")
    return MapLayerResponse(
        layer="zones",
        geojson=geojson,
        provenance=provenance,
    )


@router.get("/map/hospitals", response_model=MapLayerResponse)
def get_map_hospitals() -> MapLayerResponse:
    provenance = _layer_provenance("nasr_city_emergency_facilities.geojson")
    raw = _load_geojson("nasr_city_emergency_facilities.geojson")
    raw_features = raw.get("features", [])
    hospital_features = [
        feat
        for feat in raw_features
        if feat.get("properties", {}).get("facility_type") == "hospital"
    ]
    filtered_geojson = {
        "type": "FeatureCollection",
        "crs": raw.get("crs"),
        "features": hospital_features,
    }
    return MapLayerResponse(
        layer="hospitals",
        geojson=filtered_geojson,
        provenance=provenance,
    )


@router.post("/routes/preview", response_model=RoutePreviewResponse)
def preview_route(request: RoutePreviewRequest) -> RoutePreviewResponse:
    try:
        graph = load_routing_graph()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Routing graph asset unavailable: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to load routing graph: {exc}",
        ) from exc

    # 1. Validate both endpoints are inside the routable area. The routing
    #    engine owns the resulting snapped nodes.
    try:
        snap_coordinate_to_graph(graph, request.origin)
        snap_coordinate_to_graph(graph, request.destination)
    except RoutingPointOutsideGraphError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Coordinate outside routable area: {exc}",
        ) from exc

    # 2. Capture one immutable traffic snapshot and compute independent routes.
    now = datetime.now(timezone.utc)
    try:
        snapshot = traffic_runtime.capture_snapshot(
            graph,
            now=now,
            wall_clock=lambda: datetime.now(timezone.utc),
            monotonic=time.monotonic,
        )
    except Exception:
        # Provider/runtime failures must not remove immutable OSM base routing.
        snapshot = None
    try:
        result = compute_traffic_aware_route(
            graph, request.origin, request.destination, snapshot
        )
    except RoutingPointOutsideGraphError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Coordinate outside routable area: {exc}",
        ) from exc
    except RouteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No valid route found between coordinates: {exc}",
        ) from exc

    return RoutePreviewResponse(
        origin=request.origin,
        destination=request.destination,
        geometry=result.geometry,
        distance_m=result.distance_m,
        eta_seconds=result.eta_seconds,
        origin_snap_distance_m=result.origin_snap_distance_m,
        destination_snap_distance_m=result.destination_snap_distance_m,
        nodes=result.nodes,
        edge_keys=result.edge_keys,
        routing_source=result.routing_source,
        base_eta=result.base_eta,
        effective_eta=result.effective_eta,
        traffic_selected_path_base_eta=result.traffic_selected_path_base_eta,
        traffic_snapshot_id=result.traffic_snapshot_id,
        traffic_snapshot_version=result.traffic_snapshot_version,
        traffic_freshness_status=result.traffic_freshness_status,
        matched_traversed_edge_count=result.matched_traversed_edge_count,
        total_traversed_edge_count=result.total_traversed_edge_count,
        traffic_coverage_ratio=result.traffic_coverage_ratio,
        traffic_weight_affected_path_selection=(
            result.traffic_weight_affected_path_selection
        ),
        traffic_closure_affected_path_selection=(
            result.traffic_closure_affected_path_selection
        ),
        traffic_fallback_reason=result.traffic_fallback_reason,
        alternatives=[alternative.model_dump() for alternative in result.alternatives],
    )
