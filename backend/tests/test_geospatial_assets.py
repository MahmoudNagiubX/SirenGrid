import json
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
    "provenance.json",
]

REQUIRED_GEOJSON_LAYERS = [
    "nasr_city_boundary.geojson",
    "nasr_city_grid_500m.geojson",
    "nasr_city_emergency_facilities.geojson",
]

EXPECTED_PROVENANCE = {
    "source_repo": "MahmoudNagiubX/Egypt-Smart-City-Digital-Twin",
    "source_commit": "93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d",
    "data_reality": "REAL_DERIVED",
    "freshness_status": "STATIC",
    "purpose": "Phase 01 Nasr City geospatial bootstrap",
    "refresh_policy": "bootstrap only; refresh current OSM/Geofabrik/Overpass in Phase 02",
}


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


def test_provenance_metadata_matches():
    provenance_path = NASR_CITY_ASSETS_DIR / "provenance.json"
    assert provenance_path.is_file(), "provenance.json does not exist"

    with open(provenance_path, "r", encoding="utf-8") as f:
        provenance = json.load(f)

    assert isinstance(provenance, dict), "provenance.json root must be a JSON object"
    for key, expected_value in EXPECTED_PROVENANCE.items():
        assert key in provenance, f"Missing key '{key}' in provenance.json"
        assert provenance[key] == expected_value, (
            f"Provenance mismatch for '{key}': expected '{expected_value}', got '{provenance[key]}'"
        )


def test_graphml_parsable_by_networkx():
    graph_path = NASR_CITY_ASSETS_DIR / "nasr_city_graph.graphml"
    assert graph_path.is_file(), "nasr_city_graph.graphml does not exist"

    graph = nx.read_graphml(graph_path)
    assert isinstance(graph, (nx.Graph, nx.MultiGraph, nx.DiGraph, nx.MultiDiGraph))
    assert graph.number_of_nodes() > 0, "Parsed graph has 0 nodes"
    assert graph.number_of_edges() > 0, "Parsed graph has 0 edges"
