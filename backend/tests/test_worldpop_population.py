from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from scripts import build_worldpop_zone_population as worldpop


REPO_ROOT = Path(__file__).resolve().parents[2]
NASR_CITY_ASSETS_DIR = REPO_ROOT / "data" / "processed" / "nasr_city"


def test_exact_area_weighted_overlap_apportions_a_pixel_once() -> None:
    """A pixel split across zones is allocated by overlap, never duplicated."""
    cells = [worldpop.PopulationCell(geometry=box(0, 0, 10, 10), population=100.0)]
    zones = [
        worldpop.OperationalZone(zone_id="zone-west", geometry=box(0, 0, 5, 10)),
        worldpop.OperationalZone(zone_id="zone-east", geometry=box(5, 0, 10, 10)),
    ]

    aggregation = worldpop.aggregate_cells_to_zones(cells, zones)

    assert aggregation.zone_populations == {"zone-east": 50.0, "zone-west": 50.0}
    assert aggregation.source_population_within_modeled_union == 100.0
    assert aggregation.allocated_population == 100.0
    assert aggregation.conservation_error == 0.0


def test_nodata_is_explicitly_excluded_not_silently_counted_as_population() -> None:
    cells = [
        worldpop.PopulationCell(geometry=box(0, 0, 10, 10), population=None),
        worldpop.PopulationCell(geometry=box(10, 0, 20, 10), population=20.0),
    ]
    zones = [worldpop.OperationalZone(zone_id="zone-1", geometry=box(0, 0, 20, 10))]

    aggregation = worldpop.aggregate_cells_to_zones(cells, zones)

    assert aggregation.zone_populations == {"zone-1": 20.0}
    assert aggregation.nodata_cell_count == 1
    assert aggregation.source_population_within_modeled_union == 20.0


def test_invalid_population_and_unknown_zone_id_fail_validation() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        worldpop.aggregate_cells_to_zones(
            [worldpop.PopulationCell(geometry=box(0, 0, 1, 1), population=-0.1)],
            [worldpop.OperationalZone(zone_id="zone-1", geometry=box(0, 0, 1, 1))],
        )

    with pytest.raises(ValueError, match="zone_id"):
        worldpop.aggregate_cells_to_zones(
            [worldpop.PopulationCell(geometry=box(0, 0, 1, 1), population=1.0)],
            [worldpop.OperationalZone(zone_id="", geometry=box(0, 0, 1, 1))],
        )


def test_publish_validated_artifact_preserves_last_validated_output_on_failure(
    tmp_path: Path,
) -> None:
    target = tmp_path / "zone_population.geojson"
    target.write_text('{"validated": "old"}', encoding="utf-8")
    before = target.read_bytes()
    invalid_staged = tmp_path / "invalid.geojson"
    invalid_staged.write_text("not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="valid JSON"):
        worldpop.publish_validated_zone_population_artifact(invalid_staged, target)

    assert target.read_bytes() == before


def test_cli_writes_canonical_utf8_lf_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "population.geojson"
    artifact = {
        "type": "FeatureCollection",
        "message": "مرحبا",
        "properties": {
            "data_reality": "REAL_DERIVED",
            "freshness_status": "STATIC",
            "source_metadata": {
                "acquired_at": "2026-09-07T00:00:00+00:00",
                "allocation_crs": "EPSG:6933",
                "doi": "10.5258/SOTON/WP00803",
                "raster_url": "https://example.invalid/egy.tif",
                "release": "R2024B",
                "source": "WorldPop Egypt constrained population counts",
                "source_filename": "egy.tif",
                "source_reference": "https://example.invalid/summary",
                "source_sha256": "00",
                "underlying_data_reality": "REAL_PUBLIC",
                "version": "v1",
            },
            "validation": {
                "conservation_error": 0.0,
                "nodata_cell_count": 0,
                "total_modeled_population": 1.0,
                "zone_count": 1,
            },
        },
        "features": [
            {"properties": {"zone_id": "zone-1", "population": 1.0}}
        ],
    }
    monkeypatch.setattr(
        worldpop, "build_artifact_from_worldpop_raster", lambda *_: artifact
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_worldpop_zone_population.py",
            "--raster",
            str(tmp_path / "source.tif"),
            "--grid",
            str(tmp_path / "grid.geojson"),
            "--output",
            str(output),
        ],
    )

    worldpop.main()

    assert output.read_bytes() == worldpop.serialize_zone_population_artifact(artifact)

    manifest_path = output.parent / worldpop.WORLDPOP_PROVENANCE_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest["artifacts"][output.name]
    assert record["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert record["record_count"] == 1
    assert manifest["data_reality"] == "REAL_DERIVED"
    assert manifest["underlying_data_reality"] == "REAL_PUBLIC"


def test_zone_artifact_preserves_worldpop_reality_and_provenance() -> None:
    cells = [worldpop.PopulationCell(geometry=box(0, 0, 10, 10), population=100.0)]
    zones = [worldpop.OperationalZone(zone_id="zone-1", geometry=box(0, 0, 10, 10))]
    aggregation = worldpop.aggregate_cells_to_zones(cells, zones)

    artifact = worldpop.build_zone_population_artifact(
        zones,
        aggregation,
        source_metadata={
            "source": "WorldPop",
            "source_reference": "https://hub.worldpop.org/geodata/summary?id=56914",
            "doi": "10.5258/SOTON/WP00803",
            "release": "R2024B",
            "version": "v1",
        },
    )

    assert artifact["type"] == "FeatureCollection"
    assert artifact["properties"]["data_reality"] == "REAL_DERIVED"
    assert artifact["properties"]["source_metadata"]["underlying_data_reality"] == "REAL_PUBLIC"
    assert artifact["features"][0]["properties"] == {
        "zone_id": "zone-1",
        "population": 100.0,
        "centroid": {"longitude": 5.0, "latitude": 5.0},
    }
    json.dumps(artifact)


def test_locked_worldpop_raster_build_preserves_clipped_population_and_metadata(
    tmp_path: Path,
) -> None:
    """The raster path uses projected overlap and records the locked source identity."""
    raster_path = tmp_path / "source.tif"
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=1,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 1, 1, 1),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(numpy.array([[100.0, -9999.0]]), 1)

    grid_path = tmp_path / "grid.geojson"
    grid_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [[0, 0], [0.5, 0], [0.5, 1], [0, 1], [0, 0]]
                            ],
                        },
                        "properties": {"zone_code": "zone-west"},
                    },
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [[0.5, 0], [1, 0], [1, 1], [0.5, 1], [0.5, 0]]
                            ],
                        },
                        "properties": {"zone_code": "zone-east"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    artifact = worldpop.build_artifact_from_worldpop_raster(raster_path, grid_path)

    assert [feature["properties"]["population"] for feature in artifact["features"]] == [
        50.0,
        50.0,
    ]
    metadata = artifact["properties"]["source_metadata"]
    assert metadata["doi"] == worldpop.WORLDPOP_DOI
    assert metadata["release"] == "R2024B"
    assert metadata["version"] == "v1"
    assert artifact["properties"]["validation"] == {
        "zone_count": 2,
        "total_modeled_population": 100.0,
        "source_population_within_modeled_union": 100.0,
        "conservation_error": 0.0,
        "nodata_cell_count": 0,
    }


def test_processed_nasr_city_population_artifact_matches_locked_worldpop_contract() -> None:
    artifact_path = (
        NASR_CITY_ASSETS_DIR / "nasr_city_zone_population_worldpop_2025.geojson"
    )
    grid_path = NASR_CITY_ASSETS_DIR / "nasr_city_grid_500m.geojson"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    grid = json.loads(grid_path.read_text(encoding="utf-8"))

    assert artifact["type"] == "FeatureCollection"
    assert artifact["properties"]["data_reality"] == "REAL_DERIVED"
    metadata = artifact["properties"]["source_metadata"]
    assert metadata["underlying_data_reality"] == "REAL_PUBLIC"
    assert metadata["source_reference"] == worldpop.WORLDPOP_SOURCE_REFERENCE
    assert metadata["doi"] == worldpop.WORLDPOP_DOI
    assert metadata["release"] == worldpop.WORLDPOP_RELEASE
    assert metadata["version"] == worldpop.WORLDPOP_VERSION
    assert metadata["source_sha256"] == "75ea54bea9667335858cc5be88735c467f165403d5020d794fa52d2a7cfdf1e6"

    expected_zone_ids = sorted(
        feature["properties"]["zone_code"] for feature in grid["features"]
    )
    actual_zone_ids = [feature["properties"]["zone_id"] for feature in artifact["features"]]
    populations = [feature["properties"]["population"] for feature in artifact["features"]]
    assert actual_zone_ids == expected_zone_ids
    assert all(population >= 0 for population in populations)
    validation = artifact["properties"]["validation"]
    assert validation["zone_count"] == len(expected_zone_ids)
    assert abs(validation["conservation_error"]) <= 1e-8
    assert sum(populations) == pytest.approx(validation["total_modeled_population"])
