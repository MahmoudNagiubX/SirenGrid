from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Incident, TimelineEvent
from app.schemas import (
    DataReality,
    FreshnessStatus,
    IncidentRead,
    IncidentStatus,
    ManualIncidentCreate,
)

__all__ = [
    "router",
    "create_manual_incident",
    "serialize_incident",
    "list_incidents",
    "get_incident",
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
        "required_resources": incident.required_resources_json or [],
        "required_resources_json": incident.required_resources_json or [],
        "current_plan_id": incident.current_plan_id,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "updated_at": incident.updated_at.isoformat() if incident.updated_at else None,
        "provenance": incident.provenance_json or {},
        "provenance_json": incident.provenance_json or {},
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
        required_resources_json=required_resources,
        current_plan_id=None,
        created_at=now_utc,
        updated_at=now_utc,
        provenance_json=provenance,
    )

    # Initial timeline event for creation
    timeline_event = TimelineEvent(
        id=str(uuid.uuid4()),
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

    return serialize_incident(incident)


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

