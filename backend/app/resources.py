from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.driver_alert import refresh_driver_alert
from app.models import (
    EmergencyResource,
    Incident,
    ResponsePlan,
    TimelineEvent,
    new_timeline_event_id,
)
from app.routing import haversine_distance_m
from app.schemas import (
    DataReality,
    FreshnessStatus,
    ResourceAssignRequest,
    ResourceMovementRequest,
    ResourceRead,
    ResourceReleaseRequest,
    ResourceStatePatchRequest,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
)
from app.websocket import publish_operations_event

__all__ = [
    "router",
    "is_planner_eligible",
    "serialize_resource",
    "interpolate_route_progress",
    "list_resources",
    "get_resource",
    "assign_resource",
    "patch_resource_state",
    "release_resource",
    "patch_resource_movement",
]

router = APIRouter(tags=["resources"])


def _acquire_write_lock(db: Session) -> None:
    """Execute BEGIN IMMEDIATE on SQLite to serialize concurrent operations in one process."""
    bind = db.get_bind()
    if bind and bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def is_planner_eligible(resource: EmergencyResource | dict[str, Any]) -> bool:
    """Determine whether an emergency resource is eligible for candidate response planning.

    A resource is eligible only if its operational status is AVAILABLE
    and it is not currently assigned to an incident.
    """
    if isinstance(resource, dict):
        status_val = resource.get("status")
        assigned_id = resource.get("assigned_incident_id")
    else:
        status_val = resource.status
        assigned_id = resource.assigned_incident_id

    if hasattr(status_val, "value"):
        status_val = status_val.value

    is_available = status_val == ResourceStatus.AVAILABLE.value
    is_unassigned = not assigned_id

    return bool(is_available and is_unassigned)


def interpolate_route_progress(
    coordinates: list[list[float]],
    progress: float,
) -> tuple[float, float]:
    """Deterministically interpolate a [lon, lat] coordinate along a GeoJSON LineString.

    Args:
        coordinates: Ordered list of [longitude, latitude] coordinates (len >= 2).
        progress: Float in [0.0, 1.0] representing cumulative distance along the route.

    Returns:
        (longitude, latitude) coordinate on the route geometry path.
    """
    if not math.isfinite(progress) or not 0.0 <= progress <= 1.0:
        raise ValueError("Route progress must be between 0.0 and 1.0")

    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("Route coordinates must contain at least 2 points")

    normalized_coordinates: list[tuple[float, float]] = []
    for coordinate in coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            raise ValueError("Each route coordinate must contain longitude and latitude")
        try:
            longitude = float(coordinate[0])
            latitude = float(coordinate[1])
        except (TypeError, ValueError) as exc:
            raise ValueError("Route coordinates must be numeric") from exc
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            raise ValueError("Route coordinates must be finite")
        if not -180.0 <= longitude <= 180.0 or not -90.0 <= latitude <= 90.0:
            raise ValueError("Route coordinates are outside geographic bounds")
        normalized_coordinates.append((longitude, latitude))

    # Calculate segment lengths using haversine distance
    segment_lengths: list[float] = []
    for i in range(len(normalized_coordinates) - 1):
        p1 = normalized_coordinates[i]
        p2 = normalized_coordinates[i + 1]
        dist = haversine_distance_m(p1[0], p1[1], p2[0], p2[1])
        segment_lengths.append(dist)

    total_distance = sum(segment_lengths)
    if total_distance <= 0.0:
        raise ValueError("Route geometry must have positive length")

    if progress == 0.0:
        return normalized_coordinates[0]
    if progress == 1.0:
        return normalized_coordinates[-1]

    target_distance = progress * total_distance
    accumulated_distance = 0.0

    for i, seg_len in enumerate(segment_lengths):
        if accumulated_distance + seg_len >= target_distance:
            if seg_len <= 0.0:
                fraction = 0.0
            else:
                fraction = (target_distance - accumulated_distance) / seg_len
                fraction = max(0.0, min(1.0, fraction))

            p1 = normalized_coordinates[i]
            p2 = normalized_coordinates[i + 1]
            interp_lon = p1[0] + fraction * (p2[0] - p1[0])
            interp_lat = p1[1] + fraction * (p2[1] - p1[1])
            return float(interp_lon), float(interp_lat)

        accumulated_distance += seg_len

    return normalized_coordinates[-1]


def serialize_resource(resource: EmergencyResource) -> dict[str, Any]:
    """Serialize an EmergencyResource ORM instance into a frontend-agnostic dictionary."""
    status_str = (
        resource.status.value
        if hasattr(resource.status, "value")
        else str(resource.status)
    )
    type_str = (
        resource.resource_type.value
        if hasattr(resource.resource_type, "value")
        else str(resource.resource_type)
    )
    last_updated_iso = (
        resource.last_updated.isoformat()
        if resource.last_updated is not None
        else None
    )
    capabilities = resource.capability_tags_json or []

    route_progress: float | None = None
    if resource.assigned_incident_id is not None and resource.provenance_json:
        movement = resource.provenance_json.get("movement")
        if isinstance(movement, dict):
            raw_progress = movement.get("route_progress")
            if isinstance(raw_progress, (int, float)) and not isinstance(raw_progress, bool):
                parsed_progress = float(raw_progress)
                if math.isfinite(parsed_progress) and 0.0 <= parsed_progress <= 1.0:
                    route_progress = parsed_progress

    return {
        "id": resource.id,
        "version": resource.version,
        "name": resource.name,
        "resource_type": type_str,
        "type": type_str,
        "capabilities": capabilities,
        "capability_tags": capabilities,
        "capability_tags_json": capabilities,
        "status": status_str,
        "operational_status": status_str,
        "latitude": resource.latitude,
        "longitude": resource.longitude,
        "location": {
            "lat": resource.latitude,
            "lon": resource.longitude,
        },
        "home_zone": resource.home_zone,
        "assigned_incident_id": resource.assigned_incident_id,
        "assignment": resource.assigned_incident_id,
        "last_updated": last_updated_iso,
        "provenance": resource.provenance_json or {},
        "provenance_json": resource.provenance_json or {},
        "is_planner_eligible": is_planner_eligible(resource),
        "route_progress": route_progress,
    }


@router.get(
    "/resources",
    status_code=status.HTTP_200_OK,
    response_model=list[ResourceRead],
)
def list_resources(
    resource_type: ResourceType | None = Query(
        default=None,
        description="Filter by resource type (e.g. AMBULANCE, FIRE_RESCUE)",
    ),
    resource_status: ResourceStatus | None = Query(
        default=None,
        alias="status",
        description="Filter by operational status (e.g. AVAILABLE, ASSIGNED)",
    ),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Retrieve all simulated emergency resources, optionally filtered by type or status."""
    stmt = select(EmergencyResource)
    if resource_type is not None:
        stmt = stmt.where(EmergencyResource.resource_type == resource_type)
    if resource_status is not None:
        stmt = stmt.where(EmergencyResource.status == resource_status)

    stmt = stmt.order_by(EmergencyResource.id.asc())
    resources = db.scalars(stmt).all()
    return [serialize_resource(r) for r in resources]


@router.get(
    "/resources/{resource_id}",
    status_code=status.HTTP_200_OK,
    response_model=ResourceRead,
)
def get_resource(
    resource_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve detailed state for a specific emergency resource by its unique identifier."""
    resource = db.get(EmergencyResource, resource_id)
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency resource '{resource_id}' not found",
        )
    return serialize_resource(resource)


@router.post(
    "/resources/{resource_id}/assign",
    status_code=status.HTTP_200_OK,
    response_model=ResourceRead,
)
def assign_resource(
    resource_id: str,
    payload: ResourceAssignRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Atomically assign an available emergency resource to an existing incident with version checking."""
    _acquire_write_lock(db)

    resource = db.get(EmergencyResource, resource_id)
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency resource '{resource_id}' not found",
        )

    incident = db.get(Incident, payload.incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Referenced incident '{payload.incident_id}' not found",
        )

    if resource.version != payload.expected_resource_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale resource version: expected {payload.expected_resource_version}, "
                f"current {resource.version}"
            ),
        )

    if resource.assigned_incident_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Resource '{resource_id}' is already assigned to incident "
                f"'{resource.assigned_incident_id}'"
            ),
        )

    if resource.status != ResourceStatus.AVAILABLE:
        status_val = (
            resource.status.value
            if hasattr(resource.status, "value")
            else str(resource.status)
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Resource '{resource_id}' is not AVAILABLE "
                f"(current status: '{status_val}')"
            ),
        )

    now_utc = datetime.now(timezone.utc)

    # Atomic mutation
    resource.assigned_incident_id = incident.id
    resource.status = ResourceStatus.ASSIGNED
    resource.version = resource.version + 1
    resource.last_updated = now_utc

    current_provenance = dict(resource.provenance_json or {})
    current_provenance.pop("movement", None)
    current_provenance.pop("route_progress", None)
    resource.provenance_json = {
        **current_provenance,
        "source": current_provenance.get("source") or "operator_action",
        "data_reality": DataReality.SIMULATED.value,
        "freshness_status": FreshnessStatus.FRESH.value,
        "last_updated": now_utc.isoformat(),
        "source_reference": payload.operator_reference,
    }

    timeline_event = TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident.id,
        event_type="RESOURCE_ASSIGNED",
        details_json={
            "resource_id": resource.id,
            "resource_version": resource.version,
            "incident_id": incident.id,
            "operator_reference": payload.operator_reference,
            "status": ResourceStatus.ASSIGNED.value,
        },
        created_at=now_utc,
    )
    db.add(timeline_event)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(resource)
    result = serialize_resource(resource)
    publish_operations_event(
        event="resource.updated",
        incident_id=incident.id,
        payload=result,
    )
    return result


@router.patch(
    "/resources/{resource_id}/state",
    status_code=status.HTTP_200_OK,
    response_model=ResourceRead,
)
def patch_resource_state(
    resource_id: str,
    payload: ResourceStatePatchRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update resource operational status with version checking and incident ownership safeguards."""
    _acquire_write_lock(db)

    resource = db.get(EmergencyResource, resource_id)
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency resource '{resource_id}' not found",
        )

    if resource.version != payload.expected_resource_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale resource version: expected {payload.expected_resource_version}, "
                f"current {resource.version}"
            ),
        )

    incident: Incident | None = None
    target_status = payload.status

    if resource.assigned_incident_id is None:
        # Unassigned resource
        if payload.incident_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot assign resource via state patch; use assign operation",
            )
        if target_status not in (ResourceStatus.AVAILABLE, ResourceStatus.OUT_OF_SERVICE):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Invalid status '{target_status.value}' for unassigned resource; "
                    f"only AVAILABLE or OUT_OF_SERVICE permitted; assignment must use assign operation"
                ),
            )
    else:
        # Assigned resource
        if payload.incident_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Owning incident_id is required when resource is assigned",
            )
        if payload.incident_id != resource.assigned_incident_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cross-incident mutation rejected: resource is assigned to '{resource.assigned_incident_id}', "
                    f"got '{payload.incident_id}'"
                ),
            )
        incident = db.get(Incident, payload.incident_id)
        if incident is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Referenced incident '{payload.incident_id}' not found",
            )
        if target_status == ResourceStatus.AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot set assigned resource to AVAILABLE via state patch; use release operation",
            )
        valid_assigned_statuses = {
            ResourceStatus.ASSIGNED,
            ResourceStatus.EN_ROUTE,
            ResourceStatus.ON_SCENE,
            ResourceStatus.TRANSPORTING,
            ResourceStatus.OUT_OF_SERVICE,
        }
        if target_status not in valid_assigned_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Invalid status '{target_status.value}' for assigned resource; "
                    f"permitted statuses are {[s.value for s in valid_assigned_statuses]}"
                ),
            )

    now_utc = datetime.now(timezone.utc)
    prev_status = (
        resource.status.value
        if hasattr(resource.status, "value")
        else str(resource.status)
    )

    resource.status = target_status
    resource.version = resource.version + 1
    resource.last_updated = now_utc

    current_provenance = dict(resource.provenance_json or {})
    resource.provenance_json = {
        **current_provenance,
        "source": current_provenance.get("source") or "operator_action",
        "data_reality": DataReality.SIMULATED.value,
        "freshness_status": FreshnessStatus.FRESH.value,
        "last_updated": now_utc.isoformat(),
        "source_reference": payload.operator_reference,
    }

    if incident is not None:
        timeline_event = TimelineEvent(
            id=new_timeline_event_id(),
            incident_id=incident.id,
            event_type="RESOURCE_STATUS_CHANGED",
            details_json={
                "resource_id": resource.id,
                "resource_version": resource.version,
                "incident_id": incident.id,
                "operator_reference": payload.operator_reference,
                "previous_status": prev_status,
                "status": target_status.value,
            },
            created_at=now_utc,
        )
        db.add(timeline_event)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(resource)
    active_plan = None
    if incident is not None and incident.current_plan_id:
        active_plan = db.get(ResponsePlan, incident.current_plan_id)
    if (
        incident is not None
        and target_status == ResourceStatus.OUT_OF_SERVICE
        and active_plan is not None
        and active_plan.status == ResponsePlanStatus.APPROVED
        and resource.id in (active_plan.resource_ids_json or [])
    ):
        # Import locally to keep the resource/planning module dependency graph
        # acyclic while recording the post-commit domain trigger.
        from app.replanning import record_replan_trigger

        record_replan_trigger(
            db,
            incident_id=incident.id,
            expected_incident_version=incident.version,
            trigger_reasons=["RESOURCE_UNAVAILABLE"],
            input_references={
                "resource_id": resource.id,
                "resource_version": resource.version,
                "resource_status": resource.status.value,
            },
            now=now_utc,
        )
    result = serialize_resource(resource)
    publish_operations_event(
        event="resource.updated",
        incident_id=incident.id if incident is not None else None,
        payload=result,
    )
    return result


@router.post(
    "/resources/{resource_id}/release",
    status_code=status.HTTP_200_OK,
    response_model=ResourceRead,
)
def release_resource(
    resource_id: str,
    payload: ResourceReleaseRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Atomically release an assigned emergency resource back to AVAILABLE with version checking."""
    _acquire_write_lock(db)

    resource = db.get(EmergencyResource, resource_id)
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency resource '{resource_id}' not found",
        )

    if resource.version != payload.expected_resource_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale resource version: expected {payload.expected_resource_version}, "
                f"current {resource.version}"
            ),
        )

    if resource.assigned_incident_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resource '{resource_id}' is already unassigned",
        )

    if resource.assigned_incident_id != payload.incident_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Wrong incident: resource is assigned to '{resource.assigned_incident_id}', "
                f"release requested for '{payload.incident_id}'"
            ),
        )

    incident = db.get(Incident, payload.incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Referenced incident '{payload.incident_id}' not found",
        )

    now_utc = datetime.now(timezone.utc)

    # Atomic mutation
    resource.assigned_incident_id = None
    resource.status = ResourceStatus.AVAILABLE
    resource.version = resource.version + 1
    resource.last_updated = now_utc

    current_provenance = dict(resource.provenance_json or {})
    current_provenance.pop("movement", None)
    current_provenance.pop("route_progress", None)
    resource.provenance_json = {
        **current_provenance,
        "source": current_provenance.get("source") or "operator_action",
        "data_reality": DataReality.SIMULATED.value,
        "freshness_status": FreshnessStatus.FRESH.value,
        "last_updated": now_utc.isoformat(),
        "source_reference": payload.operator_reference,
    }

    timeline_event = TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident.id,
        event_type="RESOURCE_RELEASED",
        details_json={
            "resource_id": resource.id,
            "resource_version": resource.version,
            "incident_id": incident.id,
            "operator_reference": payload.operator_reference,
            "status": ResourceStatus.AVAILABLE.value,
        },
        created_at=now_utc,
    )
    db.add(timeline_event)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(resource)
    result = serialize_resource(resource)
    publish_operations_event(
        event="resource.updated",
        incident_id=incident.id,
        payload=result,
    )
    return result


@router.patch(
    "/resources/{resource_id}/movement",
    status_code=status.HTTP_200_OK,
    response_model=ResourceRead,
)
def patch_resource_movement(
    resource_id: str,
    payload: ResourceMovementRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Execute deterministic route-progress movement simulation on an approved route."""
    _acquire_write_lock(db)

    resource = db.get(EmergencyResource, resource_id)
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency resource '{resource_id}' not found",
        )

    incident = db.get(Incident, payload.incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{payload.incident_id}' not found",
        )

    if resource.version != payload.expected_resource_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale resource version: expected {payload.expected_resource_version}, "
                f"current {resource.version}"
            ),
        )

    if resource.assigned_incident_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resource '{resource_id}' is not assigned to any incident",
        )

    if resource.assigned_incident_id != incident.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cross-incident mutation rejected: resource is assigned to '{resource.assigned_incident_id}', "
                f"got '{incident.id}'"
            ),
        )

    if not incident.current_plan_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Incident '{incident.id}' has no associated response plan",
        )

    plan = db.get(ResponsePlan, incident.current_plan_id)
    if plan is None or plan.status != ResponsePlanStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Current response plan for incident '{incident.id}' is not APPROVED",
        )
    if plan.incident_id != incident.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Current approved plan '{plan.id}' belongs to incident "
                f"'{plan.incident_id}', not '{incident.id}'"
            ),
        )
    if not isinstance(plan.resource_ids_json, list) or resource.id not in plan.resource_ids_json:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approved response plan does not assign resource '{resource.id}'",
        )

    routes = plan.routes_json or []
    if not isinstance(routes, list):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approved response plan routes are invalid",
        )

    target_route = None
    for r in routes:
        if isinstance(r, dict) and r.get("resource_id") == resource.id:
            target_route = r
            break

    if target_route is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approved response plan does not contain a route for resource '{resource.id}'",
        )

    route_ref = str(target_route.get("route_id") or f"{plan.id}:{resource.id}")

    geometry = target_route.get("geometry") or target_route.get("route_geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Route geometry is not a valid LineString",
        )

    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Route geometry coordinates must contain at least 2 points",
        )

    try:
        interp_lon, interp_lat = interpolate_route_progress(
            coords,
            payload.route_progress,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approved route geometry is invalid: {exc}",
        ) from exc

    current_progress: float | None = None
    movement_state = (resource.provenance_json or {}).get("movement")
    if movement_state is not None:
        if not isinstance(movement_state, dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Persisted resource movement state is invalid",
            )
        if (
            movement_state.get("incident_id") != incident.id
            or movement_state.get("plan_id") != plan.id
            or movement_state.get("route_id") != route_ref
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Persisted resource movement state does not match the active route",
            )
        raw_progress = movement_state.get("route_progress")
        if (
            not isinstance(raw_progress, (int, float))
            or isinstance(raw_progress, bool)
            or not math.isfinite(float(raw_progress))
            or not 0.0 <= float(raw_progress) <= 1.0
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Persisted resource route progress is invalid",
            )
        current_progress = float(raw_progress)

    if current_progress is not None:
        if payload.route_progress == current_progress:
            # Repeated identical progress is idempotent:
            # no version bump, no fake timeline event, and no live event
            return serialize_resource(resource)
        if payload.route_progress < current_progress:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Backwards movement progress rejected: requested {payload.route_progress}, "
                    f"current progress is {current_progress}"
                ),
            )

    now_utc = datetime.now(timezone.utc)
    resource.latitude = interp_lat
    resource.longitude = interp_lon
    resource.version = resource.version + 1
    resource.last_updated = now_utc

    current_provenance = dict(resource.provenance_json or {})
    resource.provenance_json = {
        **current_provenance,
        "source": "operator_movement_command",
        "source_reference": payload.operator_reference,
        "data_reality": DataReality.SIMULATED.value,
        "freshness_status": FreshnessStatus.FRESH.value,
        "last_updated": now_utc.isoformat(),
        "movement": {
            "incident_id": incident.id,
            "plan_id": plan.id,
            "route_id": route_ref,
            "route_progress": payload.route_progress,
            "operator_reference": payload.operator_reference,
            "last_updated": now_utc.isoformat(),
        },
    }

    timeline_event = TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident.id,
        event_type="RESOURCE_MOVED",
        details_json={
            "resource_id": resource.id,
            "incident_id": incident.id,
            "plan_id": plan.id,
            "route_id": route_ref,
            "previous_progress": current_progress,
            "route_progress": payload.route_progress,
            "coordinates": {
                "latitude": interp_lat,
                "longitude": interp_lon,
            },
            "operator_reference": payload.operator_reference,
            "resource_version": resource.version,
            "source": "operator_movement_command",
            "data_reality": DataReality.SIMULATED.value,
            "freshness_status": FreshnessStatus.FRESH.value,
        },
        created_at=now_utc,
    )
    db.add(timeline_event)

    try:
        refresh_driver_alert(
            db,
            incident=incident,
            plan=plan,
            resource=resource,
            operator_reference=payload.operator_reference,
            now=now_utc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Driver alert update failed: {exc}") from exc

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(resource)
    result = serialize_resource(resource)
    publish_operations_event(
        event="resource.updated",
        incident_id=incident.id,
        payload=result,
    )
    return result
