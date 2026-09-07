"""Persistence of transparent Phase 04 candidate sets.

Candidate evaluation is deliberately separate from persistence.  This module
stores the already-ranked facts it receives and does not recalculate scores or
choose a different candidate order.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.candidate_evaluation import EvaluatedCandidate
from app.models import Incident, ReplanEvaluation, ResponsePlan, TimelineEvent
from app.schemas import IncidentStatus, ResponsePlanStatus

__all__ = ["persist_candidate_set", "persist_replacement_candidate_set"]


def _json_safe(value: Any) -> Any:
    """Convert model/dataclass values into values accepted by SQLAlchemy JSON."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_json_safe(item) for item in value]
    return value


def _route_record(candidate: EvaluatedCandidate) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for responder in candidate.combination.responders:
        route = _json_safe(responder.route.to_dict())
        route.update(
            {
                "resource_id": responder.resource.resource_id,
                "resource_type": responder.resource.resource_type.value,
                "origin": _json_safe(responder.resource.coordinate),
                "data_reality": responder.resource.data_reality.value,
                "source": responder.resource.source,
            }
        )
        records.append(route)
    return records


def _phase04_metrics(
    candidate: EvaluatedCandidate,
    *,
    candidate_set_id: str,
    candidate_rank: int,
    candidate_count: int,
    reposition_proposal: Any | None,
    requirements_metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    metrics = candidate.metrics
    baseline_by_cohort = [impact.baseline for impact in metrics.cohort_impacts]
    post_dispatch_by_cohort = [impact.post_dispatch for impact in metrics.cohort_impacts]
    representative = metrics.baseline_joint
    return {
        "candidate_set_id": candidate_set_id,
        "candidate_rank": candidate_rank,
        "candidate_count": candidate_count,
        "required_cohort_ids": [
            impact.cohort.cohort_id for impact in metrics.cohort_impacts
        ],
        "baseline_per_cohort": _json_safe(baseline_by_cohort),
        "post_dispatch_per_cohort": _json_safe(post_dispatch_by_cohort),
        "baseline_joint": _json_safe(metrics.baseline_joint),
        "post_dispatch_joint": _json_safe(metrics.post_dispatch_joint),
        "joint_aggregation_policy": metrics.baseline_joint.aggregation_policy,
        "coverage_delta": metrics.coverage_delta,
        "affected_zone_ids": list(metrics.affected_zone_ids),
        "newly_undercovered_zone_ids": list(metrics.newly_undercovered_zone_ids),
        "reserve_resource_ids_by_cohort": _json_safe(
            metrics.reserve_resource_ids_by_cohort
        ),
        "reserve_exhausted_cohort_ids": list(metrics.reserve_exhausted_cohort_ids),
        "max_incident_eta_seconds": metrics.max_incident_eta_seconds,
        "responder_arrival_spread_seconds": metrics.responder_arrival_spread_seconds,
        "population_data_reality": representative.population_data_reality.value,
        "population_source_reference": representative.population_source_reference,
        "prototype_policy_label": (
            (requirements_metadata or {}).get("prototype_policy_label")
            or "SirenGrid prototype demo configuration"
        ),
        "response_requirements": _json_safe(requirements_metadata or {}),
        "provenance": {
            "source": representative.source,
            "data_reality": representative.data_reality.value,
            "population_data_reality": representative.population_data_reality.value,
            "population_source_reference": representative.population_source_reference,
            "graph_fingerprint": representative.graph_fingerprint,
            "traffic_snapshot_ids": [
                snapshot.traffic_snapshot_id
                for snapshot in baseline_by_cohort
                if snapshot.traffic_snapshot_id is not None
            ],
        },
        "candidate_metrics": _json_safe(metrics),
    } | ({"reposition_proposal": _json_safe(reposition_proposal)} if reposition_proposal is not None else {})


def _top_level_metrics(
    candidate: EvaluatedCandidate,
    *,
    candidate_set_id: str,
    candidate_rank: int,
    candidate_count: int,
    phase04: dict[str, Any],
) -> dict[str, Any]:
    routes = [responder.route for responder in candidate.combination.responders]
    etas = [route.effective_eta for route in routes]
    routing_sources = sorted({route.routing_source for route in routes})
    return {
        "max_arrival_eta_seconds": max(etas),
        "mean_arrival_eta_seconds": sum(etas) / len(etas),
        "selected_resource_count": len(routes),
        "routing_source": routing_sources[0] if len(routing_sources) == 1 else "MIXED",
        "candidate_set_id": candidate_set_id,
        "candidate_rank": candidate_rank,
        "candidate_count": candidate_count,
        "phase04": phase04,
    }


def persist_candidate_set(
    db: Session,
    incident: Incident,
    ranked_candidates: Iterable[EvaluatedCandidate],
    *,
    candidate_set_id: str | None = None,
    reposition_proposals: Mapping[tuple[str, ...], Any] | None = None,
    requirements_metadata: Mapping[str, Any] | None = None,
    now_utc: datetime | None = None,
) -> tuple[ResponsePlan, ...]:
    """Persist one already-ranked candidate set atomically.

    The caller owns the captured routing/coverage state and ranking.  The
    function only serializes those facts, creates one recommendation plus
    alternatives, and advances the incident version once.
    """
    if incident.status in (
        IncidentStatus.CLOSED,
        IncidentStatus.CANCELLED_FALSE_REPORT,
    ):
        raise ValueError(
            f"Cannot generate response plan for incident with status {incident.status.value}"
        )
    candidates = tuple(ranked_candidates)
    if not candidates:
        raise ValueError("At least one evaluated candidate is required")
    set_id = candidate_set_id or str(uuid.uuid4())
    if not set_id.strip():
        raise ValueError("candidate_set_id must be non-empty")
    timestamp = now_utc or datetime.now(timezone.utc)
    candidate_count = len(candidates)

    existing_plans = db.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all()
    for existing in existing_plans:
        if existing.status in (
            ResponsePlanStatus.RECOMMENDED,
            ResponsePlanStatus.ALTERNATIVE,
        ):
            existing.status = ResponsePlanStatus.SUPERSEDED
    next_plan_version = (
        max((plan.plan_version for plan in existing_plans), default=0) + 1
    )
    resulting_incident_version = incident.version + 1
    persisted: list[ResponsePlan] = []

    for rank, candidate in enumerate(candidates):
        phase04 = _phase04_metrics(
            candidate,
            candidate_set_id=set_id,
            candidate_rank=rank,
            candidate_count=candidate_count,
            reposition_proposal=(
                reposition_proposals.get(candidate.combination.resource_ids)
                if reposition_proposals
                else None
            ),
            requirements_metadata=requirements_metadata,
        )
        plan = ResponsePlan(
            id=str(uuid.uuid4()),
            incident_id=incident.id,
            incident_version=resulting_incident_version,
            plan_version=next_plan_version + rank,
            status=(
                ResponsePlanStatus.RECOMMENDED
                if rank == 0
                else ResponsePlanStatus.ALTERNATIVE
            ),
            resource_ids_json=list(candidate.combination.resource_ids),
            routes_json=_route_record(candidate),
            metrics_json=_top_level_metrics(
                candidate,
                candidate_set_id=set_id,
                candidate_rank=rank,
                candidate_count=candidate_count,
                phase04=phase04,
            ),
            score_breakdown_json=_json_safe(candidate.score),
            created_at=timestamp,
        )
        db.add(plan)
        persisted.append(plan)

    incident.status = IncidentStatus.AWAITING_APPROVAL
    incident.version = resulting_incident_version
    incident.current_plan_id = persisted[0].id
    incident.updated_at = timestamp
    db.add(
        TimelineEvent(
            id=str(uuid.uuid4()),
            incident_id=incident.id,
            event_type="PLAN_GENERATED",
            details_json={
                "action": "CANDIDATE_SET_GENERATED",
                "candidate_set_id": set_id,
                "candidate_plan_ids": [plan.id for plan in persisted],
                "candidate_ranks": [
                    _json_safe(plan.metrics_json["phase04"]["candidate_rank"])
                    for plan in persisted
                ],
                "recommended_plan_id": persisted[0].id,
                "candidate_count": candidate_count,
                "incident_version": resulting_incident_version,
                "resource_ids_by_plan": {
                    plan.id: plan.resource_ids_json for plan in persisted
                },
            },
            created_at=timestamp,
        )
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    for plan in persisted:
        db.refresh(plan)
    db.refresh(incident)
    return tuple(persisted)


def persist_replacement_candidate_set(
    db: Session,
    incident: Incident,
    active_plan: ResponsePlan,
    ranked_candidates: Iterable[EvaluatedCandidate],
    *,
    evaluation: ReplanEvaluation,
    reposition_proposals: Mapping[tuple[str, ...], Any] | None = None,
    requirements_metadata: Mapping[str, Any] | None = None,
    replan_metadata: Mapping[str, Any] | None = None,
    now_utc: datetime | None = None,
) -> tuple[ResponsePlan, ...]:
    """Persist one hypothetical replacement set without moving active truth."""
    if incident.current_plan_id != active_plan.id:
        raise ValueError("Active plan changed during replacement evaluation")
    if active_plan.status != ResponsePlanStatus.APPROVED:
        raise ValueError("Replacement evaluation requires an APPROVED active plan")
    candidates = tuple(ranked_candidates)
    if not candidates:
        raise ValueError("At least one evaluated replacement candidate is required")
    timestamp = now_utc or datetime.now(timezone.utc)
    set_id = str(uuid.uuid4())
    existing_plans = db.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all()
    if incident.pending_replan_plan_id:
        for existing in existing_plans:
            metrics = existing.metrics_json or {}
            replan = metrics.get("replan") if isinstance(metrics, dict) else None
            if (
                isinstance(replan, dict)
                and replan.get("active_plan_id") == active_plan.id
                and existing.status
                in (ResponsePlanStatus.RECOMMENDED, ResponsePlanStatus.ALTERNATIVE)
            ):
                existing.status = ResponsePlanStatus.SUPERSEDED
    next_plan_version = max((plan.plan_version for plan in existing_plans), default=0) + 1
    resulting_incident_version = incident.version + 1
    persisted: list[ResponsePlan] = []
    candidate_count = len(candidates)
    for rank, candidate in enumerate(candidates):
        phase04 = _phase04_metrics(
            candidate,
            candidate_set_id=set_id,
            candidate_rank=rank,
            candidate_count=candidate_count,
            reposition_proposal=(
                reposition_proposals.get(candidate.combination.resource_ids)
                if reposition_proposals
                else None
            ),
            requirements_metadata=requirements_metadata,
        )
        metrics = _top_level_metrics(
            candidate,
            candidate_set_id=set_id,
            candidate_rank=rank,
            candidate_count=candidate_count,
            phase04=phase04,
        )
        metrics["replan"] = _json_safe(
            {**(replan_metadata or {}), "active_plan_id": active_plan.id}
        )
        plan = ResponsePlan(
            id=str(uuid.uuid4()),
            incident_id=incident.id,
            incident_version=resulting_incident_version,
            plan_version=next_plan_version + rank,
            status=(
                ResponsePlanStatus.RECOMMENDED
                if rank == 0
                else ResponsePlanStatus.ALTERNATIVE
            ),
            resource_ids_json=list(candidate.combination.resource_ids),
            routes_json=_route_record(candidate),
            metrics_json=metrics,
            score_breakdown_json=_json_safe(candidate.score),
            created_at=timestamp,
        )
        db.add(plan)
        persisted.append(plan)

    incident.version = resulting_incident_version
    incident.pending_replan_plan_id = persisted[0].id
    incident.updated_at = timestamp
    evaluation.status = "RECOMMENDED"
    evaluation.pending_plan_id = persisted[0].id
    evaluation.evaluated_at = timestamp
    evaluation.explanation_json = _json_safe(replan_metadata or {})
    db.add(
        TimelineEvent(
            id=str(uuid.uuid4()),
            incident_id=incident.id,
            event_type="REPLAN_GENERATED",
            details_json={
                **_json_safe(replan_metadata or {}),
                "pending_plan_id": persisted[0].id,
                "pending_candidate_plan_ids": [plan.id for plan in persisted],
                "resulting_incident_version": resulting_incident_version,
                "active_plan_id": active_plan.id,
            },
            created_at=timestamp,
        )
    )
    db.commit()
    for plan in persisted:
        db.refresh(plan)
    db.refresh(incident)
    db.refresh(evaluation)
    return tuple(persisted)
