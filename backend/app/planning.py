from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EmergencyResource, Incident, ResponsePlan, TimelineEvent
from app.resources import is_planner_eligible
from app.routing import (
    RouteNotFoundError,
    RouteResult,
    RoutingPointOutsideGraphError,
    compute_route_on_graph,
    load_routing_graph,
)
from app.schemas import (
    Coordinate,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
)

__all__ = [
    "router",
    "generate_response_plan",
    "serialize_plan",
]

router = APIRouter(tags=["planning"])

SCORE_BREAKDOWN_PHASE01: dict[str, Any] = {
    "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
    "coverage_considered": False,
    "traffic_source": "OSM_BASE_TRAVEL_TIME",
    "note": "Phase 01 minimal plan. Coverage-aware optimization arrives in Phase 04.",
}


def serialize_plan(plan: ResponsePlan) -> dict[str, Any]:
    """Serialize a ResponsePlan ORM model instance into a frontend-agnostic dictionary."""
    status_str = (
        plan.status.value
        if hasattr(plan.status, "value")
        else str(plan.status)
    )
    return {
        "id": plan.id,
        "plan_id": plan.id,
        "incident_id": plan.incident_id,
        "incident_version": plan.incident_version,
        "plan_version": plan.plan_version,
        "version": plan.plan_version,
        "status": status_str,
        "resource_ids": plan.resource_ids_json or [],
        "resource_ids_json": plan.resource_ids_json or [],
        "routes": plan.routes_json or [],
        "routes_json": plan.routes_json or [],
        "metrics": plan.metrics_json or {},
        "metrics_json": plan.metrics_json or {},
        "score_breakdown": plan.score_breakdown_json or {},
        "score_breakdown_json": plan.score_breakdown_json or {},
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


@router.post(
    "/incidents/{incident_id}/plans/generate",
    status_code=status.HTTP_201_CREATED,
    response_model=None,
)
def generate_response_plan(
    incident_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate a minimal deterministic candidate response plan for an incident.

    Algorithm:
    1. Query eligible AVAILABLE unassigned resources for each required resource type.
    2. Compute real base OSM route from each eligible resource to the incident coordinate.
    3. Exclude route infeasible candidates. Fail clearly with HTTP 409 if routeable candidates < count.
    4. Sort routeable candidates by eta_seconds ascending and select exact count. Never reuse a resource.
    5. Construct ResponsePlan with actual computed metrics and strict score breakdown.
    6. In one atomic DB transaction: persist ResponsePlan, set incident status AWAITING_APPROVAL,
       increment incident version, set current_plan_id, and log PLAN_GENERATED timeline event.
    """
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )

    if incident.status in (IncidentStatus.CLOSED, IncidentStatus.CANCELLED_FALSE_REPORT):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot generate response plan for incident with status {incident.status.value}",
        )

    requirements = incident.required_resources_json or []
    if not requirements:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Incident has no required resources specified",
        )

    # Load routing graph once for candidate route evaluation
    graph = load_routing_graph()
    destination = Coordinate(lat=incident.latitude, lon=incident.longitude)

    selected_resources: list[EmergencyResource] = []
    selected_routes: list[RouteResult] = []
    selected_resource_ids: set[str] = set()

    for req in requirements:
        raw_type = req.get("resource_type")
        count = int(req.get("count", 0))
        if count <= 0:
            continue

        try:
            target_type = (
                ResourceType(raw_type)
                if isinstance(raw_type, str)
                else raw_type
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown resource type: {raw_type}",
            )

        # 1. Query only EmergencyResource with matching type, status AVAILABLE, unassigned
        stmt = (
            select(EmergencyResource)
            .where(
                EmergencyResource.resource_type == target_type,
                EmergencyResource.status == ResourceStatus.AVAILABLE,
            )
            .order_by(EmergencyResource.id.asc())
        )
        candidates = db.scalars(stmt).all()

        # Filter strictly with is_planner_eligible and exclude resources selected earlier in this generation
        eligible_candidates = [
            res for res in candidates
            if res.id not in selected_resource_ids and is_planner_eligible(res)
        ]

        # 2 & 3. Compute route from candidate to incident coordinate, excluding infeasible routes
        routeable_candidates: list[tuple[EmergencyResource, RouteResult]] = []
        for candidate in eligible_candidates:
            origin = Coordinate(lat=candidate.latitude, lon=candidate.longitude)
            try:
                route = compute_route_on_graph(graph, origin, destination)
            except (RoutingPointOutsideGraphError, RouteNotFoundError, ValueError):
                continue

            routeable_candidates.append((candidate, route))

        # Check sufficiency: if fewer routeable candidates remain than required count, fail clearly
        if len(routeable_candidates) < count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Insufficient eligible routeable resources for {target_type.value}: "
                    f"required {count}, available {len(routeable_candidates)}"
                ),
            )

        # 4. Sort by eta_seconds ascending (tie-breaking deterministically by distance_m then resource id)
        routeable_candidates.sort(
            key=lambda item: (item[1].eta_seconds, item[1].distance_m, item[0].id)
        )

        chosen = routeable_candidates[:count]
        for res, route in chosen:
            selected_resources.append(res)
            selected_routes.append(route)
            selected_resource_ids.add(res.id)

    # 5. Build routes records preserving full data for approval without recomputation
    routes_records: list[dict[str, Any]] = []
    for res, route in zip(selected_resources, selected_routes):
        type_str = (
            res.resource_type.value
            if hasattr(res.resource_type, "value")
            else str(res.resource_type)
        )
        routes_records.append({
            "resource_id": res.id,
            "resource_type": type_str,
            "resource_name": res.name,
            "origin": {
                "lat": res.latitude,
                "lon": res.longitude,
            },
            "destination": {
                "lat": incident.latitude,
                "lon": incident.longitude,
            },
            "route_geometry": route.geometry,
            "geometry": route.geometry,
            "distance_m": round(route.distance_m, 2),
            "eta_seconds": round(route.eta_seconds, 2),
            "origin_snap_distance_m": round(route.origin_snap_distance_m, 2),
            "destination_snap_distance_m": round(route.destination_snap_distance_m, 2),
            "snap_distances": {
                "origin_snap_distance_m": round(route.origin_snap_distance_m, 2),
                "destination_snap_distance_m": round(route.destination_snap_distance_m, 2),
            },
            "routing_source": route.routing_source,
            "nodes": route.nodes,
        })

    # 6. Compute actual metrics
    etas = [r.eta_seconds for r in selected_routes]
    max_eta = round(max(etas), 2)
    mean_eta = round(sum(etas) / len(etas), 2)
    selected_count = len(selected_resources)

    metrics_record = {
        "max_arrival_eta_seconds": max_eta,
        "mean_arrival_eta_seconds": mean_eta,
        "selected_resource_count": selected_count,
        "routing_source": "OSM_BASE_TRAVEL_TIME",
    }

    # 7. Plan versioning and metadata
    incident_version_before = incident.version

    existing_plans = db.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all()
    plan_version = (
        max(p.plan_version for p in existing_plans) + 1
        if existing_plans
        else 1
    )

    now_utc = datetime.now(timezone.utc)
    plan_id = str(uuid.uuid4())

    plan = ResponsePlan(
        id=plan_id,
        incident_id=incident.id,
        incident_version=incident_version_before,
        plan_version=plan_version,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids_json=[res.id for res in selected_resources],
        routes_json=routes_records,
        metrics_json=metrics_record,
        score_breakdown_json=dict(SCORE_BREAKDOWN_PHASE01),
        created_at=now_utc,
    )

    # 8. Atomic single-transaction commit
    incident.status = IncidentStatus.AWAITING_APPROVAL
    incident.version = incident_version_before + 1
    incident.current_plan_id = plan_id
    incident.updated_at = now_utc

    timeline_event = TimelineEvent(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        event_type="PLAN_GENERATED",
        details_json={
            "plan_id": plan_id,
            "plan_version": plan_version,
            "incident_version": incident.version,
            "resource_ids": [res.id for res in selected_resources],
            "selected_resource_count": selected_count,
            "max_arrival_eta_seconds": max_eta,
            "mean_arrival_eta_seconds": mean_eta,
            "routing_source": "OSM_BASE_TRAVEL_TIME",
        },
        created_at=now_utc,
    )

    db.add(plan)
    db.add(timeline_event)
    db.commit()
    db.refresh(plan)
    db.refresh(incident)

    return serialize_plan(plan)
