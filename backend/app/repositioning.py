"""Bounded, hypothetical Phase 04 repositioning simulation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Iterable

import networkx as nx
from shapely.errors import ShapelyError
from shapely.geometry import shape

from app.candidate_evaluation import EvaluatedCandidate
from app.candidate_generation import CandidateResource
from app.config import settings
from app.coverage import (
    CoverageCohort,
    CoverageResource,
    CoverageSnapshot,
    CoverageZone,
    JointCoverageSnapshot,
    compute_coverage_snapshot,
    derive_joint_coverage_snapshot,
)
from app.response_requirements import ResponseRequirement
from app.routing import (
    RouteNotFoundError,
    RoutingPointOutsideGraphError,
    TrafficAwareRouteResult,
    compute_traffic_aware_route,
)
from app.schemas import Coordinate, DataReality, ResourceStatus
from app.traffic.models import TrafficSnapshot


STAGING_POINT_DATA_REALITY = DataReality.SIMULATED
STAGING_POINT_SOURCE = "phase04_prototype_simulated_zone_centroid"
STAGING_POINT_POLICY = "STRATEGIC_SIMULATED_STAGING_POINT"
MAX_REPOSITION_TARGET_ZONES = 3
MAX_REPOSITION_RESOURCES_PER_COHORT = 3


@dataclass(frozen=True)
class RepositionProposal:
    """One accepted hypothetical reserve-to-staging proposal."""

    target_zone_id: str
    staging_zone_id: str
    staging_centroid: Coordinate
    staging_data_reality: DataReality
    staging_source: str
    staging_policy: str
    repositioned_resource_id: str
    failing_cohort_ids: tuple[str, ...]
    reposition_route: TrafficAwareRouteResult
    reposition_eta_seconds: float
    reposition_distance_m: float
    pre_reposition_cohort_snapshots: tuple[CoverageSnapshot, ...]
    post_reposition_cohort_snapshots: tuple[CoverageSnapshot, ...]
    pre_reposition_joint: JointCoverageSnapshot
    post_reposition_joint: JointCoverageSnapshot
    target_failing_cohort_ids_before: tuple[str, ...]
    target_failing_cohort_ids_after: tuple[str, ...]
    target_improved: bool


@dataclass(frozen=True)
class RepositioningSimulation:
    """Deterministic repositioning result; accepted proposals are hypothetical."""

    triggered: bool
    trigger_reasons: tuple[str, ...]
    target_zone_ids: tuple[str, ...]
    proposals: tuple[RepositionProposal, ...]


def select_reposition_proposal(
    proposals: Iterable[RepositionProposal],
) -> RepositionProposal | None:
    """Select the single representative proposal using approved PD-018 order."""
    return min(
        proposals,
        key=lambda proposal: (
            -proposal.post_reposition_joint.population_weighted_coverage,
            proposal.post_reposition_joint.undercovered_zone_count,
            proposal.post_reposition_joint.unreachable_zone_count,
            proposal.reposition_eta_seconds,
            proposal.reposition_distance_m,
            proposal.target_zone_id,
            proposal.staging_zone_id,
            proposal.repositioned_resource_id,
        ),
        default=None,
    )


def _valid_geometry(zone: CoverageZone) -> Any | None:
    if not zone.geometry:
        return None
    try:
        geometry = shape(zone.geometry)
    except (AttributeError, KeyError, TypeError, ValueError, ShapelyError):
        return None
    if geometry.is_empty or not geometry.is_valid:
        return None
    return geometry


def find_adjacent_staging_zones(
    zones: Iterable[CoverageZone],
    target_zone_id: str,
) -> tuple[CoverageZone, ...]:
    """Return valid, immediate zone-centroid staging points in zone-ID order."""
    zones_tuple = tuple(zones)
    target = next((zone for zone in zones_tuple if zone.zone_id == target_zone_id), None)
    if target is None:
        return ()
    target_geometry = _valid_geometry(target)
    if target_geometry is None:
        return ()

    adjacent: list[CoverageZone] = []
    seen_centroids: set[tuple[float, float]] = set()
    candidate_centroids = {
        (zone.centroid.lat, zone.centroid.lon): sum(
            1
            for other in zones_tuple
            if (other.centroid.lat, other.centroid.lon)
            == (zone.centroid.lat, zone.centroid.lon)
        )
        for zone in zones_tuple
    }
    for candidate in sorted(zones_tuple, key=lambda zone: zone.zone_id):
        if candidate.zone_id == target_zone_id:
            continue
        centroid_key = (candidate.centroid.lat, candidate.centroid.lon)
        if candidate_centroids.get(centroid_key, 0) > 1 or centroid_key in seen_centroids:
            continue
        candidate_geometry = _valid_geometry(candidate)
        if candidate_geometry is None:
            continue
        try:
            is_adjacent = target_geometry.touches(candidate_geometry)
        except ShapelyError:
            is_adjacent = False
        if is_adjacent:
            adjacent.append(candidate)
            seen_centroids.add(centroid_key)
    return tuple(adjacent)


def _to_coverage_resource(resource: CandidateResource) -> CoverageResource:
    return CoverageResource(
        resource_id=resource.resource_id,
        resource_type=resource.resource_type,
        capability_tags=resource.capability_tags,
        status=resource.status,
        coordinate=resource.coordinate,
        data_reality=resource.data_reality,
        source=resource.source,
        assigned_incident_id=resource.assigned_incident_id,
    )


def _resource_is_eligible(
    resource: CandidateResource,
    requirement: ResponseRequirement,
    dispatched_ids: set[str],
) -> bool:
    return (
        resource.resource_id not in dispatched_ids
        and resource.status is ResourceStatus.AVAILABLE
        and resource.assigned_incident_id is None
        and resource.resource_type is requirement.resource_type
        and requirement.known_capabilities_satisfy(resource.capability_tags)
    )


def _route_to_staging(
    graph: nx.Graph,
    resource: CandidateResource,
    staging_zone: CoverageZone,
    traffic_snapshot: TrafficSnapshot | None,
) -> TrafficAwareRouteResult | None:
    try:
        return compute_traffic_aware_route(
            graph,
            resource.coordinate,
            staging_zone.centroid,
            traffic_snapshot,
        )
    except (RouteNotFoundError, RoutingPointOutsideGraphError, ValueError):
        return None


def _candidate_resources_after_reposition(
    resources: tuple[CandidateResource, ...],
    dispatched_ids: set[str],
    resource_id: str,
    staging_centroid: Coordinate,
) -> tuple[CoverageResource, ...]:
    hypothetical: list[CoverageResource] = []
    for resource in resources:
        if resource.resource_id in dispatched_ids:
            continue
        if resource.resource_id == resource_id:
            resource = replace(resource, coordinate=staging_centroid)
        hypothetical.append(_to_coverage_resource(resource))
    return tuple(hypothetical)


def _recompute_post_reposition(
    *,
    graph: nx.Graph,
    zones: tuple[CoverageZone, ...],
    resources: tuple[CandidateResource, ...],
    requirements: tuple[ResponseRequirement, ...],
    dispatched_ids: set[str],
    resource_id: str,
    staging_centroid: Coordinate,
    traffic_snapshot: TrafficSnapshot | None,
    modeled_at: datetime,
) -> tuple[tuple[CoverageSnapshot, ...], JointCoverageSnapshot]:
    hypothetical_resources = _candidate_resources_after_reposition(
        resources,
        dispatched_ids,
        resource_id,
        staging_centroid,
    )
    snapshots = tuple(
        compute_coverage_snapshot(
            graph=graph,
            zones=zones,
            resources=hypothetical_resources,
            cohort=CoverageCohort(
                resource_type=requirement.resource_type,
                required_capability_tags=requirement.required_capability_tags,
            ),
            traffic_snapshot=traffic_snapshot,
            modeled_at=modeled_at,
        )
        for requirement in requirements
    )
    return snapshots, derive_joint_coverage_snapshot(snapshots)


def _target_improved(
    *,
    target_zone_id: str,
    failing_cohort_ids: tuple[str, ...],
    after_joint: JointCoverageSnapshot,
    before_cohorts: tuple[CoverageSnapshot, ...],
    after_cohorts: tuple[CoverageSnapshot, ...],
) -> bool:
    after_joint_zone = next(
        zone for zone in after_joint.zones if zone.zone_id == target_zone_id
    )
    if after_joint_zone.covered:
        return True
    before_by_cohort = {
        snapshot.cohort.cohort_id: next(
            zone for zone in snapshot.zones if zone.zone_id == target_zone_id
        )
        for snapshot in before_cohorts
    }
    after_by_cohort = {
        snapshot.cohort.cohort_id: next(
            zone for zone in snapshot.zones if zone.zone_id == target_zone_id
        )
        for snapshot in after_cohorts
    }
    for cohort_id in failing_cohort_ids:
        before = before_by_cohort[cohort_id]
        after = after_by_cohort[cohort_id]
        if after.covered:
            return True
        if (
            before.eta_seconds is not None
            and after.eta_seconds is not None
            and after.eta_seconds < before.eta_seconds
        ):
            return True
    return False


def _useful_reposition(
    before: JointCoverageSnapshot,
    after: JointCoverageSnapshot,
) -> bool:
    return (
        after.population_weighted_coverage > before.population_weighted_coverage
        or after.undercovered_zone_count < before.undercovered_zone_count
        or after.unreachable_zone_count < before.unreachable_zone_count
    ) and after.population_weighted_coverage >= before.population_weighted_coverage


def simulate_repositioning(
    *,
    graph: nx.Graph,
    zones: Iterable[CoverageZone],
    resources: Iterable[CandidateResource],
    requirements: Iterable[ResponseRequirement],
    candidate: EvaluatedCandidate,
    traffic_snapshot: TrafficSnapshot | None,
    modeled_at: datetime,
) -> RepositioningSimulation:
    """Evaluate bounded reserve-to-adjacent-zone moves without operational mutation."""
    zones_tuple = tuple(zones)
    resources_tuple = tuple(resources)
    requirements_tuple = tuple(sorted(requirements, key=lambda item: item.cohort_key))
    if not requirements_tuple:
        raise ValueError("At least one response requirement is required")

    trigger_reasons: list[str] = []
    if candidate.metrics.newly_undercovered_zone_ids:
        trigger_reasons.append("NEWLY_UNDERCOVERED_ZONE")
    if candidate.metrics.coverage_delta <= -settings.REPOSITION_COVERAGE_DROP_TRIGGER:
        trigger_reasons.append("POPULATION_COVERAGE_DROP")
    if not trigger_reasons:
        return RepositioningSimulation(False, (), (), ())

    post_joint = candidate.metrics.post_dispatch_joint
    post_zones = {zone.zone_id: zone for zone in post_joint.zones}
    target_zone_ids = tuple(
        sorted(
            candidate.metrics.newly_undercovered_zone_ids,
            key=lambda zone_id: (-post_zones[zone_id].population, zone_id),
        )[:MAX_REPOSITION_TARGET_ZONES]
    )
    if not target_zone_ids:
        return RepositioningSimulation(True, tuple(trigger_reasons), (), ())

    dispatched_ids = set(candidate.combination.resource_ids)
    requirements_by_cohort = {
        CoverageCohort(
            resource_type=requirement.resource_type,
            required_capability_tags=requirement.required_capability_tags,
        ).cohort_id: requirement
        for requirement in requirements_tuple
    }
    proposals: list[RepositionProposal] = []
    accepted_proposal_keys: set[tuple[str, str, str]] = set()

    for target_zone_id in target_zone_ids:
        target_joint = post_zones[target_zone_id]
        failing_ids = tuple(sorted(target_joint.failing_cohort_ids))
        staging_zones = find_adjacent_staging_zones(zones_tuple, target_zone_id)
        if not staging_zones:
            continue
        for failing_id in failing_ids:
            requirement = requirements_by_cohort.get(failing_id)
            if requirement is None:
                continue
            eligible_reserves = [
                resource
                for resource in resources_tuple
                if _resource_is_eligible(resource, requirement, dispatched_ids)
            ]
            route_options: dict[str, dict[str, TrafficAwareRouteResult]] = {}
            for resource in eligible_reserves:
                for staging in staging_zones:
                    route = _route_to_staging(
                        graph, resource, staging, traffic_snapshot
                    )
                    if route is not None:
                        route_options.setdefault(resource.resource_id, {})[
                            staging.zone_id
                        ] = route
            ranked_resources = sorted(
                eligible_reserves,
                key=lambda resource: (
                    min(
                        (
                            route.effective_eta,
                            route.distance_m,
                        )
                        for route in route_options.get(
                            resource.resource_id, {}
                        ).values()
                    )
                    if route_options.get(resource.resource_id)
                    else (float("inf"), float("inf")),
                    resource.resource_id,
                ),
            )[:MAX_REPOSITION_RESOURCES_PER_COHORT]
            for resource in ranked_resources:
                for staging in staging_zones:
                    route = route_options.get(resource.resource_id, {}).get(
                        staging.zone_id
                    )
                    if route is None or route.effective_eta > settings.PROTOTYPE_TARGET_RESPONSE_TIME_SECONDS:
                        continue
                    post_cohorts, post_reposition_joint = _recompute_post_reposition(
                        graph=graph,
                        zones=zones_tuple,
                        resources=resources_tuple,
                        requirements=requirements_tuple,
                        dispatched_ids=dispatched_ids,
                        resource_id=resource.resource_id,
                        staging_centroid=staging.centroid,
                        traffic_snapshot=traffic_snapshot,
                        modeled_at=modeled_at,
                    )
                    if not _useful_reposition(post_joint, post_reposition_joint):
                        continue
                    pre_cohorts = tuple(
                        sorted(
                            candidate.metrics.cohort_impacts,
                            key=lambda impact: impact.cohort.cohort_id,
                        )
                    )
                    pre_snapshots = tuple(impact.post_dispatch for impact in pre_cohorts)
                    target_improved = _target_improved(
                        target_zone_id=target_zone_id,
                        failing_cohort_ids=failing_ids,
                        after_joint=post_reposition_joint,
                        before_cohorts=pre_snapshots,
                        after_cohorts=post_cohorts,
                    )
                    if not target_improved:
                        continue
                    proposal_key = (
                        target_zone_id,
                        staging.zone_id,
                        resource.resource_id,
                    )
                    if proposal_key in accepted_proposal_keys:
                        continue
                    after_target = next(
                        zone
                        for zone in post_reposition_joint.zones
                        if zone.zone_id == target_zone_id
                    )
                    proposals.append(
                        RepositionProposal(
                            target_zone_id=target_zone_id,
                            staging_zone_id=staging.zone_id,
                            staging_centroid=staging.centroid,
                            staging_data_reality=STAGING_POINT_DATA_REALITY,
                            staging_source=STAGING_POINT_SOURCE,
                            staging_policy=STAGING_POINT_POLICY,
                            repositioned_resource_id=resource.resource_id,
                            failing_cohort_ids=failing_ids,
                            reposition_route=route,
                            reposition_eta_seconds=route.effective_eta,
                            reposition_distance_m=route.distance_m,
                            pre_reposition_cohort_snapshots=pre_snapshots,
                            post_reposition_cohort_snapshots=post_cohorts,
                            pre_reposition_joint=post_joint,
                            post_reposition_joint=post_reposition_joint,
                            target_failing_cohort_ids_before=failing_ids,
                            target_failing_cohort_ids_after=after_target.failing_cohort_ids,
                            target_improved=True,
                        )
                    )
                    accepted_proposal_keys.add(proposal_key)

    proposals.sort(
        key=lambda proposal: (
            proposal.target_zone_id,
            proposal.staging_zone_id,
            proposal.reposition_eta_seconds,
            proposal.reposition_distance_m,
            proposal.repositioned_resource_id,
        )
    )
    return RepositioningSimulation(
        triggered=True,
        trigger_reasons=tuple(trigger_reasons),
        target_zone_ids=target_zone_ids,
        proposals=tuple(proposals),
    )
