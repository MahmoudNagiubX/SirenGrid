"""Minimal gated local controls for deterministic Phase 08 demo scenarios."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any
import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.benchmark_scenarios import (
    BenchmarkScenario,
    build_candidate_resources,
    load_scenario_manifest,
)
from app.config import REPO_ROOT, settings
from app.db import get_db
from app.incidents import serialize_incident, serialize_timeline_event
from app.models import (
    Approval,
    CorridorState,
    DriverAlert,
    EmergencyResource,
    HospitalDestination,
    HospitalOptionSet,
    HospitalPreAlert,
    Incident,
    ReplanEvaluation,
    Report,
    ResponsePlan,
    TimelineEvent,
    new_timeline_event_id,
)
from app.schemas import (
    ConfidenceLevel,
    DataReality,
    IncidentStatus,
)


router = APIRouter(prefix="/simulation", tags=["simulation"])
_state_lock = Lock()
_loaded_scenario_id: str | None = None
_next_event_index = 0


class SimulationEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_index: int | None = Field(default=None, ge=0)
    next: bool = False

    @model_validator(mode="after")
    def require_one_selector(self) -> "SimulationEventRequest":
        if self.event_index is None and not self.next:
            raise ValueError("event_index or next=true is required")
        if self.event_index is not None and self.next:
            raise ValueError("choose event_index or next=true, not both")
        return self


def _require_enabled() -> None:
    if not settings.SIMULATION_CONTROLS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SIMULATION_CONTROLS_DISABLED: demo/development only",
        )


def _simulation_incident_ids(db: Session) -> list[str]:
    return [
        incident.id
        for incident in db.scalars(select(Incident)).all()
        if incident.id.startswith("simulation-")
    ]


def _reset_simulation_rows(db: Session) -> list[str]:
    incident_ids = _simulation_incident_ids(db)
    if incident_ids:
        for model in (
            Approval,
            CorridorState,
            DriverAlert,
            HospitalDestination,
            HospitalOptionSet,
            HospitalPreAlert,
            ReplanEvaluation,
            Report,
            ResponsePlan,
            TimelineEvent,
        ):
            db.execute(delete(model).where(model.incident_id.in_(incident_ids)))
        db.execute(delete(Incident).where(Incident.id.in_(incident_ids)))

    # The benchmark seed is simulation-owned; no manually created resource is
    # removed unless it is one of these stable seed IDs.
    seed_path = REPO_ROOT / "data" / "scenarios" / "phase01_resources.json"
    try:
        seed_ids = [
            str(item["id"])
            for item in json.loads(seed_path.read_text(encoding="utf-8"))["resources"]
        ]
    except (OSError, KeyError, TypeError, ValueError):
        seed_ids = []
    if seed_ids:
        db.execute(delete(EmergencyResource).where(EmergencyResource.id.in_(seed_ids)))
    return incident_ids


def _scenario_incident(scenario: BenchmarkScenario) -> Incident:
    return Incident(
        id=f"simulation-{scenario.id}",
        version=1,
        incident_type=scenario.incident.incident_type,
        severity=scenario.incident.severity,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=scenario.incident.coordinate.lat,
        longitude=scenario.incident.coordinate.lon,
        transport_required=scenario.incident.transport_required,
        required_hospital_capabilities_json=list(
            scenario.incident.required_hospital_capabilities
        ),
        required_resources_json=[
            {
                "resource_type": requirement.resource_type.value,
                "count": requirement.minimum_count,
                "required_capability_tags": list(requirement.required_capability_tags),
            }
            for requirement in scenario.incident.requirements
        ],
        provenance_json={
            "source": "simulation_scenario_loader",
            "source_reference": scenario.id,
            "data_reality": DataReality.SYNTHETIC.value,
            "freshness_status": "STATIC",
        },
    )


def _load_resources(db: Session, scenario: BenchmarkScenario) -> list[EmergencyResource]:
    resources = build_candidate_resources(scenario)
    rows: list[EmergencyResource] = []
    now = datetime.now(timezone.utc)
    for resource in resources:
        row = EmergencyResource(
            id=resource.resource_id,
            version=1,
            name=f"Simulation {resource.resource_id}",
            resource_type=resource.resource_type,
            capability_tags_json=list(resource.capability_tags),
            status=resource.status,
            latitude=resource.coordinate.lat,
            longitude=resource.coordinate.lon,
            assigned_incident_id=resource.assigned_incident_id,
            last_updated=now,
            provenance_json={
                "source": "simulation_scenario_loader",
                "source_reference": scenario.id,
                "data_reality": DataReality.SIMULATED.value,
                "freshness_status": "STATIC",
            },
        )
        db.add(row)
        rows.append(row)
    return rows


def _find_scenario(scenario_id: str) -> BenchmarkScenario:
    manifest = load_scenario_manifest()
    try:
        return next(item for item in manifest.scenarios if item.id == scenario_id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found") from exc


@router.post("/reset")
def reset_simulation(db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_enabled()
    global _loaded_scenario_id, _next_event_index
    with _state_lock:
        removed_incidents = _reset_simulation_rows(db)
        db.commit()
        _loaded_scenario_id = None
        _next_event_index = 0
    return {
        "mode": "SIMULATED",
        "scope": "DEMO_ONLY",
        "status": "RESET",
        "removed_simulation_incident_ids": sorted(removed_incidents),
    }


@router.post("/load/{scenario_id}")
def load_simulation_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_enabled()
    scenario = _find_scenario(scenario_id)
    global _loaded_scenario_id, _next_event_index
    with _state_lock:
        _reset_simulation_rows(db)
        incident = _scenario_incident(scenario)
        db.add(incident)
        resources = _load_resources(db, scenario)
        event = TimelineEvent(
            id=new_timeline_event_id(),
            incident_id=incident.id,
            event_type="SIMULATION_SCENARIO_LOADED",
            details_json={
                "scenario_id": scenario.id,
                "dataset_version": "PHASE08_SCENARIO_DATASET_V1",
                "data_reality": DataReality.SYNTHETIC.value,
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.commit()
        db.refresh(incident)
        _loaded_scenario_id = scenario.id
        _next_event_index = 0
    return {
        "mode": "SIMULATED",
        "scope": "DEMO_ONLY",
        "status": "LOADED",
        "scenario_id": scenario.id,
        "incident": serialize_incident(incident),
        "resource_ids": sorted(resource.id for resource in resources),
        "event_count": len(scenario.events),
    }


@router.post("/events")
def trigger_simulation_event(
    payload: SimulationEventRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_enabled()
    global _next_event_index
    with _state_lock:
        if _loaded_scenario_id is None:
            raise HTTPException(status_code=409, detail="No simulation scenario is loaded")
        scenario = _find_scenario(_loaded_scenario_id)
        ordered = sorted(scenario.events, key=lambda item: (item.at_seconds, item.event_index))
        target_index = _next_event_index if payload.next else payload.event_index
        event = next((item for item in ordered if item.event_index == target_index), None)
        if event is None:
            raise HTTPException(status_code=404, detail="Simulation event not found")
        if event.event_index < _next_event_index:
            raise HTTPException(status_code=409, detail="Simulation event already applied")
        if event.event_index > _next_event_index:
            raise HTTPException(status_code=409, detail="Simulation events must follow manifest order")
        incident = db.get(Incident, f"simulation-{scenario.id}")
        if incident is None:
            raise HTTPException(status_code=409, detail="Loaded simulation incident is missing")
        changed_resources: list[str] = []
        for override in event.resource_overrides:
            resource = db.get(EmergencyResource, override.resource_id)
            if resource is None:
                raise HTTPException(status_code=409, detail="Simulation resource is missing")
            if override.status is not None:
                resource.status = override.status
            if "assigned_incident_id" in override.model_fields_set:
                resource.assigned_incident_id = override.assigned_incident_id
            if override.latitude is not None:
                resource.latitude = override.latitude
            if override.longitude is not None:
                resource.longitude = override.longitude
            resource.version += 1
            resource.last_updated = datetime.now(timezone.utc)
            changed_resources.append(resource.id)
        created_incident_id = None
        if event.event_type == "SECOND_INCIDENT" and event.incident is not None:
            created = _scenario_incident(scenario.model_copy(update={"incident": event.incident}))
            created.id = f"simulation-{scenario.id}-event-{event.event_index}"
            db.add(created)
            created_incident_id = created.id
        timeline = TimelineEvent(
            id=new_timeline_event_id(),
            incident_id=incident.id,
            event_type="SIMULATION_EVENT_TRIGGERED",
            details_json={
                "scenario_id": scenario.id,
                "event_index": event.event_index,
                "event_type": event.event_type,
                "changed_resource_ids": sorted(changed_resources),
                "created_incident_id": created_incident_id,
                "data_reality": DataReality.SIMULATED.value,
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(timeline)
        db.commit()
        _next_event_index += 1
    return {
        "mode": "SIMULATED",
        "scope": "DEMO_ONLY",
        "status": "EVENT_APPLIED",
        "scenario_id": scenario.id,
        "event_index": event.event_index,
        "event_type": event.event_type,
        "changed_resource_ids": sorted(changed_resources),
        "created_incident_id": created_incident_id,
        "timeline_event": serialize_timeline_event(timeline),
    }


@router.get("/status")
def simulation_status() -> dict[str, Any]:
    _require_enabled()
    with _state_lock:
        return {
            "mode": "SIMULATED",
            "scope": "DEMO_ONLY",
            "enabled": True,
            "scenario_id": _loaded_scenario_id,
            "next_event_index": _next_event_index,
            "scheduler": "NONE",
        }
