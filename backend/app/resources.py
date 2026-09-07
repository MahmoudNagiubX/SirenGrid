from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EmergencyResource, Incident, TimelineEvent
from app.schemas import (
    DataReality,
    FreshnessStatus,
    ResourceAssignRequest,
    ResourceRead,
    ResourceReleaseRequest,
    ResourceStatePatchRequest,
    ResourceStatus,
    ResourceType,
)

__all__ = [
    "router",
    "is_planner_eligible",
    "serialize_resource",
    "list_resources",
    "get_resource",
    "assign_resource",
    "patch_resource_state",
    "release_resource",
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
    resource.provenance_json = {
        **current_provenance,
        "source": current_provenance.get("source") or "operator_action",
        "data_reality": DataReality.SIMULATED.value,
        "freshness_status": FreshnessStatus.FRESH.value,
        "last_updated": now_utc.isoformat(),
        "source_reference": payload.operator_reference,
    }

    timeline_event = TimelineEvent(
        id=str(uuid.uuid4()),
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
    return serialize_resource(resource)


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
            id=str(uuid.uuid4()),
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
    return serialize_resource(resource)


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
    resource.provenance_json = {
        **current_provenance,
        "source": current_provenance.get("source") or "operator_action",
        "data_reality": DataReality.SIMULATED.value,
        "freshness_status": FreshnessStatus.FRESH.value,
        "last_updated": now_utc.isoformat(),
        "source_reference": payload.operator_reference,
    }

    timeline_event = TimelineEvent(
        id=str(uuid.uuid4()),
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
    return serialize_resource(resource)
