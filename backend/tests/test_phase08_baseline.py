from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import pytest

from app.benchmark_baseline import (
    BaselineInsufficientResourcesError,
    choose_greedy_baseline_resources,
)
from app.candidate_generation import CandidateResource
from app.response_requirements import ResponseRequirement
from app.routing import TrafficAwareRouteResult
from app.schemas import Coordinate, DataReality, ResourceStatus, ResourceType


def _resource(
    resource_id: str,
    *,
    resource_type: ResourceType = ResourceType.AMBULANCE,
    capability_tags: tuple[str, ...] = (),
    status: ResourceStatus = ResourceStatus.AVAILABLE,
    lon: float = 31.3,
) -> CandidateResource:
    return CandidateResource(
        resource_id=resource_id,
        resource_type=resource_type,
        capability_tags=capability_tags,
        status=status,
        assigned_incident_id=None,
        coordinate=Coordinate(lat=30.0, lon=lon),
        data_reality=DataReality.SIMULATED,
        source="phase08_test_fixture",
    )


def _route(eta: float, distance: float) -> TrafficAwareRouteResult:
    return TrafficAwareRouteResult(
        base_nodes=["origin", "incident"],
        nodes=["origin", "incident"],
        edge_keys=[("origin", "incident", "0")],
        geometry={
            "type": "LineString",
            "coordinates": [[31.3, 30.0], [31.31, 30.0]],
        },
        distance_m=distance,
        eta_seconds=eta,
        base_eta=eta,
        effective_eta=eta,
        traffic_selected_path_base_eta=eta,
        origin_snap_distance_m=0.0,
        destination_snap_distance_m=0.0,
        matched_traversed_edge_count=0,
        total_traversed_edge_count=1,
        traffic_coverage_ratio=0.0,
        traffic_fallback_reason="FIXED_PHASE08_FIXTURE",
    )


@dataclass(frozen=True)
class _RouteKey:
    eta: float
    distance: float


def test_baseline_processes_most_constrained_cohort_before_greedy_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = nx.MultiDiGraph()
    general = ResponseRequirement(ResourceType.AMBULANCE, 1)
    advanced = ResponseRequirement(ResourceType.AMBULANCE, 1, required_capability_tags=("ADVANCED",))
    resources = (
        _resource("amb-advanced", capability_tags=("ADVANCED",), lon=31.3),
        _resource("amb-general", lon=31.301),
    )
    routes = {
        "amb-advanced": _RouteKey(eta=10.0, distance=100.0),
        "amb-general": _RouteKey(eta=20.0, distance=200.0),
    }

    monkeypatch.setattr(
        "app.benchmark_baseline.compute_traffic_aware_route",
        lambda _graph, resource_coordinate, _incident_coordinate, _snapshot: _route(
            routes["amb-advanced"].eta
            if resource_coordinate == resources[0].coordinate
            else routes["amb-general"].eta,
            routes["amb-advanced"].distance
            if resource_coordinate == resources[0].coordinate
            else routes["amb-general"].distance,
        ),
    )

    result = choose_greedy_baseline_resources(
        graph=graph,
        incident_coordinate=Coordinate(lat=30.0, lon=31.31),
        resources=resources,
        requirements=(general, advanced),
        traffic_snapshot=None,
    )

    assert result.resource_ids == ("amb-advanced", "amb-general")
    assert [choice.requirement.required_capability_tags for choice in result.choices] == [
        ("ADVANCED",),
        (),
    ]


def test_baseline_uses_eta_distance_id_order_and_excludes_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = nx.MultiDiGraph()
    requirement = ResponseRequirement(ResourceType.AMBULANCE, 1)
    resources = (
        _resource("amb-z", lon=31.3),
        _resource("amb-a", lon=31.301),
        _resource("amb-fast", status=ResourceStatus.OUT_OF_SERVICE),
    )
    route_by_id = {
        "amb-z": _RouteKey(eta=30.0, distance=100.0),
        "amb-a": _RouteKey(eta=30.0, distance=100.0),
    }

    def fake_route(_graph, resource_coordinate, _incident_coordinate, _snapshot):
        resource_id = "amb-z" if resource_coordinate == resources[0].coordinate else "amb-a"
        route = route_by_id[resource_id]
        return _route(route.eta, route.distance)

    monkeypatch.setattr("app.benchmark_baseline.compute_traffic_aware_route", fake_route)

    result = choose_greedy_baseline_resources(
        graph=graph,
        incident_coordinate=Coordinate(lat=30.0, lon=31.31),
        resources=resources,
        requirements=(requirement,),
        traffic_snapshot=None,
    )

    assert result.resource_ids == ("amb-a",)
    assert result.choices[0].route.effective_eta == 30.0


def test_baseline_reports_insufficient_resources_without_backtracking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = nx.MultiDiGraph()
    general = ResponseRequirement(ResourceType.AMBULANCE, 1)
    advanced = ResponseRequirement(ResourceType.AMBULANCE, 1, required_capability_tags=("ADVANCED",))
    resources = (_resource("amb-advanced", capability_tags=("ADVANCED",)),)
    monkeypatch.setattr(
        "app.benchmark_baseline.compute_traffic_aware_route",
        lambda *_args: _route(10.0, 100.0),
    )

    with pytest.raises(BaselineInsufficientResourcesError, match="INSUFFICIENT_RESOURCES"):
        choose_greedy_baseline_resources(
            graph=graph,
            incident_coordinate=Coordinate(lat=30.0, lon=31.31),
            resources=resources,
            requirements=(general, advanced),
            traffic_snapshot=None,
        )
