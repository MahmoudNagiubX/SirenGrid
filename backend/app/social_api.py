"""REST actions for unverified public social intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import build_evidence_claims
from app.claims import append_claims_to_evidence_items
from app.config import settings
from app.db import get_db
from app.fusion import FusionDecision, evaluate_report_association
from app.incidents import (
    _acquire_write_lock,
    serialize_incident,
    serialize_report,
    serialize_timeline_event,
)
from app.models import Incident, Report, TimelineEvent
from app.phase06_api import _incident_fusion_view, _report_fusion_view
from app.schemas import DataReality
from app.social import (
    SOCIAL_NORMALIZATION_VERSION,
    SOCIAL_SOURCE_TYPE,
    BlueskyPublicProvider,
    DeterministicSyntheticSocialProvider,
    NormalizedSocialSignal,
    ProviderState,
    SocialProvider,
    normalize_social_post,
)
from app.websocket import publish_operations_event

router = APIRouter(tags=["social"])

DEFAULT_SOCIAL_QUERY = (
    "accident collision fire smoke ambulance "
    "حادث تصادم حريق دخان إسعاف"
)


class SocialRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["bluesky", "synthetic"] = "bluesky"
    query: str = Field(default=DEFAULT_SOCIAL_QUERY, min_length=1, max_length=300)
    limit: int = Field(default=25, ge=1, le=50)


class SocialReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_reference: str = Field(min_length=1, max_length=200)


class SocialAssociationRequest(SocialReviewRequest):
    target_incident_id: str = Field(min_length=1, max_length=36)
    expected_incident_version: int = Field(ge=1)


def _provider(name: str) -> SocialProvider:
    if name == "synthetic":
        return DeterministicSyntheticSocialProvider()
    return BlueskyPublicProvider(
        endpoint=settings.social_bluesky_api_url,
        timeout_seconds=settings.social_provider_timeout_seconds,
    )


def _social_signal_payload(report: Report) -> dict[str, Any]:
    data = serialize_report(report)
    provenance = report.provenance_json or {}
    data["social_signal"] = provenance.get("social_signal", {})
    data["association_evaluation"] = provenance.get("association_evaluation", [])
    data["association_outcome"] = provenance.get("association_outcome")
    return data


def _safe_provider_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Retain only small provider identifiers needed for audit/debugging."""
    safe: dict[str, str] = {}
    for key in ("cid", "fixture"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            safe[key] = value[:300]
    return safe


def _create_social_report(db: Session, signal: NormalizedSocialSignal) -> Report:
    report_id = str(uuid.uuid4())
    evidence_id = f"social-evidence:{signal.provider_post_id}"
    claim_provenance = {
        **signal.provenance,
        "source": signal.provider,
        "verification_status": "UNVERIFIED",
        "data_reality": signal.data_reality.value,
        "observed_at": signal.posted_at.isoformat(),
    }
    claims = build_evidence_claims(
        list(signal.claims),
        evidence_id=evidence_id,
        report_id=report_id,
        provider=signal.provider,
        model=SOCIAL_NORMALIZATION_VERSION,
        observed_at=signal.posted_at,
        provenance=claim_provenance,
    )
    evidence_items: list[dict[str, Any]] = [
        {
            "type": "SOCIAL_SIGNAL",
            "uri_or_reference": signal.source_url or signal.provider_post_id,
            "extracted_facts": {
                "normalized_keywords": list(signal.normalized_keywords),
                "location_clues": list(signal.location_clues),
                "canonical_category": signal.canonical_category,
                "unknown_fields": list(signal.unknown_fields),
            },
            "provenance": {
                "source": signal.provider,
                "provider_post_id": signal.provider_post_id,
                "data_reality": signal.data_reality.value,
                "verification_status": "UNVERIFIED",
                "normalization_policy": SOCIAL_NORMALIZATION_VERSION,
            },
            "confidence_support": "LOW",
            "created_at": signal.retrieved_at.isoformat(),
        }
    ]
    evidence_items = append_claims_to_evidence_items(evidence_items, claims)
    provenance = {
        **signal.provenance,
        "source": signal.provider,
        "provider": signal.provider,
        "provider_post_id": signal.provider_post_id,
        "source_url": signal.source_url,
        "posted_at": signal.posted_at.isoformat(),
        "retrieved_at": signal.retrieved_at.isoformat(),
        "data_reality": signal.data_reality.value,
        "verification_status": "UNVERIFIED",
        "canonical_category": signal.canonical_category,
        "coordinates_trusted": signal.coordinates_trusted,
        "normalized_keywords": list(signal.normalized_keywords),
        "location_clues": list(signal.location_clues),
        "unknown_fields": list(signal.unknown_fields),
        "provider_metadata": _safe_provider_metadata(signal.provider_metadata),
        "normalization_policy": SOCIAL_NORMALIZATION_VERSION,
        "social_signal": {
            "provider": signal.provider,
            "provider_post_id": signal.provider_post_id,
            "source_url": signal.source_url,
            "posted_at": signal.posted_at.isoformat(),
            "retrieved_at": signal.retrieved_at.isoformat(),
            "location_clues": list(signal.location_clues),
            "normalized_keywords": list(signal.normalized_keywords),
            "canonical_category": signal.canonical_category,
            "unknown_fields": list(signal.unknown_fields),
            "media_references": list(signal.media_references),
            "data_reality": signal.data_reality.value,
            "verification_status": "UNVERIFIED",
            "review_state": signal.filter_state,
        },
    }
    initial_status = signal.filter_state
    report = Report(
        id=report_id,
        incident_id=None,
        source_type=SOCIAL_SOURCE_TYPE,
        source_reference=signal.provider_post_id,
        raw_text=signal.text,
        location_text=signal.location_text,
        location_json=signal.location_json,
        received_at=signal.posted_at,
        data_reality=signal.data_reality,
        provenance_json=provenance,
        processing_status=initial_status,
        evidence_items_json=evidence_items,
        created_at=signal.retrieved_at,
    )
    db.add(report)
    return report


def _evaluate_association(db: Session, report: Report) -> tuple[str, list[dict[str, Any]]]:
    provenance = report.provenance_json or {}
    if report.processing_status == "IRRELEVANT":
        return "IRRELEVANT", []
    incidents = db.scalars(select(Incident).order_by(Incident.id.asc())).all()
    evaluations: list[dict[str, Any]] = []
    for incident in incidents:
        result = evaluate_report_association(
            _report_fusion_view(report),
            _incident_fusion_view(incident),
        )
        evaluations.append(
            {
                "incident_id": incident.id,
                **result.model_dump(mode="json"),
            }
        )
    if any(item["decision"] == FusionDecision.AUTO_ASSOCIATE.value for item in evaluations):
        if not any(item["decision"] == FusionDecision.REQUIRES_REVIEW.value for item in evaluations):
            outcome = "POSSIBLE_EXISTING_INCIDENT"
        else:
            outcome = "REQUIRES_REVIEW"
    elif any(item["decision"] == FusionDecision.REQUIRES_REVIEW.value for item in evaluations):
        outcome = "REQUIRES_REVIEW"
    elif report.processing_status == "POTENTIALLY_RELEVANT":
        outcome = "POSSIBLE_NEW_INCIDENT"
    else:
        outcome = "INSUFFICIENT_CONTEXT"
    provenance["association_evaluation"] = evaluations
    provenance["association_outcome"] = outcome
    report.provenance_json = provenance
    if report.processing_status not in {"DISMISSED", "ASSOCIATED"}:
        report.processing_status = outcome
    return outcome, evaluations


def _review_history(provenance: dict[str, Any]) -> list[dict[str, Any]]:
    history = provenance.get("review_history", [])
    return list(history) if isinstance(history, list) else []


def _record_review(
    report: Report,
    *,
    action: str,
    operator_reference: str,
    at: datetime,
) -> None:
    provenance = dict(report.provenance_json or {})
    history = _review_history(provenance)
    history.append(
        {
            "action": action,
            "operator_reference": operator_reference,
            "at": at.isoformat(),
        }
    )
    provenance["review_history"] = history
    report.provenance_json = provenance


@router.post("/social/refresh", status_code=status.HTTP_200_OK)
def refresh_social_signals(
    payload: SocialRefreshRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    query = payload.query.strip()
    result = _provider(payload.provider).search(
        query=query,
        limit=min(payload.limit, settings.social_max_results),
        retrieved_at=datetime.now(timezone.utc),
    )
    if result.status is not ProviderState.AVAILABLE:
        return {
            "provider": result.provider,
            "provider_status": result.status.value,
            "query": query,
            "signals": [],
            "new_signal_count": 0,
            "duplicate_signal_count": 0,
            "failure_code": result.failure_code,
            "data_reality": DataReality.REAL_PUBLIC.value
            if payload.provider == "bluesky"
            else DataReality.SYNTHETIC.value,
        }

    _acquire_write_lock(db)
    signals: list[dict[str, Any]] = []
    new_reports: list[Report] = []
    duplicate_count = 0
    for post in result.posts:
        existing = db.scalar(
            select(Report).where(
                Report.source_type == SOCIAL_SOURCE_TYPE,
                Report.source_reference == post.post_id,
            )
        )
        if existing is not None:
            duplicate_count += 1
            signals.append(_social_signal_payload(existing))
            continue
        report = _create_social_report(db, normalize_social_post(post))
        _evaluate_association(db, report)
        new_reports.append(report)
        signals.append(_social_signal_payload(report))

    db.commit()
    for report in new_reports:
        db.refresh(report)
        publish_operations_event(
            event="social.signal_detected",
            incident_id=None,
            payload=_social_signal_payload(report),
        )
    return {
        "provider": result.provider,
        "provider_status": result.status.value,
        "query": query,
        "signals": signals,
        "new_signal_count": len(new_reports),
        "duplicate_signal_count": duplicate_count,
        "failure_code": None,
        "data_reality": DataReality.REAL_PUBLIC.value
        if payload.provider == "bluesky"
        else DataReality.SYNTHETIC.value,
    }


@router.get("/social/signals", status_code=status.HTTP_200_OK)
def list_social_signals(
    state: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    stmt = (
        select(Report)
        .where(Report.source_type == SOCIAL_SOURCE_TYPE)
    )
    if state:
        stmt = stmt.where(Report.processing_status == state)
    stmt = stmt.order_by(Report.created_at.desc(), Report.id.asc()).limit(limit)
    reports = db.scalars(stmt).all()
    return {"signals": [_social_signal_payload(report) for report in reports]}


@router.get("/social/signals/{signal_id}", status_code=status.HTTP_200_OK)
def get_social_signal(signal_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    report = db.get(Report, signal_id)
    if report is None or report.source_type != SOCIAL_SOURCE_TYPE:
        raise HTTPException(status_code=404, detail=f"Social signal '{signal_id}' not found")
    return _social_signal_payload(report)


@router.post("/social/signals/{signal_id}/dismiss", status_code=status.HTTP_200_OK)
def dismiss_social_signal(
    signal_id: str,
    payload: SocialReviewRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _acquire_write_lock(db)
    report = db.get(Report, signal_id)
    if report is None or report.source_type != SOCIAL_SOURCE_TYPE:
        raise HTTPException(status_code=404, detail=f"Social signal '{signal_id}' not found")
    if report.incident_id:
        raise HTTPException(status_code=409, detail="associated social signal cannot be dismissed")
    if report.processing_status != "DISMISSED":
        report.processing_status = "DISMISSED"
        _record_review(
            report,
            action="DISMISSED",
            operator_reference=payload.operator_reference,
            at=datetime.now(timezone.utc),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        publish_operations_event(
            event="social.signal_reviewed",
            incident_id=None,
            payload=_social_signal_payload(report),
        )
    return _social_signal_payload(report)


@router.post("/social/signals/{signal_id}/possible-new", status_code=status.HTTP_200_OK)
def mark_possible_new_incident(
    signal_id: str,
    payload: SocialReviewRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _acquire_write_lock(db)
    report = db.get(Report, signal_id)
    if report is None or report.source_type != SOCIAL_SOURCE_TYPE:
        raise HTTPException(status_code=404, detail=f"Social signal '{signal_id}' not found")
    if report.incident_id:
        raise HTTPException(status_code=409, detail="associated social signal cannot be marked as new")
    if report.processing_status != "POSSIBLE_NEW_INCIDENT":
        if report.processing_status in {"DISMISSED", "ASSOCIATED"}:
            raise HTTPException(status_code=409, detail="social signal is no longer reviewable")
        report.processing_status = "POSSIBLE_NEW_INCIDENT"
        provenance = dict(report.provenance_json or {})
        provenance["association_outcome"] = "POSSIBLE_NEW_INCIDENT"
        report.provenance_json = provenance
        _record_review(
            report,
            action="MARKED_POSSIBLE_NEW_INCIDENT",
            operator_reference=payload.operator_reference,
            at=datetime.now(timezone.utc),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        publish_operations_event(
            event="social.signal_reviewed",
            incident_id=None,
            payload=_social_signal_payload(report),
        )
    return _social_signal_payload(report)


@router.post("/social/signals/{signal_id}/associate", status_code=status.HTTP_200_OK)
def associate_social_signal(
    signal_id: str,
    payload: SocialAssociationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _acquire_write_lock(db)
    report = db.get(Report, signal_id)
    incident = db.get(Incident, payload.target_incident_id)
    if report is None or report.source_type != SOCIAL_SOURCE_TYPE:
        raise HTTPException(status_code=404, detail=f"Social signal '{signal_id}' not found")
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{payload.target_incident_id}' not found")
    if payload.expected_incident_version != incident.version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Incident version mismatch: expected {payload.expected_incident_version}, "
                f"but current version is {incident.version}"
            ),
        )
    if report.incident_id is not None:
        if report.incident_id == incident.id:
            return {
                "action": "NO_OP_ALREADY_ASSOCIATED",
                "incident_id": incident.id,
                "incident_version": incident.version,
                "signal": _social_signal_payload(report),
            }
        raise HTTPException(status_code=409, detail="social signal is associated with another incident")
    if report.processing_status == "DISMISSED":
        raise HTTPException(status_code=409, detail="dismissed social signal cannot be associated")

    now_utc = datetime.now(timezone.utc)
    previous_version = incident.version
    report.incident_id = incident.id
    report.processing_status = "ASSOCIATED"
    _record_review(
        report,
        action="ASSOCIATED",
        operator_reference=payload.operator_reference,
        at=now_utc,
    )
    incident.version += 1
    incident.updated_at = now_utc
    provenance = dict(report.provenance_json or {})
    provenance["association_outcome"] = "OPERATOR_ASSOCIATED"
    provenance["operator_association"] = {
        "incident_id": incident.id,
        "operator_reference": payload.operator_reference,
        "previous_incident_version": previous_version,
        "resulting_incident_version": incident.version,
        "associated_at": now_utc.isoformat(),
    }
    report.provenance_json = provenance
    event = TimelineEvent(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        event_type="SOCIAL_SIGNAL_ASSOCIATED",
        details_json={
            "social_signal_id": report.id,
            "provider_post_id": report.source_reference,
            "operator_reference": payload.operator_reference,
            "previous_incident_version": previous_version,
            "new_incident_version": incident.version,
            "claims_projected": False,
            "data_reality": report.data_reality.value
            if hasattr(report.data_reality, "value")
            else str(report.data_reality),
        },
        created_at=now_utc,
    )
    db.add(report)
    db.add(incident)
    db.add(event)
    db.commit()
    db.refresh(report)
    db.refresh(incident)
    publish_operations_event(
        event="timeline.appended",
        incident_id=incident.id,
        payload=serialize_timeline_event(event),
    )
    publish_operations_event(
        event="incident.updated",
        incident_id=incident.id,
        payload=serialize_incident(incident),
    )
    return {
        "action": "ASSOCIATED",
        "incident_id": incident.id,
        "incident_version": incident.version,
        "signal": _social_signal_payload(report),
    }


__all__ = ["router"]
