from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from shapely.geometry import shape

from app.config import settings

__all__ = [
    "HOSPITAL_SCORE_POLICY_VERSION",
    "HOSPITAL_ETA_NORMALIZER_SECONDS",
    "HOSPITAL_SCORE_WEIGHTS",
    "HospitalStaticRecord",
    "HospitalOperationalSnapshot",
    "HospitalRouteCandidate",
    "load_static_hospitals",
    "rank_hospital_candidates",
]

HOSPITAL_SCORE_POLICY_VERSION = "SIRENGRID_PROTOTYPE_HOSPITAL_SCORE_V1"
HOSPITAL_ETA_NORMALIZER_SECONDS = settings.HOSPITAL_ETA_NORMALIZER_SECONDS
HOSPITAL_SCORE_WEIGHTS = settings.HOSPITAL_SCORE_WEIGHTS


class HospitalStaticRecord(BaseModel):
    """Static hospital facts from the approved OSM/Overpass asset only."""

    model_config = ConfigDict(frozen=True)

    id: str
    source_id: str
    name: str | None = None
    latitude: float
    longitude: float
    static_capabilities: tuple[str, ...] = ()
    confirmed_incompatible_capabilities: tuple[str, ...] = ()
    static_capacity: int | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class HospitalOperationalSnapshot(BaseModel):
    """Explicitly simulated mutable hospital state; unknown is the default."""

    model_config = ConfigDict(frozen=True)

    hospital_id: str
    version: int = 0
    accepting_state: str = "UNKNOWN"
    simulated_load_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    simulated_free_capacity: int | None = Field(default=None, ge=0)
    incoming_cases: int | None = Field(default=None, ge=0)
    freshness_status: str = "UNKNOWN"
    data_reality: str = "SIMULATED"
    last_updated: str | None = None
    source: str = "SIMULATED_HOSPITAL_GATEWAY"

    @classmethod
    def unknown(cls, hospital_id: str) -> "HospitalOperationalSnapshot":
        return cls(hospital_id=hospital_id)


class HospitalRouteCandidate(BaseModel):
    """A hospital plus one captured route and its optional simulated state."""

    hospital: HospitalStaticRecord
    operational_state: HospitalOperationalSnapshot
    route: dict[str, Any]
    score: float | None = None
    score_breakdown: dict[str, Any] = Field(default_factory=dict)


def _normalize_capability(value: str) -> str:
    return re.sub(r"\s+", "_", value.strip().upper())


def _parse_capabilities(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, str) or not raw.strip():
        return ()
    values = re.split(r"[,;|]", raw)
    return tuple(sorted({_normalize_capability(value) for value in values if value.strip()}))


def _static_capacity(properties: dict[str, Any]) -> int | None:
    for key in ("beds", "capacity", "beds:capacity"):
        raw = properties.get(key)
        if raw is None or raw == "":
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _artifact_provenance() -> dict[str, Any]:
    path = settings.NASR_CITY_DATA_DIR / "provenance.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {
            "source": "OpenStreetMap via OSMnx/Overpass",
            "data_reality": "REAL_DERIVED",
            "freshness_status": "STATIC",
            "source_reference": "nasr_city_emergency_facilities.geojson",
        }
    record = data.get("artifacts", {}).get("nasr_city_emergency_facilities.geojson", {})
    return {
        "source": record.get("source", "OpenStreetMap via OSMnx/Overpass"),
        "data_reality": "REAL_DERIVED",
        "freshness_status": "STATIC",
        "last_updated": record.get("retrieved_at"),
        "source_reference": record.get(
            "source_reference", "nasr_city_emergency_facilities.geojson"
        ),
        "artifact_sha256": record.get("sha256"),
    }


def load_static_hospitals(
    asset_path: Path | str | None = None,
) -> list[HospitalStaticRecord]:
    """Load OSM hospital points without fuzzy name merging or fabricated facts."""
    path = Path(asset_path) if asset_path is not None else (
        settings.NASR_CITY_DATA_DIR / "nasr_city_emergency_facilities.geojson"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features", [])
    if not isinstance(features, list):
        raise ValueError("Hospital asset features must be a list")

    records: list[HospitalStaticRecord] = []
    seen_source_keys: set[tuple[str, str]] = set()
    artifact = _artifact_provenance()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        if properties.get("facility_type") != "hospital":
            continue
        geometry = feature.get("geometry") or {}
        try:
            point = shape(geometry).centroid
        except (TypeError, ValueError):
            continue
        if point.is_empty or not point.is_valid:
            continue
        coordinates = (float(point.x), float(point.y))
        source_id = str(feature.get("id") or f"coordinate:{coordinates[0]}:{coordinates[1]}")
        source_key = (source_id, f"{coordinates[0]}:{coordinates[1]}")
        if source_key in seen_source_keys:
            continue
        seen_source_keys.add(source_key)
        source_provenance = {
            **artifact,
            "source_id": source_id,
            "data_reality": properties.get("data_reality", "REAL_PUBLIC"),
            "source_feature_reality": properties.get("data_reality", "REAL_PUBLIC"),
        }
        name = properties.get("name:en") or properties.get("name")
        records.append(
            HospitalStaticRecord(
                id=f"osm:{source_id}",
                source_id=source_id,
                name=str(name) if name else None,
                latitude=coordinates[1],
                longitude=coordinates[0],
                static_capabilities=_parse_capabilities(
                    properties.get("healthcare:speciality")
                ),
                confirmed_incompatible_capabilities=_parse_capabilities(
                    properties.get("confirmed_incompatible_capabilities")
                ),
                static_capacity=_static_capacity(properties),
                provenance=source_provenance,
            )
        )
    return sorted(records, key=lambda hospital: hospital.id)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _freshness_penalty(snapshot: HospitalOperationalSnapshot) -> float:
    status = snapshot.freshness_status.upper()
    if status in {"LIVE", "FRESH"}:
        return 0.0
    if status == "STALE":
        return 1.0
    return 0.5


def rank_hospital_candidates(
    candidates: list[HospitalRouteCandidate],
    *,
    required_capabilities: tuple[str, ...] = (),
) -> list[HospitalRouteCandidate]:
    """Filter and rank hospital routes using the locked prototype policy."""
    required = {_normalize_capability(value) for value in required_capabilities}
    ranked: list[HospitalRouteCandidate] = []
    for candidate in candidates:
        hospital = candidate.hospital
        state = candidate.operational_state
        if state.accepting_state.upper() == "NOT_ACCEPTING":
            continue
        if required.intersection(hospital.confirmed_incompatible_capabilities):
            continue
        try:
            eta_seconds = float(candidate.route["eta_seconds"])
        except (KeyError, TypeError, ValueError):
            continue
        if eta_seconds < 0 or not eta_seconds < float("inf"):
            continue

        confirmed_capability = not required or required.issubset(
            set(hospital.static_capabilities)
        )
        capability_penalty = 0.0 if confirmed_capability else 0.5
        load_penalty = (
            _clamp(float(state.simulated_load_ratio))
            if state.simulated_load_ratio is not None
            else 0.5
        )
        freshness_penalty = _freshness_penalty(state)
        eta_term = eta_seconds / HOSPITAL_ETA_NORMALIZER_SECONDS
        capacity_penalty = 0.0
        weighted_terms = {
            "eta": HOSPITAL_SCORE_WEIGHTS["eta"] * eta_term,
            "capability": HOSPITAL_SCORE_WEIGHTS["capability"] * capability_penalty,
            "load": HOSPITAL_SCORE_WEIGHTS["load"] * load_penalty,
            "freshness": HOSPITAL_SCORE_WEIGHTS["freshness"] * freshness_penalty,
            "capacity": HOSPITAL_SCORE_WEIGHTS["capacity"] * capacity_penalty,
        }
        score = sum(weighted_terms.values())
        breakdown = {
            "policy_version": HOSPITAL_SCORE_POLICY_VERSION,
            "weights": dict(HOSPITAL_SCORE_WEIGHTS),
            "eta_normalizer_seconds": HOSPITAL_ETA_NORMALIZER_SECONDS,
            "route_eta_seconds": eta_seconds,
            "eta_term": eta_term,
            "capability_penalty": capability_penalty,
            "load_penalty": load_penalty,
            "freshness_penalty": freshness_penalty,
            "capacity_penalty": capacity_penalty,
            "required_capabilities": sorted(required),
            "capability_status": "CONFIRMED" if confirmed_capability else "UNKNOWN",
            "load_status": "KNOWN" if state.simulated_load_ratio is not None else "UNKNOWN",
            "freshness_status": state.freshness_status,
            "static_capacity": hospital.static_capacity,
            "incoming_cases": state.incoming_cases,
            "weighted_terms": weighted_terms,
            "final_score": score,
        }
        ranked.append(
            candidate.model_copy(update={"score": score, "score_breakdown": breakdown})
        )

    def sort_key(candidate: HospitalRouteCandidate) -> tuple[Any, ...]:
        breakdown = candidate.score_breakdown
        load = candidate.operational_state.simulated_load_ratio
        incoming = candidate.operational_state.incoming_cases
        return (
            float(candidate.score or 0.0),
            float(breakdown["route_eta_seconds"]),
            0 if breakdown["capability_status"] == "CONFIRMED" else 1,
            0 if load is not None else 1,
            float(load) if load is not None else float("inf"),
            0 if incoming is not None else 1,
            int(incoming) if incoming is not None else 2**31 - 1,
            candidate.hospital.id,
        )

    return sorted(ranked, key=sort_key)
