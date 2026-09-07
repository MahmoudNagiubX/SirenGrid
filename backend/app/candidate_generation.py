"""Bounded, deterministic Phase 04 candidate resource generation."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from typing import Iterable

import networkx as nx

from app.config import settings
from app.response_requirements import ResponseRequirement
from app.routing import (
    RouteNotFoundError,
    RoutingPointOutsideGraphError,
    TrafficAwareRouteResult,
    compute_traffic_aware_route,
)
from app.schemas import Coordinate, DataReality, ResourceStatus, ResourceType
from app.traffic.models import TrafficSnapshot


MAX_CANDIDATES_PER_COHORT = settings.MAX_CANDIDATE_RESPONDERS_PER_COHORT
MAX_FEASIBLE_CANDIDATE_COMBINATIONS = settings.MAX_FEASIBLE_CANDIDATE_COMBINATIONS


class NoFeasibleCandidateError(ValueError):
    """Raised when hard constraints leave no valid candidate set."""


@dataclass(frozen=True)
class CandidateResource:
    """Captured operational resource facts used only for planning simulation."""

    resource_id: str
    resource_type: ResourceType
    capability_tags: tuple[str, ...]
    status: ResourceStatus
    assigned_incident_id: str | None
    coordinate: Coordinate
    data_reality: DataReality
    source: str

    def __post_init__(self) -> None:
        if not self.resource_id.strip():
            raise ValueError("Candidate resource_id must be non-empty")
        if not self.source.strip():
            raise ValueError("Candidate resource source must be non-empty")
        normalized_tags = tuple(sorted({tag.strip() for tag in self.capability_tags}))
        if any(not tag for tag in normalized_tags):
            raise ValueError("Candidate resource capability tags must be non-empty")
        object.__setattr__(self, "capability_tags", normalized_tags)


@dataclass(frozen=True)
class CandidateResponder:
    requirement: ResponseRequirement
    resource: CandidateResource
    route: TrafficAwareRouteResult


@dataclass(frozen=True)
class CandidatePool:
    requirement: ResponseRequirement
    responders: tuple[CandidateResponder, ...]


@dataclass(frozen=True)
class CandidateCombination:
    responders: tuple[CandidateResponder, ...]

    @property
    def resource_ids(self) -> tuple[str, ...]:
        return tuple(responder.resource.resource_id for responder in self.responders)


@dataclass(frozen=True)
class CandidateGenerationResult:
    candidate_pools: tuple[CandidatePool, ...]
    combinations: tuple[CandidateCombination, ...]


def _is_hard_eligible(
    resource: CandidateResource,
    requirement: ResponseRequirement,
    *,
    incident_id: str | None = None,
) -> bool:
    same_incident_active = (
        incident_id is not None
        and resource.assigned_incident_id == incident_id
        and resource.status in (ResourceStatus.ASSIGNED, ResourceStatus.EN_ROUTE)
    )
    return (
        (
            resource.status is ResourceStatus.AVAILABLE
            and resource.assigned_incident_id is None
        )
        or same_incident_active
    ) and (
        resource.resource_type is requirement.resource_type
        and requirement.known_capabilities_satisfy(resource.capability_tags)
    )


def _validate_inputs(
    resources: tuple[CandidateResource, ...],
    requirements: tuple[ResponseRequirement, ...],
) -> None:
    resource_ids = [resource.resource_id for resource in resources]
    if len(resource_ids) != len(set(resource_ids)):
        raise ValueError("Candidate resource IDs must be unique")
    if not requirements:
        raise ValueError("At least one response requirement is required")
    cohort_keys = [requirement.cohort_key for requirement in requirements]
    if len(cohort_keys) != len(set(cohort_keys)):
        raise ValueError("Candidate requirements must not duplicate a resource cohort")


def generate_candidate_combinations(
    *,
    graph: nx.Graph,
    incident_coordinate: Coordinate,
    resources: Iterable[CandidateResource],
    requirements: Iterable[ResponseRequirement],
    traffic_snapshot: TrafficSnapshot | None,
    incident_id: str | None = None,
) -> CandidateGenerationResult:
    """Return bounded feasible combinations without mutating resources or graph.

    Routes use exactly the captured traffic snapshot supplied by the caller;
    unavailable, committed, incompatible, and unroutable resources are never
    eligible and route failures never become zero-valued metrics.
    """
    resources_tuple = tuple(resources)
    requirements_tuple = tuple(
        sorted(requirements, key=lambda requirement: requirement.cohort_key)
    )
    _validate_inputs(resources_tuple, requirements_tuple)
    route_cache: dict[str, TrafficAwareRouteResult | None] = {}
    pools: list[CandidatePool] = []

    for requirement in requirements_tuple:
        routeable: list[CandidateResponder] = []
        for resource in sorted(resources_tuple, key=lambda item: item.resource_id):
            if not _is_hard_eligible(resource, requirement, incident_id=incident_id):
                continue
            route = route_cache.get(resource.resource_id)
            if resource.resource_id not in route_cache:
                try:
                    route = compute_traffic_aware_route(
                        graph,
                        resource.coordinate,
                        incident_coordinate,
                        traffic_snapshot,
                    )
                except (RouteNotFoundError, RoutingPointOutsideGraphError, ValueError):
                    route = None
                route_cache[resource.resource_id] = route
            if route is not None:
                routeable.append(
                    CandidateResponder(
                        requirement=requirement,
                        resource=resource,
                        route=route,
                    )
                )
        ranked = tuple(
            sorted(
                routeable,
                key=lambda responder: (
                    responder.route.effective_eta,
                    responder.route.distance_m,
                    responder.resource.resource_id,
                ),
            )[:MAX_CANDIDATES_PER_COHORT]
        )
        if len(ranked) < requirement.minimum_count:
            raise NoFeasibleCandidateError(
                "Insufficient hard-eligible, routeable resources for "
                f"{requirement.resource_type.value}"
            )
        pools.append(CandidatePool(requirement=requirement, responders=ranked))

    selection_options = [
        tuple(combinations(pool.responders, pool.requirement.minimum_count))
        for pool in pools
    ]
    feasible: list[CandidateCombination] = []
    for selections in product(*selection_options):
        responders = tuple(
            sorted(
                (responder for selection in selections for responder in selection),
                key=lambda responder: responder.resource.resource_id,
            )
        )
        resource_ids = tuple(responder.resource.resource_id for responder in responders)
        if len(resource_ids) != len(set(resource_ids)):
            continue
        feasible.append(CandidateCombination(responders=responders))
        if len(feasible) == MAX_FEASIBLE_CANDIDATE_COMBINATIONS:
            break
    if not feasible:
        raise NoFeasibleCandidateError(
            "No feasible candidate combinations satisfy hard resource constraints"
        )
    return CandidateGenerationResult(
        candidate_pools=tuple(pools),
        combinations=tuple(feasible),
    )
