from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any
import uuid
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.candidate_evaluation import (
    evaluate_candidate_combination,
    rank_evaluated_candidates,
    rescore_evaluated_candidate,
)
from app.candidate_generation import (
    CandidateResource,
    NoFeasibleCandidateError,
    generate_candidate_combinations,
)
from app.candidate_persistence import persist_candidate_set
from app.repositioning import select_reposition_proposal, simulate_repositioning
from app.config import settings
from app.corridor import corridor_provenance, extract_corridor_signals
from app.coverage import load_population_zones
from app.driver_alert import refresh_driver_alert
from app.models import (
    Approval,
    CorridorState,
    DriverAlert,
    EmergencyResource,
    Incident,
    ResponsePlan,
    TimelineEvent,
)
from app.incidents import serialize_incident
from app.resources import interpolate_route_progress, is_planner_eligible, serialize_resource
from app.response_requirements import (
    ResponseRequirement,
    ResponseRequirementsUnavailableError,
    resolve_response_requirements,
)
from app.traffic.runtime import traffic_runtime
from app.websocket import publish_operations_event
from app.routing import (
    RouteNotFoundError,
    RouteResult,
    RoutingPointOutsideGraphError,
    compute_route_on_graph,
    load_routing_graph,
)
from app.schemas import (
    ApprovalResult,
    ApprovePlanRequest,
    Coordinate,
    DataReality,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanRead,
    ResponsePlanStatus,
    SelectAlternativePlanRequest,
)

__all__ = [
    "router",
    "generate_response_plan",
    "generate_phase04_candidate_plans",
    "serialize_plan",
    "approve_response_plan",
    "list_incident_plans",
    "get_response_plan",
    "select_alternative_plan",
    "SCORE_BREAKDOWN_PHASE01",
]

router = APIRouter(tags=["planning"])


@dataclass(frozen=True)
class _Phase04PlanningState:
    incident: tuple[Any, ...]
    resources: tuple[tuple[Any, ...], ...]


def _capture_phase04_planning_state(
    incident: Incident,
    resources: tuple[EmergencyResource, ...],
) -> _Phase04PlanningState:
    return _Phase04PlanningState(
        incident=(
            incident.id,
            incident.version,
            incident.status,
            incident.incident_type,
            incident.severity,
            incident.latitude,
            incident.longitude,
            json.dumps(
                incident.required_resources_json or [],
                sort_keys=True,
                separators=(",", ":"),
            ),
            incident.current_plan_id,
        ),
        resources=tuple(
            (
                resource.id,
                resource.version,
                resource.status,
                resource.assigned_incident_id,
                resource.latitude,
                resource.longitude,
                resource.resource_type,
                tuple(resource.capability_tags_json or ()),
                (resource.provenance_json or {}).get("data_reality"),
                (resource.provenance_json or {}).get("source"),
            )
            for resource in resources
        ),
    )

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
    metrics = plan.metrics_json or {}
    phase04 = metrics.get("phase04") if isinstance(metrics, dict) else None
    if not isinstance(phase04, dict):
        phase04 = metrics if isinstance(metrics, dict) else {}
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
        "candidate_set_id": phase04.get("candidate_set_id"),
        "candidate_rank": phase04.get("candidate_rank"),
        "candidate_count": phase04.get("candidate_count"),
    }


@router.post(
    "/incidents/{incident_id}/plans/generate",
    status_code=status.HTTP_201_CREATED,
    response_model=ResponsePlanRead,
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
    6. In one atomic DB transaction: persist ResponsePlan with incident_version matching the post-generation
       incident version, mark prior current RECOMMENDED plan SUPERSEDED, set incident status AWAITING_APPROVAL,
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
    if incident.current_plan_id:
        active_plan = db.get(ResponsePlan, incident.current_plan_id)
        if active_plan is not None and active_plan.status == ResponsePlanStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Incident already has an active APPROVED plan; use the Phase 07 "
                    "replan trigger/evaluation flow"
                ),
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
    post_gen_incident_version = incident.version + 1

    # Minimally and atomically mark prior current RECOMMENDED plan SUPERSEDED
    if incident.current_plan_id:
        prev_plan = db.get(ResponsePlan, incident.current_plan_id)
        if prev_plan and prev_plan.status == ResponsePlanStatus.RECOMMENDED:
            prev_plan.status = ResponsePlanStatus.SUPERSEDED

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
        incident_version=post_gen_incident_version,
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
    incident.version = post_gen_incident_version
    incident.current_plan_id = plan_id
    incident.updated_at = now_utc

    timeline_event = TimelineEvent(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        event_type="PLAN_GENERATED",
        details_json={
            "plan_id": plan_id,
            "plan_version": plan_version,
            "incident_version": post_gen_incident_version,
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

    publish_operations_event(
        event="incident.updated",
        incident_id=incident.id,
        payload=serialize_incident(incident),
    )

    return serialize_plan(plan)


def _phase04_source_requirements(
    raw_requirements: object,
) -> tuple[ResponseRequirement, ...] | None:
    if raw_requirements is None:
        return None
    if not isinstance(raw_requirements, list):
        raise ValueError("Incident required resources must be a list")
    if not raw_requirements:
        return None
    parsed: list[ResponseRequirement] = []
    for item in raw_requirements:
        if not isinstance(item, dict):
            raise ValueError("Each incident resource requirement must be an object")
        try:
            resource_type = ResourceType(item.get("resource_type"))
            count = int(item.get("count", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Incident resource requirements are invalid") from exc
        raw_tags = item.get("required_capability_tags", ())
        if raw_tags is None:
            raw_tags = ()
        if not isinstance(raw_tags, (list, tuple)) or not all(
            isinstance(tag, str) for tag in raw_tags
        ):
            raise ValueError("Required capability tags must be a list of strings")
        parsed.append(
            ResponseRequirement(
                resource_type=resource_type,
                minimum_count=count,
                required_capability_tags=tuple(raw_tags),
            )
        )
    return tuple(parsed)


def resource_coordinate_for_replan(
    resource: EmergencyResource,
    active_plan: ResponsePlan | None,
    *,
    incident_id: str,
) -> Coordinate:
    """Capture an assigned responder's current modeled route position.

    Phase 07 route replacement must start from the current position of an
    ``EN_ROUTE`` responder. The position is derived from the immutable active
    route and explicit cumulative-distance progress.
    """
    coordinate = Coordinate(lat=resource.latitude, lon=resource.longitude)
    if (
        active_plan is None
        or resource.assigned_incident_id != incident_id
        or resource.status != ResourceStatus.EN_ROUTE
    ):
        return coordinate

    movement = (resource.provenance_json or {}).get("movement")
    if not isinstance(movement, dict):
        return coordinate
    raw_progress = movement.get("route_progress")
    if not isinstance(raw_progress, (int, float)) or isinstance(raw_progress, bool):
        raise ValueError(f"Resource '{resource.id}' has invalid route progress")
    progress = float(raw_progress)
    if not 0.0 <= progress <= 1.0:
        raise ValueError(f"Resource '{resource.id}' has invalid route progress")

    route_record = next(
        (
            route
            for route in (active_plan.routes_json or [])
            if isinstance(route, dict) and route.get("resource_id") == resource.id
        ),
        None,
    )
    if route_record is None:
        raise ValueError(
            f"Active plan '{active_plan.id}' has no route for resource '{resource.id}'"
        )
    geometry = (
        movement.get("route_geometry")
        or route_record.get("geometry")
        or route_record.get("route_geometry")
    )
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        raise ValueError(f"Active route for resource '{resource.id}' has invalid geometry")
    coordinates = geometry.get("coordinates")
    try:
        longitude, latitude = interpolate_route_progress(coordinates, progress)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Active route for resource '{resource.id}' cannot resolve current position: {exc}"
        ) from exc
    return Coordinate(lat=latitude, lon=longitude)


def evaluate_phase04_candidate_set(
    db: Session,
    incident: Incident,
    *,
    now_utc: datetime | None = None,
    planning_incident_id: str | None = None,
    graph_override: Any | None = None,
    zones_override: tuple[Any, ...] | None = None,
    traffic_snapshot_override: Any = None,
    use_traffic_runtime: bool = True,
    resources_override: tuple[CandidateResource, ...] | None = None,
    travel_times_cache: dict[tuple[Any, ...], Any] | None = None,
    zone_nodes_cache: dict[tuple[Any, ...], Any] | None = None,
    include_route_alternatives: bool = True,
) -> tuple[Any, tuple[Any, ...], dict[tuple[str, ...], Any], datetime]:
    """Evaluate one coherent Phase 04 candidate set without persisting it.

    The optional overrides are an internal deterministic replay seam used by
    Phase 08. Normal API callers retain the existing graph, zone, traffic,
    and database-resource behavior.
    """
    source_requirements = _phase04_source_requirements(
        incident.required_resources_json
    )
    resolution = resolve_response_requirements(
        incident_type=incident.incident_type,
        severity=incident.severity,
        source_requirements=source_requirements,
    )
    graph = graph_override if graph_override is not None else load_routing_graph()
    zones = zones_override or load_population_zones(
        settings.NASR_CITY_DATA_DIR
        / "nasr_city_zone_population_worldpop_2025.geojson"
    )
    timestamp = now_utc or datetime.now(timezone.utc)
    if use_traffic_runtime:
        traffic_snapshot = traffic_runtime.capture_snapshot(
            graph,
            now=timestamp,
            wall_clock=lambda: datetime.now(timezone.utc),
            monotonic=time.monotonic,
        )
    else:
        traffic_snapshot = traffic_snapshot_override
    active_plan = (
        db.get(ResponsePlan, incident.current_plan_id)
        if planning_incident_id and incident.current_plan_id
        else None
    )
    if resources_override is not None:
        resources = resources_override
    else:
        resources = tuple(
            CandidateResource(
                resource_id=resource.id,
                resource_type=resource.resource_type,
                capability_tags=tuple(resource.capability_tags_json or ()),
                status=resource.status,
                assigned_incident_id=resource.assigned_incident_id,
                coordinate=resource_coordinate_for_replan(
                    resource,
                    active_plan,
                    incident_id=planning_incident_id or incident.id,
                ),
                data_reality=DataReality(
                    (resource.provenance_json or {}).get(
                        "data_reality", DataReality.SIMULATED.value
                    )
                ),
                source=(resource.provenance_json or {}).get(
                    "source", "phase03_simulated_resource"
                ),
            )
            for resource in db.scalars(
                select(EmergencyResource).order_by(EmergencyResource.id.asc())
            ).all()
        )
    generated = generate_candidate_combinations(
        graph=graph,
        incident_coordinate=Coordinate(
            lat=incident.latitude,
            lon=incident.longitude,
        ),
        resources=resources,
        requirements=resolution.requirements,
        traffic_snapshot=traffic_snapshot,
        incident_id=planning_incident_id,
        include_route_alternatives=include_route_alternatives,
    )
    travel_times_cache = travel_times_cache if travel_times_cache is not None else {}
    zone_nodes_cache = zone_nodes_cache if zone_nodes_cache is not None else {}
    evaluated = tuple(
        evaluate_candidate_combination(
            graph=graph,
            zones=zones,
            resources=resources,
            requirements=resolution.requirements,
            combination=combination,
            traffic_snapshot=traffic_snapshot,
            modeled_at=timestamp,
            incident_id=planning_incident_id,
            travel_times_cache=travel_times_cache,
            zone_nodes_cache=zone_nodes_cache,
        )
        for combination in generated.combinations
    )
    reposition_proposals: dict[tuple[str, ...], Any] = {}
    rescored_candidates = []
    for candidate in evaluated:
        repositioning = simulate_repositioning(
            graph=graph,
            zones=zones,
            resources=resources,
            requirements=resolution.requirements,
            candidate=candidate,
            traffic_snapshot=traffic_snapshot,
            modeled_at=timestamp,
            travel_times_cache=travel_times_cache,
            zone_nodes_cache=zone_nodes_cache,
            include_route_alternatives=include_route_alternatives,
        )
        selected_proposal = select_reposition_proposal(repositioning.proposals)
        if selected_proposal is not None:
            reposition_proposals[candidate.combination.resource_ids] = selected_proposal
            candidate = rescore_evaluated_candidate(
                candidate,
                proposed_reposition_eta_seconds=(
                    selected_proposal.reposition_eta_seconds
                ),
            )
        rescored_candidates.append(candidate)
    return resolution, rank_evaluated_candidates(rescored_candidates), reposition_proposals, timestamp


@router.post(
    "/incidents/{incident_id}/plans/generate-candidates",
    status_code=status.HTTP_201_CREATED,
    response_model=list[ResponsePlanRead],
)
def generate_phase04_candidate_plans(
    incident_id: str,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Generate and persist the bounded Phase 04 comparison candidate set."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    if incident.status in (
        IncidentStatus.CLOSED,
        IncidentStatus.CANCELLED_FALSE_REPORT,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot generate response plans for incident with status {incident.status.value}",
        )
    if incident.current_plan_id:
        active_plan = db.get(ResponsePlan, incident.current_plan_id)
        if active_plan is not None and active_plan.status == ResponsePlanStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Incident already has an active APPROVED plan; use the Phase 07 "
                    "replan trigger/evaluation flow"
                ),
            )

    resource_records = tuple(
        db.scalars(
            select(EmergencyResource).order_by(EmergencyResource.id.asc())
        ).all()
    )
    captured_state = _capture_phase04_planning_state(incident, resource_records)
    # Candidate routing/coverage is CPU- and I/O-heavy. Release the read
    # transaction before evaluating so concurrent authoritative mutations can
    # proceed; the captured state is checked again before persistence.
    db.rollback()
    try:
        resolution, ranked, reposition_proposals, now_utc = evaluate_phase04_candidate_set(
            db,
            incident,
        )
    except ResponseRequirementsUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Phase 04 planning assets unavailable: {exc}",
        ) from exc
    except (NoFeasibleCandidateError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No feasible Phase 04 candidate set: {exc}",
        ) from exc

    _acquire_write_lock(db)
    db.expire_all()
    current_incident = db.get(Incident, incident_id)
    current_resources = tuple(
        db.scalars(
            select(EmergencyResource).order_by(EmergencyResource.id.asc())
        ).all()
    )
    if (
        current_incident is None
        or _capture_phase04_planning_state(current_incident, current_resources)
        != captured_state
    ):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stale planning state: incident or resource inputs changed during candidate generation",
        )

    persisted = persist_candidate_set(
        db,
        current_incident,
        ranked,
        reposition_proposals=reposition_proposals,
        now_utc=now_utc,
        requirements_metadata={
            "source": resolution.source.value,
            "matrix_version": resolution.matrix_version,
            "prototype_policy_label": resolution.prototype_policy_label,
        },
    )
    publish_operations_event(
        event="incident.updated",
        incident_id=current_incident.id,
        payload=serialize_incident(current_incident),
    )
    return [serialize_plan(plan) for plan in persisted]


@router.get(
    "/incidents/{incident_id}/plans",
    status_code=status.HTTP_200_OK,
    response_model=list[ResponsePlanRead],
)
def list_incident_plans(
    incident_id: str,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Retrieve all persisted response plans for a given incident ordered deterministically."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    stmt = (
        select(ResponsePlan)
        .where(ResponsePlan.incident_id == incident_id)
        .order_by(ResponsePlan.plan_version.asc(), ResponsePlan.id.asc())
    )
    plans = db.scalars(stmt).all()
    return [serialize_plan(p) for p in plans]


@router.get(
    "/plans/{plan_id}",
    status_code=status.HTTP_200_OK,
    response_model=ResponsePlanRead,
)
def get_response_plan(
    plan_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve detailed state for a specific response plan by its unique identifier."""
    plan = db.get(ResponsePlan, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response plan '{plan_id}' not found",
        )
    return serialize_plan(plan)


def _candidate_set_id(plan: ResponsePlan) -> str | None:
    metrics = plan.metrics_json or {}
    if not isinstance(metrics, dict):
        return None
    phase04 = metrics.get("phase04")
    if isinstance(phase04, dict) and phase04.get("candidate_set_id"):
        return str(phase04["candidate_set_id"])
    if metrics.get("candidate_set_id"):
        return str(metrics["candidate_set_id"])
    return None


@router.post(
    "/plans/{plan_id}/select",
    status_code=status.HTTP_200_OK,
    response_model=ResponsePlanRead,
)
@router.post(
    "/incidents/{incident_id}/plans/{plan_id}/select",
    status_code=status.HTTP_200_OK,
    response_model=ResponsePlanRead,
)
def select_alternative_plan(
    plan_id: str,
    payload: SelectAlternativePlanRequest,
    incident_id: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Promote one active alternative without assigning resources."""
    _acquire_write_lock(db)

    if incident_id is None:
        plan = db.get(ResponsePlan, plan_id)
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Response plan '{plan_id}' not found",
            )
        incident_id = plan.incident_id

    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    plan = db.get(ResponsePlan, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response plan '{plan_id}' not found",
        )
    if plan.incident_id != incident.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Response plan does not belong to the requested incident",
        )
    if plan.status != ResponsePlanStatus.ALTERNATIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an ALTERNATIVE response plan can be selected",
        )
    if payload.expected_incident_version != incident.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale incident version: expected {payload.expected_incident_version}, "
                f"current {incident.version}"
            ),
        )
    if payload.expected_plan_version != plan.plan_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale plan version: expected {payload.expected_plan_version}, "
                f"current {plan.plan_version}"
            ),
        )
    if plan.incident_version != incident.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alternative response plan is stale for the current incident version",
        )

    candidate_set_id = _candidate_set_id(plan)
    if candidate_set_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Response plan is not part of an active candidate set",
        )
    if incident.current_plan_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Incident has no current recommended response plan",
        )
    previous_recommended = db.get(ResponsePlan, incident.current_plan_id)
    if previous_recommended is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Incident current_plan_id does not reference a response plan",
        )
    if previous_recommended.status != ResponsePlanStatus.RECOMMENDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Incident current plan is not RECOMMENDED",
        )
    if _candidate_set_id(previous_recommended) != candidate_set_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Response plan is not in the incident's current candidate set",
        )

    candidate_set_plans = db.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all()
    active_set_plans = [
        candidate
        for candidate in candidate_set_plans
        if _candidate_set_id(candidate) == candidate_set_id
    ]
    if plan not in active_set_plans:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Response plan is not in the active candidate set",
        )

    previous_recommended_id = previous_recommended.id
    superseded_candidate_ids: list[str] = []
    for candidate in active_set_plans:
        if candidate.id == plan.id:
            continue
        if candidate.status in (
            ResponsePlanStatus.RECOMMENDED,
            ResponsePlanStatus.ALTERNATIVE,
        ):
            candidate.status = ResponsePlanStatus.SUPERSEDED
            superseded_candidate_ids.append(candidate.id)

    now_utc = datetime.now(timezone.utc)
    incident.version += 1
    incident.updated_at = now_utc
    incident.current_plan_id = plan.id
    plan.status = ResponsePlanStatus.RECOMMENDED
    plan.incident_version = incident.version
    timeline_event = TimelineEvent(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        event_type="PLAN_ALTERNATIVE_SELECTED",
        details_json={
            "action": "SELECT_ALTERNATIVE_PLAN",
            "previous_recommended_plan_id": previous_recommended_id,
            "selected_plan_id": plan.id,
            "selected_plan_version": plan.plan_version,
            "resulting_incident_version": incident.version,
            "operator_reference": payload.operator_reference,
            "superseded_candidate_ids": sorted(superseded_candidate_ids),
        },
        created_at=now_utc,
    )
    try:
        db.add(timeline_event)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(plan)
    db.refresh(incident)
    publish_operations_event(
        event="incident.updated",
        incident_id=incident.id,
        payload=serialize_incident(incident),
    )
    return serialize_plan(plan)


def _acquire_write_lock(db: Session) -> None:
    """Acquire an immediate SQLite write transaction to serialize validation and mutation.

    This ensures concurrent approval requests wait for an active approval transaction
    to complete before reading plan, incident, or resource state, preventing race
    conditions and duplicate approvals.
    """
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _plan_route_geometry(plan: ResponsePlan, resource_id: str) -> Any:
    routes = plan.routes_json if isinstance(plan.routes_json, list) else []
    route = next(
        (
            item
            for item in routes
            if isinstance(item, dict) and item.get("resource_id") == resource_id
        ),
        None,
    )
    if not isinstance(route, dict):
        return None
    return route.get("geometry") or route.get("route_geometry")


def _supersede_replaced_route_state(
    db: Session,
    *,
    incident: Incident,
    previous_plan: ResponsePlan,
    replacement_plan: ResponsePlan,
    resources: list[EmergencyResource],
    operator_reference: str,
    now_utc: datetime,
) -> None:
    """Move route-derived state to an approved replacement route only.

    The active plan is already being switched in this transaction. Existing
    corridor and driver-alert records remain historical, while new derived
    state is created only for resources that had a route-derived operational
    record on the old approved plan.
    """
    old_corridors = db.scalars(
        select(CorridorState).where(
            CorridorState.incident_id == incident.id,
            CorridorState.plan_id == previous_plan.id,
        )
    ).all()
    active_alerts = db.scalars(
        select(DriverAlert).where(
            DriverAlert.incident_id == incident.id,
            DriverAlert.plan_id == previous_plan.id,
            DriverAlert.status == "ACTIVE",
        )
    ).all()
    resource_by_id = {resource.id: resource for resource in resources}
    now_iso = now_utc.isoformat()

    for row in old_corridors:
        row.provenance_json = {
            **dict(row.provenance_json or {}),
            "status": "SUPERSEDED",
            "superseded_by_plan_id": replacement_plan.id,
            "superseded_at": now_iso,
            "operator_reference": operator_reference,
        }
        db.add(
            TimelineEvent(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                event_type="CORRIDOR_SUPERSEDED",
                details_json={
                    "corridor_id": row.id,
                    "old_plan_id": previous_plan.id,
                    "new_plan_id": replacement_plan.id,
                    "operator_reference": operator_reference,
                },
                created_at=now_utc,
            )
        )
        resource_id = row.route_reference.rsplit(":", 1)[-1]
        replacement_route = next(
            (
                route
                for route in (replacement_plan.routes_json or [])
                if isinstance(route, dict) and route.get("resource_id") == resource_id
            ),
            None,
        )
        if not isinstance(replacement_route, dict):
            continue
        geometry = replacement_route.get("geometry") or replacement_route.get("route_geometry")
        eta_seconds = replacement_route.get("eta_seconds")
        if not isinstance(geometry, dict) or not isinstance(eta_seconds, (int, float)):
            continue
        signals = extract_corridor_signals(
            geometry,
            float(eta_seconds),
            now_iso=now_iso,
        )
        new_row = CorridorState(
            id=str(uuid.uuid4()),
            incident_id=incident.id,
            plan_id=replacement_plan.id,
            route_reference=str(
                replacement_route.get("route_id")
                or f"{replacement_plan.id}:{resource_id}"
            ),
            route_geometry_json=geometry,
            signals_json=[signal.__dict__ for signal in signals],
            state="NORMAL",
            safety_lead_time_seconds=settings.SIGNAL_PRIORITY_SAFETY_LEAD_TIME_SECONDS,
            version=1,
            data_reality=DataReality.REAL_DERIVED,
            provenance_json={
                **corridor_provenance(),
                "source": "approved_replacement_response_route + OSM traffic signal asset",
                "derived_from_plan_id": replacement_plan.id,
                "superseded_plan_id": previous_plan.id,
                "priority_reality": DataReality.SIMULATED.value,
            },
            updated_at=now_utc,
        )
        db.add(new_row)
        db.add(
            TimelineEvent(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                event_type="CORRIDOR_REDERIVED",
                details_json={
                    "corridor_id": new_row.id,
                    "plan_id": replacement_plan.id,
                    "resource_id": resource_id,
                    "data_reality": DataReality.REAL_DERIVED.value,
                },
                created_at=now_utc,
            )
        )

    active_alert_resource_ids: set[str] = set()
    for alert in active_alerts:
        alert.status = "EXPIRED"
        alert.provenance_json = {
            **dict(alert.provenance_json or {}),
            "status": "SUPERSEDED",
            "superseded_by_plan_id": replacement_plan.id,
            "superseded_at": now_iso,
            "operator_reference": operator_reference,
        }
        active_alert_resource_ids.add(alert.resource_id)
        db.add(
            TimelineEvent(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                event_type="DRIVER_ALERT_SUPERSEDED",
                details_json={
                    "driver_alert_id": alert.id,
                    "old_plan_id": previous_plan.id,
                    "new_plan_id": replacement_plan.id,
                    "resource_id": alert.resource_id,
                    "data_reality": DataReality.SIMULATED.value,
                },
                created_at=now_utc,
            )
        )

    for resource_id in sorted(active_alert_resource_ids):
        resource = resource_by_id.get(resource_id)
        if resource is None or resource.assigned_incident_id != incident.id:
            continue
        refresh_driver_alert(
            db,
            incident=incident,
            plan=replacement_plan,
            resource=resource,
            operator_reference=operator_reference,
            now=now_utc,
        )


@router.post(
    "/plans/{plan_id}/approve",
    status_code=status.HTTP_200_OK,
    response_model=ApprovalResult,
)
def approve_response_plan(
    plan_id: str,
    payload: ApprovePlanRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Execute version-checked transactional approval of a candidate response plan.

    Validation rules:
    1. Response plan must exist; 404 if missing.
    2. Referenced incident must exist; 404 if missing.
    3. Plan status must be RECOMMENDED. If already APPROVED, returns 409 with PLAN_ALREADY_APPROVED.
       Any other non-RECOMMENDED status returns 409.
    4. Incident status must be AWAITING_APPROVAL; otherwise 409.
    5. Incident current_plan_id must match plan.id; mismatch returns 409.
    6. Plan incident_version must match current incident.version; mismatch returns 409.
    7. Expected incident version must match current incident version; mismatch returns 409.
    8. Expected plan version must match current plan version; mismatch returns 409.
    9. Plan must not contain duplicate resource IDs; conflict returns 409.
    10. Every selected resource must exist, remain status AVAILABLE, and have no assigned_incident_id;
       any conflict returns 409.

    Atomic transaction:
    - Sets plan.status = APPROVED.
    - Sets incident.status = RESPONSE_ACTIVE.
    - Increments incident.version exactly once.
    - Sets each selected resource.status = ASSIGNED and assigned_incident_id = incident.id,
      incrementing each resource.version exactly once.
    - Inserts Approval row recording operator reference, action, and expected versions.
    - Appends auditable PLAN_APPROVED and RESOURCES_ASSIGNED timeline events.
    - Commits exactly once.
    """
    _acquire_write_lock(db)

    plan = db.get(ResponsePlan, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response plan '{plan_id}' not found",
        )

    incident = db.get(Incident, plan.incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Referenced incident '{plan.incident_id}' not found",
        )

    if plan.status == ResponsePlanStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PLAN_ALREADY_APPROVED: response plan has already been approved",
        )

    if plan.status != ResponsePlanStatus.RECOMMENDED:
        status_val = (
            plan.status.value
            if hasattr(plan.status, "value")
            else str(plan.status)
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Response plan status is '{status_val}', expected '{ResponsePlanStatus.RECOMMENDED.value}'",
        )

    pending_replacement = incident.pending_replan_plan_id == plan.id
    if not pending_replacement and incident.status != IncidentStatus.AWAITING_APPROVAL:
        inc_status_val = (
            incident.status.value
            if hasattr(incident.status, "value")
            else str(incident.status)
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Incident status is '{inc_status_val}', expected '{IncidentStatus.AWAITING_APPROVAL.value}'",
        )

    if pending_replacement:
        if incident.current_plan_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Incident has no active approved plan for replacement approval",
            )
    elif incident.current_plan_id != plan.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Response plan '{plan.id}' is not the current plan for incident '{incident.id}' "
                f"(current_plan_id: '{incident.current_plan_id}')"
            ),
        )

    if plan.incident_version != incident.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Plan incident version mismatch: plan has incident_version {plan.incident_version}, "
                f"current incident version is {incident.version}"
            ),
        )

    if payload.expected_incident_version != incident.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale incident version: expected {payload.expected_incident_version}, "
                f"current {incident.version}"
            ),
        )

    if payload.expected_plan_version != plan.plan_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stale plan version: expected {payload.expected_plan_version}, "
                f"current {plan.plan_version}"
            ),
        )

    selected_resource_ids = plan.resource_ids_json or []
    if len(selected_resource_ids) != len(set(selected_resource_ids)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Response plan contains duplicate resource IDs",
        )

    previous_plan = (
        db.get(ResponsePlan, incident.current_plan_id)
        if pending_replacement and incident.current_plan_id
        else None
    )
    previous_resource_ids = set(previous_plan.resource_ids_json or []) if previous_plan else set()
    resources: list[EmergencyResource] = []
    for res_id in selected_resource_ids:
        res = db.get(EmergencyResource, res_id)
        if res is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Selected resource '{res_id}' not found in registry",
            )
        if pending_replacement and res_id in previous_resource_ids:
            if res.assigned_incident_id != incident.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Active replacement resource '{res_id}' is not assigned to "
                        f"incident '{incident.id}'"
                    ),
                )
            if res.status in (
                ResourceStatus.ON_SCENE,
                ResourceStatus.TRANSPORTING,
            ):
                if previous_plan is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Active responder '{res_id}' cannot be validated for replacement",
                    )
                old_geometry = _plan_route_geometry(previous_plan, res_id)
                new_geometry = _plan_route_geometry(plan, res_id)
                if old_geometry != new_geometry:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Cannot reroute responder '{res_id}' while in state "
                            f"'{res.status.value}'; explicit handoff is required"
                        ),
                    )
                # Retaining an already committed responder on the same route is
                # safe; changing or substituting it is rejected.
                resources.append(res)
                continue
            if res.status not in (ResourceStatus.ASSIGNED, ResourceStatus.RESERVED, ResourceStatus.EN_ROUTE):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Active resource '{res_id}' has invalid replacement state",
                )
            resources.append(res)
            continue
        if res.status != ResourceStatus.AVAILABLE:
            res_status_val = (
                res.status.value
                if hasattr(res.status, "value")
                else str(res.status)
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Resource '{res_id}' is not AVAILABLE (current: '{res_status_val}')",
            )
        if res.assigned_incident_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Resource '{res_id}' is already assigned to incident '{res.assigned_incident_id}'",
            )
        resources.append(res)

    if pending_replacement and previous_plan is not None:
        for previous_resource_id in sorted(previous_resource_ids - set(selected_resource_ids)):
            previous_resource = db.get(EmergencyResource, previous_resource_id)
            if previous_resource is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Previously assigned resource '{previous_resource_id}' not found",
                )
            if previous_resource.assigned_incident_id != incident.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Previously assigned resource '{previous_resource_id}' is no longer "
                        "owned by this incident"
                    ),
                )
            if previous_resource.status in (
                ResourceStatus.EN_ROUTE,
                ResourceStatus.ON_SCENE,
                ResourceStatus.TRANSPORTING,
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Cannot replace active responder '{previous_resource_id}' "
                        f"in state '{previous_resource.status.value}'"
                    ),
                )

    now_utc = datetime.now(timezone.utc)

    # Atomic single-transaction mutations
    plan.status = ResponsePlanStatus.APPROVED

    if pending_replacement and previous_plan is not None:
        previous_plan.status = ResponsePlanStatus.SUPERSEDED
    if pending_replacement:
        incident.current_plan_id = plan.id
        incident.pending_replan_plan_id = None
    else:
        incident.status = IncidentStatus.RESPONSE_ACTIVE
    incident.version = incident.version + 1
    incident.updated_at = now_utc

    released_resources: list[EmergencyResource] = []
    if pending_replacement and previous_plan is not None:
        for previous_resource_id in sorted(previous_resource_ids - set(selected_resource_ids)):
            previous_resource = db.get(EmergencyResource, previous_resource_id)
            assert previous_resource is not None
            # Releasing an explicitly unavailable resource must not reactivate
            # it as a side effect of approving a replacement plan.
            previous_resource.status = (
                ResourceStatus.OUT_OF_SERVICE
                if previous_resource.status == ResourceStatus.OUT_OF_SERVICE
                else ResourceStatus.AVAILABLE
            )
            previous_resource.assigned_incident_id = None
            previous_resource.version += 1
            previous_resource.last_updated = now_utc
            previous_provenance = dict(previous_resource.provenance_json or {})
            previous_provenance.pop("movement", None)
            previous_provenance.pop("route_progress", None)
            previous_resource.provenance_json = {
                **previous_provenance,
                "data_reality": DataReality.SIMULATED.value,
                "freshness_status": "FRESH",
                "last_updated": now_utc.isoformat(),
                "source_reference": payload.operator_reference,
            }
            released_resources.append(previous_resource)

    selected_resource_set = set(selected_resource_ids)
    for res in resources:
        if pending_replacement and res.id in previous_resource_ids:
            if res.status == ResourceStatus.EN_ROUTE:
                new_route = next(
                    (
                        route
                        for route in (plan.routes_json or [])
                        if isinstance(route, dict) and route.get("resource_id") == res.id
                    ),
                    None,
                )
                geometry = new_route.get("geometry") if isinstance(new_route, dict) else None
                movement = (res.provenance_json or {}).get("movement")
                res.version += 1
                res.last_updated = now_utc
                res.provenance_json = {
                    **dict(res.provenance_json or {}),
                    "data_reality": DataReality.SIMULATED.value,
                    "freshness_status": "FRESH",
                    "last_updated": now_utc.isoformat(),
                    "movement": {
                        "incident_id": incident.id,
                        "plan_id": plan.id,
                        "route_id": f"{plan.id}:{res.id}",
                        "route_progress": 0.0,
                        "operator_reference": payload.operator_reference,
                        "last_updated": now_utc.isoformat(),
                        "previous_route": movement,
                        "route_geometry": geometry,
                    },
                }
            continue
        res.status = ResourceStatus.ASSIGNED
        res.assigned_incident_id = incident.id
        res.version = res.version + 1
        res.last_updated = now_utc

    if pending_replacement and previous_plan is not None:
        _supersede_replaced_route_state(
            db,
            incident=incident,
            previous_plan=previous_plan,
            replacement_plan=plan,
            resources=resources,
            operator_reference=payload.operator_reference,
            now_utc=now_utc,
        )

    approval = Approval(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        incident_id=incident.id,
        operator_reference=payload.operator_reference,
        action="APPROVE_PLAN",
        expected_incident_version=payload.expected_incident_version,
        expected_plan_version=payload.expected_plan_version,
        created_at=now_utc,
    )

    plan_approved_event = TimelineEvent(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        event_type="PLAN_APPROVED",
        details_json={
            "plan_id": plan.id,
            "plan_version": plan.plan_version,
            "incident_version": incident.version,
            "operator_reference": payload.operator_reference,
            "action": "APPROVE_PLAN",
        },
        created_at=now_utc,
    )

    resources_assigned_event = TimelineEvent(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        event_type="RESOURCES_ASSIGNED",
        details_json={
            "plan_id": plan.id,
            "incident_id": incident.id,
            "resource_ids": [r.id for r in resources if r.id in selected_resource_set],
            "resource_count": len(selected_resource_ids),
            "operator_reference": payload.operator_reference,
            "released_resource_ids": [resource.id for resource in released_resources],
            "replacement": pending_replacement,
        },
        created_at=now_utc,
    )

    try:
        db.add(approval)
        db.add(plan_approved_event)
        db.add(resources_assigned_event)
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(plan)
    db.refresh(incident)
    for res in [*resources, *released_resources]:
        db.refresh(res)
    db.refresh(approval)

    serialized_plan = serialize_plan(plan)
    inc_status_str = (
        incident.status.value
        if hasattr(incident.status, "value")
        else str(incident.status)
    )

    result = {
        **serialized_plan,
        "incident_status": inc_status_str,
        "incident": {
            "id": incident.id,
            "status": inc_status_str,
            "version": incident.version,
        },
        "resources": [serialize_resource(res) for res in [*resources, *released_resources]],
        "approval": {
            "id": approval.id,
            "plan_id": approval.plan_id,
            "incident_id": approval.incident_id,
            "action": approval.action,
            "operator_reference": approval.operator_reference,
            "expected_incident_version": approval.expected_incident_version,
            "expected_plan_version": approval.expected_plan_version,
            "created_at": approval.created_at.isoformat() if approval.created_at else None,
        },
    }

    publish_operations_event(
        event="plan.approved",
        incident_id=plan.incident_id,
        payload=result,
    )

    return result
