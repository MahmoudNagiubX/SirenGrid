from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    EmergencyResource,
    Incident,
    Report,
    ResponsePlan,
    TimelineEvent,
    new_timeline_event_id,
)
from app.schemas import (
    DataReality,
    FreshnessStatus,
    IncidentCancelRequest,
    IncidentCloseRequest,
    IncidentFactsPatchRequest,
    IncidentFactsPatchResponse,
    IncidentRead,
    IncidentStatus,
    IncidentTransitionRequest,
    ManualIncidentCreate,
    ReportCreate,
    ReportRead,
    ResourceStatus,
    ResponsePlanStatus,
    TimelineEventRead,
)
from app.websocket import publish_operations_event

__all__ = [
    "router",
    "create_manual_incident",
    "serialize_incident",
    "serialize_report",
    "serialize_timeline_event",
    "list_incidents",
    "get_incident",
    "get_incident_timeline",
    "patch_incident_facts",
    "create_incident_report",
    "list_incident_reports",
    "create_standalone_report",
    "get_report",
    "transition_incident_lifecycle",
    "close_incident",
    "cancel_incident",
    "committed_response_blockers",
    "LOCKED_FORWARD_TRANSITIONS",
    "PLANNING_INPUT_FACT_FIELDS",
    "NON_ACTIONABLE_INCIDENT_STATUSES",
    "is_incident_actionable",
    "ensure_incident_actionable",
]

router = APIRouter(tags=["incidents"])


def serialize_incident(incident: Incident) -> dict[str, Any]:
    """Serialize an Incident ORM instance into a frontend-agnostic dictionary."""
    status_str = (
        incident.status.value
        if hasattr(incident.status, "value")
        else str(incident.status)
    )
    severity_str = (
        incident.severity.value
        if hasattr(incident.severity, "value")
        else str(incident.severity)
    )
    confidence_str = (
        incident.confidence_level.value
        if hasattr(incident.confidence_level, "value")
        else str(incident.confidence_level)
    )
    return {
        "id": incident.id,
        "version": incident.version,
        "status": status_str,
        "incident_type": incident.incident_type,
        "severity": severity_str,
        "confidence_level": confidence_str,
        "location": {
            "lat": incident.latitude,
            "lon": incident.longitude,
        },
        "latitude": incident.latitude,
        "longitude": incident.longitude,
        "location_text": incident.location_text,
        "casualty_count": incident.casualty_count,
        "casualty_range": incident.casualty_range,
        "trapped_person": incident.trapped_person,
        "road_blockage": incident.road_blockage,
        "transport_required": incident.transport_required,
        "required_hospital_capabilities": incident.required_hospital_capabilities_json or [],
        "required_resources": incident.required_resources_json or [],
        "required_resources_json": incident.required_resources_json or [],
        "current_plan_id": incident.current_plan_id,
        "pending_replan_plan_id": incident.pending_replan_plan_id,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "updated_at": incident.updated_at.isoformat() if incident.updated_at else None,
        "provenance": incident.provenance_json or {},
        "provenance_json": incident.provenance_json or {},
    }


LOCKED_FORWARD_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.RECEIVED: {IncidentStatus.INTERPRETING},
    IncidentStatus.INTERPRETING: {IncidentStatus.ACTIVE_UNCONFIRMED},
    IncidentStatus.ACTIVE_UNCONFIRMED: {IncidentStatus.RESPONSE_PROPOSED},
    IncidentStatus.RESPONSE_PROPOSED: {IncidentStatus.AWAITING_APPROVAL},
    IncidentStatus.AWAITING_APPROVAL: {IncidentStatus.RESPONSE_ACTIVE},
    IncidentStatus.RESPONSE_ACTIVE: {IncidentStatus.EN_ROUTE},
    IncidentStatus.EN_ROUTE: {IncidentStatus.ON_SCENE},
    IncidentStatus.ON_SCENE: {IncidentStatus.TRANSPORT_ACTIVE, IncidentStatus.HANDOVER},
    IncidentStatus.TRANSPORT_ACTIVE: {IncidentStatus.HANDOVER},
    IncidentStatus.HANDOVER: {IncidentStatus.CLOSED},
    IncidentStatus.CLOSED: set(),
    IncidentStatus.REQUIRES_REVIEW: set(),
    IncidentStatus.DUPLICATE_MERGED: set(),
    IncidentStatus.CANCELLED_FALSE_REPORT: set(),
}


NON_ACTIONABLE_INCIDENT_STATUSES: frozenset[IncidentStatus] = frozenset(
    {
        IncidentStatus.CLOSED,
        IncidentStatus.CANCELLED_FALSE_REPORT,
        IncidentStatus.DUPLICATE_MERGED,
        IncidentStatus.REQUIRES_REVIEW,
    }
)


def is_incident_actionable(incident: Incident) -> bool:
    """Return whether operational planning may act on this incident.

    Closed and cancelled incidents are terminal. A duplicate that has been
    merged into a canonical incident must never be revived by planning, and a
    review-held incident must wait for the operator to resolve it.
    """
    return incident.status not in NON_ACTIONABLE_INCIDENT_STATUSES


def ensure_incident_actionable(incident: Incident, action: str) -> None:
    """Reject an operational action on a non-actionable incident with 409."""
    if is_incident_actionable(incident):
        return
    status_value = (
        incident.status.value
        if hasattr(incident.status, "value")
        else str(incident.status)
    )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Cannot {action} for incident with status {status_value}",
    )


COMMITTED_RESOURCE_STATUSES: frozenset[ResourceStatus] = frozenset(
    {
        ResourceStatus.ASSIGNED,
        ResourceStatus.EN_ROUTE,
        ResourceStatus.ON_SCENE,
        ResourceStatus.TRANSPORTING,
    }
)
CANCELLABLE_TERMINAL_STATUSES: frozenset[IncidentStatus] = frozenset(
    {
        IncidentStatus.CLOSED,
        IncidentStatus.DUPLICATE_MERGED,
        IncidentStatus.CANCELLED_FALSE_REPORT,
    }
)


def committed_response_blockers(db: Session, incident: Incident) -> list[str]:
    """Return reasons an incident already has a committed operational response.

    Cancelling a false report must never silently demobilize responders that
    are already committed, so an approved active plan or any committed
    responder blocks the command.
    """
    blockers: list[str] = []
    if incident.current_plan_id:
        plan = db.get(ResponsePlan, incident.current_plan_id)
        if plan is not None and plan.status == ResponsePlanStatus.APPROVED:
            blockers.append(f"approved response plan '{plan.id}' is active")

    committed = db.scalars(
        select(EmergencyResource)
        .where(EmergencyResource.assigned_incident_id == incident.id)
        .order_by(EmergencyResource.id.asc())
    ).all()
    for resource in committed:
        status_value = (
            resource.status.value
            if hasattr(resource.status, "value")
            else str(resource.status)
        )
        if resource.status in COMMITTED_RESOURCE_STATUSES:
            blockers.append(f"resource '{resource.id}' is {status_value}")
    return blockers


def _acquire_write_lock(db: Session) -> None:
    """Execute BEGIN IMMEDIATE on SQLite to serialize concurrent operations in one process."""
    bind = db.get_bind()
    if bind and bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def serialize_report(report: Report) -> dict[str, Any]:
    """Serialize a Report ORM instance into a frontend-agnostic dictionary."""
    data_reality_str = (
        report.data_reality.value
        if hasattr(report.data_reality, "value")
        else str(report.data_reality)
    )
    loc_coord = None
    if report.location_json and "lat" in report.location_json and "lon" in report.location_json:
        loc_coord = {
            "lat": report.location_json["lat"],
            "lon": report.location_json["lon"],
        }
    return {
        "id": report.id,
        "incident_id": report.incident_id,
        "source_type": report.source_type,
        "source_reference": report.source_reference,
        "raw_text": report.raw_text,
        "location_text": report.location_text,
        "location": loc_coord,
        "location_json": report.location_json,
        "received_at": report.received_at.isoformat() if report.received_at else None,
        "data_reality": data_reality_str,
        "provenance": report.provenance_json or {},
        "provenance_json": report.provenance_json or {},
        "processing_status": report.processing_status,
        "evidence_items": report.evidence_items_json or [],
        "evidence_items_json": report.evidence_items_json or [],
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


PLANNING_INPUT_FACT_FIELDS: set[str] = {
    "location",
    "required_resources",
    "transport_required",
    "required_hospital_capabilities",
}
FACT_FIELD_NAMES: set[str] = {
    "incident_type",
    "severity",
    "confidence_level",
    "location",
    "location_text",
    "casualty_count",
    "casualty_range",
    "trapped_person",
    "road_blockage",
    "transport_required",
    "required_hospital_capabilities",
    "required_resources",
}


def serialize_timeline_event(event: TimelineEvent) -> dict[str, Any]:
    """Serialize a TimelineEvent ORM instance into a frontend-agnostic dictionary."""
    return {
        "id": event.id,
        "incident_id": event.incident_id,
        "event_type": event.event_type,
        "details": event.details_json or {},
        "details_json": event.details_json or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


@router.post(
    "/intake/manual",
    status_code=status.HTTP_201_CREATED,
    response_model=IncidentRead,
)
def create_manual_incident(
    payload: ManualIncidentCreate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Process manual operator-entered structured incident intake.

    Validates operator input, assigns an initial active status (ACTIVE_UNCONFIRMED),
    records full provenance metadata indicating simulated manual entry, logs the initial
    timeline creation event, and commits the incident transactionally to the operational DB.
    """
    incident_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)

    # Required resources as JSON-safe enum strings and counts
    required_resources = [
        {
            "resource_type": req.resource_type.value,
            "count": req.count,
        }
        for req in payload.required_resources
    ]

    # Provenance for manual simulated demo world
    provenance = {
        "source": "operator_manual_entry",
        "data_reality": DataReality.SIMULATED.value,
        "freshness_status": FreshnessStatus.FRESH.value,
        "last_updated": now_utc.isoformat(),
        "source_reference": payload.operator_reference,
    }

    # Incident model instance
    incident = Incident(
        id=incident_id,
        version=1,
        incident_type=payload.incident_type,
        severity=payload.severity,
        confidence_level=payload.confidence_level,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=payload.location.lat,
        longitude=payload.location.lon,
        location_text=payload.location_text,
        casualty_count=payload.casualty_count,
        casualty_range=payload.casualty_range,
        trapped_person=payload.trapped_person,
        road_blockage=payload.road_blockage,
        transport_required=payload.transport_required,
        required_hospital_capabilities_json=payload.required_hospital_capabilities,
        required_resources_json=required_resources,
        current_plan_id=None,
        created_at=now_utc,
        updated_at=now_utc,
        provenance_json=provenance,
    )

    # Initial timeline event for creation
    timeline_event = TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident_id,
        event_type="INCIDENT_CREATED",
        details_json={
            "operator_reference": payload.operator_reference,
            "status": IncidentStatus.ACTIVE_UNCONFIRMED.value,
            "source": "operator_manual_entry",
        },
        created_at=now_utc,
    )

    # Atomic transaction
    db.add(incident)
    db.add(timeline_event)
    db.commit()
    db.refresh(incident)

    result = serialize_incident(incident)
    publish_operations_event(
        event="incident.created",
        incident_id=incident.id,
        payload=result,
    )
    return result

@router.get(
    "/incidents",
    status_code=status.HTTP_200_OK,
    response_model=list[IncidentRead],
)
def list_incidents(
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Retrieve all persisted incidents ordered deterministically by creation time descending then ID ascending."""
    stmt = select(Incident).order_by(Incident.created_at.desc(), Incident.id.asc())
    incidents = db.scalars(stmt).all()
    return [serialize_incident(inc) for inc in incidents]


@router.get(
    "/incidents/{incident_id}",
    status_code=status.HTTP_200_OK,
    response_model=IncidentRead,
)
def get_incident(
    incident_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve detailed state for a specific incident by unique identifier."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    return serialize_incident(incident)


@router.post(
    "/incidents/{incident_id}/reports",
    status_code=status.HTTP_201_CREATED,
    response_model=ReportRead,
)
def create_incident_report(
    incident_id: str,
    payload: ReportCreate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )

    now_utc = datetime.now(timezone.utc)
    received_at = payload.received_at or now_utc

    location_json = payload.location.model_dump() if payload.location else None
    provenance = payload.provenance or {
        "source": payload.source_type,
        "data_reality": payload.data_reality.value,
        "freshness_status": FreshnessStatus.FRESH.value,
        "last_updated": now_utc.isoformat(),
        "source_reference": payload.source_reference,
    }

    evidence_items = [
        {
            "type": item.type,
            "uri_or_reference": item.uri_or_reference,
            "extracted_facts": item.extracted_facts,
            "provenance": item.provenance or {
                "source": payload.source_type,
                "data_reality": payload.data_reality.value,
            },
            "confidence_support": item.confidence_support,
            "created_at": item.created_at.isoformat() if item.created_at else now_utc.isoformat(),
        }
        for item in payload.evidence_items
    ]

    report = Report(
        id=str(uuid.uuid4()),
        incident_id=incident_id,
        source_type=payload.source_type,
        source_reference=payload.source_reference,
        raw_text=payload.raw_text,
        location_text=payload.location_text,
        location_json=location_json,
        received_at=received_at,
        data_reality=payload.data_reality,
        provenance_json=provenance,
        processing_status=payload.processing_status,
        evidence_items_json=evidence_items,
        created_at=now_utc,
    )

    timeline_event = TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident_id,
        event_type="REPORT_CREATED",
        details_json={
            "report_id": report.id,
            "source_type": payload.source_type,
            "source_reference": payload.source_reference,
            "data_reality": payload.data_reality.value,
            "processing_status": payload.processing_status,
            "evidence_count": len(evidence_items),
        },
        created_at=now_utc,
    )

    db.add(report)
    db.add(timeline_event)
    db.commit()
    db.refresh(report)

    result = serialize_report(report)
    publish_operations_event(
        event="timeline.appended",
        incident_id=incident_id,
        payload=serialize_timeline_event(timeline_event),
    )
    return result


@router.get(
    "/incidents/{incident_id}/reports",
    status_code=status.HTTP_200_OK,
    response_model=list[ReportRead],
)
def list_incident_reports(
    incident_id: str,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    stmt = (
        select(Report)
        .where(Report.incident_id == incident_id)
        .order_by(Report.created_at.asc(), Report.id.asc())
    )
    reports = db.scalars(stmt).all()
    return [serialize_report(r) for r in reports]


@router.post(
    "/reports",
    status_code=status.HTTP_201_CREATED,
    response_model=ReportRead,
)
def create_standalone_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.incident_id:
        incident = db.get(Incident, payload.incident_id)
        if incident is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident '{payload.incident_id}' not found",
            )

    now_utc = datetime.now(timezone.utc)
    received_at = payload.received_at or now_utc

    location_json = payload.location.model_dump() if payload.location else None
    provenance = payload.provenance or {
        "source": payload.source_type,
        "data_reality": payload.data_reality.value,
        "freshness_status": FreshnessStatus.FRESH.value,
        "last_updated": now_utc.isoformat(),
        "source_reference": payload.source_reference,
    }

    evidence_items = [
        {
            "type": item.type,
            "uri_or_reference": item.uri_or_reference,
            "extracted_facts": item.extracted_facts,
            "provenance": item.provenance or {
                "source": payload.source_type,
                "data_reality": payload.data_reality.value,
            },
            "confidence_support": item.confidence_support,
            "created_at": item.created_at.isoformat() if item.created_at else now_utc.isoformat(),
        }
        for item in payload.evidence_items
    ]

    report = Report(
        id=str(uuid.uuid4()),
        incident_id=payload.incident_id,
        source_type=payload.source_type,
        source_reference=payload.source_reference,
        raw_text=payload.raw_text,
        location_text=payload.location_text,
        location_json=location_json,
        received_at=received_at,
        data_reality=payload.data_reality,
        provenance_json=provenance,
        processing_status=payload.processing_status,
        evidence_items_json=evidence_items,
        created_at=now_utc,
    )

    db.add(report)

    if payload.incident_id:
        timeline_event = TimelineEvent(
            id=new_timeline_event_id(),
            incident_id=payload.incident_id,
            event_type="REPORT_CREATED",
            details_json={
                "report_id": report.id,
                "source_type": payload.source_type,
                "source_reference": payload.source_reference,
                "data_reality": payload.data_reality.value,
                "processing_status": payload.processing_status,
                "evidence_count": len(evidence_items),
            },
            created_at=now_utc,
        )
        db.add(timeline_event)

    db.commit()
    db.refresh(report)

    result = serialize_report(report)
    if payload.incident_id and timeline_event is not None:
        publish_operations_event(
            event="timeline.appended",
            incident_id=payload.incident_id,
            payload=serialize_timeline_event(timeline_event),
        )
    return result


@router.get(
    "/reports/{report_id}",
    status_code=status.HTTP_200_OK,
    response_model=ReportRead,
)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found",
        )
    return serialize_report(report)


@router.post(
    "/incidents/{incident_id}/transition",
    status_code=status.HTTP_200_OK,
    response_model=IncidentRead,
)
def transition_incident_lifecycle(
    incident_id: str,
    payload: IncidentTransitionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _acquire_write_lock(db)

    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )

    if payload.expected_incident_version != incident.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Incident version mismatch: expected {payload.expected_incident_version}, "
                f"but current version is {incident.version}"
            ),
        )

    allowed = LOCKED_FORWARD_TRANSITIONS.get(incident.status, set())
    if payload.target_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Illegal lifecycle transition from '{incident.status.value}' to '{payload.target_status.value}'. "
                f"Allowed transitions: {sorted(s.value for s in allowed)}"
            ),
        )

    now_utc = datetime.now(timezone.utc)
    from_status = incident.status
    previous_version = incident.version

    incident.status = payload.target_status
    incident.version = previous_version + 1
    incident.updated_at = now_utc

    timeline_event = TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident.id,
        event_type="LIFECYCLE_TRANSITION",
        details_json={
            "from_status": from_status.value,
            "to_status": payload.target_status.value,
            "previous_version": previous_version,
            "new_version": incident.version,
            "operator_reference": payload.operator_reference,
            "reason": payload.reason,
        },
        created_at=now_utc,
    )

    db.add(incident)
    db.add(timeline_event)
    db.commit()
    db.refresh(incident)

    result = serialize_incident(incident)
    publish_operations_event(
        event="incident.updated",
        incident_id=incident.id,
        payload=result,
    )
    return result


@router.post(
    "/incidents/{incident_id}/close",
    status_code=status.HTTP_200_OK,
    response_model=IncidentRead,
)
def close_incident(
    incident_id: str,
    payload: IncidentCloseRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    transition_req = IncidentTransitionRequest(
        target_status=IncidentStatus.CLOSED,
        expected_incident_version=payload.expected_incident_version,
        operator_reference=payload.operator_reference,
        reason=payload.reason or "Incident closed via close endpoint",
    )
    return transition_incident_lifecycle(
        incident_id=incident_id,
        payload=transition_req,
        db=db,
    )


@router.post(
    "/incidents/{incident_id}/cancel",
    status_code=status.HTTP_200_OK,
    response_model=IncidentRead,
)
def cancel_incident(
    incident_id: str,
    payload: IncidentCancelRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cancel an incident that turned out to be a false report.

    This is only safe before an operational response is committed. If an
    approved plan is active or any responder is committed to the incident, the
    command is rejected with 409 so responders are never silently demobilized;
    controlled operator resolution is required instead.

    Unapproved candidate plans are superseded and the pending pointers are
    cleared so the cancelled incident cannot be approved or replanned later.
    """
    _acquire_write_lock(db)

    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )

    if incident.status in CANCELLABLE_TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"INCIDENT_NOT_CANCELLABLE: incident is already "
                f"{incident.status.value}"
            ),
        )

    if payload.expected_incident_version != incident.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Incident version mismatch: expected {payload.expected_incident_version}, "
                f"but current version is {incident.version}"
            ),
        )

    blockers = committed_response_blockers(db, incident)
    if blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "RESPONSE_ALREADY_COMMITTED: cannot cancel as a false report "
                "because " + "; ".join(blockers) + ". Controlled operator "
                "resolution is required instead."
            ),
        )

    now_utc = datetime.now(timezone.utc)
    previous_status = incident.status
    previous_version = incident.version

    superseded_plan_ids: list[str] = []
    open_plans = db.scalars(
        select(ResponsePlan)
        .where(ResponsePlan.incident_id == incident.id)
        .order_by(ResponsePlan.plan_version.asc(), ResponsePlan.id.asc())
    ).all()
    for plan in open_plans:
        if plan.status in (
            ResponsePlanStatus.CANDIDATE,
            ResponsePlanStatus.RECOMMENDED,
            ResponsePlanStatus.ALTERNATIVE,
        ):
            plan.status = ResponsePlanStatus.SUPERSEDED
            superseded_plan_ids.append(plan.id)
            db.add(plan)

    incident.status = IncidentStatus.CANCELLED_FALSE_REPORT
    incident.current_plan_id = None
    incident.pending_replan_plan_id = None
    incident.version = previous_version + 1
    incident.updated_at = now_utc

    timeline_event = TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident.id,
        event_type="INCIDENT_CANCELLED",
        details_json={
            "from_status": previous_status.value,
            "to_status": IncidentStatus.CANCELLED_FALSE_REPORT.value,
            "previous_version": previous_version,
            "new_version": incident.version,
            "operator_reference": payload.operator_reference,
            "reason_code": payload.reason_code,
            "reason": payload.reason,
            "superseded_plan_ids": superseded_plan_ids,
        },
        created_at=now_utc,
    )

    db.add(incident)
    db.add(timeline_event)
    db.commit()
    db.refresh(incident)

    result = serialize_incident(incident)
    publish_operations_event(
        event="incident.updated",
        incident_id=incident.id,
        payload=result,
    )
    return result


@router.get(
    "/incidents/{incident_id}/timeline",
    status_code=status.HTTP_200_OK,
    response_model=list[TimelineEventRead],
)
def get_incident_timeline(
    incident_id: str,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Retrieve all timeline events for an incident in deterministic ascending created_at then id order."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    stmt = (
        select(TimelineEvent)
        .where(TimelineEvent.incident_id == incident_id)
        .order_by(TimelineEvent.created_at.asc(), TimelineEvent.id.asc())
    )
    events = db.scalars(stmt).all()
    return [serialize_timeline_event(e) for e in events]


@router.patch(
    "/incidents/{incident_id}/facts",
    status_code=status.HTTP_200_OK,
    response_model=IncidentFactsPatchResponse,
)
def patch_incident_facts(
    incident_id: str,
    payload: IncidentFactsPatchRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Atomically patch typed incident facts with single version increment, audit event, and dirty flag."""
    _acquire_write_lock(db)

    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )

    if payload.expected_incident_version != incident.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Incident version mismatch: expected {payload.expected_incident_version}, "
                f"but current version is {incident.version}"
            ),
        )

    provided_fields = payload.model_fields_set.intersection(FACT_FIELD_NAMES)

    changed_fields: list[str] = []
    old_values: dict[str, Any] = {}
    new_values: dict[str, Any] = {}

    for field in sorted(provided_fields):
        if field == "incident_type":
            old_val = incident.incident_type
            new_val = payload.incident_type
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "severity":
            old_val = incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity)
            new_val = payload.severity.value if hasattr(payload.severity, "value") else str(payload.severity)
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "confidence_level":
            old_val = incident.confidence_level.value if hasattr(incident.confidence_level, "value") else str(incident.confidence_level)
            new_val = payload.confidence_level.value if hasattr(payload.confidence_level, "value") else str(payload.confidence_level)
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "location":
            old_val = {"lat": incident.latitude, "lon": incident.longitude}
            new_val = {"lat": payload.location.lat, "lon": payload.location.lon}
            if abs(incident.latitude - payload.location.lat) > 1e-7 or abs(incident.longitude - payload.location.lon) > 1e-7:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "location_text":
            old_val = incident.location_text
            new_val = payload.location_text
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "casualty_count":
            old_val = incident.casualty_count
            new_val = payload.casualty_count
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "casualty_range":
            old_val = incident.casualty_range
            new_val = payload.casualty_range
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "trapped_person":
            old_val = incident.trapped_person
            new_val = payload.trapped_person
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "road_blockage":
            old_val = incident.road_blockage
            new_val = payload.road_blockage
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "transport_required":
            old_val = incident.transport_required
            new_val = payload.transport_required
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "required_hospital_capabilities":
            old_val = list(incident.required_hospital_capabilities_json or [])
            new_val = sorted(set(payload.required_hospital_capabilities or []))
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val
        elif field == "required_resources":
            old_val = list(incident.required_resources_json or [])
            new_val = [
                {"resource_type": req.resource_type.value, "count": req.count}
                for req in payload.required_resources
            ]
            if new_val != old_val:
                changed_fields.append(field)
                old_values[field] = old_val
                new_values[field] = new_val

    # Semantic no-op: return 200 with unchanged incident and no version increment or event
    if not changed_fields:
        return {
            "incident": serialize_incident(incident),
            "changed_fields": [],
            "downstream_inputs_dirty": False,
        }

    now_utc = datetime.now(timezone.utc)
    downstream_inputs_dirty = any(f in PLANNING_INPUT_FACT_FIELDS for f in changed_fields)

    # Mutate accepted changes atomically
    for field in changed_fields:
        if field == "incident_type":
            incident.incident_type = payload.incident_type
        elif field == "severity":
            incident.severity = payload.severity
        elif field == "confidence_level":
            incident.confidence_level = payload.confidence_level
        elif field == "location":
            incident.latitude = payload.location.lat
            incident.longitude = payload.location.lon
        elif field == "location_text":
            incident.location_text = payload.location_text
        elif field == "casualty_count":
            incident.casualty_count = payload.casualty_count
        elif field == "casualty_range":
            incident.casualty_range = payload.casualty_range
        elif field == "trapped_person":
            incident.trapped_person = payload.trapped_person
        elif field == "road_blockage":
            incident.road_blockage = payload.road_blockage
        elif field == "transport_required":
            incident.transport_required = payload.transport_required
        elif field == "required_hospital_capabilities":
            incident.required_hospital_capabilities_json = new_values[field]
        elif field == "required_resources":
            incident.required_resources_json = new_values[field]

    # Increment version exactly once
    incident.version = incident.version + 1
    incident.updated_at = now_utc

    # Update provenance_json with operator-corrected field map
    provenance = dict(incident.provenance_json or {})
    provenance["last_updated"] = now_utc.isoformat()
    corrected_fields = dict(provenance.get("corrected_fields", {}))
    for field in changed_fields:
        corrected_fields[field] = {
            "source": "operator_correction",
            "operator_reference": payload.operator_reference,
            "data_reality": DataReality.SIMULATED.value,
            "freshness": FreshnessStatus.FRESH.value,
            "freshness_status": FreshnessStatus.FRESH.value,
            "timestamp": now_utc.isoformat(),
        }
    provenance["corrected_fields"] = corrected_fields
    provenance["operator_corrected_fields"] = corrected_fields
    incident.provenance_json = provenance

    # Exactly one FACTS_CORRECTED TimelineEvent
    changes_dict = {
        field: {
            "old": old_values[field],
            "new": new_values[field],
            "old_value": old_values[field],
            "new_value": new_values[field],
        }
        for field in changed_fields
    }
    event_details = {
        "operator_reference": payload.operator_reference,
        "timestamp": now_utc.isoformat(),
        "correction_timestamp": now_utc.isoformat(),
        "changed_fields": list(changed_fields),
        "downstream_inputs_dirty": downstream_inputs_dirty,
        "changes": changes_dict,
    }
    for field, change_info in changes_dict.items():
        event_details[field] = change_info

    timeline_event = TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident.id,
        event_type="FACTS_CORRECTED",
        details_json=event_details,
        created_at=now_utc,
    )

    db.add(incident)
    db.add(timeline_event)
    db.commit()
    db.refresh(incident)

    if downstream_inputs_dirty and incident.current_plan_id:
        active_plan = db.get(ResponsePlan, incident.current_plan_id)
        if active_plan is not None and getattr(active_plan.status, "value", active_plan.status) == "APPROVED":
            # Corrections are already authoritative and versioned by this
            # endpoint. Replanning is a separate pending evaluation and does
            # not mutate the active approved plan.
            from app.replanning import record_replan_trigger

            record_replan_trigger(
                db,
                incident_id=incident.id,
                expected_incident_version=incident.version,
                trigger_reasons=["INCIDENT_FACT_CHANGED"],
                input_references={
                    "changed_fields": list(changed_fields),
                    "changed_values": new_values,
                    "requirements_changed": True,
                },
                now=now_utc,
            )

    serialized_incident = serialize_incident(incident)
    publish_operations_event(
        event="incident.updated",
        incident_id=incident.id,
        payload=serialized_incident,
    )

    return {
        "incident": serialized_incident,
        "changed_fields": changed_fields,
        "downstream_inputs_dirty": downstream_inputs_dirty,
    }
