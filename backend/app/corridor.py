from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import transform

from app.config import settings

__all__ = ["CorridorSignal", "extract_corridor_signals"]


_TO_METERS = Transformer.from_crs("EPSG:4326", "EPSG:32636", always_xy=True).transform
_TO_WGS84 = Transformer.from_crs("EPSG:32636", "EPSG:4326", always_xy=True).transform


@dataclass(frozen=True)
class CorridorSignal:
    signal_id: str
    latitude: float
    longitude: float
    distance_along_route_m: float
    estimated_arrival_seconds: float
    request_time: str
    state: str
    provenance: dict[str, Any]


def _signal_asset_path() -> Path:
    return settings.NASR_CITY_DATA_DIR / "nasr_city_traffic_signals.geojson"


def _load_signal_features() -> list[dict[str, Any]]:
    path = _signal_asset_path()
    if not path.is_file():
        raise FileNotFoundError(f"Traffic signal asset not found: {path.name}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("Traffic signal asset must be a GeoJSON FeatureCollection")
    features: list[dict[str, Any]] = []
    for feature in payload["features"]:
        if not isinstance(feature, dict) or feature.get("geometry", {}).get("type") != "Point":
            continue
        coordinates = feature.get("geometry", {}).get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        try:
            float(coordinates[0])
            float(coordinates[1])
        except (TypeError, ValueError):
            continue
        features.append(feature)
    features.sort(
        key=lambda feature: (
            str(feature.get("id") or ""),
            float(feature["geometry"]["coordinates"][0]),
            float(feature["geometry"]["coordinates"][1]),
        )
    )
    return features


def _signal_identity(feature: dict[str, Any]) -> str:
    source_id = feature.get("id")
    if source_id is not None and str(source_id).strip():
        return str(source_id)
    lon, lat = feature["geometry"]["coordinates"][:2]
    return f"coordinate:{float(lon):.7f},{float(lat):.7f}"


def extract_corridor_signals(
    route_geometry: dict[str, Any],
    route_eta_seconds: float,
    *,
    now_iso: str,
) -> list[CorridorSignal]:
    """Extract real OSM signal points within the approved route tolerance."""
    if route_geometry.get("type") != "LineString":
        raise ValueError("Approved route geometry must be a LineString")
    coordinates = route_geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("Approved route geometry must contain at least two coordinates")
    line = LineString(coordinates)
    metric_line = transform(_TO_METERS, line)
    route_length = metric_line.length
    if route_length <= 0:
        raise ValueError("Approved route geometry must have positive length")

    seen: set[str] = set()
    base_time = datetime.fromisoformat(now_iso)
    selected: list[CorridorSignal] = []
    for feature in _load_signal_features():
        signal_id = _signal_identity(feature)
        if signal_id in seen:
            continue
        lon, lat = feature["geometry"]["coordinates"][:2]
        metric_point = transform(_TO_METERS, Point(float(lon), float(lat)))
        if metric_line.distance(metric_point) > settings.CORRIDOR_SIGNAL_BUFFER_METERS:
            continue
        along_route_m = metric_line.project(metric_point)
        arrival_seconds = float(route_eta_seconds) * along_route_m / route_length
        selected.append(
            CorridorSignal(
                signal_id=signal_id,
                latitude=float(lat),
                longitude=float(lon),
                distance_along_route_m=round(along_route_m, 3),
                estimated_arrival_seconds=round(arrival_seconds, 3),
                request_time=(
                    base_time
                    + timedelta(
                        seconds=arrival_seconds - settings.SIGNAL_PRIORITY_SAFETY_LEAD_TIME_SECONDS
                    )
                ).isoformat(),
                state="NORMAL",
                provenance={
                    "source": "OSM_TRAFFIC_SIGNAL_ASSET",
                    "data_reality": "REAL_PUBLIC",
                    "freshness_status": "STATIC",
                    "source_reference": "nasr_city_traffic_signals.geojson",
                    "matching_tolerance_m": settings.CORRIDOR_SIGNAL_BUFFER_METERS,
                },
            )
        )
        seen.add(signal_id)
    selected.sort(key=lambda signal: (signal.distance_along_route_m, signal.signal_id))
    return selected


def corridor_provenance() -> dict[str, Any]:
    return {
        "source": "approved_response_route + OSM traffic signal asset",
        "data_reality": "REAL_DERIVED",
        "freshness_status": "STATIC",
        "source_reference": "nasr_city_traffic_signals.geojson",
        "signal_data_reality": "REAL_PUBLIC",
        "signal_buffer_m": settings.CORRIDOR_SIGNAL_BUFFER_METERS,
        "priority_reality": "SIMULATED",
    }


def serialize_route_geometry(route_geometry: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy without changing the approved geometry."""
    return mapping(shape(route_geometry))
