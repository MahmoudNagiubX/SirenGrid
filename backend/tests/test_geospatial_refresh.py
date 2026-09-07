from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import networkx as nx
import pytest

from scripts import refresh_nasr_city_geospatial as refresh


RETRIEVED_AT = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def valid_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    road_names = (
        "شارع رابعة العدوية",
        "شارع الطيران",
        "شارع عباس العقاد",
        "شارع مكرم عبيد",
        "طريق النصر",
    )
    for index in range(6):
        graph.add_node(str(index), x=31.33 + index * 0.001, y=30.06)
    for index, name in enumerate(road_names):
        graph.add_edge(
            str(index),
            str(index + 1),
            key="0",
            name=name,
            oneway=True,
            access="yes",
            length=100.0,
            length_m=100.0,
            travel_time=10.0,
            base_travel_time_s=10.0,
        )
    return graph


def feature_collection(kind: str = "hospital") -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [31.33, 30.06]},
                "properties": {"kind": kind, "name": f"OSM {kind}"},
            }
        ],
    }


def file_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.iterdir()
        if path.is_file()
    }


def test_json_writer_emits_canonical_utf8_lf_bytes(tmp_path: Path) -> None:
    output = tmp_path / "artifact.json"

    refresh._write_json(output, {"type": "FeatureCollection", "message": "مرحبا"})

    assert output.read_bytes() == (
        b'{\n  "message": "\xd9\x85\xd8\xb1\xd8\xad\xd8\xa8\xd8\xa7",\n'
        b'  "type": "FeatureCollection"\n}\n'
    )


def write_valid_bundle(directory: Path, marker: str) -> None:
    directory.mkdir(exist_ok=True)
    graph = valid_graph()
    graph.graph["bundle_marker"] = marker
    nx.write_graphml(graph, directory / refresh.GRAPH_FILENAME)
    for filename in (refresh.FACILITIES_FILENAME, refresh.SIGNALS_FILENAME):
        (directory / filename).write_text(
            json.dumps(feature_collection(marker)), encoding="utf-8"
        )
    (directory / refresh.SAMPLES_FILENAME).write_text(
        json.dumps(refresh.build_corridor_sample_points(graph), ensure_ascii=False),
        encoding="utf-8",
    )
    artifacts = {
        filename: directory / filename for filename in refresh.REFRESHED_FILENAMES
    }
    provenance = refresh.build_provenance(artifacts, retrieved_at=RETRIEVED_AT)
    (directory / refresh.PROVENANCE_FILENAME).write_text(
        json.dumps(provenance), encoding="utf-8"
    )


def test_validate_graph_accepts_directed_real_base_contract() -> None:
    refresh.validate_graph(valid_graph())


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda graph: nx.MultiGraph(graph), "directed"),
        (lambda graph: nx.MultiDiGraph(crs="EPSG:4326"), "empty"),
        (
            lambda graph: graph.copy().edge_subgraph([]).copy(),
            "empty",
        ),
    ],
)
def test_validate_graph_rejects_invalid_topology(mutation, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        refresh.validate_graph(mutation(valid_graph()))


def test_validate_graph_rejects_missing_oneway_and_bad_travel_time() -> None:
    graph = valid_graph()
    del graph["0"]["1"]["0"]["oneway"]
    with pytest.raises(ValueError, match="oneway"):
        refresh.validate_graph(graph)

    graph = valid_graph()
    graph["0"]["1"]["0"]["travel_time"] = 0
    with pytest.raises(ValueError, match="travel_time"):
        refresh.validate_graph(graph)

    with pytest.raises(ValueError, match="MultiDiGraph"):
        refresh.validate_graph(nx.DiGraph(valid_graph()))


def test_validate_feature_collection_rejects_malformed_or_empty() -> None:
    with pytest.raises(ValueError, match="FeatureCollection"):
        refresh.validate_feature_collection({}, "signals")
    with pytest.raises(ValueError, match="non-empty"):
        refresh.validate_feature_collection(
            {"type": "FeatureCollection", "features": []}, "signals"
        )


def test_corridor_samples_are_derived_from_five_named_graph_edges() -> None:
    payload = refresh.build_corridor_sample_points(valid_graph())

    refresh.validate_feature_collection(payload, "corridor samples")
    assert [
        feature["properties"]["corridor_name"] for feature in payload["features"]
    ] == ["Rabaa", "Tayaran", "Abbas El Akkad", "Makram Ebeid", "El Nasr Road"]
    assert all(
        feature["properties"]["coordinate_derivation"]
        == "MIDPOINT_OF_NAMED_OSM_GRAPH_EDGE"
        for feature in payload["features"]
    )
    graph_names = {data["name"] for *_, data in valid_graph().edges(data=True)}
    assert all(
        feature["properties"]["osm_name"] in graph_names
        for feature in payload["features"]
    )


def test_provenance_records_owner_decision_reality_hashes_and_limitations(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "nasr_city_graph.graphml"
    nx.write_graphml(valid_graph(), graph_path)
    provenance = refresh.build_provenance(
        {graph_path.name: graph_path}, retrieved_at=RETRIEVED_AT
    )

    artifact = provenance["artifacts"]["nasr_city_graph.graphml"]
    assert artifact["source"] == "OpenStreetMap via OSMnx/Overpass"
    assert artifact["source_reference"].startswith("https://")
    assert "query=graph_from_polygon" in artifact["source_reference"]
    assert datetime.fromisoformat(artifact["retrieved_at"]).tzinfo is not None
    assert artifact["data_reality"] == "REAL_DERIVED"
    assert artifact["freshness_status"] == "STATIC"
    assert artifact["sha256"] == hashlib.sha256(graph_path.read_bytes()).hexdigest()
    assert provenance["acquisition_mode"] == "DIRECT_OSMNX_OVERPASS_OWNER_APPROVED"
    assert provenance["approved_fallback"] == "Geofabrik Egypt OSM extract"
    assert provenance["turn_restriction_support"] == "NOT_PROCESSED_OR_VALIDATED"
    assert provenance["failed_refresh_policy"] == "PRESERVE_LAST_VALIDATED_REAL_GRAPH"


def test_failed_publication_rolls_back_without_changing_validated_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "nasr_city"
    write_valid_bundle(target, "validated-old")
    before = file_hashes(target)

    staging = tmp_path / "staging"
    write_valid_bundle(staging, "validated-new")

    real_replace = os.replace
    calls = 0

    def fail_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publication failure")
        return real_replace(source, destination)

    monkeypatch.setattr(refresh.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="injected"):
        refresh.publish_validated_artifacts(staging, target)

    assert file_hashes(target) == before


def test_publication_rejects_valid_but_manifest_mismatched_artifact(
    tmp_path: Path,
) -> None:
    target = tmp_path / "nasr_city"
    write_valid_bundle(target, "validated-old")
    before = file_hashes(target)
    staging = tmp_path / "staging"
    write_valid_bundle(staging, "validated-new")
    (staging / refresh.SIGNALS_FILENAME).write_text(
        json.dumps(feature_collection("tampered-after-manifest")), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        refresh.publish_validated_artifacts(staging, target)

    assert file_hashes(target) == before


def test_build_refresh_artifacts_uses_bounded_acquisition_and_writes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = tmp_path / "boundary.geojson"
    boundary.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [[31.3, 30.0], [31.4, 30.0], [31.4, 30.1], [31.3, 30.0]]
                            ],
                        },
                        "properties": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(refresh, "_acquire_osm_graph", lambda polygon: valid_graph())
    monkeypatch.setattr(
        refresh,
        "_acquire_osm_features",
        lambda polygon, tags: feature_collection("signal" if "highway" in tags else "hospital"),
    )
    staging = tmp_path / "staging"

    artifacts = refresh.build_refresh_artifacts(
        boundary, staging, retrieved_at=RETRIEVED_AT
    )

    expected = {
        "nasr_city_graph.graphml",
        "nasr_city_emergency_facilities.geojson",
        "nasr_city_traffic_signals.geojson",
        "nasr_city_traffic_sample_points.geojson",
        "provenance.json",
    }
    assert set(artifacts) == expected
    assert all(path.is_file() and path.stat().st_size > 0 for path in artifacts.values())
    manifest = json.loads(artifacts["provenance.json"].read_text(encoding="utf-8"))
    assert set(manifest["artifacts"]) == expected - {"provenance.json"}
