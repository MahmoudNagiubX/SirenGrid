from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

import networkx as nx
import pytest

from app.candidate_evaluation import (
    evaluate_candidate_combination,
    rank_evaluated_candidates,
)
from app.candidate_generation import (
    CandidateCombination,
    CandidateResource,
    CandidateResponder,
)
from app.coverage import CoverageZone
from app.response_requirements import ResponseRequirement
from app.routing import TrafficAwareRouteResult
from app.schemas import Coordinate, DataReality, ResourceStatus, ResourceType


def _route(eta_seconds: float) -> TrafficAwareRouteResult:
    return TrafficAwareRouteResult(
        base_nodes=["origin", "incident"],
        nodes=["origin", "incident"],
        edge_keys=[("origin", "incident", "0")],
        geometry={
            "type": "LineString",
            "coordinates": [[31.3, 30.0], [31.31, 30.0]],
        },
        distance_m=1000.0,
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


def test_candidate_evaluation_uses_joint_coverage_for_reproducible_score_without_mutation() -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("ambulance", x=31.3000, y=30.0000)
    graph.add_node("fire", x=31.3200, y=30.0000)
    graph.add_node("zone", x=31.3100, y=30.0000)
    graph.add_edge("ambulance", "zone", key="0", length=1000.0, travel_time=120.0, base_travel_time_s=120.0)
    graph.add_edge("fire", "zone", key="0", length=1000.0, travel_time=180.0, base_travel_time_s=180.0)
    ambulance_requirement = ResponseRequirement(ResourceType.AMBULANCE, 1)
    fire_requirement = ResponseRequirement(ResourceType.FIRE_RESCUE, 1)
    ambulance = CandidateResource(
        resource_id="amb-1",
        resource_type=ResourceType.AMBULANCE,
        capability_tags=(),
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id=None,
        coordinate=Coordinate(lat=30.0, lon=31.3),
        data_reality=DataReality.SIMULATED,
        source="phase03_simulated_resource",
    )
    fire = CandidateResource(
        resource_id="fire-1",
        resource_type=ResourceType.FIRE_RESCUE,
        capability_tags=(),
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id=None,
        coordinate=Coordinate(lat=30.0, lon=31.32),
        data_reality=DataReality.SIMULATED,
        source="phase03_simulated_resource",
    )
    resources = [ambulance, fire]
    combination = CandidateCombination(
        responders=(
            CandidateResponder(ambulance_requirement, ambulance, _route(120.0)),
            CandidateResponder(fire_requirement, fire, _route(180.0)),
        )
    )
    original_resources = deepcopy(resources)
    original_graph = deepcopy(list(graph.edges(data=True, keys=True)))

    evaluated = evaluate_candidate_combination(
        graph=graph,
        zones=(
            CoverageZone(
                zone_id="zone",
                centroid=Coordinate(lat=30.0, lon=31.31),
                population=100.0,
            ),
        ),
        resources=resources,
        requirements=(ambulance_requirement, fire_requirement),
        combination=combination,
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert len(evaluated.metrics.cohort_impacts) == 2
    assert evaluated.metrics.baseline_joint.population_weighted_coverage == 1.0
    assert evaluated.metrics.post_dispatch_joint.population_weighted_coverage == 0.0
    assert evaluated.metrics.coverage_delta == -1.0
    assert evaluated.metrics.newly_undercovered_zone_ids == ("zone",)
    assert evaluated.metrics.post_dispatch_joint.zones[0].failing_cohort_ids == (
        "AMBULANCE",
        "FIRE_RESCUE",
    )
    assert evaluated.score.policy_version == "SIRENGRID_PROTOTYPE_PLAN_SCORE_V1"
    assert evaluated.score.normalized_eta_term == pytest.approx(0.3)
    assert evaluated.score.coverage_penalty == 1.0
    assert evaluated.score.reserve_penalty == 1.0
    assert evaluated.score.reposition_penalty == 0.0
    assert evaluated.score.hospital_penalty == 0.0
    assert evaluated.score.final_score == pytest.approx(0.705)

    over_target = evaluate_candidate_combination(
        graph=graph,
        zones=(
            CoverageZone(
                zone_id="zone",
                centroid=Coordinate(lat=30.0, lon=31.31),
                population=100.0,
            ),
        ),
        resources=resources,
        requirements=(ambulance_requirement, fire_requirement),
        combination=replace(
            combination,
            responders=(
                CandidateResponder(ambulance_requirement, ambulance, _route(720.0)),
                CandidateResponder(fire_requirement, fire, _route(180.0)),
            ),
        ),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    assert over_target.score.normalized_eta_term == pytest.approx(1.2)
    assert resources == original_resources
    assert list(graph.edges(data=True, keys=True)) == original_graph


def test_candidate_ranking_uses_locked_score_then_deterministic_tie_breakers() -> None:
    # Ranking is intentionally tested from constructed evaluation facts so it
    # remains independent of routing and coverage calculation internals.
    requirement = ResponseRequirement(ResourceType.AMBULANCE, 1)
    resource = CandidateResource(
        resource_id="amb-base",
        resource_type=ResourceType.AMBULANCE,
        capability_tags=(),
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id=None,
        coordinate=Coordinate(lat=30.0, lon=31.3),
        data_reality=DataReality.SIMULATED,
        source="phase03_simulated_resource",
    )
    responder = CandidateResponder(requirement, resource, _route(100.0))
    graph = nx.MultiDiGraph()
    graph.add_node("origin", x=31.3, y=30.0)
    graph.add_node("zone", x=31.31, y=30.0)
    graph.add_edge("origin", "zone", key="0", length=1000.0, travel_time=100.0, base_travel_time_s=100.0)
    evaluated = evaluate_candidate_combination(
        graph=graph,
        zones=(CoverageZone("zone", Coordinate(lat=30.0, lon=31.31), 1.0),),
        resources=(resource,),
        requirements=(requirement,),
        combination=CandidateCombination((responder,)),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    lower_eta = replace(
        evaluated,
        metrics=replace(evaluated.metrics, max_incident_eta_seconds=90.0),
        score=replace(evaluated.score, final_score=1.0),
    )
    higher_eta = replace(
        evaluated,
        metrics=replace(evaluated.metrics, max_incident_eta_seconds=100.0),
        score=replace(evaluated.score, final_score=1.0),
    )

    assert rank_evaluated_candidates((higher_eta, lower_eta)) == (
        lower_eta,
        higher_eta,
    )
