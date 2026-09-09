from __future__ import annotations

from datetime import datetime, timezone
import re
import time
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.hospitals import (
    HospitalOperationalSnapshot,
    HospitalRouteCandidate,
    HospitalStaticRecord,
    load_static_hospitals,
    rank_hospital_candidates,
)
from app.hospital_gateway import SimulatedHospitalGateway
from app.models import (
    EmergencyResource,
    HospitalDestination,
    HospitalOperationalState,
    HospitalOptionSet,
    HospitalPreAlert,
    Incident,
    ResponsePlan,
    TimelineEvent,
    new_timeline_event_id,
)
from app.routing import (
    RouteNotFoundError,
    RoutingPointOutsideGraphError,
    compute_traffic_aware_route,
    load_routing_graph,
)
from app.schemas import (
    Coordinate,
    DataReality,
    FreshnessStatus,
    HospitalAcceptingState,
    HospitalDestinationRead,
    HospitalOperationalStatePatchRequest,
    HospitalOptionRead,
    HospitalOptionsResponse,
    HospitalPreAlertRead,
    HospitalPreAlertRequest,
    HospitalPreAlertStatus,
    HospitalRead,
    SelectHospitalDestinationRequest,
)
from app.traffic.runtime import traffic_runtime
from app.websocket import publish_operations_event

__all__ = ["router"]

router = APIRouter(tags=["hospitals"])
hospital_gateway = SimulatedHospitalGateway()


def _acquire_write_lock(db: Session) -> None:
    bind = db.get_bind()
    if bind and bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _static_hospital(hospital_id: str) -> HospitalStaticRecord:
    for hospital in load_static_hospitals():
        if hospital.id == hospital_id:
            return hospital
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Hospital '{hospital_id}' not found in the approved static registry",
    )


def _snapshot(db: Session, hospital_id: str) -> HospitalOperationalSnapshot:
    row = db.get(HospitalOperationalState, hospital_id)
    if row is None:
        return HospitalOperationalSnapshot.unknown(hospital_id)
    return HospitalOperationalSnapshot(
        hospital_id=row.hospital_id,
        version=row.version,
        accepting_state=row.accepting_state,
        simulated_load_ratio=row.simulated_load_ratio,
        simulated_free_capacity=row.simulated_free_capacity,
        incoming_cases=row.incoming_cases,
        simulated_capability_tags=tuple(row.simulated_capability_tags_json or ()),
        freshness_status=row.freshness_status,
        data_reality=(row.data_reality.value if hasattr(row.data_reality, "value") else str(row.data_reality)),
        last_updated=row.last_updated.isoformat() if row.last_updated else None,
        source=row.source,
    )


def _serialize_hospital(
    hospital: HospitalStaticRecord,
    state: HospitalOperationalSnapshot,
) -> dict[str, Any]:
    return HospitalRead(
        id=hospital.id,
        source_id=hospital.source_id,
        name=hospital.name,
        latitude=hospital.latitude,
        longitude=hospital.longitude,
        operational_version=state.version,
        static_capabilities=list(hospital.static_capabilities),
        static_capacity=hospital.static_capacity,
        accepting_state=state.accepting_state,
        simulated_load_ratio=state.simulated_load_ratio,
        simulated_free_capacity=state.simulated_free_capacity,
        incoming_cases=state.incoming_cases,
        simulated_capability_tags=list(state.simulated_capability_tags),
        operational_freshness_status=state.freshness_status,
        static_provenance=hospital.provenance,
        operational_provenance={
            "source": state.source,
            "data_reality": state.data_reality,
            "freshness_status": state.freshness_status,
            "last_updated": state.last_updated,
            "source_reference": f"simulated-hospital:{hospital.id}",
        },
    ).model_dump(mode="json")


def _approved_plan(db: Session, incident: Incident) -> ResponsePlan:
    if incident.current_plan_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Incident has no current approved response plan",
        )
    plan = db.get(ResponsePlan, incident.current_plan_id)
    plan_status = getattr(plan.status, "value", plan.status) if plan is not None else None
    if plan is None or plan_status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hospital operations require the current APPROVED response plan",
        )
    return plan


def _require_transport(incident: Incident) -> None:
    if incident.transport_required is not True:
        detail = (
            "Hospital planning requires transport_required=true"
            if incident.transport_required is False
            else "Transport requirement is UNKNOWN; operator confirmation is required"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _selected_hospital_destination(
    db: Session,
    *,
    incident_id: str,
    plan_id: str,
) -> HospitalDestination | None:
    return db.scalars(
        select(HospitalDestination)
        .where(
            HospitalDestination.incident_id == incident_id,
            HospitalDestination.plan_id == plan_id,
            HospitalDestination.status == "SELECTED",
        )
        .order_by(HospitalDestination.selected_at.desc(), HospitalDestination.id.desc())
    ).first()


def invalidate_selected_hospital_for_replan(
    db: Session,
    *,
    incident_id: str,
    hospital_id: str,
    reason: str,
    operator_reference: str,
    acquire_lock: bool = True,
    commit: bool = True,
    generate_options: bool = True,
) -> bool:
    """Invalidate a selected destination after a confirmed route-health event."""
    if acquire_lock:
        _acquire_write_lock(db)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    plan = _approved_plan(db, incident)
    destination = _selected_hospital_destination(
        db,
        incident_id=incident.id,
        plan_id=plan.id,
    )
    if destination is None:
        return False
    if destination.hospital_id != hospital_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hospital invalidation does not match the current destination",
        )

    now = datetime.now(timezone.utc)
    destination.status = "INVALIDATED"
    destination.provenance_json = {
        **dict(destination.provenance_json or {}),
        "invalidation_source": "phase07_hospital_route_health",
        "invalidation_reason": reason,
        "invalidation_at": now.isoformat(),
        "operator_reference": operator_reference,
    }
    db.add(
        TimelineEvent(
            id=new_timeline_event_id(),
            incident_id=incident.id,
            event_type="HOSPITAL_DESTINATION_INVALIDATED",
            details_json={
                "hospital_id": hospital_id,
                "destination_id": destination.id,
                "plan_id": plan.id,
                "reason": reason,
                "operator_reference": operator_reference,
            },
            created_at=now,
        )
    )
    # Refresh recommendations against the same active response plan before
    # commit. This creates options only; it never selects or redirects a
    # destination. An outer atomic command may keep this work in its own
    # transaction by passing commit=False and generate_options=False.
    try:
        if generate_options and plan.resource_ids_json:
            _generate_hospital_options(
                incident.id,
                db,
                acquire_lock=False,
                commit=False,
            )
        if commit:
            db.commit()
    except Exception:
        if commit:
            db.rollback()
        raise
    return True


def _resource_origin(db: Session, plan: ResponsePlan) -> tuple[str, dict[str, float]]:
    route_records = plan.routes_json if isinstance(plan.routes_json, list) else []
    resources = {
        resource.id: resource
        for resource in db.scalars(
            select(EmergencyResource).where(
                EmergencyResource.id.in_(plan.resource_ids_json or [])
            )
        ).all()
    }
    candidates: list[tuple[float, float, str, dict[str, float]]] = []
    for record in route_records:
        if not isinstance(record, dict):
            continue
        origin = record.get("origin")
        if not isinstance(origin, dict):
            continue
        resource_id = str(record.get("resource_id", ""))
        resource_type = str(record.get("resource_type", ""))
        resource = resources.get(resource_id)
        if resource is not None:
            origin = {"lat": float(resource.latitude), "lon": float(resource.longitude)}
        try:
            eta = float(record.get("eta_seconds", float("inf")))
            distance = float(record.get("distance_m", float("inf")))
        except (TypeError, ValueError):
            continue
        if resource_type == "AMBULANCE":
            candidates.append((eta, distance, resource_id, origin))
    if not candidates:
        for record in route_records:
            if not isinstance(record, dict) or not isinstance(record.get("origin"), dict):
                continue
            candidates.append((
                float(record.get("eta_seconds", float("inf"))),
                float(record.get("distance_m", float("inf"))),
                str(record.get("resource_id", "")),
                record["origin"],
            ))
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approved response plan contains no usable transport origin",
        )
    _, _, resource_id, origin = min(candidates, key=lambda item: item[:3])
    return resource_id, {"lat": float(origin["lat"]), "lon": float(origin["lon"])}


def _traffic_snapshot(graph: Any) -> Any:
    now = datetime.now(timezone.utc)
    try:
        return traffic_runtime.capture_snapshot(
            graph,
            now=now,
            wall_clock=lambda: datetime.now(timezone.utc),
            monotonic=time.monotonic,
        )
    except (OSError, RuntimeError, ValueError):
        # Phase 02 requires provider failures/malformed freshness to remain
        # observable through the route fallback, never to block base routing.
        return None


def _option_response(option_set: HospitalOptionSet, incident: Incident) -> dict[str, Any]:
    return HospitalOptionsResponse(
        incident_id=option_set.incident_id,
        plan_id=option_set.plan_id,
        incident_version=option_set.incident_version,
        plan_version=option_set.plan_version,
        option_set_id=option_set.id,
        option_set_version=option_set.version,
        transport_required=True,
        required_hospital_capabilities=incident.required_hospital_capabilities_json or [],
        options=[HospitalOptionRead.model_validate(item) for item in option_set.options_json or []],
        excluded_hospitals=option_set.excluded_hospitals_json or [],
        generated_at=option_set.created_at.isoformat(),
        provenance=option_set.provenance_json or {},
    ).model_dump(mode="json")


@router.get("/hospitals", response_model=list[HospitalRead])
def list_hospitals(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [
        _serialize_hospital(hospital, _snapshot(db, hospital.id))
        for hospital in load_static_hospitals()
    ]


@router.get("/hospitals/{hospital_id}", response_model=HospitalRead)
def get_hospital(hospital_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    hospital = _static_hospital(hospital_id)
    return _serialize_hospital(hospital, _snapshot(db, hospital.id))


@router.patch("/hospitals/{hospital_id}/simulation-state", response_model=HospitalRead)
def patch_hospital_simulation_state(
    hospital_id: str,
    payload: HospitalOperationalStatePatchRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    hospital = _static_hospital(hospital_id)
    _acquire_write_lock(db)
    row = db.get(HospitalOperationalState, hospital_id)
    is_new = row is None
    if row is None:
        if payload.expected_version is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Hospital simulation state does not exist")
        row = HospitalOperationalState(
            hospital_id=hospital_id,
            version=1,
            accepting_state=HospitalAcceptingState.UNKNOWN.value,
            freshness_status=FreshnessStatus.UNKNOWN.value,
            data_reality=DataReality.SIMULATED,
        )
        db.add(row)
    elif payload.expected_version != row.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale hospital simulation version: expected {payload.expected_version}, current {row.version}",
        )
    changed = payload.model_fields_set - {"expected_version", "operator_reference"}
    if not changed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No simulation state fields supplied")
    if "accepting_state" in payload.model_fields_set:
        row.accepting_state = payload.accepting_state.value if payload.accepting_state else HospitalAcceptingState.UNKNOWN.value
    if "simulated_load_ratio" in payload.model_fields_set:
        row.simulated_load_ratio = payload.simulated_load_ratio
    if "simulated_free_capacity" in payload.model_fields_set:
        row.simulated_free_capacity = payload.simulated_free_capacity
    if "incoming_cases" in payload.model_fields_set:
        row.incoming_cases = payload.incoming_cases
    if "simulated_capability_tags" in payload.model_fields_set:
        row.simulated_capability_tags_json = sorted(
            {
                re.sub(r"\s+", "_", tag.strip().upper())
                for tag in (payload.simulated_capability_tags or [])
                if tag.strip()
            }
        )
    row.freshness_status = (
        payload.freshness_status.value
        if payload.freshness_status is not None
        else FreshnessStatus.FRESH.value
    )
    if not is_new:
        row.version += 1
    now = datetime.now(timezone.utc)
    row.last_updated = now
    row.source = "SIMULATED_HOSPITAL_GATEWAY"
    row.data_reality = DataReality.SIMULATED
    row.provenance_json = {
        "source": row.source,
        "data_reality": DataReality.SIMULATED.value,
        "freshness_status": row.freshness_status,
        "last_updated": now.isoformat(),
        "source_reference": payload.operator_reference,
    }
    invalidated_destinations: list[tuple[str, str]] = []
    if row.accepting_state == HospitalAcceptingState.NOT_ACCEPTING.value:
        for destination in db.scalars(
            select(HospitalDestination).where(
                HospitalDestination.hospital_id == hospital_id,
                HospitalDestination.status == "SELECTED",
            )
        ).all():
            incident = db.get(Incident, destination.incident_id)
            active_plan = (
                db.get(ResponsePlan, incident.current_plan_id)
                if incident is not None and incident.current_plan_id
                else None
            )
            if (
                incident is None
                or active_plan is None
                or active_plan.status != "APPROVED"
                or destination.plan_id != active_plan.id
            ):
                continue
            destination.status = "INVALIDATED"
            invalidated_destinations.append((incident.id, hospital_id))
            db.add(
                TimelineEvent(
                    id=new_timeline_event_id(),
                    incident_id=incident.id,
                    event_type="HOSPITAL_DESTINATION_INVALIDATED",
                    details_json={
                        "hospital_id": hospital_id,
                        "destination_id": destination.id,
                        "plan_id": active_plan.id,
                        "reason": "NOT_ACCEPTING",
                        "operator_reference": payload.operator_reference,
                    },
                    created_at=now,
                )
            )
    db.commit()
    db.refresh(row)
    if invalidated_destinations:
        # Hospital operational invalidation is a material Phase 07 trigger,
        # but it must never rewrite the active plan or redirect a destination.
        # Record it only for incidents whose selected destination still belongs
        # to their active approved plan.
        from app.replanning import record_replan_trigger

        for incident_id, invalidated_hospital_id in invalidated_destinations:
            incident = db.get(Incident, incident_id)
            if incident is None:
                continue
            record_replan_trigger(
                db,
                incident_id=incident.id,
                expected_incident_version=incident.version,
                trigger_reasons=["HOSPITAL_STATE_CHANGED"],
                input_references={
                    "hospital_id": invalidated_hospital_id,
                    "hospital_not_accepting": True,
                    "accepting_state": row.accepting_state,
                },
            )
            active_plan = db.get(ResponsePlan, incident.current_plan_id)
            if active_plan is not None and active_plan.resource_ids_json:
                # Refresh the option set against the updated simulated state;
                # this remains an explicit hospital recommendation and does
                # not select or redirect a destination.
                generate_hospital_options(incident.id, db)
    return _serialize_hospital(hospital, _snapshot(db, hospital_id))


def _generate_hospital_options(
    incident_id: str,
    db: Session,
    *,
    acquire_lock: bool = True,
    commit: bool = True,
) -> dict[str, Any]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")
    _require_transport(incident)
    plan = _approved_plan(db, incident)
    try:
        graph = load_routing_graph()
        snapshot = _traffic_snapshot(graph)
        resource_id, origin = _resource_origin(db, plan)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Hospital routing assets unavailable: {exc}") from exc

    excluded: list[dict[str, Any]] = []
    candidates: list[HospitalRouteCandidate] = []
    for hospital in load_static_hospitals():
        state = _snapshot(db, hospital.id)
        if state.accepting_state == HospitalAcceptingState.NOT_ACCEPTING.value:
            excluded.append({"hospital_id": hospital.id, "reason": "NOT_ACCEPTING"})
            continue
        if set(incident.required_hospital_capabilities_json or []).intersection(
            hospital.confirmed_incompatible_capabilities
        ):
            excluded.append({"hospital_id": hospital.id, "reason": "CONFIRMED_INCOMPATIBLE_CAPABILITY"})
            continue
        try:
            route_result = compute_traffic_aware_route(
                graph,
                origin=Coordinate(lat=origin["lat"], lon=origin["lon"]),
                destination=Coordinate(lat=hospital.latitude, lon=hospital.longitude),
                snapshot=snapshot,
            )
        except (RoutingPointOutsideGraphError, RouteNotFoundError, ValueError):
            excluded.append({"hospital_id": hospital.id, "reason": "UNREACHABLE"})
            continue
        candidates.append(
            HospitalRouteCandidate(
                hospital=hospital,
                operational_state=state,
                route=route_result.model_dump(mode="json"),
            )
        )
    ranked = rank_hospital_candidates(
        candidates,
        required_capabilities=tuple(incident.required_hospital_capabilities_json or []),
    )
    if acquire_lock:
        _acquire_write_lock(db)
    option_set_id = str(uuid.uuid4())
    options = []
    for rank, candidate in enumerate(ranked, start=1):
        hospital_payload = _serialize_hospital(candidate.hospital, candidate.operational_state)
        options.append({
            "option_id": f"{option_set_id}:{candidate.hospital.id}",
            "option_set_id": option_set_id,
            "option_version": 1,
            "rank": rank,
            "hospital": hospital_payload,
            "route": candidate.route,
            "score": candidate.score,
            "score_breakdown": candidate.score_breakdown,
            "provenance": {
                "source": "SIRENGRID_HOSPITAL_OPTION_ENGINE",
                "data_reality": "REAL_DERIVED",
                "freshness_status": (
                    candidate.route.get("traffic_freshness_status")
                    or (snapshot.freshness_status.value if snapshot is not None else "UNKNOWN")
                ),
                "source_reference": candidate.route.get("traffic_snapshot_id") or "OSM_BASE_TRAVEL_TIME",
                "transport_origin_resource_id": resource_id,
            },
        })
    option_set = HospitalOptionSet(
        id=option_set_id,
        incident_id=incident.id,
        plan_id=plan.id,
        incident_version=incident.version,
        plan_version=plan.plan_version,
        version=1,
        options_json=options,
        excluded_hospitals_json=excluded,
        provenance_json={
            "source": "OSM/Overpass + SirenGrid routing",
            "data_reality": "REAL_DERIVED",
            "freshness_status": (
                snapshot.freshness_status.value if snapshot is not None else "UNKNOWN"
            ),
            "source_reference": "nasr_city_emergency_facilities.geojson",
            "traffic_snapshot_id": snapshot.snapshot_id if snapshot else None,
        },
        created_at=datetime.now(timezone.utc),
    )
    db.add(option_set)
    db.flush()
    if commit:
        db.commit()
        db.refresh(option_set)
    return _option_response(option_set, incident)


@router.post("/incidents/{incident_id}/hospital-options", response_model=HospitalOptionsResponse)
def generate_hospital_options(
    incident_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _generate_hospital_options(incident_id, db)


@router.get("/incidents/{incident_id}/hospital-options", response_model=HospitalOptionsResponse)
def get_hospital_options(incident_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")
    plan = _approved_plan(db, incident)
    option_set = db.scalars(
        select(HospitalOptionSet)
        .where(HospitalOptionSet.incident_id == incident.id, HospitalOptionSet.plan_id == plan.id)
        .order_by(HospitalOptionSet.created_at.desc(), HospitalOptionSet.id.desc())
    ).first()
    if option_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hospital option set has been generated")
    return _option_response(option_set, incident)


def _serialize_destination(destination: HospitalDestination) -> dict[str, Any]:
    return HospitalDestinationRead(
        id=destination.id,
        incident_id=destination.incident_id,
        plan_id=destination.plan_id,
        option_set_id=destination.option_set_id,
        hospital_id=destination.hospital_id,
        status=destination.status,
        incident_version=destination.incident_version,
        plan_version=destination.plan_version,
        selected_at=destination.selected_at.isoformat(),
        provenance=destination.provenance_json or {},
    ).model_dump(mode="json")


@router.post("/incidents/{incident_id}/hospital-destination/select", response_model=HospitalDestinationRead)
def select_hospital_destination(
    incident_id: str,
    payload: SelectHospitalDestinationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _acquire_write_lock(db)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")
    _require_transport(incident)
    plan = _approved_plan(db, incident)
    if payload.expected_incident_version != incident.version or payload.expected_plan_version != plan.plan_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale incident or plan version")
    option_set = db.scalars(
        select(HospitalOptionSet)
        .where(HospitalOptionSet.incident_id == incident.id, HospitalOptionSet.plan_id == plan.id)
        .order_by(HospitalOptionSet.created_at.desc(), HospitalOptionSet.id.desc())
    ).first()
    if option_set is None or option_set.incident_version != incident.version or option_set.version != payload.expected_option_set_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale hospital option set")
    option = next((item for item in option_set.options_json or [] if item.get("hospital", {}).get("id") == payload.hospital_id), None)
    if option is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Hospital is not in the current option set")
    current = db.scalars(
        select(HospitalDestination)
        .where(HospitalDestination.incident_id == incident.id, HospitalDestination.plan_id == plan.id, HospitalDestination.status == "SELECTED")
        .order_by(HospitalDestination.selected_at.desc(), HospitalDestination.id.desc())
    ).first()
    if current is not None:
        existing_alert = db.scalars(select(HospitalPreAlert).where(HospitalPreAlert.destination_id == current.id)).first()
        if existing_alert is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Destination cannot be replaced after pre-alert request")
        if current.hospital_id == payload.hospital_id:
            return _serialize_destination(current)
        current.status = "SUPERSEDED"
    now = datetime.now(timezone.utc)
    incident.version += 1
    incident.updated_at = now
    option_set.incident_version = incident.version
    destination = HospitalDestination(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        plan_id=plan.id,
        option_set_id=option_set.id,
        hospital_id=payload.hospital_id,
        status="SELECTED",
        incident_version=incident.version,
        plan_version=plan.plan_version,
        selected_at=now,
        provenance_json={
            "source": "operator_hospital_destination_selection",
            "data_reality": "SIMULATED",
            "freshness_status": "FRESH",
            "source_reference": payload.operator_reference,
        },
    )
    db.add(destination)
    db.add(TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident.id,
        event_type="HOSPITAL_DESTINATION_SELECTED",
        details_json={
            "hospital_id": payload.hospital_id,
            "option_set_id": option_set.id,
            "plan_id": plan.id,
            "resulting_incident_version": incident.version,
            "operator_reference": payload.operator_reference,
        },
        created_at=now,
    ))
    db.commit()
    db.refresh(destination)
    publish_operations_event(event="hospital.updated", incident_id=incident.id, payload=_serialize_destination(destination))
    return _serialize_destination(destination)


@router.get("/incidents/{incident_id}/hospital-destination", response_model=HospitalDestinationRead)
def get_hospital_destination(
    incident_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")
    plan = _approved_plan(db, incident)
    destination = db.scalars(
        select(HospitalDestination)
        .where(
            HospitalDestination.incident_id == incident.id,
            HospitalDestination.plan_id == plan.id,
            HospitalDestination.status.in_(("SELECTED", "INVALIDATED")),
        )
        .order_by(HospitalDestination.selected_at.desc(), HospitalDestination.id.desc())
    ).first()
    if destination is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hospital destination is selected")
    return _serialize_destination(destination)


def _build_prealert_payload(
    incident: Incident,
    plan: ResponsePlan,
    destination: HospitalDestination,
    option_set: HospitalOptionSet,
) -> dict[str, Any]:
    option = next(
        item for item in option_set.options_json or []
        if item.get("hospital", {}).get("id") == destination.hospital_id
    )
    payload: dict[str, Any] = {
        "receiving_hospital": {
            "id": destination.hospital_id,
            "name": option.get("hospital", {}).get("name"),
        },
        "incoming_resources": list(plan.resource_ids_json or []),
        "incident_category": incident.incident_type,
        "severity": incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
        "eta_seconds": option.get("route", {}).get("eta_seconds"),
    }
    if incident.casualty_count is not None:
        payload["patient_count"] = incident.casualty_count
    if incident.required_hospital_capabilities_json:
        payload["known_required_capabilities"] = list(incident.required_hospital_capabilities_json)
    return payload


def _serialize_prealert(alert: HospitalPreAlert) -> dict[str, Any]:
    return HospitalPreAlertRead(
        id=alert.id,
        incident_id=alert.incident_id,
        plan_id=alert.plan_id,
        destination_id=alert.destination_id,
        status=alert.status,
        payload=alert.payload_json or {},
        requested_at=alert.requested_at.isoformat(),
        sent_at=alert.sent_at.isoformat() if alert.sent_at else None,
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        failed_at=alert.failed_at.isoformat() if alert.failed_at else None,
        failure_reason=alert.failure_reason,
        data_reality=alert.data_reality,
        provenance=alert.provenance_json or {},
    ).model_dump(mode="json")


@router.post("/incidents/{incident_id}/hospital-prealert", response_model=HospitalPreAlertRead)
def request_hospital_prealert(
    incident_id: str,
    payload: HospitalPreAlertRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _acquire_write_lock(db)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")
    _require_transport(incident)
    plan = _approved_plan(db, incident)
    if payload.expected_incident_version != incident.version or payload.expected_plan_version != plan.plan_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale incident or plan version")
    destination = db.scalars(
        select(HospitalDestination)
        .where(HospitalDestination.incident_id == incident.id, HospitalDestination.plan_id == plan.id, HospitalDestination.status == "SELECTED")
        .order_by(HospitalDestination.selected_at.desc(), HospitalDestination.id.desc())
    ).first()
    if destination is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A hospital destination must be selected first")
    existing = db.scalars(select(HospitalPreAlert).where(HospitalPreAlert.destination_id == destination.id)).first()
    if existing is not None:
        return _serialize_prealert(existing)
    option_set = db.get(HospitalOptionSet, destination.option_set_id)
    if option_set is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Hospital option set is unavailable")
    now = datetime.now(timezone.utc)
    alert = HospitalPreAlert(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        plan_id=plan.id,
        destination_id=destination.id,
        status=HospitalPreAlertStatus.REQUESTED.value,
        payload_json=_build_prealert_payload(incident, plan, destination, option_set),
        requested_at=now,
        data_reality=DataReality.SIMULATED,
        provenance_json={
            "source": "SIMULATED_HOSPITAL_GATEWAY",
            "data_reality": "SIMULATED",
            "freshness_status": "FRESH",
            "source_reference": payload.operator_reference,
        },
    )
    db.add(alert)
    db.add(TimelineEvent(
        id=new_timeline_event_id(), incident_id=incident.id,
        event_type="HOSPITAL_PREALERT_REQUESTED",
        details_json={"prealert_id": alert.id, "hospital_id": destination.hospital_id, "operator_reference": payload.operator_reference},
        created_at=now,
    ))
    gateway_result = hospital_gateway.request_pre_alert(
        payload=alert.payload_json,
        requested_at=now,
        simulate_failure=payload.simulate_failure,
    )
    alert.sent_at = gateway_result.sent_at
    if gateway_result.status is not HospitalPreAlertStatus.FAILED:
        alert.status = HospitalPreAlertStatus.SENT.value
        db.add(TimelineEvent(
            id=new_timeline_event_id(), incident_id=incident.id,
            event_type="HOSPITAL_PREALERT_SENT",
            details_json={"prealert_id": alert.id, "data_reality": DataReality.SIMULATED.value},
            created_at=now,
        ))
    alert.status = gateway_result.status.value
    alert.acknowledged_at = gateway_result.acknowledged_at
    alert.failed_at = gateway_result.failed_at
    alert.failure_reason = gateway_result.failure_reason
    event_type = (
        "HOSPITAL_PREALERT_FAILED"
        if gateway_result.status is HospitalPreAlertStatus.FAILED
        else "HOSPITAL_PREALERT_ACKNOWLEDGED"
    )
    db.add(TimelineEvent(
        id=new_timeline_event_id(), incident_id=incident.id,
        event_type=event_type,
        details_json={"prealert_id": alert.id, "data_reality": DataReality.SIMULATED.value},
        created_at=now,
    ))
    db.commit()
    db.refresh(alert)
    result = _serialize_prealert(alert)
    publish_operations_event(event="hospital.updated", incident_id=incident.id, payload=result)
    return result


@router.get("/incidents/{incident_id}/hospital-prealert", response_model=HospitalPreAlertRead)
def get_hospital_prealert(
    incident_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")
    plan = _approved_plan(db, incident)
    alert = db.scalars(
        select(HospitalPreAlert)
        .where(HospitalPreAlert.incident_id == incident.id, HospitalPreAlert.plan_id == plan.id)
        .order_by(HospitalPreAlert.requested_at.desc(), HospitalPreAlert.id.desc())
    ).first()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hospital pre-alert has been requested")
    return _serialize_prealert(alert)
