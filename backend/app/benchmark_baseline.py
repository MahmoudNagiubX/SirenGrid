"""Simple, safe Phase 08 benchmark baseline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import networkx as nx

from app.candidate_generation import CandidateResource, _is_hard_eligible
from app.hospitals import (
    HospitalOperationalSnapshot,
    HospitalRouteCandidate,
    HospitalStaticRecord,
    load_static_hospitals,
)
from app.response_requirements import ResponseRequirement
from app.routing import (
    RouteNotFoundError,
    RoutingPointOutsideGraphError,
    TrafficAwareRouteResult,
    compute_traffic_aware_route,
)
from app.schemas import Coordinate
from app.traffic.models import TrafficSnapshot


class BaselineInsufficientResourcesError(ValueError):
    """The safe greedy baseline cannot satisfy all hard requirements."""


@dataclass(frozen=True)
class BaselineChoice:
    requirement: ResponseRequirement
    resource: CandidateResource
    route: TrafficAwareRouteResult


@dataclass(frozen=True)
class BaselineSelection:
    """One greedy baseline decision, with no operational-state mutation."""

    choices: tuple[BaselineChoice, ...]

    @property
    def resource_ids(self) -> tuple[str, ...]:
        return tuple(choice.resource.resource_id for choice in self.choices)

    @property
    def max_incident_eta_seconds(self) -> float:
        return max(choice.route.effective_eta for choice in self.choices)


def _compute_baseline_route(
    graph: nx.Graph,
    origin: Coordinate,
    destination: Coordinate,
    traffic_snapshot: TrafficSnapshot | None,
    *,
    include_alternatives: bool,
) -> TrafficAwareRouteResult:
    """Calculate a baseline route while keeping simple test doubles compatible."""
    try:
        return compute_traffic_aware_route(
            graph,
            origin,
            destination,
            traffic_snapshot,
            include_alternatives=include_alternatives,
        )
    except TypeError as exc:
        # Existing focused tests use four-argument route doubles.  The fallback
        # is limited to that compatibility shape and never hides other errors.
        if "include_alternatives" not in str(exc):
            raise
        return compute_traffic_aware_route(graph, origin, destination, traffic_snapshot)


def choose_nearest_baseline_hospital(
    *,
    graph: nx.Graph,
    origin: Coordinate,
    required_capabilities: tuple[str, ...] = (),
    traffic_snapshot: TrafficSnapshot | None,
    hospitals: Iterable[HospitalStaticRecord] | None = None,
    operational_states: dict[str, HospitalOperationalSnapshot] | None = None,
    include_route_alternatives: bool = True,
) -> HospitalRouteCandidate | None:
    """Choose the feasible hospital with the lowest route ETA.

    This deliberately applies Phase 05 hard truth filters without using its
    weighted hospital score, matching the architecture's simple baseline.
    """
    required = {value.strip().upper() for value in required_capabilities if value.strip()}
    states = operational_states or {}
    routeable: list[HospitalRouteCandidate] = []
    for hospital in hospitals if hospitals is not None else load_static_hospitals():
        state = states.get(hospital.id) or HospitalOperationalSnapshot.unknown(hospital.id)
        if state.accepting_state.upper() == "NOT_ACCEPTING":
            continue
        if required.intersection(hospital.confirmed_incompatible_capabilities):
            continue
        try:
            route = _compute_baseline_route(
                graph,
                origin,
                Coordinate(lat=hospital.latitude, lon=hospital.longitude),
                traffic_snapshot,
                include_alternatives=include_route_alternatives,
            )
        except (RouteNotFoundError, RoutingPointOutsideGraphError, ValueError):
            continue
        routeable.append(
            HospitalRouteCandidate(
                hospital=hospital,
                operational_state=state,
                route=route.model_dump(mode="json"),
            )
        )
    return min(
        routeable,
        key=lambda candidate: (
            float(candidate.route["effective_eta"] if "effective_eta" in candidate.route else candidate.route["eta_seconds"]),
            float(candidate.route["distance_m"]),
            candidate.hospital.id,
        ),
        default=None,
    )


def _requirement_key(requirement: ResponseRequirement) -> tuple[str, tuple[str, ...]]:
    return requirement.resource_type.value, requirement.required_capability_tags


def _validated_requirements(
    requirements: Iterable[ResponseRequirement],
) -> tuple[ResponseRequirement, ...]:
    values = tuple(requirements)
    if not values:
        raise BaselineInsufficientResourcesError(
            "INSUFFICIENT_RESOURCES: no requirements were provided"
        )
    keys = [_requirement_key(requirement) for requirement in values]
    if len(keys) != len(set(keys)):
        raise ValueError("Baseline requirements must not duplicate a resource cohort")
    return values


def choose_greedy_baseline_resources(
    *,
    graph: nx.Graph,
    incident_coordinate: Coordinate,
    resources: Iterable[CandidateResource],
    requirements: Iterable[ResponseRequirement],
    traffic_snapshot: TrafficSnapshot | None,
    incident_id: str | None = None,
    include_route_alternatives: bool = True,
) -> BaselineSelection:
    """Choose eligible resources using the approved simple greedy policy.

    The most constrained cohort is determined from routeable, hard-eligible
    physical resources. Once selected, a resource is removed from all later
    cohorts. There is intentionally no backtracking or coverage-aware choice.
    """
    resources_tuple = tuple(resources)
    resource_ids = [resource.resource_id for resource in resources_tuple]
    if len(resource_ids) != len(set(resource_ids)):
        raise ValueError("Baseline resources must have unique IDs")
    requirements_tuple = _validated_requirements(requirements)

    routes: dict[str, TrafficAwareRouteResult | None] = {}
    routeable_by_requirement: dict[
        tuple[str, tuple[str, ...]], tuple[BaselineChoice, ...]
    ] = {}
    for requirement in requirements_tuple:
        choices: list[BaselineChoice] = []
        for resource in sorted(resources_tuple, key=lambda item: item.resource_id):
            if not _is_hard_eligible(resource, requirement, incident_id=incident_id):
                continue
            if resource.resource_id not in routes:
                try:
                    routes[resource.resource_id] = _compute_baseline_route(
                        graph,
                        resource.coordinate,
                        incident_coordinate,
                        traffic_snapshot,
                        include_alternatives=include_route_alternatives,
                    )
                except (RouteNotFoundError, RoutingPointOutsideGraphError, ValueError):
                    routes[resource.resource_id] = None
            route = routes[resource.resource_id]
            if route is not None:
                choices.append(
                    BaselineChoice(
                        requirement=requirement,
                        resource=resource,
                        route=route,
                    )
                )
        routeable_by_requirement[_requirement_key(requirement)] = tuple(
            sorted(
                choices,
                key=lambda choice: (
                    choice.route.effective_eta,
                    choice.route.distance_m,
                    choice.resource.resource_id,
                ),
            )
        )

    ordered_requirements = sorted(
        requirements_tuple,
        key=lambda requirement: (
            len(routeable_by_requirement[_requirement_key(requirement)]),
            _requirement_key(requirement),
        ),
    )
    remaining_ids = {resource.resource_id for resource in resources_tuple}
    selected: list[BaselineChoice] = []
    for requirement in ordered_requirements:
        available = [
            choice
            for choice in routeable_by_requirement[_requirement_key(requirement)]
            if choice.resource.resource_id in remaining_ids
        ]
        if len(available) < requirement.minimum_count:
            raise BaselineInsufficientResourcesError(
                "INSUFFICIENT_RESOURCES: greedy baseline cannot satisfy "
                f"{requirement.resource_type.value}"
            )
        chosen = available[: requirement.minimum_count]
        selected.extend(chosen)
        remaining_ids.difference_update(choice.resource.resource_id for choice in chosen)

    return BaselineSelection(choices=tuple(selected))
