from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.driver_alert import current_driver_alert, refresh_driver_alert
from app.hospital_api import _approved_plan
from app.models import DriverAlert, EmergencyResource, Incident
from app.schemas import DriverAlertRead, DriverAlertRefreshRequest
from app.websocket import publish_operations_event

__all__ = ["router"]

router = APIRouter(tags=["driver-alerts"])


def _acquire_write_lock(db: Session) -> None:
    bind = db.get_bind()
    if bind and bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _serialize_alert(alert: DriverAlert) -> dict[str, Any]:
    return DriverAlertRead(
        id=alert.id,
        incident_id=alert.incident_id,
        plan_id=alert.plan_id,
        resource_id=alert.resource_id,
        route_reference=alert.route_reference,
        route_progress=alert.route_progress,
        geometry=alert.geometry_json,
        created_at=alert.created_at.isoformat(),
        expires_at=alert.expires_at.isoformat(),
        status=alert.status,
        data_reality=alert.data_reality,
        provenance=alert.provenance_json or {},
    ).model_dump(mode="json")


def _context(db: Session, incident_id: str, resource_id: str) -> tuple[Incident, Any, EmergencyResource]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")
    plan = _approved_plan(db, incident)
    resource = db.get(EmergencyResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Emergency resource '{resource_id}' not found")
    if resource.assigned_incident_id != incident.id or resource.id not in (plan.resource_ids_json or []):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Resource is not on the current approved response route")
    return incident, plan, resource


@router.post(
    "/incidents/{incident_id}/resources/{resource_id}/driver-alert/refresh",
    response_model=DriverAlertRead,
)
def refresh_alert(
    incident_id: str,
    resource_id: str,
    payload: DriverAlertRefreshRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _acquire_write_lock(db)
    incident, plan, resource = _context(db, incident_id, resource_id)
    if resource.version != payload.expected_resource_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale resource version")
    try:
        alert = refresh_driver_alert(
            db,
            incident=incident,
            plan=plan,
            resource=resource,
            operator_reference=payload.operator_reference,
            now=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if alert is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No driver alert state could be created")
    db.commit()
    db.refresh(alert)
    result = _serialize_alert(alert)
    publish_operations_event(event="resource.updated", incident_id=incident.id, payload=result)
    return result


@router.get(
    "/incidents/{incident_id}/resources/{resource_id}/driver-alert",
    response_model=DriverAlertRead,
)
def get_alert(
    incident_id: str,
    resource_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")
    plan = _approved_plan(db, incident)
    alert = current_driver_alert(
        db,
        incident_id=incident.id,
        plan_id=plan.id,
        resource_id=resource_id,
    )
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No driver alert state exists")
    return _serialize_alert(alert)
