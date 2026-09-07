"""Transparent Phase 04 candidate metrics and prototype scoring."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable

import networkx as nx

from app.candidate_generation import CandidateCombination, CandidateResource
from app.config import settings
from app.coverage import (
    CoverageCohort,
    CoverageResource,
    CoverageZone,
    DispatchImpactSimulation,
    JointCoverageSnapshot,
    derive_joint_coverage_snapshot,
    simulate_dispatch_impact,
)
from app.response_requirements import ResponseRequirement
from app.traffic.models import TrafficSnapshot


SCORE_POLICY_VERSION = "SIRENGRID_PROTOTYPE_PLAN_SCORE_V1"
SCORE_CONVENTION = "LOWER_IS_BETTER"


@dataclass(frozen=True)
class CandidateMetrics:
    cohort_impacts: tuple[DispatchImpactSimulation, ...]
    baseline_joint: JointCoverageSnapshot
    post_dispatch_joint: JointCoverageSnapshot
    max_incident_eta_seconds: float
    responder_arrival_spread_seconds: float
    coverage_delta: float
    affected_zone_ids: tuple[str, ...]
    newly_undercovered_zone_ids: tuple[str, ...]
    reserve_resource_ids_by_cohort: tuple[tuple[str, tuple[str, ...]], ...]
    reserve_exhausted_cohort_ids: tuple[str, ...]


@dataclass(frozen=True)
class CandidateScoreBreakdown:
    policy_version: str
    convention: str
    max_incident_eta_seconds: float
    post_dispatch_joint_population_weighted_coverage: float
    remaining_reserve_exhausted: bool
    proposed_reposition_eta_seconds: float | None
    normalized_eta_term: float
    coverage_penalty: float
    reserve_penalty: float
    reposition_penalty: float
    hospital_penalty: float
    weights: dict[str, float]
    weighted_terms: dict[str, float]
    final_score: float


@dataclass(frozen=True)
class EvaluatedCandidate:
    combination: CandidateCombination
    metrics: CandidateMetrics
    score: CandidateScoreBreakdown


def rescore_candidate_for_reposition(
    candidate: EvaluatedCandidate,
    proposed_reposition_eta_seconds: float,
) -> EvaluatedCandidate:
    return replace(
        candidate,
        score=_score(candidate.metrics, proposed_reposition_eta_seconds),
    )


def _coverage_resources(
    resources: Iterable[CandidateResource],
) -> tuple[CoverageResource, ...]:
    return tuple(
        CoverageResource(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            capability_tags=resource.capability_tags,
            status=resource.status,
            coordinate=resource.coordinate,
            data_reality=resource.data_reality,
            source=resource.source,
            assigned_incident_id=resource.assigned_incident_id,
        )
        for resource in resources
    )


def _validate_combination(
    requirements: tuple[ResponseRequirement, ...],
    combination: CandidateCombination,
    resource_ids: set[str],
) -> dict[tuple[object, tuple[str, ...]], tuple[str, ...]]:
    requirement_keys = {requirement.cohort_key for requirement in requirements}
    grouped: dict[tuple[object, tuple[str, ...]], list[str]] = {
        requirement.cohort_key: [] for requirement in requirements
    }
    selected_ids: set[str] = set()
    for responder in combination.responders:
        if responder.requirement.cohort_key not in requirement_keys:
            raise ValueError("Candidate responder has a requirement outside this evaluation")
        if responder.resource.resource_id not in resource_ids:
            raise ValueError("Candidate responder is not in the captured resource set")
        if responder.resource.resource_id in selected_ids:
            raise ValueError("Candidate may not dispatch one physical resource twice")
        selected_ids.add(responder.resource.resource_id)
        grouped[responder.requirement.cohort_key].append(responder.resource.resource_id)
    dispatched_by_requirement: dict[tuple[object, tuple[str, ...]], tuple[str, ...]] = {}
    for requirement in requirements:
        selected = tuple(sorted(grouped[requirement.cohort_key]))
        if len(selected) != requirement.minimum_count:
            raise ValueError("Candidate does not satisfy every required resource count")
        dispatched_by_requirement[requirement.cohort_key] = selected
    return dispatched_by_requirement


def _score(
    metrics: CandidateMetrics,
    proposed_reposition_eta_seconds: float | None = None,
) -> CandidateScoreBreakdown:
    if proposed_reposition_eta_seconds is not None and proposed_reposition_eta_seconds < 0:
        raise ValueError("Proposed reposition ETA must be non-negative")
    target = settings.PROTOTYPE_TARGET_RESPONSE_TIME_SECONDS
    weights = settings.PROTOTYPE_SCORE_WEIGHTS
    normalized_eta = metrics.max_incident_eta_seconds / target
    coverage_penalty = 1 - metrics.post_dispatch_joint.population_weighted_coverage
    reserve_penalty = 1.0 if metrics.reserve_exhausted_cohort_ids else 0.0
    reposition_penalty = (
        proposed_reposition_eta_seconds / target
        if proposed_reposition_eta_seconds is not None
        else 0.0
    )
    hospital_penalty = 0.0
    weighted_terms = {
        "eta": weights["eta"] * normalized_eta,
        "coverage": weights["coverage"] * coverage_penalty,
        "reserve": weights["reserve"] * reserve_penalty,
        "reposition": weights["reposition"] * reposition_penalty,
        "hospital": weights["hospital"] * hospital_penalty,
    }
    return CandidateScoreBreakdown(
        policy_version=SCORE_POLICY_VERSION,
        convention=SCORE_CONVENTION,
        max_incident_eta_seconds=metrics.max_incident_eta_seconds,
        post_dispatch_joint_population_weighted_coverage=(
            metrics.post_dispatch_joint.population_weighted_coverage
        ),
        remaining_reserve_exhausted=bool(metrics.reserve_exhausted_cohort_ids),
        proposed_reposition_eta_seconds=proposed_reposition_eta_seconds,
        normalized_eta_term=normalized_eta,
        coverage_penalty=coverage_penalty,
        reserve_penalty=reserve_penalty,
        reposition_penalty=reposition_penalty,
        hospital_penalty=hospital_penalty,
        weights=weights,
        weighted_terms=weighted_terms,
        final_score=sum(weighted_terms.values()),
    )


def evaluate_candidate_combination(
    *,
    graph: nx.Graph,
    zones: Iterable[CoverageZone],
    resources: Iterable[CandidateResource],
    requirements: Iterable[ResponseRequirement],
    combination: CandidateCombination,
    traffic_snapshot: TrafficSnapshot | None,
    modeled_at: datetime,
) -> EvaluatedCandidate:
    """Evaluate one hypothetical combination without mutating operations state."""
    resources_tuple = tuple(resources)
    requirements_tuple = tuple(
        sorted(requirements, key=lambda requirement: requirement.cohort_key)
    )
    if not requirements_tuple:
        raise ValueError("At least one response requirement is required")
    resource_ids = {resource.resource_id for resource in resources_tuple}
    dispatched_by_requirement = _validate_combination(
        requirements_tuple, combination, resource_ids
    )
    coverage_resources = _coverage_resources(resources_tuple)
    zones_tuple = tuple(zones)
    impacts: list[DispatchImpactSimulation] = []
    for requirement in requirements_tuple:
        cohort = CoverageCohort(
            resource_type=requirement.resource_type,
            required_capability_tags=requirement.required_capability_tags,
        )
        impacts.append(
            simulate_dispatch_impact(
                graph=graph,
                zones=zones_tuple,
                resources=coverage_resources,
                cohort=cohort,
                dispatched_resource_ids=dispatched_by_requirement[requirement.cohort_key],
                traffic_snapshot=traffic_snapshot,
                modeled_at=modeled_at,
            )
        )
    baseline_joint = derive_joint_coverage_snapshot(
        impact.baseline for impact in impacts
    )
    post_dispatch_joint = derive_joint_coverage_snapshot(
        impact.post_dispatch for impact in impacts
    )
    baseline_by_zone = {zone.zone_id: zone for zone in baseline_joint.zones}
    post_by_zone = {zone.zone_id: zone for zone in post_dispatch_joint.zones}
    affected_zone_ids = tuple(
        zone_id
        for zone_id in sorted(baseline_by_zone)
        if baseline_by_zone[zone_id].eta_seconds != post_by_zone[zone_id].eta_seconds
    )
    newly_undercovered_zone_ids = tuple(
        zone_id
        for zone_id in sorted(baseline_by_zone)
        if baseline_by_zone[zone_id].covered and not post_by_zone[zone_id].covered
    )
    reserve_by_cohort = tuple(
        (impact.cohort.cohort_id, impact.remaining_reserve_resource_ids)
        for impact in impacts
    )
    reserve_exhausted = tuple(
        cohort_id for cohort_id, resource_ids in reserve_by_cohort if not resource_ids
    )
    arrival_etas = [responder.route.effective_eta for responder in combination.responders]
    if not arrival_etas:
        raise ValueError("Candidate must contain at least one responder")
    metrics = CandidateMetrics(
        cohort_impacts=tuple(impacts),
        baseline_joint=baseline_joint,
        post_dispatch_joint=post_dispatch_joint,
        max_incident_eta_seconds=max(arrival_etas),
        responder_arrival_spread_seconds=max(arrival_etas) - min(arrival_etas),
        coverage_delta=(
            post_dispatch_joint.population_weighted_coverage
            - baseline_joint.population_weighted_coverage
        ),
        affected_zone_ids=affected_zone_ids,
        newly_undercovered_zone_ids=newly_undercovered_zone_ids,
        reserve_resource_ids_by_cohort=reserve_by_cohort,
        reserve_exhausted_cohort_ids=reserve_exhausted,
    )
    return EvaluatedCandidate(
        combination=combination,
        metrics=metrics,
        score=_score(metrics),
    )


def rank_evaluated_candidates(
    candidates: Iterable[EvaluatedCandidate],
) -> tuple[EvaluatedCandidate, ...]:
    """Rank candidates by the approved transparent score and tie order."""
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.score.final_score,
                candidate.metrics.max_incident_eta_seconds,
                -candidate.metrics.post_dispatch_joint.population_weighted_coverage,
                candidate.score.proposed_reposition_eta_seconds is not None,
                candidate.combination.resource_ids,
            ),
        )
    )
