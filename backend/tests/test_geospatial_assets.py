import json
import hashlib
from pathlib import Path

import networkx as nx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NASR_CITY_ASSETS_DIR = REPO_ROOT / "data" / "processed" / "nasr_city"

REQUIRED_FILES = [
    "nasr_city_boundary.geojson",
    "nasr_city_grid_500m.geojson",
    "nasr_city_graph.graphml",
    "nasr_city_emergency_facilities.geojson",
    "nasr_city_traffic_signals.geojson",
    "nasr_city_traffic_sample_points.geojson",
    "nasr_city_zone_population_worldpop_2025.geojson",
    "provenance.json",
    "worldpop_provenance.json",
]

REQUIRED_GEOJSON_LAYERS = [
    "nasr_city_boundary.geojson",
    "nasr_city_grid_500m.geojson",
    "nasr_city_emergency_facilities.geojson",
    "nasr_city_traffic_signals.geojson",
    "nasr_city_traffic_sample_points.geojson",
]


def test_required_geospatial_files_exist_and_non_empty():
    assert NASR_CITY_ASSETS_DIR.exists(), f"Directory does not exist: {NASR_CITY_ASSETS_DIR}"
    assert NASR_CITY_ASSETS_DIR.is_dir(), f"Path is not a directory: {NASR_CITY_ASSETS_DIR}"

    for filename in REQUIRED_FILES:
        filepath = NASR_CITY_ASSETS_DIR / filename
        assert filepath.exists(), f"Required asset file missing: {filename}"
        assert filepath.is_file(), f"Path is not a file: {filename}"
        assert filepath.stat().st_size > 0, f"Asset file is empty: {filename}"


@pytest.mark.parametrize("geojson_filename", REQUIRED_GEOJSON_LAYERS)
def test_geojson_layers_valid_non_empty_feature_collections(geojson_filename: str):
    filepath = NASR_CITY_ASSETS_DIR / geojson_filename
    assert filepath.is_file(), f"GeoJSON file does not exist: {geojson_filename}"

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict), f"GeoJSON root must be an object in {geojson_filename}"
    assert data.get("type") == "FeatureCollection", f"{geojson_filename} is not a FeatureCollection"

    features = data.get("features")
    assert isinstance(features, list), f"{geojson_filename} features must be a list"
    assert len(features) > 0, f"{geojson_filename} features list is empty"


def test_phase_02_provenance_metadata_and_hashes_match():
    provenance_path = NASR_CITY_ASSETS_DIR / "provenance.json"
    assert provenance_path.is_file(), "provenance.json does not exist"

    with open(provenance_path, "r", encoding="utf-8") as f:
        provenance = json.load(f)

    assert isinstance(provenance, dict), "provenance.json root must be a JSON object"
    assert provenance["acquisition_mode"] == "DIRECT_OSMNX_OVERPASS_OWNER_APPROVED"
    assert provenance["approved_fallback"] == "Geofabrik Egypt OSM extract"
    assert provenance["fallback_used"] is False
    assert provenance["failed_refresh_policy"] == "PRESERVE_LAST_VALIDATED_REAL_GRAPH"
    assert provenance["turn_restriction_support"] == "NOT_PROCESSED_OR_VALIDATED"
    assert provenance["traffic_signal_operational_state"] == "NOT_AVAILABLE_FROM_OSM"

    artifacts = provenance["artifacts"]
    assert set(artifacts) == {
        "nasr_city_graph.graphml",
        "nasr_city_emergency_facilities.geojson",
        "nasr_city_traffic_signals.geojson",
        "nasr_city_traffic_sample_points.geojson",
    }
    for filename, metadata in artifacts.items():
        path = NASR_CITY_ASSETS_DIR / filename
        assert metadata["data_reality"] == "REAL_DERIVED"
        assert metadata["freshness_status"] == "STATIC"
        assert metadata["acquisition_freshness_status"] == "FRESH"
        assert metadata["record_count"] > 0
        # Provenance hashes describe the canonical UTF-8/LF bytes emitted by
        # the refresh writers. Git's Windows checkout may materialize tracked
        # text assets with CRLF, so normalize only line endings for comparison.
        canonical_bytes = path.read_bytes().replace(b"\r\n", b"\n")
        assert metadata["sha256"] == hashlib.sha256(canonical_bytes).hexdigest()

    retained = provenance["retained_artifacts"]
    for filename in ("nasr_city_boundary.geojson", "nasr_city_grid_500m.geojson"):
        assert retained[filename]["source_repo"] == (
            "MahmoudNagiubX/Egypt-Smart-City-Digital-Twin"
        )
        assert retained[filename]["source_commit"] == (
            "93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d"
        )


def test_worldpop_artifact_has_dedicated_integrity_manifest() -> None:
    manifest_path = NASR_CITY_ASSETS_DIR / "worldpop_provenance.json"
    artifact_path = NASR_CITY_ASSETS_DIR / "nasr_city_zone_population_worldpop_2025.geojson"
    assert manifest_path.is_file()
    assert artifact_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    record = manifest["artifacts"][artifact_path.name]
    canonical_bytes = artifact_path.read_bytes().replace(b"\r\n", b"\n")

    assert manifest["phase"] == "PHASE_04_COVERAGE_AND_RESPONSE_PLANNING"
    assert manifest["data_reality"] == "REAL_DERIVED"
    assert manifest["underlying_data_reality"] == "REAL_PUBLIC"
    assert record["sha256"] == hashlib.sha256(canonical_bytes).hexdigest()
    assert record["record_count"] == len(artifact["features"])
    assert record["record_count"] == artifact["properties"]["validation"]["zone_count"]
    assert record["total_modeled_population"] == artifact["properties"]["validation"]["total_modeled_population"]
    assert record["source_sha256"] == artifact["properties"]["source_metadata"]["source_sha256"]
    assert record["source_reference"] == artifact["properties"]["source_metadata"]["source_reference"]
    assert record["release"] == artifact["properties"]["source_metadata"]["release"]
    assert record["version"] == artifact["properties"]["source_metadata"]["version"]
    assert record["doi"] == artifact["properties"]["source_metadata"]["doi"]
    assert record["freshness_status"] == "STATIC"


def test_graphml_parsable_by_networkx():
    graph_path = NASR_CITY_ASSETS_DIR / "nasr_city_graph.graphml"
    assert graph_path.is_file(), "nasr_city_graph.graphml does not exist"

    graph = nx.read_graphml(graph_path)
    assert isinstance(graph, (nx.Graph, nx.MultiGraph, nx.DiGraph, nx.MultiDiGraph))
    assert graph.number_of_nodes() > 0, "Parsed graph has 0 nodes"
    assert graph.number_of_edges() > 0, "Parsed graph has 0 edges"
    assert graph.is_directed()
    assert graph.is_multigraph()
    assert graph.graph["turn_restriction_support"] == "NOT_PROCESSED_OR_VALIDATED"
    for _u, _v, data in graph.edges(data=True):
        assert "oneway" in data
        assert float(data["travel_time"]) > 0
        assert float(data["base_travel_time_s"]) > 0


def test_corridor_samples_preserve_utf8_and_bind_to_named_graph_edges():
    graph = nx.read_graphml(NASR_CITY_ASSETS_DIR / "nasr_city_graph.graphml")
    payload = json.loads(
        (NASR_CITY_ASSETS_DIR / "nasr_city_traffic_sample_points.geojson").read_text(
            encoding="utf-8"
        )
    )
    assert [feature["properties"]["corridor_name"] for feature in payload["features"]] == [
        "Rabaa",
        "Tayaran",
        "Abbas El Akkad",
        "Makram Ebeid",
        "El Nasr Road",
    ]
    graph_names = {str(data.get("name", "")) for *_, data in graph.edges(data=True)}
    for feature in payload["features"]:
        name = feature["properties"]["osm_name"]
        assert name in graph_names
        assert "Ø" not in name and "Ù" not in name
