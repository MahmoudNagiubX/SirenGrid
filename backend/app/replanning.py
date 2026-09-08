"""Shared Phase 07 pending-trigger helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.candidate_persistence import persist_replacement_candidate_set
from app.db import get_db
from app.incidents import _acquire_write_lock, serialize_incident
from app.materiality import (
    ReplanMaterialityResult,
    build_replan_input_fingerprint,
    evaluate_replan_materiality,
)
from app.models import Incident, ReplanEvaluation, ResponsePlan, TimelineEvent, new_timeline_event_id
from app.planning import evaluate_phase04_candidate_set, serialize_plan
from app.schemas import (
    ReplanEvaluationRead,
    ReplanEvaluateRequest,
    ReplanEvaluationResponse,
    ReplanTriggerRequest,
    ResponsePlanStatus,
)
from app.websocket import publish_operations_event

router = APIRouter(tags=["replanning"])

KNOWN_REPLAN_TRIGGER_REASONS = {
    "TRAFFIC_CHANGED",
    "ROAD_CLOSED",
    "ACTIVE_ROUTE_CLOSURE",
    "ROUTE_UNREACHABLE",
    "ACTIVE_ROUTE_UNREACHABLE",
    "RESOURCE_UNAVAILABLE",
    "RESOURCE_ASSIGNMENT_CONFLICT",
    "INCIDENT_FACT_CHANGED",
    "HOSPITAL_STATE_CHANGED",
    "SECOND_INCIDENT_ACTIVATED",
    "OPERATOR_CONSTRAINT_CHANGED",
    "COVERAGE_CHANGED",
}


def materiality_for_trigger(
    *,
    reasons: list[str],
    references: dict[str, Any],
) -> ReplanMaterialityResult:
    """Map explicit trigger facts into the shared materiality policy."""
    unknown_reasons = sorted(set(reasons) - KNOWN_REPLAN_TRIGGER_REASONS)
    if unknown_reasons:
        raise ValueError(f"Unknown replan trigger reason(s): {unknown_reasons}")
    reason_set = set(reasons)
    return evaluate_replan_materiality(
        old_eta_seconds=references.get("old_eta_seconds"),
        new_eta_seconds=references.get("new_eta_seconds"),
        route_edge_overlap_ratio=references.get("route_edge_overlap_ratio"),
        route_geometry_overlap_ratio=references.get("route_geometry_overlap_ratio"),
        active_route_closure=bool(
            references.get("active_route_closure")
            or {"ROAD_CLOSED", "ACTIVE_ROUTE_CLOSURE"} & reason_set
        ),
        route_unreachable=bool(
            references.get("route_unreachable")
            or {"ROUTE_UNREACHABLE", "ACTIVE_ROUTE_UNREACHABLE"} & reason_set
        ),
        required_resource_unavailable=bool(
            references.get("required_resource_unavailable")
            or "RESOURCE_UNAVAILABLE" in reason_set
        ),
        resource_assignment_conflict=bool(
            references.get("resource_assignment_conflict")
            or "RESOURCE_ASSIGNMENT_CONFLICT" in reason_set
        ),
        requirements_changed=bool(
            references.get("requirements_changed")
            or "OPERATOR_CONSTRAINT_CHANGED" in reason_set
        ),
        hospital_not_accepting=bool(references.get("hospital_not_accepting")),
        hospital_unreachable=bool(references.get("hospital_unreachable")),
        contention_resource_unavailable=bool(
            references.get("contention_resource_unavailable")
            or "SECOND_INCIDENT_ACTIVATED" in reason_set
            and references.get("contention_resource_ids")
        ),
        newly_joint_undercovered=bool(references.get("newly_joint_undercovered")),
        joint_coverage_drop=references.get("joint_coverage_drop"),
        unknown_state=bool(references.get("unknown_state")),
    )


def merge_pending_trigger(
    *,
    existing_reasons: list[str],
    existing_references: dict[str, Any],
    new_reasons: list[str],
    new_references: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """Merge one trigger into a pending trigger deterministically.

    Reasons are a set-like audit field. References are latest-value fields, so
    a newer event replaces only keys it explicitly supplies.
    """
    reasons = sorted({*existing_reasons, *new_reasons})
    references = {**existing_references, **new_references}
    return reasons, references


def serialize_replan_evaluation(
    evaluation: ReplanEvaluation,
    *,
    incident_version: int,
) -> dict[str, Any]:
    return {
        "id": evaluation.id,
        "incident_id": evaluation.incident_id,
        "active_plan_id": evaluation.active_plan_id,
        "pending_plan_id": evaluation.pending_plan_id,
        "input_fingerprint": evaluation.input_fingerprint,
        "status": evaluation.status,
        "trigger_reasons": evaluation.trigger_reasons_json or [],
        "input_references": evaluation.input_references_json or {},
        "explanation": evaluation.explanation_json or {},
        "first_triggered_at": (
            evaluation.first_triggered_at.isoformat()
            if evaluation.first_triggered_at
            else None
        ),
        "last_triggered_at": (
            evaluation.last_triggered_at.isoformat()
            if evaluation.last_triggered_at
            else None
        ),
        "debounce_until": (
            evaluation.debounce_until.isoformat()
            if evaluation.debounce_until
            else None
        ),
        "evaluated_at": (
            evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None
        ),
        "incident_version": incident_version,
        "idempotent": False,
    }


def _get_active_approved_plan(db: Session, incident: Incident) -> ResponsePlan:
    if not incident.current_plan_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Incident has no active approved response plan",
        )
    plan = db.get(ResponsePlan, incident.current_plan_id)
    if plan is None or plan.status != ResponsePlanStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Incident current_plan_id does not reference an APPROVED plan",
        )
    return plan


def _pending_for_active_plan(
    db: Session,
    *,
    incident_id: str,
    active_plan_id: str,
) -> ReplanEvaluation | None:
    return db.scalar(
        select(ReplanEvaluation)
        .where(
            ReplanEvaluation.incident_id == incident_id,
            ReplanEvaluation.active_plan_id == active_plan_id,
            ReplanEvaluation.status.in_(
                ("PENDING", "RECOMMENDED", "NO_MATERIAL_CHANGE")
            ),
        )
        .order_by(ReplanEvaluation.first_triggered_at.desc())
    )


def _all_plans_for_candidate_set(
    db: Session,
    *,
    incident_id: str,
    candidate_set_id: str | None,
) -> list[dict[str, Any]]:
    if not candidate_set_id:
        return []
    plans: list[ResponsePlan] = []
    for plan in db.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident_id)
    ).all():
        metrics = plan.metrics_json or {}
        phase04 = metrics.get("phase04") if isinstance(metrics, dict) else None
        replan = metrics.get("replan") if isinstance(metrics, dict) else None
        if (
            isinstance(phase04, dict)
            and phase04.get("candidate_set_id") == candidate_set_id
            and isinstance(replan, dict)
        ):
            plans.append(plan)
    return [serialize_plan(plan) for plan in sorted(plans, key=lambda item: item.plan_version)]


def _evaluation_response(
    *,
    incident: Incident,
    active_plan: ResponsePlan,
    evaluation: ReplanEvaluation | None,
    status_value: str,
    material: bool,
    idempotent: bool,
    plans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "incident_id": incident.id,
        "incident_version": incident.version,
        "active_plan_id": active_plan.id,
        "pending_plan_id": incident.pending_replan_plan_id,
        "status": status_value,
        "material": material,
        "idempotent": idempotent,
        "trigger_reasons": evaluation.trigger_reasons_json if evaluation else [],
        "input_fingerprint": evaluation.input_fingerprint if evaluation else None,
        "explanation": evaluation.explanation_json if evaluation else {},
        "evaluation": (
            serialize_replan_evaluation(evaluation, incident_version=incident.version)
            if evaluation
            else None
        ),
        "plans": plans or [],
    }


def record_replan_trigger(
    db: Session,
    *,
    incident_id: str,
    expected_incident_version: int,
    trigger_reasons: list[str],
    input_references: dict[str, Any],
    now: datetime | None = None,
) -> tuple[ReplanEvaluation, bool]:
    """Acquire the write lock, record/coalesce a trigger, and commit.

    Returns ``(evaluation, idempotent)``. Use this from a REST command that
    owns the whole request. A caller that is already inside its own write
    transaction must call :func:`apply_replan_trigger` instead so the work
    joins that transaction rather than committing separately.
    """
    _acquire_write_lock(db)
    evaluation, idempotent = apply_replan_trigger(
        db,
        incident_id=incident_id,
        expected_incident_version=expected_incident_version,
        trigger_reasons=trigger_reasons,
        input_references=input_references,
        now=now,
    )
    db.commit()
    db.refresh(evaluation)
    return evaluation, idempotent


def apply_replan_trigger(
    db: Session,
    *,
    incident_id: str,
    expected_incident_version: int,
    trigger_reasons: list[str],
    input_references: dict[str, Any],
    now: datetime | None = None,
) -> tuple[ReplanEvaluation, bool]:
    """Record/coalesce a trigger inside the caller's open write transaction.

    Acquires no lock and performs no commit, so a command that already changed
    authoritative state can record its trigger atomically with that change
    instead of leaving a partially applied correction behind on failure.

    Does not change the incident version.
    """
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    active_plan = _get_active_approved_plan(db, incident)

    now_utc = now or datetime.now(timezone.utc)
    fingerprint = build_replan_input_fingerprint(
        active_plan_id=active_plan.id,
        incident_version=incident.version,
        trigger_facts={"trigger_reasons": trigger_reasons},
        input_references=input_references,
    )
    evaluation = _pending_for_active_plan(
        db,
        incident_id=incident.id,
        active_plan_id=active_plan.id,
    )
    if evaluation is not None:
        if evaluation.input_fingerprint == fingerprint:
            return evaluation, True
    if expected_incident_version != incident.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale incident version: expected {expected_incident_version}, "
                f"current {incident.version}"
            ),
        )
    if evaluation is not None:
        merged_reasons, merged_references = merge_pending_trigger(
            existing_reasons=evaluation.trigger_reasons_json or [],
            existing_references=evaluation.input_references_json or {},
            new_reasons=trigger_reasons,
            new_references=input_references,
        )
        evaluation.trigger_reasons_json = merged_reasons
        evaluation.input_references_json = merged_references
        evaluation.input_fingerprint = build_replan_input_fingerprint(
            active_plan_id=active_plan.id,
            incident_version=incident.version,
            trigger_facts={"trigger_reasons": merged_reasons},
            input_references=merged_references,
        )
        evaluation.last_triggered_at = now_utc
        evaluation.debounce_until = now_utc + timedelta(
            seconds=settings.REPLAN_DEBOUNCE_SECONDS
        )
        evaluation.status = "PENDING"
        idempotent = False
    else:
        evaluation = ReplanEvaluation(
            id=str(uuid.uuid4()),
            incident_id=incident.id,
            active_plan_id=active_plan.id,
            input_fingerprint=fingerprint,
            status="PENDING",
            trigger_reasons_json=sorted(set(trigger_reasons)),
            input_references_json=dict(input_references),
            first_triggered_at=now_utc,
            last_triggered_at=now_utc,
            debounce_until=now_utc
            + timedelta(seconds=settings.REPLAN_DEBOUNCE_SECONDS),
        )
        db.add(evaluation)
        idempotent = False

    db.add(
        TimelineEvent(
            id=new_timeline_event_id(),
            incident_id=incident.id,
            event_type="REPLAN_TRIGGER_RECORDED",
            details_json={
                "active_plan_id": active_plan.id,
                "input_fingerprint": evaluation.input_fingerprint,
                "trigger_reasons": evaluation.trigger_reasons_json,
                "input_references": evaluation.input_references_json,
                "incident_version": incident.version,
            },
            created_at=now_utc,
        )
    )
    # No commit here: the caller owns the transaction.
    db.flush()
    return evaluation, idempotent


def evaluate_pending_replan(
    db: Session,
    *,
    incident_id: str,
    expected_incident_version: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Flush the current pending trigger and optionally persist a replacement set."""
    _acquire_write_lock(db)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    active_plan = _get_active_approved_plan(db, incident)
    evaluation = _pending_for_active_plan(
        db,
        incident_id=incident.id,
        active_plan_id=active_plan.id,
    )
    if evaluation is None:
        if expected_incident_version != incident.version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Stale incident version: expected {expected_incident_version}, "
                    f"current {incident.version}"
                ),
            )
        return _evaluation_response(
            incident=incident,
            active_plan=active_plan,
            evaluation=None,
            status_value="NO_PENDING_TRIGGER",
            material=False,
            idempotent=True,
        )

    if evaluation.status == "RECOMMENDED":
        pending_plan = (
            db.get(ResponsePlan, evaluation.pending_plan_id)
            if evaluation.pending_plan_id
            else None
        )
        pending_metrics = pending_plan.metrics_json if pending_plan else {}
        pending_phase04 = (
            pending_metrics.get("phase04")
            if isinstance(pending_metrics, dict)
            else None
        )
        return _evaluation_response(
            incident=incident,
            active_plan=active_plan,
            evaluation=evaluation,
            status_value="IDEMPOTENT_NO_OP",
            material=True,
            idempotent=True,
            plans=_all_plans_for_candidate_set(
                db,
                incident_id=incident.id,
                candidate_set_id=(
                    pending_phase04.get("candidate_set_id")
                    if isinstance(pending_phase04, dict)
                    else None
                ),
            ),
        )

    if evaluation.status == "NO_MATERIAL_CHANGE":
        return _evaluation_response(
            incident=incident,
            active_plan=active_plan,
            evaluation=evaluation,
            status_value="NO_MATERIAL_CHANGE",
            material=False,
            idempotent=True,
        )

    if expected_incident_version != incident.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale incident version: expected {expected_incident_version}, "
                f"current {incident.version}"
            ),
        )

    try:
        materiality = materiality_for_trigger(
            reasons=evaluation.trigger_reasons_json or [],
            references=evaluation.input_references_json or {},
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    timestamp = now or datetime.now(timezone.utc)
    explanation = {
        "materiality_policy_version": "SIRENGRID_REPLAN_MATERIALITY_V1",
        "trigger_reasons": evaluation.trigger_reasons_json or [],
        "input_references": evaluation.input_references_json or {},
        "input_fingerprint": evaluation.input_fingerprint,
        "old_approved_plan_id": active_plan.id,
        "old_approved_plan_version": active_plan.plan_version,
        "evaluation_timestamp": timestamp.isoformat(),
        "material": materiality.material,
        "materiality_reasons": list(materiality.reasons),
    }
    if not materiality.material:
        evaluation.status = "NO_MATERIAL_CHANGE"
        evaluation.evaluated_at = timestamp
        evaluation.explanation_json = explanation
        db.commit()
        db.refresh(incident)
        db.refresh(evaluation)
        return _evaluation_response(
            incident=incident,
            active_plan=active_plan,
            evaluation=evaluation,
            status_value="NO_MATERIAL_CHANGE",
            material=False,
            idempotent=False,
        )

    try:
        resolution, ranked, reposition_proposals, modeled_at = (
            evaluate_phase04_candidate_set(
                db,
                incident,
                now_utc=timestamp,
                planning_incident_id=incident.id,
            )
        )
        persisted = persist_replacement_candidate_set(
            db,
            incident,
            active_plan,
            ranked,
            evaluation=evaluation,
            reposition_proposals=reposition_proposals,
            now_utc=modeled_at,
            requirements_metadata={
                "source": resolution.source.value,
                "matrix_version": resolution.matrix_version,
                "prototype_policy_label": resolution.prototype_policy_label,
            },
            replan_metadata=explanation,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Replacement plan evaluation failed: {exc}",
        ) from exc
    db.refresh(evaluation)
    db.refresh(incident)
    candidate_set_id = (
        (persisted[0].metrics_json or {}).get("phase04", {}).get("candidate_set_id")
    )
    result = _evaluation_response(
        incident=incident,
        active_plan=active_plan,
        evaluation=evaluation,
        status_value="REPLACEMENT_RECOMMENDED",
        material=True,
        idempotent=False,
        plans=_all_plans_for_candidate_set(
            db,
            incident_id=incident.id,
            candidate_set_id=candidate_set_id,
        ),
    )
    publish_operations_event(
        event="replan.generated",
        incident_id=incident.id,
        payload={"replan": result, "incident": serialize_incident(incident)},
    )
    return result


@router.post(
    "/incidents/{incident_id}/replan/triggers",
    response_model=ReplanEvaluationRead,
)
def create_replan_trigger(
    incident_id: str,
    payload: ReplanTriggerRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.input_references.get("hospital_unreachable") and not payload.input_references.get(
        "hospital_id"
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="hospital_id is required when hospital_unreachable is confirmed",
        )
    evaluation, idempotent = record_replan_trigger(
        db,
        incident_id=incident_id,
        expected_incident_version=payload.expected_incident_version,
        trigger_reasons=payload.trigger_reasons,
        input_references=payload.input_references,
    )
    if payload.input_references.get("hospital_unreachable"):
        from app.hospital_api import invalidate_selected_hospital_for_replan

        invalidate_selected_hospital_for_replan(
            db,
            incident_id=incident_id,
            hospital_id=str(payload.input_references["hospital_id"]),
            reason="UNREACHABLE",
            operator_reference=payload.input_references.get(
                "operator_reference", "replan-trigger"
            ),
        )
    incident = db.get(Incident, incident_id)
    assert incident is not None
    result = serialize_replan_evaluation(
        evaluation,
        incident_version=incident.version,
    )
    result["idempotent"] = idempotent
    publish_operations_event(
        event="replan.required",
        incident_id=incident.id,
        payload={"replan": result, "incident": serialize_incident(incident)},
    )
    return result


@router.post(
    "/incidents/{incident_id}/replan/evaluate",
    response_model=ReplanEvaluationResponse,
)
def flush_replan(
    incident_id: str,
    payload: ReplanEvaluateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return evaluate_pending_replan(
        db,
        incident_id=incident_id,
        expected_incident_version=payload.expected_incident_version,
    )


@router.get(
    "/incidents/{incident_id}/replan",
    response_model=ReplanEvaluationRead | None,
)
def get_pending_replan(
    incident_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any] | None:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    if not incident.current_plan_id:
        return None
    evaluation = _pending_for_active_plan(
        db,
        incident_id=incident.id,
        active_plan_id=incident.current_plan_id,
    )
    if evaluation is None:
        return None
    return serialize_replan_evaluation(evaluation, incident_version=incident.version)
