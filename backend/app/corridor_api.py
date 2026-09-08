from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.corridor import corridor_provenance, extract_corridor_signals
from app.config import settings
from app.db import get_db
from app.hospital_api import _approved_plan
from app.models import (
    CorridorState,
    EmergencyResource,
    Incident,
    TimelineEvent,
    new_timeline_event_id,
)
from app.schemas import (
    CorridorGenerateRequest,
    CorridorPriorityRequest,
    CorridorRead,
    CorridorSignalState,
    DataReality,
)
from app.traffic_signal_gateway import TrafficSignalGateway
from app.websocket import publish_operations_event

__all__ = ["router"]

router = APIRouter(tags=["corridor"])
traffic_signal_gateway = TrafficSignalGateway()


def _acquire_write_lock(db: Session) -> None:
    bind = db.get_bind()
    if bind and bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _incident(db: Session, incident_id: str) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")
    return incident


def _approved_route(db: Session, incident: Incident, resource_id: str) -> tuple[Any, dict[str, Any], str]:
    plan = _approved_plan(db, incident)
    if resource_id not in (plan.resource_ids_json or []):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Resource is not assigned by the current approved plan")
    resource = db.get(EmergencyResource, resource_id)
    if resource is None or resource.assigned_incident_id != incident.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved route resource is not active for this incident")
    routes = plan.routes_json if isinstance(plan.routes_json, list) else []
    route = next((item for item in routes if isinstance(item, dict) and item.get("resource_id") == resource_id), None)
    if route is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved plan has no route for the requested resource")
    geometry = route.get("route_geometry") or route.get("geometry")
    if not isinstance(geometry, dict):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved route has no valid geometry")
    route_reference = str(route.get("route_id") or f"{plan.id}:{resource_id}")
    return plan, route, route_reference


def _serialize_corridor(row: CorridorState) -> dict[str, Any]:
    return CorridorRead(
        id=row.id,
        incident_id=row.incident_id,
        plan_id=row.plan_id,
        route_reference=row.route_reference,
        route_geometry=row.route_geometry_json,
        signals=row.signals_json or [],
        state=row.state,
        safety_lead_time_seconds=row.safety_lead_time_seconds,
        data_reality=row.data_reality,
        provenance=row.provenance_json or {},
        updated_at=row.updated_at.isoformat(),
    ).model_dump(mode="json")


@router.post("/incidents/{incident_id}/corridor", response_model=CorridorRead)
def generate_corridor(
    incident_id: str,
    payload: CorridorGenerateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    incident = _incident(db, incident_id)
    plan, route, route_reference = _approved_route(db, incident, payload.resource_id)
    geometry = route.get("route_geometry") or route.get("geometry")
    try:
        signals = extract_corridor_signals(
            geometry,
            float(route.get("eta_seconds")),
            now_iso=datetime.now(timezone.utc).isoformat(),
        )
    except (FileNotFoundError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Corridor asset/route unavailable: {exc}") from exc

    _acquire_write_lock(db)
    now = datetime.now(timezone.utc)
    row = db.scalars(
        select(CorridorState)
        .where(CorridorState.incident_id == incident.id, CorridorState.plan_id == plan.id, CorridorState.route_reference == route_reference)
    ).first()
    if row is None:
        row = CorridorState(
            id=str(uuid.uuid4()),
            incident_id=incident.id,
            plan_id=plan.id,
            route_reference=route_reference,
            route_geometry_json=geometry,
            signals_json=[signal.__dict__ for signal in signals],
            state=CorridorSignalState.NORMAL.value,
            safety_lead_time_seconds=settings.SIGNAL_PRIORITY_SAFETY_LEAD_TIME_SECONDS,
            version=1,
            data_reality=DataReality.REAL_DERIVED,
            provenance_json=corridor_provenance(),
            updated_at=now,
        )
        db.add(row)
        event_type = "CORRIDOR_GENERATED"
    else:
        row.route_geometry_json = geometry
        row.signals_json = [signal.__dict__ for signal in signals]
        row.version += 1
        row.updated_at = now
        event_type = "CORRIDOR_REFRESHED"
    db.add(TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident.id,
        event_type=event_type,
        details_json={
            "corridor_id": row.id,
            "plan_id": plan.id,
            "route_reference": route_reference,
            "signal_count": len(signals),
            "data_reality": DataReality.REAL_DERIVED.value,
        },
        created_at=now,
    ))
    db.commit()
    db.refresh(row)
    result = _serialize_corridor(row)
    publish_operations_event(event="route.updated", incident_id=incident.id, payload=result)
    return result


@router.get("/incidents/{incident_id}/corridor", response_model=CorridorRead)
def get_corridor(incident_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    incident = _incident(db, incident_id)
    plan = _approved_plan(db, incident)
    row = db.scalars(
        select(CorridorState)
        .where(CorridorState.incident_id == incident.id, CorridorState.plan_id == plan.id)
        .order_by(CorridorState.updated_at.desc(), CorridorState.id.desc())
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No corridor has been generated")
    return _serialize_corridor(row)


@router.post("/incidents/{incident_id}/corridor/priority", response_model=CorridorRead)
def update_corridor_priority(
    incident_id: str,
    payload: CorridorPriorityRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _acquire_write_lock(db)
    incident = _incident(db, incident_id)
    plan = _approved_plan(db, incident)
    if payload.expected_incident_version != incident.version or payload.expected_plan_version != plan.plan_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale incident or plan version")
    row = db.scalars(
        select(CorridorState)
        .where(CorridorState.incident_id == incident.id, CorridorState.plan_id == plan.id)
        .order_by(CorridorState.updated_at.desc(), CorridorState.id.desc())
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Generate the approved-route corridor first")
    try:
        gateway_result = traffic_signal_gateway.transition(row.state, payload.state)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    target_state = gateway_result.state.value
    now = datetime.now(timezone.utc)
    row.state = target_state
    row.version += 1
    row.updated_at = now
    signals = []
    for signal in row.signals_json or []:
        updated = dict(signal)
        updated["state"] = target_state
        updated["provenance"] = {
            **(updated.get("provenance") or {}),
            "priority_reality": DataReality.SIMULATED.value,
            "operator_reference": payload.operator_reference,
        }
        signals.append(updated)
    row.signals_json = signals
    db.add(TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident.id,
        event_type="CORRIDOR_PRIORITY_CHANGED",
        details_json={
            "corridor_id": row.id,
            "state": target_state,
            "operator_reference": payload.operator_reference,
            "route_eta_mutated": False,
            "data_reality": DataReality.SIMULATED.value,
        },
        created_at=now,
    ))
    db.commit()
    db.refresh(row)
    result = _serialize_corridor(row)
    publish_operations_event(event="route.updated", incident_id=incident.id, payload=result)
    return result
