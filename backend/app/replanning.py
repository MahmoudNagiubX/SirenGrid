"""Shared Phase 07 pending-trigger helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.incidents import _acquire_write_lock, serialize_incident
from app.materiality import build_replan_input_fingerprint
from app.models import Incident, ReplanEvaluation, ResponsePlan, TimelineEvent
from app.schemas import ReplanEvaluationRead, ReplanTriggerRequest, ResponsePlanStatus
from app.websocket import publish_operations_event

router = APIRouter(tags=["replanning"])


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
            ReplanEvaluation.status == "PENDING",
        )
        .order_by(ReplanEvaluation.first_triggered_at.desc())
    )


def record_replan_trigger(
    db: Session,
    *,
    incident_id: str,
    expected_incident_version: int,
    trigger_reasons: list[str],
    input_references: dict[str, Any],
    now: datetime | None = None,
) -> tuple[ReplanEvaluation, bool]:
    """Record/coalesce a trigger without changing incident version.

    Returns ``(evaluation, idempotent)``. The caller owns the transaction and
    can use this helper from both the REST command and future domain events.
    """
    _acquire_write_lock(db)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    active_plan = _get_active_approved_plan(db, incident)
    if expected_incident_version != incident.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale incident version: expected {expected_incident_version}, "
                f"current {incident.version}"
            ),
        )

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
            id=str(uuid.uuid4()),
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
    db.commit()
    db.refresh(evaluation)
    return evaluation, idempotent


@router.post(
    "/incidents/{incident_id}/replan/triggers",
    response_model=ReplanEvaluationRead,
)
def create_replan_trigger(
    incident_id: str,
    payload: ReplanTriggerRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    evaluation, idempotent = record_replan_trigger(
        db,
        incident_id=incident_id,
        expected_incident_version=payload.expected_incident_version,
        trigger_reasons=payload.trigger_reasons,
        input_references=payload.input_references,
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
