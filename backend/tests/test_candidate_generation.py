from __future__ import annotations

from copy import deepcopy

import networkx as nx
import pytest

from app.candidate_generation import (
    MAX_CANDIDATES_PER_COHORT,
    MAX_FEASIBLE_CANDIDATE_COMBINATIONS,
    CandidateResource,
    generate_candidate_combinations,
)
from app.response_requirements import ResponseRequirement
from app.routing import RouteNotFoundError, TrafficAwareRouteResult
from app.schemas import Coordinate, DataReality, ResourceStatus, ResourceType


def _resource(
    resource_id: str,
    resource_type: ResourceType,
    route_key: int,
    *,
    capability_tags: tuple[str, ...] = (),
    status: ResourceStatus = ResourceStatus.AVAILABLE,
    assigned_incident_id: str | None = None,
) -> CandidateResource:
    return CandidateResource(
        resource_id=resource_id,
        resource_type=resource_type,
        capability_tags=capability_tags,
        status=status,
        assigned_incident_id=assigned_incident_id,
        coordinate=Coordinate(lat=30.0 + route_key / 10_000, lon=31.3),
        data_reality=DataReality.SIMULATED,
        source="phase03_simulated_resource",
    )


def _route(eta_seconds: float, distance_m: float) -> TrafficAwareRouteResult:
    return TrafficAwareRouteResult(
        base_nodes=["origin", "destination"],
        nodes=["origin", "destination"],
        edge_keys=[("origin", "destination", "0")],
        geometry={
            "type": "LineString",
            "coordinates": [[31.3, 30.0], [31.31, 30.01]],
        },
        distance_m=distance_m,
        eta_seconds=eta_seconds,
        base_eta=eta_seconds,
        effective_eta=eta_seconds,
        traffic_selected_path_base_eta=eta_seconds,
        origin_snap_distance_m=1.0,
        destination_snap_distance_m=1.0,
        matched_traversed_edge_count=0,
        total_traversed_edge_count=1,
        traffic_coverage_ratio=0.0,
        traffic_fallback_reason="TOMTOM_SNAPSHOT_UNAVAILABLE",
    )


def test_candidate_generation_applies_hard_constraints_top_five_and_deterministic_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = nx.MultiDiGraph()
    route_facts = {
        1: (100.0, 1000.0),
        2: (100.0, 900.0),
        3: (100.0, 900.0),
        4: (110.0, 800.0),
        5: (120.0, 700.0),
        6: (130.0, 600.0),
        10: (80.0, 1000.0),
        11: (90.0, 900.0),
        12: (100.0, 800.0),
        13: (110.0, 700.0),
        14: (120.0, 600.0),
    }

    def fake_route(
        _graph: nx.Graph,
        origin: Coordinate,
        _destination: Coordinate,
        _snapshot: object,
        **_kwargs: object,
    ) -> TrafficAwareRouteResult:
        route_key = round((origin.lat - 30.0) * 10_000)
        if route_key == 99:
            raise RouteNotFoundError("no route")
        eta_seconds, distance_m = route_facts[route_key]
        return _route(eta_seconds, distance_m)

    monkeypatch.setattr("app.candidate_generation.compute_traffic_aware_route", fake_route)
    resources = [
        _resource("amb-a", ResourceType.AMBULANCE, 1, capability_tags=("als",)),
        _resource("amb-b", ResourceType.AMBULANCE, 2, capability_tags=("als",)),
        _resource("amb-c", ResourceType.AMBULANCE, 3, capability_tags=("als",)),
        _resource("amb-d", ResourceType.AMBULANCE, 4, capability_tags=("als",)),
        _resource("amb-e", ResourceType.AMBULANCE, 5, capability_tags=("als",)),
        _resource("amb-slow", ResourceType.AMBULANCE, 6, capability_tags=("als",)),
        _resource("amb-unavailable", ResourceType.AMBULANCE, 1, capability_tags=("als",), status=ResourceStatus.OUT_OF_SERVICE),
        _resource("amb-committed", ResourceType.AMBULANCE, 1, capability_tags=("als",), assigned_incident_id="other-incident"),
        _resource("amb-incompatible", ResourceType.AMBULANCE, 1, capability_tags=("bls",)),
        _resource("amb-unroutable", ResourceType.AMBULANCE, 99, capability_tags=("als",)),
        *[
            _resource(f"fire-{key}", ResourceType.FIRE_RESCUE, key)
            for key in (10, 11, 12, 13, 14)
        ],
    ]
    original_resources = deepcopy(resources)
    requirements = (
        ResponseRequirement(ResourceType.AMBULANCE, 3, ("als",)),
        ResponseRequirement(ResourceType.FIRE_RESCUE, 2),
    )

    result = generate_candidate_combinations(
        graph=graph,
        incident_coordinate=Coordinate(lat=30.01, lon=31.31),
        resources=resources,
        requirements=requirements,
        traffic_snapshot=None,
    )
    reversed_result = generate_candidate_combinations(
        graph=graph,
        incident_coordinate=Coordinate(lat=30.01, lon=31.31),
        resources=reversed(resources),
        requirements=reversed(requirements),
        traffic_snapshot=None,
    )

    assert MAX_CANDIDATES_PER_COHORT == 5
    assert MAX_FEASIBLE_CANDIDATE_COMBINATIONS == 50
    ambulance_pool = next(
        pool for pool in result.candidate_pools
        if pool.requirement.resource_type is ResourceType.AMBULANCE
    )
    assert [candidate.resource.resource_id for candidate in ambulance_pool.responders] == [
        "amb-b",
        "amb-c",
        "amb-a",
        "amb-d",
        "amb-e",
    ]
    assert len(result.combinations) == MAX_FEASIBLE_CANDIDATE_COMBINATIONS
    assert all(
        len(combination.resource_ids) == len(set(combination.resource_ids))
        for combination in result.combinations
    )
    selected_ids = {
        resource_id
        for combination in result.combinations
        for resource_id in combination.resource_ids
    }
    assert not {
        "amb-slow",
        "amb-unavailable",
        "amb-committed",
        "amb-incompatible",
        "amb-unroutable",
    } & selected_ids
    assert [combo.resource_ids for combo in result.combinations] == [
        combo.resource_ids for combo in reversed_result.combinations
    ]
    assert resources == original_resources


def test_candidate_generation_requests_skip_route_alternatives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidate generation must request include_alternatives=False."""
    from app import candidate_generation

    called_kwargs: list[dict[str, object]] = []
    original_compute = candidate_generation.compute_traffic_aware_route

    def spy_compute(*args: object, **kwargs: object):
        called_kwargs.append(kwargs)
        return original_compute(*args, **kwargs)

    monkeypatch.setattr(candidate_generation, "compute_traffic_aware_route", spy_compute)

    graph = nx.MultiDiGraph()
    graph.add_node("res", x=31.300, y=30.000)
    graph.add_node("inc", x=31.310, y=30.010)
    graph.add_edge("res", "inc", key="0", length=100.0, travel_time=10.0, base_travel_time_s=10.0)

    resource = CandidateResource(
        resource_id="amb-1",
        resource_type=ResourceType.AMBULANCE,
        capability_tags=("als",),
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id=None,
        coordinate=Coordinate(lat=30.000, lon=31.300),
        data_reality=DataReality.SIMULATED,
        source="phase03_simulated_resource",
    )
    requirements = (
        ResponseRequirement(ResourceType.AMBULANCE, 1, ("als",)),
    )
    incident_coord = Coordinate(lat=30.010, lon=31.310)

    candidate_generation.generate_candidate_combinations(
        graph=graph,
        incident_coordinate=incident_coord,
        resources=[resource],
        requirements=requirements,
        traffic_snapshot=None,
    )
    assert len(called_kwargs) > 0
    for kw in called_kwargs:
        assert kw.get("include_alternatives") is False
