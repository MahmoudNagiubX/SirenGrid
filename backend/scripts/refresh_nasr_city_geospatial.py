from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import uuid4

import networkx as nx
from shapely import wkt
from shapely.geometry import LineString, mapping, shape
from shapely.ops import unary_union


GRAPH_FILENAME = "nasr_city_graph.graphml"
FACILITIES_FILENAME = "nasr_city_emergency_facilities.geojson"
SIGNALS_FILENAME = "nasr_city_traffic_signals.geojson"
SAMPLES_FILENAME = "nasr_city_traffic_sample_points.geojson"
PROVENANCE_FILENAME = "provenance.json"

REFRESHED_FILENAMES = (
    GRAPH_FILENAME,
    FACILITIES_FILENAME,
    SIGNALS_FILENAME,
    SAMPLES_FILENAME,
)

CORRIDOR_ROADS = (
    ("Rabaa", ("رابعة", "rabaa", "rabia")),
    ("Tayaran", ("الطيران", "tayaran")),
    ("Abbas El Akkad", ("عباس العقاد", "abbas el akk", "abbas al akk")),
    ("Makram Ebeid", ("مكرم عبيد", "makram ebeid", "makram obeid")),
    ("El Nasr Road", ("طريق النصر", "el nasr road", "al nasr road")),
)

OVERPASS_REFERENCE = "https://overpass-api.de/api/interpreter"
GEOFABRIK_REFERENCE = "https://download.geofabrik.de/africa/egypt.html"


def _number(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"expected a numeric value, got {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"expected a finite numeric value, got {value!r}")
    return parsed


def validate_graph(graph: nx.Graph) -> None:
    """Validate the minimum immutable OSM base-graph contract."""
    if not graph.is_directed():
        raise ValueError("routing graph must be directed")
    if not graph.is_multigraph():
        raise ValueError("routing graph must preserve MultiDiGraph edge keys")
    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise ValueError("routing graph must be non-empty")
    for u, v, data in graph.edges(data=True):
        if "oneway" not in data:
            raise ValueError(f"edge {u!r}->{v!r} is missing source oneway state")
        travel_time = _number(data.get("travel_time"))
        if travel_time <= 0:
            raise ValueError(f"edge {u!r}->{v!r} has invalid travel_time")
        length = _number(data.get("length"))
        if length <= 0:
            raise ValueError(f"edge {u!r}->{v!r} has invalid length")


def validate_feature_collection(payload: Any, name: str) -> None:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError(f"{name} must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError(f"{name} must contain a non-empty features list")
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"{name} contains an invalid GeoJSON feature")
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or not geometry.get("type"):
            raise ValueError(f"{name} contains a feature without geometry")
        if not isinstance(feature.get("properties"), dict):
            raise ValueError(f"{name} contains a feature without properties")


def _load_boundary(boundary_path: Path) -> Any:
    with boundary_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    validate_feature_collection(payload, "Nasr City boundary")
    polygons = [shape(feature["geometry"]) for feature in payload["features"]]
    polygon = unary_union(polygons)
    if polygon.is_empty or polygon.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Nasr City boundary must contain polygon geometry")
    return polygon


def _acquire_osm_graph(polygon: Any) -> nx.MultiDiGraph:
    import osmnx as ox

    graph = ox.graph.graph_from_polygon(
        polygon,
        network_type="drive",
        simplify=True,
        retain_all=False,
    )
    graph = ox.routing.add_edge_speeds(graph)
    return ox.routing.add_edge_travel_times(graph)


def _acquire_osm_features(polygon: Any, tags: dict[str, Any]) -> Any:
    import osmnx as ox

    return ox.features.features_from_polygon(polygon, tags)


def _to_feature_collection(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        payload = value
    elif hasattr(value, "to_json"):
        payload = json.loads(value.to_json())
    else:
        raise ValueError("Overpass result cannot be converted to GeoJSON")
    if isinstance(payload, dict):
        payload.pop("crs", None)
    return payload


def _normalize_graph(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    for _u, _v, _key, data in graph.edges(keys=True, data=True):
        if "oneway" not in data:
            raise ValueError("OSM acquisition returned an edge without oneway state")
        length = _number(data.get("length"))
        travel_time = _number(data.get("travel_time"))
        if length <= 0 or travel_time <= 0:
            raise ValueError("OSM acquisition returned non-positive edge metrics")
        data["length_m"] = length
        data["base_travel_time_s"] = travel_time
        data["highway_type"] = str(data.get("highway", "unknown"))
        data["access_restriction_state"] = str(
            data.get("access", "OSMNX_DRIVE_NETWORK_FILTER")
        )
        data["turn_restriction_support_status"] = "NOT_PROCESSED_OR_VALIDATED"
    graph.graph["data_reality"] = "REAL_DERIVED"
    graph.graph["freshness_status"] = "STATIC"
    graph.graph["turn_restriction_support"] = "NOT_PROCESSED_OR_VALIDATED"
    graph.graph["acquisition_mode"] = "DIRECT_OSMNX_OVERPASS_OWNER_APPROVED"
    return graph


def _edge_names(raw_name: Any) -> tuple[str, ...]:
    if isinstance(raw_name, (list, tuple)):
        return tuple(str(item) for item in raw_name)
    if raw_name is None:
        return ()
    text = str(raw_name)
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text.replace("'", '"'))
            if isinstance(parsed, list):
                return tuple(str(item) for item in parsed)
        except json.JSONDecodeError:
            pass
    return (text,)


def _node_point(graph: nx.Graph, node: Any) -> tuple[float, float]:
    data = graph.nodes[node]
    return _number(data.get("x")), _number(data.get("y"))


def _edge_line(graph: nx.Graph, u: Any, v: Any, data: dict[str, Any]) -> LineString:
    geometry = data.get("geometry")
    if isinstance(geometry, LineString):
        return geometry
    if isinstance(geometry, str):
        parsed = wkt.loads(geometry)
        if isinstance(parsed, LineString):
            return parsed
    return LineString((_node_point(graph, u), _node_point(graph, v)))


def build_corridor_sample_points(graph: nx.MultiDiGraph) -> dict[str, Any]:
    """Derive the five MVP sample coordinates from named OSM graph edges."""
    features: list[dict[str, Any]] = []
    edges = sorted(
        graph.edges(keys=True, data=True),
        key=lambda edge: (str(edge[0]), str(edge[1]), str(edge[2])),
    )
    for index, (corridor_name, aliases) in enumerate(CORRIDOR_ROADS, start=1):
        selected = None
        for u, v, key, data in edges:
            names = _edge_names(data.get("name"))
            if any(
                alias.casefold() in name.casefold()
                for alias in aliases
                for name in names
            ):
                selected = (u, v, key, data, names[0])
                break
        if selected is None:
            raise ValueError(f"No named OSM graph edge found for {corridor_name}")
        u, v, key, data, osm_name = selected
        midpoint = _edge_line(graph, u, v, data).interpolate(0.5, normalized=True)
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(midpoint),
                "properties": {
                    "sample_id": f"nasr-corridor-{index}",
                    "corridor_name": corridor_name,
                    "osm_name": osm_name,
                    "source_edge": [str(u), str(v), str(key)],
                    "coordinate_derivation": "MIDPOINT_OF_NAMED_OSM_GRAPH_EDGE",
                    "data_reality": "REAL_DERIVED",
                    "freshness_status": "STATIC",
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _normalize_facilities(payload: dict[str, Any]) -> dict[str, Any]:
    for feature in payload["features"]:
        properties = feature["properties"]
        facility_type = properties.get("amenity") or properties.get("emergency")
        properties["facility_type"] = str(facility_type or "emergency_facility")
        properties["data_reality"] = "REAL_PUBLIC"
        properties["freshness_status"] = "STATIC"
    return payload


def _normalize_signals(payload: dict[str, Any]) -> dict[str, Any]:
    for feature in payload["features"]:
        properties = feature["properties"]
        properties["infrastructure_type"] = "traffic_signal"
        properties["operational_state"] = "NOT_AVAILABLE_FROM_OSM"
        properties["data_reality"] = "REAL_PUBLIC"
        properties["freshness_status"] = "STATIC"
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    )


def _save_graph(graph: nx.MultiDiGraph, path: Path) -> None:
    import osmnx as ox

    ox.io.save_graphml(graph, filepath=path)


def _record_count(path: Path) -> int:
    if path.suffix == ".graphml":
        return nx.read_graphml(path, force_multigraph=True).number_of_edges()
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return len(payload.get("features", []))


def _artifact_source(filename: str) -> tuple[str, str, str]:
    if filename == GRAPH_FILENAME:
        return (
            "OpenStreetMap via OSMnx/Overpass",
            f"{OVERPASS_REFERENCE}?query=graph_from_polygon&network_type=drive",
            "REAL_DERIVED",
        )
    if filename == SAMPLES_FILENAME:
        return (
            "SirenGrid derivation from refreshed named OSM graph edges",
            GRAPH_FILENAME,
            "REAL_DERIVED",
        )
    query = "traffic_signals" if filename == SIGNALS_FILENAME else "emergency_facilities"
    return (
        "OpenStreetMap via OSMnx/Overpass",
        f"{OVERPASS_REFERENCE}?query={query}",
        "REAL_DERIVED",
    )


def build_provenance(
    artifacts: dict[str, Path], *, retrieved_at: datetime
) -> dict[str, Any]:
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    artifact_records: dict[str, Any] = {}
    for filename, path in sorted(artifacts.items()):
        source, source_reference, reality = _artifact_source(filename)
        artifact_records[filename] = {
            "source": source,
            "source_reference": source_reference,
            "retrieved_at": retrieved_at.isoformat(),
            "data_reality": reality,
            "freshness_status": "STATIC",
            "acquisition_freshness_status": "FRESH",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "record_count": _record_count(path),
        }
    return {
        "phase": "PHASE_02_GEOSPATIAL_TRAFFIC_RUNTIME",
        "acquisition_mode": "DIRECT_OSMNX_OVERPASS_OWNER_APPROVED",
        "approved_fallback": "Geofabrik Egypt OSM extract",
        "approved_fallback_reference": GEOFABRIK_REFERENCE,
        "fallback_used": False,
        "failed_refresh_policy": "PRESERVE_LAST_VALIDATED_REAL_GRAPH",
        "turn_restriction_support": "NOT_PROCESSED_OR_VALIDATED",
        "traffic_signal_operational_state": "NOT_AVAILABLE_FROM_OSM",
        "retrieved_at": retrieved_at.isoformat(),
        "retained_artifacts": {
            "nasr_city_boundary.geojson": {
                "source": "MahmoudNagiubX/Egypt-Smart-City-Digital-Twin",
                "source_repo": "MahmoudNagiubX/Egypt-Smart-City-Digital-Twin",
                "source_commit": "93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d",
                "source_reference": "nasr_city_boundary.geojson",
                "data_reality": "REAL_DERIVED",
                "freshness_status": "STATIC",
            },
            "nasr_city_grid_500m.geojson": {
                "source": "MahmoudNagiubX/Egypt-Smart-City-Digital-Twin",
                "source_repo": "MahmoudNagiubX/Egypt-Smart-City-Digital-Twin",
                "source_commit": "93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d",
                "source_reference": "nasr_city_grid_500m.geojson",
                "data_reality": "REAL_DERIVED",
                "freshness_status": "STATIC",
            },
        },
        "artifacts": artifact_records,
    }


def build_refresh_artifacts(
    boundary_path: Path,
    staging_dir: Path,
    *,
    retrieved_at: datetime | None = None,
) -> dict[str, Path]:
    """Acquire and fully validate artifacts in staging without publishing them."""
    if staging_dir.exists() and any(staging_dir.iterdir()):
        raise ValueError("staging directory must be empty")
    staging_dir.mkdir(parents=True, exist_ok=True)
    captured_at = retrieved_at or datetime.now(timezone.utc)
    polygon = _load_boundary(boundary_path)

    graph = _normalize_graph(_acquire_osm_graph(polygon))
    validate_graph(graph)
    facilities = _normalize_facilities(
        _to_feature_collection(
            _acquire_osm_features(
                polygon,
                {
                    "amenity": ["hospital", "clinic", "doctors", "fire_station"],
                    "emergency": "ambulance_station",
                },
            )
        )
    )
    signals = _normalize_signals(
        _to_feature_collection(
            _acquire_osm_features(polygon, {"highway": "traffic_signals"})
        )
    )
    samples = build_corridor_sample_points(graph)
    validate_feature_collection(facilities, "emergency facilities")
    validate_feature_collection(signals, "traffic signals")
    validate_feature_collection(samples, "traffic corridor samples")

    artifacts = {
        GRAPH_FILENAME: staging_dir / GRAPH_FILENAME,
        FACILITIES_FILENAME: staging_dir / FACILITIES_FILENAME,
        SIGNALS_FILENAME: staging_dir / SIGNALS_FILENAME,
        SAMPLES_FILENAME: staging_dir / SAMPLES_FILENAME,
    }
    _save_graph(graph, artifacts[GRAPH_FILENAME])
    _write_json(artifacts[FACILITIES_FILENAME], facilities)
    _write_json(artifacts[SIGNALS_FILENAME], signals)
    _write_json(artifacts[SAMPLES_FILENAME], samples)
    provenance = build_provenance(artifacts, retrieved_at=captured_at)
    provenance_path = staging_dir / PROVENANCE_FILENAME
    _write_json(provenance_path, provenance)
    return {**artifacts, PROVENANCE_FILENAME: provenance_path}


def _validate_staged_directory(directory: Path) -> None:
    graph = nx.read_graphml(directory / GRAPH_FILENAME, force_multigraph=True)
    validate_graph(graph)
    feature_payloads: dict[str, dict[str, Any]] = {}
    for filename in (FACILITIES_FILENAME, SIGNALS_FILENAME, SAMPLES_FILENAME):
        with (directory / filename).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        validate_feature_collection(payload, filename)
        feature_payloads[filename] = payload
    with (directory / PROVENANCE_FILENAME).open("r", encoding="utf-8") as handle:
        provenance = json.load(handle)
    if provenance.get("turn_restriction_support") != "NOT_PROCESSED_OR_VALIDATED":
        raise ValueError("staged provenance has an invalid turn-restriction claim")
    artifact_records = provenance.get("artifacts")
    if not isinstance(artifact_records, dict):
        raise ValueError("staged provenance has no artifact manifest")
    for filename in REFRESHED_FILENAMES:
        metadata = artifact_records.get(filename)
        if not isinstance(metadata, dict):
            raise ValueError(f"staged provenance is missing {filename}")
        path = directory / filename
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if metadata.get("sha256") != actual_hash:
            raise ValueError(f"staged artifact hash mismatch: {filename}")
        actual_count = (
            graph.number_of_edges()
            if filename == GRAPH_FILENAME
            else len(feature_payloads[filename]["features"])
        )
        if metadata.get("record_count") != actual_count:
            raise ValueError(f"staged artifact record-count mismatch: {filename}")

    for feature in feature_payloads[SAMPLES_FILENAME]["features"]:
        properties = feature["properties"]
        source_edge = properties.get("source_edge")
        if not isinstance(source_edge, list) or len(source_edge) != 3:
            raise ValueError("traffic sample is missing a source OSM edge")
        u, v, expected_key = source_edge
        edges = graph.get_edge_data(u, v)
        if not edges:
            raise ValueError("traffic sample source OSM edge is absent")
        matching_data = next(
            (data for key, data in edges.items() if str(key) == str(expected_key)),
            None,
        )
        if matching_data is None or properties.get("osm_name") not in _edge_names(
            matching_data.get("name")
        ):
            raise ValueError("traffic sample is not bound to its named OSM edge")


def publish_validated_artifacts(staging_dir: Path, target_dir: Path) -> None:
    """Publish by directory swap, rolling back the exact previous target on failure."""
    staging = staging_dir.resolve()
    target = target_dir.resolve()
    if target.name != "nasr_city" or staging.parent != target.parent:
        raise ValueError("refresh staging and target must be sibling Nasr City directories")
    if not target.is_dir():
        raise FileNotFoundError("validated Nasr City target directory does not exist")
    _validate_staged_directory(staging)

    candidate = target.parent / f".nasr-city-publish-{uuid4()}"
    backup = target.parent / f".nasr-city-backup-{uuid4()}"
    shutil.copytree(target, candidate)
    try:
        for filename in (*REFRESHED_FILENAMES, PROVENANCE_FILENAME):
            shutil.copy2(staging / filename, candidate / filename)
        _validate_staged_directory(candidate)
        os.replace(target, backup)
        try:
            os.replace(candidate, target)
        except BaseException:
            os.replace(backup, target)
            raise
        shutil.rmtree(backup)
    finally:
        if candidate.exists():
            shutil.rmtree(candidate)
        if backup.exists() and target.exists():
            shutil.rmtree(backup)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    default_target = repo_root / "data" / "processed" / "nasr_city"
    parser = argparse.ArgumentParser(description="Refresh validated Nasr City OSM assets")
    parser.add_argument(
        "--boundary",
        type=Path,
        default=default_target / "nasr_city_boundary.geojson",
    )
    parser.add_argument("--target", type=Path, default=default_target)
    args = parser.parse_args()

    target = args.target.resolve()
    target_parent = target.parent
    staging = Path(
        tempfile.mkdtemp(prefix=".nasr-city-refresh-", dir=target_parent)
    ).resolve()
    try:
        build_refresh_artifacts(args.boundary.resolve(), staging)
        publish_validated_artifacts(staging, target)
    finally:
        if staging.exists() and staging.parent == target_parent:
            shutil.rmtree(staging)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
