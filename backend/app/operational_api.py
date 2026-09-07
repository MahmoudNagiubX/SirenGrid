from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.corridor_api import _serialize_corridor
from app.db import get_db
from app.driver_alert_api import _serialize_alert
from app.hospital_api import _approved_plan, _option_response, _serialize_destination, _serialize_prealert
from app.models import (
    CorridorState,
    DriverAlert,
    HospitalDestination,
    HospitalOptionSet,
    HospitalPreAlert,
    Incident,
)
from app.schemas import IncidentOperationalStateRead

__all__ = ["router"]

router = APIRouter(tags=["operations"])


@router.get("/incidents/{incident_id}/operational-state", response_model=IncidentOperationalStateRead)
def get_incident_operational_state(
    incident_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")

    plan = None
    if incident.current_plan_id:
        plan = _approved_plan(db, incident)

    option_response = None
    selected_destination = None
    pre_alert = None
    corridors: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    if plan is not None:
        option_set = db.scalars(
            select(HospitalOptionSet)
            .where(HospitalOptionSet.incident_id == incident.id, HospitalOptionSet.plan_id == plan.id)
            .order_by(HospitalOptionSet.created_at.desc(), HospitalOptionSet.id.desc())
        ).first()
        if option_set is not None:
            option_response = _option_response(option_set, incident)

        destination = db.scalars(
            select(HospitalDestination)
            .where(
                HospitalDestination.incident_id == incident.id,
                HospitalDestination.plan_id == plan.id,
                HospitalDestination.status.in_(("SELECTED", "INVALIDATED")),
            )
            .order_by(HospitalDestination.selected_at.desc(), HospitalDestination.id.desc())
        ).first()
        if destination is not None:
            selected_destination = _serialize_destination(destination)
            alert = db.scalars(
                select(HospitalPreAlert)
                .where(HospitalPreAlert.destination_id == destination.id)
            ).first()
            if alert is not None:
                pre_alert = _serialize_prealert(alert)

        corridor_rows = db.scalars(
            select(CorridorState)
            .where(CorridorState.incident_id == incident.id, CorridorState.plan_id == plan.id)
            .order_by(CorridorState.updated_at.desc(), CorridorState.id.desc())
        ).all()
        corridors = [_serialize_corridor(row) for row in corridor_rows]

        alert_rows = db.scalars(
            select(DriverAlert)
            .where(DriverAlert.incident_id == incident.id, DriverAlert.plan_id == plan.id)
            .order_by(DriverAlert.created_at.desc(), DriverAlert.id.desc())
        ).all()
        latest_by_resource: dict[str, DriverAlert] = {}
        for alert_row in alert_rows:
            latest_by_resource.setdefault(alert_row.resource_id, alert_row)
        alerts = [_serialize_alert(row) for row in latest_by_resource.values()]

    return IncidentOperationalStateRead(
        incident_id=incident.id,
        incident_version=incident.version,
        plan_id=plan.id if plan is not None else None,
        hospital_options=option_response,
        selected_destination=selected_destination,
        hospital_pre_alert=pre_alert,
        corridor=corridors[0] if corridors else None,
        corridors=corridors,
        driver_alert=alerts[0] if alerts else None,
        driver_alerts=alerts,
    ).model_dump(mode="json")
