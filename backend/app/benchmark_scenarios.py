"""Typed Phase 08 scenario inputs and fixed replay fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from app.candidate_generation import CandidateResource
from app.config import REPO_ROOT, settings
from app.response_requirements import ResponseRequirement
from app.schemas import Coordinate, DataReality, ResourceStatus, ResourceType, Severity
from app.traffic.matching import graph_fingerprint
from app.traffic.models import (
    TrafficOverlay,
    TrafficOverlayEntry,
    TrafficProviderState,
    TrafficSnapshot,
)


PHASE08_DATASET_VERSION = "PHASE08_SCENARIO_DATASET_V1"
PHASE08_BENCHMARK_POLICY_VERSION = "SIRENGRID_PHASE08_BENCHMARK_V1"
PHASE08_FIXED_REPLAY_TIME = datetime(2026, 9, 8, tzinfo=timezone.utc)
DEFAULT_SCENARIO_MANIFEST = REPO_ROOT / "data" / "evaluation" / "phase08" / "scenarios.json"
DEFAULT_RESOURCE_SEED = REPO_ROOT / "data" / "scenarios" / "phase01_resources.json"


class ScenarioRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: ResourceType
    minimum_count: int = Field(ge=1)
    required_capability_tags: list[str] = Field(default_factory=list)


class ScenarioIncident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_type: str = Field(min_length=1)
    severity: Severity | None = None
    coordinate: Coordinate
    requirements: list[ScenarioRequirement] = Field(min_length=1)
    transport_required: bool | None = None
    required_hospital_capabilities: list[str] = Field(default_factory=list)

    def response_requirements(self) -> tuple[ResponseRequirement, ...]:
        return tuple(
            ResponseRequirement(
                resource_type=requirement.resource_type,
                minimum_count=requirement.minimum_count,
                required_capability_tags=tuple(requirement.required_capability_tags),
            )
            for requirement in self.requirements
        )


class ScenarioResourceOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1)
    status: ResourceStatus | None = None
    assigned_incident_id: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    capability_tags: list[str] | None = None


class ScenarioHospitalOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hospital_id: str = Field(min_length=1)
    accepting_state: str | None = None
    simulated_load_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    simulated_free_capacity: int | None = Field(default=None, ge=0)
    incoming_cases: int | None = Field(default=None, ge=0)
    freshness_status: str | None = None


class TrafficFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(min_length=1)
    mode: Literal["FALLBACK", "STALE", "CLOSURE", "CONGESTION"]
    source_reference: str = Field(min_length=1)
    closure_edge_index: int | None = Field(default=None, ge=0)
    congestion_factor: float = Field(default=2.0, gt=0)


class ScenarioEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_index: int = Field(ge=0)
    at_seconds: int = Field(ge=0)
    event_type: Literal["RESOURCE_STATE", "SECOND_INCIDENT", "NO_OP"]
    resource_overrides: list[ScenarioResourceOverride] = Field(default_factory=list)
    incident: ScenarioIncident | None = None


class ScenarioExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline: str = Field(min_length=1)
    sirengrid: str = Field(min_length=1)
    notes: str | None = None


class BenchmarkScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    seed: int
    master_plan_case: str | None = None
    tags: list[str] = Field(min_length=1)
    incident: ScenarioIncident
    resource_overrides: list[ScenarioResourceOverride] = Field(default_factory=list)
    hospital_overrides: list[ScenarioHospitalOverride] = Field(default_factory=list)
    traffic_fixture: TrafficFixture
    events: list[ScenarioEvent] = Field(default_factory=list)
    expected: ScenarioExpected


class BenchmarkManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version: str
    policy_version: str
    scenarios: list[BenchmarkScenario]


def load_scenario_manifest(
    path: Path | str = DEFAULT_SCENARIO_MANIFEST,
) -> BenchmarkManifest:
    """Load the committed 36-case manifest and validate its required coverage."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    manifest = BenchmarkManifest.model_validate(payload)
    if manifest.dataset_version != PHASE08_DATASET_VERSION:
        raise ValueError("Unsupported Phase 08 scenario dataset version")
    if manifest.policy_version != PHASE08_BENCHMARK_POLICY_VERSION:
        raise ValueError("Unsupported Phase 08 benchmark policy version")
    if len(manifest.scenarios) != 36:
        raise ValueError("Phase 08 benchmark requires exactly 36 scenarios")
    scenario_ids = [scenario.id for scenario in manifest.scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("Phase 08 scenario IDs must be unique")
    required_cases = {f"T{index:02d}" for index in range(1, 16)}
    actual_cases = {
        scenario.master_plan_case
        for scenario in manifest.scenarios
        if scenario.master_plan_case is not None
    }
    if actual_cases != required_cases:
        raise ValueError("Phase 08 manifest must contain exactly one T01-T15 case")
    if sum(scenario.master_plan_case is not None for scenario in manifest.scenarios) != 15:
        raise ValueError("Phase 08 manifest must contain 15 dedicated Master Plan cases")
    return manifest


def _resource_override_map(
    scenario: BenchmarkScenario,
) -> dict[str, ScenarioResourceOverride]:
    overrides = {item.resource_id: item for item in scenario.resource_overrides}
    if len(overrides) != len(scenario.resource_overrides):
        raise ValueError("Scenario resource overrides must have unique IDs")
    return overrides


def build_candidate_resources(
    scenario: BenchmarkScenario,
    *,
    seed_path: Path | str = DEFAULT_RESOURCE_SEED,
) -> tuple[CandidateResource, ...]:
    """Build immutable planning inputs without changing the seed file or DB."""
    payload = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    raw_resources = payload.get("resources", payload)
    if not isinstance(raw_resources, list):
        raise ValueError("Resource seed must contain a resources list")
    overrides = _resource_override_map(scenario)
    seen_ids: set[str] = set()
    result: list[CandidateResource] = []
    for raw in raw_resources:
        resource_id = str(raw["id"])
        seen_ids.add(resource_id)
        override = overrides.pop(resource_id, None)
        status = override.status if override and override.status is not None else ResourceStatus(raw.get("status", "AVAILABLE"))
        assigned = (
            override.assigned_incident_id
            if override and "assigned_incident_id" in override.model_fields_set
            else raw.get("assigned_incident_id")
        )
        latitude = override.latitude if override and override.latitude is not None else float(raw["latitude"])
        longitude = override.longitude if override and override.longitude is not None else float(raw["longitude"])
        capabilities = (
            override.capability_tags
            if override and override.capability_tags is not None
            else list(raw.get("capability_tags", raw.get("capabilities", [])))
        )
        provenance = raw.get("provenance") or {}
        result.append(
            CandidateResource(
                resource_id=resource_id,
                resource_type=ResourceType(raw["resource_type"]),
                capability_tags=tuple(str(tag) for tag in capabilities),
                status=status,
                assigned_incident_id=assigned,
                coordinate=Coordinate(lat=latitude, lon=longitude),
                data_reality=DataReality(provenance.get("data_reality", DataReality.SIMULATED.value)),
                source=str(provenance.get("source", "scenario_phase01_seed")),
            )
        )
    if overrides:
        raise ValueError(
            "Scenario override references unknown resources: "
            + ", ".join(sorted(overrides))
        )
    return tuple(sorted(result, key=lambda resource: resource.resource_id))


def build_hospital_operational_states(
    scenario: BenchmarkScenario,
) -> dict[str, Any]:
    """Build explicit simulated hospital state overrides for one scenario."""
    from app.hospitals import HospitalOperationalSnapshot

    result: dict[str, HospitalOperationalSnapshot] = {}
    for override in scenario.hospital_overrides:
        if override.hospital_id in result:
            raise ValueError(
                "Scenario hospital overrides must have unique hospital IDs"
            )
        values = {
            name: value
            for name, value in (
                ("accepting_state", override.accepting_state),
                ("simulated_load_ratio", override.simulated_load_ratio),
                ("simulated_free_capacity", override.simulated_free_capacity),
                ("incoming_cases", override.incoming_cases),
                ("freshness_status", override.freshness_status),
            )
            if name in override.model_fields_set
        }
        result[override.hospital_id] = HospitalOperationalSnapshot(
            hospital_id=override.hospital_id,
            **values,
        )
    return result


def _graph_edges(graph: nx.Graph) -> list[tuple[str, str, str]]:
    if graph.is_multigraph():
        edges = [(str(u), str(v), str(key)) for u, v, key in graph.edges(keys=True)]
    else:
        edges = [(str(u), str(v), "0") for u, v in graph.edges()]
    return sorted(edges)


def build_fixed_traffic_snapshot(
    graph: nx.Graph,
    fixture: TrafficFixture,
) -> TrafficSnapshot | None:
    """Create a deterministic replay snapshot; never calls a traffic provider."""
    if fixture.mode == "FALLBACK":
        return None
    edges = _graph_edges(graph)
    if not edges:
        raise ValueError("Cannot build a traffic fixture for an empty graph")
    edge_index = fixture.closure_edge_index or 0
    if edge_index >= len(edges):
        raise ValueError("Traffic fixture edge index is outside the graph")
    fingerprint = graph_fingerprint(graph)
    entries: tuple[TrafficOverlayEntry, ...]
    if fixture.mode == "STALE":
        entries = ()
        freshness = "STALE"
    else:
        edge_key = edges[edge_index]
        entries = (
            TrafficOverlayEntry(
                edge_key=edge_key,
                observation_id=f"phase08-{fixture.fixture_id}-observation",
                traffic_factor=(
                    None if fixture.mode == "CLOSURE" else fixture.congestion_factor
                ),
                road_closure=fixture.mode == "CLOSURE",
            ),
        )
        freshness = "FRESH"
    from app.schemas import FreshnessStatus

    snapshot_id = f"phase08-traffic-{fixture.fixture_id}"
    return TrafficSnapshot(
        snapshot_id=snapshot_id,
        version=1,
        graph_fingerprint=fingerprint,
        sample_points_fingerprint=hashlib.sha256(
            fixture.fixture_id.encode("utf-8")
        ).hexdigest(),
        provider_state=TrafficProviderState.AVAILABLE,
        refresh_attempted_at=PHASE08_FIXED_REPLAY_TIME,
        retrieved_at=PHASE08_FIXED_REPLAY_TIME,
        freshness_status=FreshnessStatus(freshness),
        source="Phase 08 fixed traffic replay fixture",
        source_reference=fixture.source_reference,
        data_reality=None,
        flow_style=settings.TOMTOM_FLOW_STYLE,
        flow_zoom=settings.TOMTOM_FLOW_ZOOM,
        units=settings.TOMTOM_FLOW_UNITS,
        overlay=TrafficOverlay(
            snapshot_id=snapshot_id,
            graph_fingerprint=fingerprint,
            entries=entries,
        )
        if entries
        else None,
    )
