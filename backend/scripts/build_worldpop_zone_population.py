"""Build the Phase 04 Nasr City zone-population artifact from locked WorldPop data."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union


WORLDPOP_SOURCE_REFERENCE = "https://hub.worldpop.org/geodata/summary?id=56914"
WORLDPOP_RASTER_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2024B/2025/"
    "EGY/v1/100m/constrained/egy_pop_2025_CN_100m_R2024B_v1.tif"
)
WORLDPOP_DOI = "10.5258/SOTON/WP00803"
WORLDPOP_RELEASE = "R2024B"
WORLDPOP_VERSION = "v1"
EQUAL_AREA_CRS = "EPSG:6933"
WORLDPOP_PROVENANCE_FILENAME = "worldpop_provenance.json"
WORLDPOP_PROVENANCE_PHASE = "PHASE_04_COVERAGE_AND_RESPONSE_PLANNING"


@dataclass(frozen=True)
class OperationalZone:
    """One valid SirenGrid operational zone, optionally retaining display geometry."""

    zone_id: str
    geometry: BaseGeometry
    display_geometry: BaseGeometry | None = None


@dataclass(frozen=True)
class PopulationCell:
    """One raster cell in the same projected CRS as the zone geometries."""

    geometry: BaseGeometry
    population: float | None


@dataclass(frozen=True)
class PopulationAggregation:
    zone_populations: dict[str, float]
    source_population_within_modeled_union: float
    allocated_population: float
    conservation_error: float
    nodata_cell_count: int


def _validate_zones(zones: Iterable[OperationalZone]) -> list[OperationalZone]:
    validated = sorted(zones, key=lambda zone: zone.zone_id)
    if not validated:
        raise ValueError("At least one operational zone is required")
    zone_ids = [zone.zone_id for zone in validated]
    if any(not zone_id.strip() for zone_id in zone_ids):
        raise ValueError("Every zone_id must be non-empty")
    if len(zone_ids) != len(set(zone_ids)):
        raise ValueError("Every zone_id must be unique")
    for zone in validated:
        if zone.geometry.is_empty or not zone.geometry.is_valid or zone.geometry.area <= 0:
            raise ValueError(f"Zone {zone.zone_id} geometry must be valid and non-empty")
    return validated


def aggregate_cells_to_zones(
    cells: Iterable[PopulationCell], zones: Iterable[OperationalZone]
) -> PopulationAggregation:
    """Allocate every valid cell population by exact overlap in a projected CRS."""
    validated_zones = _validate_zones(zones)
    modeled_union = unary_union([zone.geometry for zone in validated_zones])
    populations = {zone.zone_id: 0.0 for zone in validated_zones}
    source_population = 0.0
    nodata_cell_count = 0

    for cell in cells:
        if cell.geometry.is_empty or not cell.geometry.is_valid or cell.geometry.area <= 0:
            raise ValueError("Population cell geometry must be valid and non-empty")
        if cell.population is not None and (
            not math.isfinite(cell.population) or cell.population < 0
        ):
            raise ValueError("Population values must be finite and non-negative")

        overlap_with_union = cell.geometry.intersection(modeled_union)
        if overlap_with_union.is_empty or overlap_with_union.area <= 0:
            continue
        if cell.population is None:
            nodata_cell_count += 1
            continue

        source_population += cell.population * (
            overlap_with_union.area / cell.geometry.area
        )
        for zone in validated_zones:
            overlap = cell.geometry.intersection(zone.geometry)
            if not overlap.is_empty and overlap.area > 0:
                populations[zone.zone_id] += cell.population * (
                    overlap.area / cell.geometry.area
                )

    normalized_populations = {
        zone_id: round(population, 12)
        for zone_id, population in sorted(populations.items())
    }
    allocated_population = round(sum(normalized_populations.values()), 12)
    source_population = round(source_population, 12)
    conservation_error = round(allocated_population - source_population, 12)
    if not math.isclose(allocated_population, source_population, abs_tol=1e-8):
        raise ValueError("Area-weighted allocation failed population conservation")
    return PopulationAggregation(
        zone_populations=normalized_populations,
        source_population_within_modeled_union=source_population,
        allocated_population=allocated_population,
        conservation_error=conservation_error,
        nodata_cell_count=nodata_cell_count,
    )


def build_zone_population_artifact(
    zones: Iterable[OperationalZone],
    aggregation: PopulationAggregation,
    source_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the deterministic, self-describing processed zone artifact."""
    validated_zones = _validate_zones(zones)
    if set(aggregation.zone_populations) != {zone.zone_id for zone in validated_zones}:
        raise ValueError("Aggregation zone IDs do not match the operational zones")
    required_metadata = {"source", "source_reference", "doi", "release", "version"}
    missing_metadata = required_metadata - set(source_metadata)
    if missing_metadata:
        raise ValueError(f"Missing source metadata: {sorted(missing_metadata)}")

    features: list[dict[str, Any]] = []
    for zone in validated_zones:
        display_geometry = zone.display_geometry or zone.geometry
        centroid = display_geometry.centroid
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(display_geometry),
                "properties": {
                    "zone_id": zone.zone_id,
                    "population": aggregation.zone_populations[zone.zone_id],
                    "centroid": {
                        "longitude": round(float(centroid.x), 12),
                        "latitude": round(float(centroid.y), 12),
                    },
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "properties": {
            "data_reality": "REAL_DERIVED",
            "freshness_status": "STATIC",
            "source_metadata": {
                **dict(source_metadata),
                "underlying_data_reality": "REAL_PUBLIC",
            },
            "validation": {
                "zone_count": len(features),
                "total_modeled_population": aggregation.allocated_population,
                "source_population_within_modeled_union": (
                    aggregation.source_population_within_modeled_union
                ),
                "conservation_error": aggregation.conservation_error,
                "nodata_cell_count": aggregation.nodata_cell_count,
            },
        },
        "features": features,
    }


def _validate_artifact_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Zone population artifact must be valid JSON object")
    if payload.get("type") != "FeatureCollection":
        raise ValueError("Zone population artifact must be a FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Zone population artifact must contain features")
    for feature in features:
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict) or not properties.get("zone_id"):
            raise ValueError("Zone population artifact feature requires zone_id")
        population = properties.get("population")
        if not isinstance(population, (int, float)) or population < 0:
            raise ValueError("Zone population artifact population must be non-negative")


def publish_validated_zone_population_artifact(staged_path: Path, target_path: Path) -> None:
    """Validate before atomic replacement so a failed build preserves prior output."""
    try:
        payload = json.loads(staged_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Zone population artifact must be valid JSON") from exc
    _validate_artifact_payload(payload)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged_path, target_path)


def serialize_zone_population_artifact(artifact: Mapping[str, Any]) -> bytes:
    """Return the canonical UTF-8/LF bytes locked by the manifest hash."""
    return json.dumps(
        artifact, ensure_ascii=False, indent=2, sort_keys=True
    ).encode("utf-8")


def build_worldpop_provenance(
    artifact: Mapping[str, Any], artifact_filename: str
) -> dict[str, Any]:
    """Build the integrity manifest for a published WorldPop zone artifact."""
    properties = artifact["properties"]
    source_metadata = properties["source_metadata"]
    validation = properties["validation"]
    artifact_bytes = serialize_zone_population_artifact(artifact)
    return {
        "phase": WORLDPOP_PROVENANCE_PHASE,
        "generated_by": "backend/scripts/build_worldpop_zone_population.py",
        "data_reality": properties["data_reality"],
        "underlying_data_reality": source_metadata["underlying_data_reality"],
        "hash_encoding": "canonical UTF-8 bytes with LF line endings",
        "artifacts": {
            artifact_filename: {
                "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
                "byte_count": len(artifact_bytes),
                "data_reality": properties["data_reality"],
                "freshness_status": properties["freshness_status"],
                "record_count": validation["zone_count"],
                "total_modeled_population": validation["total_modeled_population"],
                "conservation_error": validation["conservation_error"],
                "nodata_cell_count": validation["nodata_cell_count"],
                "source": source_metadata["source"],
                "source_reference": source_metadata["source_reference"],
                "source_filename": source_metadata["source_filename"],
                "source_sha256": source_metadata["source_sha256"],
                "raster_url": source_metadata["raster_url"],
                "doi": source_metadata["doi"],
                "release": source_metadata["release"],
                "version": source_metadata["version"],
                "acquired_at": source_metadata["acquired_at"],
                "allocation_crs": source_metadata["allocation_crs"],
            }
        },
    }


def load_operational_zones(grid_path: Path) -> list[OperationalZone]:
    payload = json.loads(grid_path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not isinstance(
        payload.get("features"), list
    ):
        raise ValueError("Operational zone grid must be a FeatureCollection")
    zones = [
        OperationalZone(
            zone_id=str(feature.get("properties", {}).get("zone_code", "")),
            geometry=shape(feature["geometry"]),
        )
        for feature in payload["features"]
    ]
    return _validate_zones(zones)


def _transform_geometry(geometry: BaseGeometry, source_crs: object, target_crs: str) -> BaseGeometry:
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return transform(transformer.transform, geometry)


def _require_rasterio() -> Any:
    try:
        import rasterio
    except ImportError as exc:  # pragma: no cover - exercised by real CLI only
        raise RuntimeError("rasterio is required for WorldPop GeoTIFF processing") from exc
    return rasterio


def _require_numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - rasterio requires numpy
        raise RuntimeError("numpy is required for WorldPop GeoTIFF processing") from exc
    return numpy


def build_artifact_from_worldpop_raster(
    raster_path: Path, grid_path: Path, acquired_at: datetime | None = None
) -> dict[str, Any]:
    """Read the locked raster, project cell geometries, and build the artifact."""
    rasterio = _require_rasterio()
    numpy = _require_numpy()
    original_zones = load_operational_zones(grid_path)
    acquired_at = acquired_at or datetime.now(timezone.utc)
    if acquired_at.tzinfo is None:
        raise ValueError("acquired_at must be timezone-aware")

    with rasterio.open(raster_path) as dataset:
        if dataset.crs is None:
            raise ValueError("WorldPop raster must declare a CRS")
        raster_zones = [
            OperationalZone(
                zone_id=zone.zone_id,
                geometry=_transform_geometry(zone.geometry, "EPSG:4326", str(dataset.crs)),
                display_geometry=zone.geometry,
            )
            for zone in original_zones
        ]
        equal_area_zones = [
            OperationalZone(
                zone_id=zone.zone_id,
                geometry=_transform_geometry(zone.geometry, dataset.crs, EQUAL_AREA_CRS),
                display_geometry=zone.display_geometry,
            )
            for zone in raster_zones
        ]
        union_bounds = unary_union([zone.geometry for zone in raster_zones]).bounds
        window = rasterio.windows.from_bounds(*union_bounds, transform=dataset.transform)
        full_window = rasterio.windows.Window(0, 0, dataset.width, dataset.height)
        window = window.round_offsets().round_lengths().intersection(full_window)
        data = dataset.read(1, window=window, masked=True)
        mask = numpy.ma.getmaskarray(data)
        window_transform = dataset.window_transform(window)
        cells: list[PopulationCell] = []
        for row in range(data.shape[0]):
            for column in range(data.shape[1]):
                upper_left = rasterio.transform.xy(window_transform, row, column, offset="ul")
                lower_right = rasterio.transform.xy(window_transform, row, column, offset="lr")
                projected_cell = _transform_geometry(
                    box(upper_left[0], lower_right[1], lower_right[0], upper_left[1]),
                    dataset.crs,
                    EQUAL_AREA_CRS,
                )
                population = None if mask[row, column] else float(data[row, column])
                cells.append(PopulationCell(geometry=projected_cell, population=population))

        aggregation = aggregate_cells_to_zones(cells, equal_area_zones)
        source_metadata = {
            "source": "WorldPop Egypt constrained population counts",
            "source_reference": WORLDPOP_SOURCE_REFERENCE,
            "raster_url": WORLDPOP_RASTER_URL,
            "doi": WORLDPOP_DOI,
            "release": WORLDPOP_RELEASE,
            "version": WORLDPOP_VERSION,
            "acquired_at": acquired_at.isoformat(),
            "source_filename": raster_path.name,
            "source_sha256": hashlib.sha256(raster_path.read_bytes()).hexdigest(),
            "source_crs": str(dataset.crs),
            "source_nodata_value": dataset.nodata,
            "allocation_crs": EQUAL_AREA_CRS,
        }
    return build_zone_population_artifact(original_zones, aggregation, source_metadata)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raster", required=True, type=Path)
    parser.add_argument("--grid", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    artifact = build_artifact_from_worldpop_raster(arguments.raster, arguments.grid)
    staged_path = arguments.output.with_suffix(arguments.output.suffix + ".staged")
    staged_path.write_bytes(serialize_zone_population_artifact(artifact))
    publish_validated_zone_population_artifact(staged_path, arguments.output)

    # The manifest is written only after the validated artifact is in place.
    provenance = build_worldpop_provenance(artifact, arguments.output.name)
    provenance_path = arguments.output.parent / WORLDPOP_PROVENANCE_FILENAME
    provenance_path.write_bytes(
        (json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        .encode("utf-8")
    )


if __name__ == "__main__":  # pragma: no cover
    main()
