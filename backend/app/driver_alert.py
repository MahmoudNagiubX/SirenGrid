from __future__ import annotations

from datetime import datetime, timedelta
import json
import uuid
from typing import Any

from pyproj import Transformer
from shapely.geometry import LineString, mapping
from shapely.ops import substring, transform
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DriverAlert, EmergencyResource, Incident, ResponsePlan, TimelineEvent, new_timeline_event_id

__all__ = [
    "DriverAlertGateway",
    "refresh_driver_alert",
    "current_driver_alert",
    "build_forward_alert_geometry",
]


_TO_METERS = Transformer.from_crs("EPSG:4326", "EPSG:32636", always_xy=True).transform
_TO_WGS84 = Transformer.from_crs("EPSG:32636", "EPSG:4326", always_xy=True).transform


class DriverAlertGateway:
    """Simulation boundary for geographic alert delivery."""

    data_reality = "SIMULATED"

    def delivery_state(self, *, geometry: dict[str, Any] | None) -> str:
        return "SIMULATED_DELIVERED" if geometry is not None else "SIMULATED_EXPIRED"


driver_alert_gateway = DriverAlertGateway()


def _route_for_resource(plan: ResponsePlan, resource_id: str) -> tuple[dict[str, Any], str]:
    routes = plan.routes_json if isinstance(plan.routes_json, list) else []
    route = next((item for item in routes if isinstance(item, dict) and item.get("resource_id") == resource_id), None)
    if route is None:
        raise ValueError("Approved plan has no route for the resource")
    geometry = route.get("geometry") or route.get("route_geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        raise ValueError("Approved route geometry is not a LineString")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("Approved route geometry has insufficient coordinates")
    return route, str(route.get("route_id") or f"{plan.id}:{resource_id}")


def build_forward_alert_geometry(
    route_geometry: dict[str, Any],
    route_progress: float,
) -> dict[str, Any] | None:
    """Return a buffered WGS84 polygon for only the route ahead of progress."""
    line = LineString(route_geometry["coordinates"])
    metric_line = transform(_TO_METERS, line)
    route_length = metric_line.length
    if route_length <= 0:
        raise ValueError("Approved route geometry must have positive length")
    start = route_length * route_progress
    if start >= route_length:
        return None
    end = min(route_length, start + settings.DRIVER_ALERT_LOOKAHEAD_METERS)
    forward = substring(metric_line, start, end)
    buffered = forward.buffer(settings.DRIVER_ALERT_BUFFER_METERS)
    polygon = transform(_TO_WGS84, buffered)
    return json.loads(json.dumps(mapping(polygon)))


def _expire_active_alerts(
    db: Session,
    *,
    incident_id: str,
    plan_id: str,
    resource_id: str,
    now: datetime,
) -> None:
    active = db.scalars(
        select(DriverAlert).where(
            DriverAlert.incident_id == incident_id,
            DriverAlert.plan_id == plan_id,
            DriverAlert.resource_id == resource_id,
            DriverAlert.status == "ACTIVE",
        )
    ).all()
    for alert in active:
        alert.status = "EXPIRED"
        db.add(TimelineEvent(
            id=new_timeline_event_id(),
            incident_id=incident_id,
            event_type="DRIVER_ALERT_EXPIRED",
            details_json={
                "driver_alert_id": alert.id,
                "resource_id": resource_id,
                "route_reference": alert.route_reference,
                "data_reality": "SIMULATED",
            },
            created_at=now,
        ))


def refresh_driver_alert(
    db: Session,
    *,
    incident: Incident,
    plan: ResponsePlan,
    resource: EmergencyResource,
    operator_reference: str,
    now: datetime,
    create_terminal_state: bool = True,
) -> DriverAlert | None:
    movement = (resource.provenance_json or {}).get("movement")
    if not isinstance(movement, dict):
        raise ValueError("Resource has no explicit route_progress state")
    progress = movement.get("route_progress")
    if not isinstance(progress, (int, float)) or isinstance(progress, bool) or not 0.0 <= float(progress) <= 1.0:
        raise ValueError("Resource route_progress is invalid")
    route, route_reference = _route_for_resource(plan, resource.id)
    geometry = route.get("geometry") or route.get("route_geometry")
    alert_geometry = build_forward_alert_geometry(geometry, float(progress))
    _expire_active_alerts(
        db,
        incident_id=incident.id,
        plan_id=plan.id,
        resource_id=resource.id,
        now=now,
    )
    if alert_geometry is None and not create_terminal_state:
        return None
    status = "ACTIVE" if alert_geometry is not None else "EXPIRED"
    alert = DriverAlert(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        plan_id=plan.id,
        resource_id=resource.id,
        route_reference=route_reference,
        route_progress=float(progress),
        geometry_json=alert_geometry,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.DRIVER_ALERT_EXPIRY_SECONDS),
        status=status,
        version=1,
        data_reality="SIMULATED",
        provenance_json={
            "source": "SIMULATED_DRIVER_ALERT_GATEWAY",
            "data_reality": "SIMULATED",
            "freshness_status": "FRESH",
            "source_reference": operator_reference,
            "route_reference": route_reference,
            "route_progress": float(progress),
            "lookahead_m": settings.DRIVER_ALERT_LOOKAHEAD_METERS,
            "buffer_m": settings.DRIVER_ALERT_BUFFER_METERS,
            "expiry_seconds": settings.DRIVER_ALERT_EXPIRY_SECONDS,
            "geometry_reality": "REAL_DERIVED",
            "delivery_state": driver_alert_gateway.delivery_state(geometry=alert_geometry),
        },
    )
    db.add(alert)
    db.add(TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident.id,
        event_type="DRIVER_ALERT_REFRESHED" if status == "ACTIVE" else "DRIVER_ALERT_EXPIRED",
        details_json={
            "driver_alert_id": alert.id,
            "resource_id": resource.id,
            "route_reference": route_reference,
            "route_progress": float(progress),
            "status": status,
            "data_reality": "SIMULATED",
        },
        created_at=now,
    ))
    return alert


def current_driver_alert(
    db: Session,
    *,
    incident_id: str,
    plan_id: str,
    resource_id: str,
) -> DriverAlert | None:
    return db.scalars(
        select(DriverAlert)
        .where(
            DriverAlert.incident_id == incident_id,
            DriverAlert.plan_id == plan_id,
            DriverAlert.resource_id == resource_id,
        )
        .order_by(DriverAlert.created_at.desc(), DriverAlert.id.desc())
    ).first()
