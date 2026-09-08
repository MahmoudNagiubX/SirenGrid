"""Deterministic Phase 04 graph-based operational coverage calculations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import networkx as nx

from app.config import settings
from app.routing import (
    ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME,
    ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED,
    RoutingPointOutsideGraphError,
    compute_single_source_travel_times,
)
from app.schemas import (
    Coordinate,
    DataReality,
    FreshnessStatus,
    ResourceStatus,
    ResourceType,
)
from app.traffic.matching import graph_fingerprint
from app.traffic.models import TrafficSnapshot


PROTOTYPE_TARGET_RESPONSE_TIME_SECONDS = (
    settings.PROTOTYPE_TARGET_RESPONSE_TIME_SECONDS
)
WORLDPOP_SOURCE_REFERENCE = "https://hub.worldpop.org/geodata/summary?id=56914"
JOINT_COVERAGE_AGGREGATION_POLICY = "JOINT_ALL_REQUIRED_COHORTS_V1"


@dataclass(frozen=True)
class CoverageCohort:
    resource_type: ResourceType
    required_capability_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized = tuple(sorted(set(self.required_capability_tags)))
        if any(not tag.strip() for tag in normalized):
            raise ValueError("Required capability tags must be non-empty")
        object.__setattr__(self, "required_capability_tags", normalized)

    @property
    def cohort_id(self) -> str:
        if not self.required_capability_tags:
            return self.resource_type.value
        return f"{self.resource_type.value}|{','.join(self.required_capability_tags)}"


@dataclass(frozen=True)
class CoverageResource:
    resource_id: str
    resource_type: ResourceType
    capability_tags: tuple[str, ...]
    status: ResourceStatus
    coordinate: Coordinate
    data_reality: DataReality
    source: str
    assigned_incident_id: str | None = None

    def __post_init__(self) -> None:
        if not self.resource_id.strip():
            raise ValueError("Coverage resource_id must be non-empty")
        if not self.source.strip():
            raise ValueError("Coverage resource source must be non-empty")
        if any(not tag.strip() for tag in self.capability_tags):
            raise ValueError("Coverage resource capability tags must be non-empty")


@dataclass(frozen=True)
class CoverageZone:
    zone_id: str
    centroid: Coordinate
    population: float
    geometry: dict[str, Any] | None = None
    data_reality: DataReality = DataReality.REAL_DERIVED
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.zone_id.strip():
            raise ValueError("Coverage zone_id must be non-empty")
        if not math.isfinite(self.population) or self.population < 0:
            raise ValueError("Coverage zone population must be finite and non-negative")


@dataclass(frozen=True)
class ZoneCoverage:
    zone_id: str
    population: float
    eta_seconds: float | None
    base_eta_seconds: float | None
    covered: bool
    routing_source: str


@dataclass(frozen=True)
class CoverageSnapshot:
    cohort: CoverageCohort
    modeled_at: datetime
    source: str
    data_reality: DataReality
    population_data_reality: DataReality
    population_source_reference: str | None
    graph_fingerprint: str
    prototype_target_response_time_seconds: int
    zones: tuple[ZoneCoverage, ...]
    eligible_resource_ids: tuple[str, ...]
    excluded_resource_ids: tuple[str, ...]
    total_modeled_population: float
    covered_population: float
    population_weighted_coverage: float
    worst_zone_eta: float | None
    worst_finite_zone_eta: float | None
    undercovered_zone_count: int
    unreachable_zone_count: int
    unreachable_zone_ids: tuple[str, ...]
    routing_source: str
    traffic_snapshot_id: str | None
    traffic_snapshot_version: int | None
    traffic_freshness_status: FreshnessStatus | None
    traffic_source_reference: str | None
    traffic_fallback_reason: str | None
    traffic_adjusted_zone_count: int


@dataclass(frozen=True)
class JointZoneCoverage:
    """One zone's all-required-cohort coverage result."""

    zone_id: str
    population: float
    eta_seconds: float | None
    covered: bool
    failing_cohort_ids: tuple[str, ...]


@dataclass(frozen=True)
class JointCoverageSnapshot:
    """Plan-level coverage derived from retained required-cohort snapshots."""

    aggregation_policy: str
    cohort_snapshots: tuple[CoverageSnapshot, ...]
    modeled_at: datetime
    source: str
    data_reality: DataReality
    population_data_reality: DataReality
    population_source_reference: str | None
    graph_fingerprint: str
    prototype_target_response_time_seconds: int
    zones: tuple[JointZoneCoverage, ...]
    total_modeled_population: float
    covered_population: float
    population_weighted_coverage: float
    worst_zone_eta: float | None
    worst_finite_zone_eta: float | None
    undercovered_zone_count: int
    unreachable_zone_count: int
    unreachable_zone_ids: tuple[str, ...]
    traffic_snapshot_id: str | None
    traffic_snapshot_version: int | None
    traffic_freshness_status: FreshnessStatus | None


@dataclass(frozen=True)
class DispatchImpactSimulation:
    """Immutable baseline/post-dispatch coverage facts for one analytical cohort."""

    cohort: CoverageCohort
    dispatched_resource_ids: tuple[str, ...]
    baseline: CoverageSnapshot
    post_dispatch: CoverageSnapshot
    coverage_delta: float
    affected_zone_ids: tuple[str, ...]
    newly_undercovered_zone_ids: tuple[str, ...]
    remaining_reserve_resource_ids: tuple[str, ...]


def load_population_zones(path: Path) -> tuple[CoverageZone, ...]:
    """Load and validate the immutable REAL_DERIVED population-zone artifact."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not isinstance(
        payload.get("features"), list
    ):
        raise ValueError("Population zones artifact must be a FeatureCollection")
    properties = payload.get("properties")
    if not isinstance(properties, dict) or properties.get("data_reality") != "REAL_DERIVED":
        raise ValueError("Population zones artifact must be REAL_DERIVED")
    source_metadata = properties.get("source_metadata")
    if not isinstance(source_metadata, dict) or source_metadata.get(
        "underlying_data_reality"
    ) != "REAL_PUBLIC":
        raise ValueError("Population zones artifact must retain REAL_PUBLIC source reality")
    source_reference = source_metadata.get("source_reference")
    if not isinstance(source_reference, str) or not source_reference.strip():
        raise ValueError("Population zones artifact source_reference is required")

    zones: list[CoverageZone] = []
    for feature in payload["features"]:
        feature_properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(feature_properties, dict):
            raise ValueError("Population zone feature properties are required")
        centroid = feature_properties.get("centroid")
        if not isinstance(centroid, dict):
            raise ValueError("Population zone centroid is required")
        zones.append(
            CoverageZone(
                zone_id=str(feature_properties.get("zone_id", "")),
                population=float(feature_properties.get("population", -1)),
                centroid=Coordinate(
                    lon=float(centroid.get("longitude")),
                    lat=float(centroid.get("latitude")),
                ),
                geometry=feature.get("geometry"),
                data_reality=DataReality.REAL_DERIVED,
                source_reference=source_reference,
            )
        )
    return _validate_zones(zones)


def _validate_zones(zones: Iterable[CoverageZone]) -> tuple[CoverageZone, ...]:
    validated = tuple(sorted(zones, key=lambda zone: zone.zone_id))
    if not validated:
        raise ValueError("At least one coverage zone is required")
    zone_ids = [zone.zone_id for zone in validated]
    if len(zone_ids) != len(set(zone_ids)):
        raise ValueError("Coverage zone IDs must be unique")
    return validated


def _traffic_cache_identity(snapshot: TrafficSnapshot | None) -> str | None:
    if snapshot is None:
        return None
    return hashlib.sha256(
        snapshot.model_dump_json().encode("utf-8")
    ).hexdigest()


def _matches_cohort(resource: CoverageResource, cohort: CoverageCohort) -> bool:
    return (
        resource.status is ResourceStatus.AVAILABLE
        and resource.assigned_incident_id is None
        and resource.resource_type is cohort.resource_type
        and set(cohort.required_capability_tags).issubset(set(resource.capability_tags))
    )


def _traffic_materially_adjusted(
    base_eta: float,
    effective_eta: float,
    base_path: list[Any],
    effective_path: list[Any],
    snapshot: TrafficSnapshot | None,
    overlay_available: bool,
) -> bool:
    if not overlay_available or snapshot is None:
        return False
    if not math.isclose(base_eta, effective_eta):
        return True
    if base_path != effective_path and snapshot.overlay is not None:
        return any(entry.road_closure for entry in snapshot.overlay.entries)
    return False


def compute_coverage_snapshot(
    *,
    graph: nx.Graph,
    zones: Iterable[CoverageZone],
    resources: Iterable[CoverageResource],
    cohort: CoverageCohort,
    traffic_snapshot: TrafficSnapshot | None,
    modeled_at: datetime,
    travel_times_cache: dict[tuple[Any, ...], Any] | None = None,
    zone_nodes_cache: dict[tuple[Any, ...], Any] | None = None,
) -> CoverageSnapshot:
    """Calculate minimum graph ETA coverage without mutating graph or resources."""
    if modeled_at.tzinfo is None or modeled_at.utcoffset() is None:
        raise ValueError("modeled_at must be timezone-aware")
    validated_zones = _validate_zones(zones)
    population_realities = {zone.data_reality for zone in validated_zones}
    if len(population_realities) != 1:
        raise ValueError("Coverage zones must have one explicit population data reality")
    population_source_references = {
        zone.source_reference for zone in validated_zones if zone.source_reference
    }
    if len(population_source_references) > 1:
        raise ValueError("Coverage zones must have one explicit source reference")
    graph_hash = graph_fingerprint(graph)
    zone_nodes: dict[str, Any] = {}
    for zone in validated_zones:
        zone_cache_key = (
            graph_hash,
            zone.zone_id,
            zone.centroid.lat,
            zone.centroid.lon,
        )
        try:
            snapped = (
                zone_nodes_cache.get(zone_cache_key)
                if zone_nodes_cache is not None
                else None
            )
            if snapped is None:
                snapped, _ = _snap_zone(graph, zone.centroid)
                if zone_nodes_cache is not None:
                    zone_nodes_cache[zone_cache_key] = snapped
            zone_nodes[zone.zone_id] = snapped
        except RoutingPointOutsideGraphError as exc:
            raise ValueError(f"Coverage zone {zone.zone_id} cannot snap to graph") from exc
    selected_resources = sorted(
        (resource for resource in resources if _matches_cohort(resource, cohort)),
        key=lambda resource: resource.resource_id,
    )
    traffic_identity = _traffic_cache_identity(traffic_snapshot)
    trees = []
    excluded_resource_ids: list[str] = []
    for resource in selected_resources:
        cache_key = (
            graph_hash,
            resource.resource_id,
            resource.coordinate.lat,
            resource.coordinate.lon,
            traffic_identity,
        )
        try:
            tree = (
                travel_times_cache.get(cache_key)
                if travel_times_cache is not None
                else None
            )
            if tree is None:
                tree = compute_single_source_travel_times(
                    graph, resource.coordinate, traffic_snapshot
                )
                if travel_times_cache is not None:
                    travel_times_cache[cache_key] = tree
            trees.append((resource.resource_id, tree))
        except RoutingPointOutsideGraphError:
            excluded_resource_ids.append(resource.resource_id)

    zone_results: list[ZoneCoverage] = []
    traffic_adjusted_zone_count = 0
    for zone in validated_zones:
        candidates: list[tuple[str, float, float, list[Any], list[Any], Any]] = []
        for resource_id, tree in trees:
            zone_node = zone_nodes[zone.zone_id]
            effective_eta = tree.effective_travel_times.get(zone_node)
            base_eta = tree.base_travel_times.get(zone_node)
            if effective_eta is None or base_eta is None:
                continue
            candidates.append(
                (
                    resource_id,
                    effective_eta,
                    base_eta,
                    tree.base_paths[zone_node],
                    tree.effective_paths[zone_node],
                    tree,
                )
            )
        if not candidates:
            zone_results.append(
                ZoneCoverage(
                    zone_id=zone.zone_id,
                    population=zone.population,
                    eta_seconds=None,
                    base_eta_seconds=None,
                    covered=False,
                    routing_source=ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME,
                )
            )
            continue
        selected_candidate = min(
            candidates, key=lambda candidate: (candidate[1], candidate[2], candidate[0])
        )
        base_candidate = min(
            candidates, key=lambda candidate: (candidate[2], candidate[1], candidate[0])
        )
        (
            selected_resource_id,
            effective_eta,
            selected_base_eta,
            base_path,
            effective_path,
            tree,
        ) = selected_candidate
        _base_resource_id, _base_effective_eta, base_eta, *_ = base_candidate
        adjusted = _traffic_materially_adjusted(
            selected_base_eta,
            effective_eta,
            base_path,
            effective_path,
            traffic_snapshot,
            tree.traffic_overlay_available,
        ) or (
            tree.traffic_overlay_available
            and selected_resource_id != base_candidate[0]
        )
        if adjusted:
            traffic_adjusted_zone_count += 1
        zone_results.append(
            ZoneCoverage(
                zone_id=zone.zone_id,
                population=zone.population,
                eta_seconds=effective_eta,
                base_eta_seconds=base_eta,
                covered=effective_eta <= PROTOTYPE_TARGET_RESPONSE_TIME_SECONDS,
                routing_source=(
                    ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED
                    if adjusted
                    else ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
                ),
            )
        )

    total_population = sum(zone.population for zone in zone_results)
    covered_population = sum(
        zone.population for zone in zone_results if zone.covered
    )
    coverage_ratio = (
        covered_population / total_population if total_population > 0 else 0.0
    )
    finite_etas = [zone.eta_seconds for zone in zone_results if zone.eta_seconds is not None]
    unreachable_zone_ids = tuple(
        zone.zone_id for zone in zone_results if zone.eta_seconds is None
    )
    representative_tree = trees[0][1] if trees else None
    return CoverageSnapshot(
        cohort=cohort,
        modeled_at=modeled_at,
        source="SirenGrid graph-based coverage calculation",
        data_reality=DataReality.REAL_DERIVED,
        population_data_reality=next(iter(population_realities)),
        population_source_reference=next(iter(population_source_references), None),
        graph_fingerprint=graph_hash,
        prototype_target_response_time_seconds=PROTOTYPE_TARGET_RESPONSE_TIME_SECONDS,
        zones=tuple(zone_results),
        eligible_resource_ids=tuple(resource_id for resource_id, _tree in trees),
        excluded_resource_ids=tuple(excluded_resource_ids),
        total_modeled_population=total_population,
        covered_population=covered_population,
        population_weighted_coverage=coverage_ratio,
        worst_zone_eta=None if unreachable_zone_ids else max(finite_etas, default=None),
        worst_finite_zone_eta=max(finite_etas, default=None),
        undercovered_zone_count=sum(1 for zone in zone_results if not zone.covered),
        unreachable_zone_count=len(unreachable_zone_ids),
        unreachable_zone_ids=unreachable_zone_ids,
        routing_source=(
            ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED
            if traffic_adjusted_zone_count
            else ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
        ),
        traffic_snapshot_id=(
            representative_tree.traffic_snapshot_id if representative_tree else (
                traffic_snapshot.snapshot_id if traffic_snapshot else None
            )
        ),
        traffic_snapshot_version=(
            representative_tree.traffic_snapshot_version if representative_tree else (
                traffic_snapshot.version if traffic_snapshot else None
            )
        ),
        traffic_freshness_status=(
            representative_tree.traffic_freshness_status if representative_tree else (
                traffic_snapshot.freshness_status if traffic_snapshot else None
            )
        ),
        traffic_source_reference=(
            traffic_snapshot.source_reference if traffic_snapshot else None
        ),
        traffic_fallback_reason=(
            representative_tree.traffic_fallback_reason if representative_tree else (
                "TOMTOM_SNAPSHOT_UNAVAILABLE" if traffic_snapshot is None else None
            )
        ),
        traffic_adjusted_zone_count=traffic_adjusted_zone_count,
    )


def simulate_dispatch_impact(
    *,
    graph: nx.Graph,
    zones: Iterable[CoverageZone],
    resources: Iterable[CoverageResource],
    cohort: CoverageCohort,
    dispatched_resource_ids: Iterable[str],
    traffic_snapshot: TrafficSnapshot | None,
    modeled_at: datetime,
    allowed_precommitted_resource_ids: Iterable[str] = (),
    travel_times_cache: dict[tuple[Any, ...], Any] | None = None,
    zone_nodes_cache: dict[tuple[Any, ...], Any] | None = None,
) -> DispatchImpactSimulation:
    """Compare coverage before and after a purely hypothetical dispatch.

    The caller supplies one captured traffic snapshot. This function neither
    refreshes traffic nor mutates graph or resource state; candidate planning
    remains an analytical operation until the existing approval boundary.
    """
    zones_tuple = tuple(zones)
    resources_tuple = tuple(resources)
    resource_ids = [resource.resource_id for resource in resources_tuple]
    if len(resource_ids) != len(set(resource_ids)):
        raise ValueError("Coverage resource IDs must be unique")
    dispatched_ids = tuple(sorted(set(dispatched_resource_ids)))
    dispatched_id_set = set(dispatched_ids)
    allowed_precommitted_ids = set(allowed_precommitted_resource_ids)
    if any(not resource_id.strip() for resource_id in dispatched_ids):
        raise ValueError("Dispatched resource IDs must be non-empty")

    baseline = compute_coverage_snapshot(
        graph=graph,
        zones=zones_tuple,
        resources=resources_tuple,
        cohort=cohort,
        traffic_snapshot=traffic_snapshot,
        modeled_at=modeled_at,
        travel_times_cache=travel_times_cache,
        zone_nodes_cache=zone_nodes_cache,
    )
    eligible_ids = set(baseline.eligible_resource_ids)
    captured_ids = set(resource_ids)
    unknown_or_ineligible_ids = (
        dispatched_id_set & captured_ids
    ) - eligible_ids - allowed_precommitted_ids
    unknown_or_unapproved_ids = dispatched_id_set - captured_ids
    if unknown_or_ineligible_ids:
        names = ", ".join(sorted(unknown_or_ineligible_ids))
        raise ValueError(
            "Dispatched resources must be currently eligible for the coverage cohort: "
            f"{names}"
        )
    if unknown_or_unapproved_ids:
        names = ", ".join(sorted(unknown_or_unapproved_ids))
        raise ValueError(
            "Dispatched resources must be present in the captured coverage set: "
            f"{names}"
        )

    post_dispatch = compute_coverage_snapshot(
        graph=graph,
        zones=zones_tuple,
        resources=(
            resource
            for resource in resources_tuple
            if resource.resource_id not in dispatched_id_set
        ),
        cohort=cohort,
        traffic_snapshot=traffic_snapshot,
        modeled_at=modeled_at,
        travel_times_cache=travel_times_cache,
        zone_nodes_cache=zone_nodes_cache,
    )
    baseline_by_zone = {zone.zone_id: zone for zone in baseline.zones}
    post_by_zone = {zone.zone_id: zone for zone in post_dispatch.zones}
    affected_zone_ids = tuple(
        zone_id
        for zone_id in sorted(baseline_by_zone)
        if baseline_by_zone[zone_id].eta_seconds != post_by_zone[zone_id].eta_seconds
    )
    newly_undercovered_zone_ids = tuple(
        zone_id
        for zone_id in sorted(baseline_by_zone)
        if baseline_by_zone[zone_id].covered
        and not post_by_zone[zone_id].covered
    )
    return DispatchImpactSimulation(
        cohort=cohort,
        dispatched_resource_ids=dispatched_ids,
        baseline=baseline,
        post_dispatch=post_dispatch,
        coverage_delta=(
            post_dispatch.population_weighted_coverage
            - baseline.population_weighted_coverage
        ),
        affected_zone_ids=affected_zone_ids,
        newly_undercovered_zone_ids=newly_undercovered_zone_ids,
        remaining_reserve_resource_ids=post_dispatch.eligible_resource_ids,
    )


def derive_joint_coverage_snapshot(
    cohort_snapshots: Iterable[CoverageSnapshot],
) -> JointCoverageSnapshot:
    """Derive all-required-cohort coverage using one shared zone population total."""
    snapshots = tuple(
        sorted(cohort_snapshots, key=lambda snapshot: snapshot.cohort.cohort_id)
    )
    if not snapshots:
        raise ValueError("At least one required cohort snapshot is required")
    cohort_ids = [snapshot.cohort.cohort_id for snapshot in snapshots]
    if len(cohort_ids) != len(set(cohort_ids)):
        raise ValueError("Joint coverage requires unique cohort snapshots")
    reference = snapshots[0]
    reference_zone_ids = tuple(zone.zone_id for zone in reference.zones)
    for snapshot in snapshots[1:]:
        if tuple(zone.zone_id for zone in snapshot.zones) != reference_zone_ids:
            raise ValueError("Joint coverage snapshots must use identical modeled zones")
        if snapshot.modeled_at != reference.modeled_at:
            raise ValueError("Joint coverage snapshots must share one modeled_at timestamp")
        if snapshot.graph_fingerprint != reference.graph_fingerprint:
            raise ValueError("Joint coverage snapshots must share one graph fingerprint")
        if (
            snapshot.prototype_target_response_time_seconds
            != reference.prototype_target_response_time_seconds
        ):
            raise ValueError("Joint coverage snapshots must share one coverage target")
        if snapshot.population_data_reality != reference.population_data_reality:
            raise ValueError("Joint coverage snapshots must share population reality")
        if snapshot.population_source_reference != reference.population_source_reference:
            raise ValueError("Joint coverage snapshots must share population provenance")
        if snapshot.traffic_snapshot_id != reference.traffic_snapshot_id:
            raise ValueError("Joint coverage snapshots must share one traffic snapshot")
        if snapshot.traffic_snapshot_version != reference.traffic_snapshot_version:
            raise ValueError("Joint coverage snapshots must share one traffic version")
        if snapshot.traffic_freshness_status != reference.traffic_freshness_status:
            raise ValueError("Joint coverage snapshots must share traffic freshness")

    joint_zones: list[JointZoneCoverage] = []
    for index, zone_id in enumerate(reference_zone_ids):
        cohort_zones = [(snapshot, snapshot.zones[index]) for snapshot in snapshots]
        population = cohort_zones[0][1].population
        if any(
            not math.isclose(zone.population, population, rel_tol=0.0, abs_tol=1e-9)
            for _snapshot, zone in cohort_zones[1:]
        ):
            raise ValueError("Joint coverage snapshots must share zone population values")
        failing_cohort_ids = tuple(
            snapshot.cohort.cohort_id
            for snapshot, zone in cohort_zones
            if not zone.covered
        )
        eta_values = [zone.eta_seconds for _snapshot, zone in cohort_zones]
        eta_seconds = None if any(eta is None for eta in eta_values) else max(eta_values)
        joint_zones.append(
            JointZoneCoverage(
                zone_id=zone_id,
                population=population,
                eta_seconds=eta_seconds,
                covered=not failing_cohort_ids,
                failing_cohort_ids=failing_cohort_ids,
            )
        )

    total_population = sum(zone.population for zone in joint_zones)
    covered_population = sum(zone.population for zone in joint_zones if zone.covered)
    finite_etas = [zone.eta_seconds for zone in joint_zones if zone.eta_seconds is not None]
    unreachable_zone_ids = tuple(
        zone.zone_id for zone in joint_zones if zone.eta_seconds is None
    )
    return JointCoverageSnapshot(
        aggregation_policy=JOINT_COVERAGE_AGGREGATION_POLICY,
        cohort_snapshots=snapshots,
        modeled_at=reference.modeled_at,
        source="SirenGrid joint required-cohort coverage calculation",
        data_reality=DataReality.REAL_DERIVED,
        population_data_reality=reference.population_data_reality,
        population_source_reference=reference.population_source_reference,
        graph_fingerprint=reference.graph_fingerprint,
        prototype_target_response_time_seconds=(
            reference.prototype_target_response_time_seconds
        ),
        zones=tuple(joint_zones),
        total_modeled_population=total_population,
        covered_population=covered_population,
        population_weighted_coverage=(
            covered_population / total_population if total_population > 0 else 0.0
        ),
        worst_zone_eta=None if unreachable_zone_ids else max(finite_etas, default=None),
        worst_finite_zone_eta=max(finite_etas, default=None),
        undercovered_zone_count=sum(1 for zone in joint_zones if not zone.covered),
        unreachable_zone_count=len(unreachable_zone_ids),
        unreachable_zone_ids=unreachable_zone_ids,
        traffic_snapshot_id=reference.traffic_snapshot_id,
        traffic_snapshot_version=reference.traffic_snapshot_version,
        traffic_freshness_status=reference.traffic_freshness_status,
    )


def _snap_zone(graph: nx.Graph, coordinate: Coordinate) -> tuple[Any, float]:
    """Use the same safe snap policy as resource origins for zone centroids."""
    from app.routing import snap_coordinate_to_graph

    return snap_coordinate_to_graph(graph, coordinate)
