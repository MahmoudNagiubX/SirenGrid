from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import networkx as nx
import pytest

from app.candidate_evaluation import evaluate_candidate_combination
from app.candidate_generation import CandidateCombination, CandidateResource, CandidateResponder
from app.coverage import CoverageZone
from app.repositioning import (
    find_adjacent_staging_zones,
    select_reposition_proposal,
    simulate_repositioning,
)
from app.response_requirements import ResponseRequirement
from app.routing import compute_traffic_aware_route
from app.schemas import Coordinate, DataReality, ResourceStatus, ResourceType


def square(min_lon: float, max_lon: float) -> dict[str, object]:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_lon, 29.9995],
                [max_lon, 29.9995],
                [max_lon, 30.0005],
                [min_lon, 30.0005],
                [min_lon, 29.9995],
            ]
        ],
    }


def zone(zone_id: str, centroid_lon: float, min_lon: float, max_lon: float) -> CoverageZone:
    return CoverageZone(
        zone_id=zone_id,
        centroid=Coordinate(lat=30.0, lon=centroid_lon),
        population=100.0,
        geometry=square(min_lon, max_lon),
    )


def test_adjacent_staging_zones_use_only_valid_unique_immediate_neighbors() -> None:
    target = zone("zone-target", 31.305, 31.3045, 31.3055)
    west = zone("zone-west", 31.304, 31.3035, 31.3045)
    east = zone("zone-east", 31.306, 31.3055, 31.3065)
    duplicate_centroid = zone("zone-duplicate", 31.304, 31.3065, 31.3075)
    invalid = CoverageZone(
        zone_id="zone-invalid",
        centroid=Coordinate(lat=30.0, lon=31.308),
        population=100.0,
        geometry={"type": "Polygon", "coordinates": []},
    )

    adjacent = find_adjacent_staging_zones(
        (target, west, east, duplicate_centroid, invalid),
        "zone-target",
    )

    assert tuple(candidate.zone_id for candidate in adjacent) == ("zone-east",)
    assert all(candidate.zone_id != "zone-target" for candidate in adjacent)


def movement_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    nodes = {
        "amb-dispatch": 31.300,
        "fire-dispatch": 31.301,
        "fire-reserve": 31.303,
        "amb-reserve": 31.302,
        "zone-west": 31.304,
        "zone-target": 31.305,
        "zone-east": 31.306,
    }
    for node, lon in nodes.items():
        graph.add_node(node, x=lon, y=30.0)
    edges = (
        ("amb-dispatch", "zone-target", 100.0),
        ("fire-dispatch", "zone-target", 110.0),
        ("fire-reserve", "zone-target", 100.0),
        ("amb-reserve", "zone-west", 600.0),
        ("zone-west", "zone-target", 500.0),
    )
    for source, destination, travel_time in edges:
        graph.add_edge(
            source,
            destination,
            key="0",
            length=travel_time,
            travel_time=travel_time,
            base_travel_time_s=travel_time,
        )
    return graph


def resource(
    resource_id: str,
    resource_type: ResourceType,
    lon: float,
) -> CandidateResource:
    return CandidateResource(
        resource_id=resource_id,
        resource_type=resource_type,
        capability_tags=(),
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id=None,
        coordinate=Coordinate(lat=30.0, lon=lon),
        data_reality=DataReality.SIMULATED,
        source="phase03_simulated_resource",
    )


def proposal(
    *,
    coverage: float = 0.5,
    undercovered: int = 2,
    unreachable: int = 1,
    eta: float = 300.0,
    distance: float = 1000.0,
    target: str = "zone-b",
    staging: str = "stage-b",
    resource_id: str = "resource-b",
) -> SimpleNamespace:
    return SimpleNamespace(
        post_reposition_joint=SimpleNamespace(
            population_weighted_coverage=coverage,
            undercovered_zone_count=undercovered,
            unreachable_zone_count=unreachable,
        ),
        reposition_eta_seconds=eta,
        reposition_distance_m=distance,
        target_zone_id=target,
        staging_zone_id=staging,
        repositioned_resource_id=resource_id,
    )


@pytest.mark.parametrize(
    ("preferred", "other"),
    (
        (proposal(coverage=0.8), proposal(coverage=0.7)),
        (proposal(undercovered=1), proposal(undercovered=2)),
        (proposal(unreachable=0), proposal(unreachable=1)),
        (proposal(eta=200.0), proposal(eta=300.0)),
        (proposal(distance=900.0), proposal(distance=1000.0)),
        (
            proposal(target="zone-a", staging="stage-a", resource_id="resource-a"),
            proposal(target="zone-b", staging="stage-a", resource_id="resource-a"),
        ),
        (
            proposal(target="zone-a", staging="stage-a", resource_id="resource-a"),
            proposal(target="zone-a", staging="stage-b", resource_id="resource-a"),
        ),
        (
            proposal(target="zone-a", staging="stage-a", resource_id="resource-a"),
            proposal(target="zone-a", staging="stage-a", resource_id="resource-b"),
        ),
    ),
    ids=(
        "highest-coverage",
        "fewest-undercovered",
        "fewest-unreachable",
        "lowest-eta",
        "lowest-distance",
        "lexical-target",
        "lexical-staging",
        "lexical-resource",
    ),
)
def test_select_reposition_proposal_uses_pd018_priority(
    preferred: SimpleNamespace,
    other: SimpleNamespace,
) -> None:
    assert select_reposition_proposal((other, preferred)) is preferred


def test_reposition_is_hypothetical_targeted_and_improves_joint_coverage() -> None:
    graph = movement_graph()
    zones = (
        zone("zone-west", 31.304, 31.3035, 31.3045),
        zone("zone-target", 31.305, 31.3045, 31.3055),
        zone("zone-east", 31.306, 31.3055, 31.3065),
    )
    resources = (
        resource("amb-dispatch", ResourceType.AMBULANCE, 31.300),
        resource("fire-dispatch", ResourceType.FIRE_RESCUE, 31.301),
        resource("amb-reserve", ResourceType.AMBULANCE, 31.302),
        resource("fire-reserve", ResourceType.FIRE_RESCUE, 31.303),
    )
    requirements = (
        ResponseRequirement(ResourceType.AMBULANCE, 1),
        ResponseRequirement(ResourceType.FIRE_RESCUE, 1),
    )
    target_coordinate = Coordinate(lat=30.0, lon=31.305)
    responders = tuple(
        CandidateResponder(
            requirement=requirement,
            resource=selected,
            route=compute_traffic_aware_route(
                graph,
                selected.coordinate,
                target_coordinate,
                None,
            ),
        )
        for requirement, selected in (
            (requirements[0], resources[0]),
            (requirements[1], resources[1]),
        )
    )
    candidate = evaluate_candidate_combination(
        graph=graph,
        zones=zones,
        resources=resources,
        requirements=requirements,
        combination=CandidateCombination(responders),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    original_resources = deepcopy(resources)
    original_edges = deepcopy(list(graph.edges(data=True, keys=True)))

    result = simulate_repositioning(
        graph=graph,
        zones=zones,
        resources=resources,
        requirements=requirements,
        candidate=candidate,
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert result.triggered is True
    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    assert proposal.target_zone_id == "zone-target"
    assert proposal.staging_zone_id == "zone-west"
    assert proposal.staging_data_reality is DataReality.SIMULATED
    assert proposal.failing_cohort_ids == ("AMBULANCE",)
    assert proposal.repositioned_resource_id == "amb-reserve"
    assert proposal.reposition_eta_seconds == 600.0
    assert proposal.post_reposition_joint.population_weighted_coverage > (
        proposal.pre_reposition_joint.population_weighted_coverage
    )
    assert len(proposal.post_reposition_cohort_snapshots) == 2
    assert proposal.target_improved is True
    target_after = next(
        item for item in proposal.post_reposition_joint.zones if item.zone_id == "zone-target"
    )
    assert target_after.covered is True
    assert resources == original_resources
    assert list(graph.edges(data=True, keys=True)) == original_edges


def test_reposition_eta_above_prototype_target_is_rejected() -> None:
    graph = movement_graph()
    graph["amb-reserve"]["zone-west"]["0"]["travel_time"] = 601.0
    graph["amb-reserve"]["zone-west"]["0"]["base_travel_time_s"] = 601.0
    zones = (
        zone("zone-west", 31.304, 31.3035, 31.3045),
        zone("zone-target", 31.305, 31.3045, 31.3055),
        zone("zone-east", 31.306, 31.3055, 31.3065),
    )
    resources = (
        resource("amb-dispatch", ResourceType.AMBULANCE, 31.300),
        resource("fire-dispatch", ResourceType.FIRE_RESCUE, 31.301),
        resource("amb-reserve", ResourceType.AMBULANCE, 31.302),
        resource("fire-reserve", ResourceType.FIRE_RESCUE, 31.303),
    )
    requirements = (
        ResponseRequirement(ResourceType.AMBULANCE, 1),
        ResponseRequirement(ResourceType.FIRE_RESCUE, 1),
    )
    target_coordinate = Coordinate(lat=30.0, lon=31.305)
    candidate = evaluate_candidate_combination(
        graph=graph,
        zones=zones,
        resources=resources,
        requirements=requirements,
        combination=CandidateCombination(
            tuple(
                CandidateResponder(
                    requirement=requirement,
                    resource=selected,
                    route=compute_traffic_aware_route(
                        graph, selected.coordinate, target_coordinate, None
                    ),
                )
                for requirement, selected in (
                    (requirements[0], resources[0]),
                    (requirements[1], resources[1]),
                )
            )
        ),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    result = simulate_repositioning(
        graph=graph,
        zones=zones,
        resources=resources,
        requirements=requirements,
        candidate=candidate,
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert result.triggered is True
    assert result.proposals == ()


def test_coverage_drop_trigger_uses_inclusive_approved_boundary() -> None:
    graph = movement_graph()
    zones = (
        zone("zone-west", 31.304, 31.3035, 31.3045),
        zone("zone-target", 31.305, 31.3045, 31.3055),
        zone("zone-east", 31.306, 31.3055, 31.3065),
    )
    resources = (
        resource("amb-dispatch", ResourceType.AMBULANCE, 31.300),
        resource("fire-dispatch", ResourceType.FIRE_RESCUE, 31.301),
        resource("amb-reserve", ResourceType.AMBULANCE, 31.302),
        resource("fire-reserve", ResourceType.FIRE_RESCUE, 31.303),
    )
    requirements = (
        ResponseRequirement(ResourceType.AMBULANCE, 1),
        ResponseRequirement(ResourceType.FIRE_RESCUE, 1),
    )
    target_coordinate = Coordinate(lat=30.0, lon=31.305)
    candidate = evaluate_candidate_combination(
        graph=graph,
        zones=zones,
        resources=resources,
        requirements=requirements,
        combination=CandidateCombination(
            tuple(
                CandidateResponder(
                    requirement=requirement,
                    resource=selected,
                    route=compute_traffic_aware_route(
                        graph, selected.coordinate, target_coordinate, None
                    ),
                )
                for requirement, selected in (
                    (requirements[0], resources[0]),
                    (requirements[1], resources[1]),
                )
            )
        ),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    candidate = replace(
        candidate,
        metrics=replace(
            candidate.metrics,
            coverage_delta=-0.05,
            newly_undercovered_zone_ids=(),
        ),
    )

    result = simulate_repositioning(
        graph=graph,
        zones=zones,
        resources=resources,
        requirements=requirements,
        candidate=candidate,
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert result.triggered is True
    assert result.trigger_reasons == ("POPULATION_COVERAGE_DROP",)
    assert result.target_zone_ids == ()
    assert result.proposals == ()
