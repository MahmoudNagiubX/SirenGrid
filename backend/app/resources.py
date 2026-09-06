from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EmergencyResource
from app.schemas import ResourceRead, ResourceStatus, ResourceType

__all__ = [
    "router",
    "is_planner_eligible",
    "serialize_resource",
    "list_resources",
    "get_resource",
]

router = APIRouter(tags=["resources"])


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
