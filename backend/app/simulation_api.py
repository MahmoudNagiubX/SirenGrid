from __future__ import annotations

from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session
from typing_extensions import Self

from app.benchmark_scenarios import load_scenario_manifest
from app.config import settings
from app.db import get_db
from app.hospital_api import patch_hospital_simulation_state
from app.models import EmergencyResource
from app.resources import patch_resource_state
from app.schemas import (
    DataReality,
    HospitalAcceptingState,
    HospitalOperationalStatePatchRequest,
    ResourceStatePatchRequest,
    ResourceStatus,
)

router = APIRouter(prefix="/simulation", tags=["simulation"])


class SimulationStatusRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    loaded_scenario_id: str | None = None
    seed: int | None = None
    runtime_version: int = 1
    event_index: int = 0
    last_event_type: str | None = None
    reality: str = DataReality.SYNTHETIC.value


class SimulationResetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "RESET"
    simulation: SimulationStatusRead
    reality: str = DataReality.SYNTHETIC.value


class SimulationLoadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "LOADED"
    scenario_id: str
    seed: int
    master_plan_case: str
    simulation: SimulationStatusRead
    reality: str = DataReality.SYNTHETIC.value


class ResourceStateEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1)
    status: ResourceStatus
    expected_resource_version: int | None = None
    incident_id: str | None = None


class HospitalStateEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hospital_id: str = Field(min_length=1)
    accepting_state: HospitalAcceptingState | None = None
    simulated_load_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    simulated_free_capacity: int | None = Field(default=None, ge=0)
    expected_version: int | None = None


class SimulationEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["RESOURCE_STATE", "HOSPITAL_STATE"]
    resource_payload: ResourceStateEventPayload | None = None
    hospital_payload: HospitalStateEventPayload | None = None

    @model_validator(mode="after")
    def validate_payload_matches_type(self) -> Self:
        if self.event_type == "RESOURCE_STATE":
            if self.resource_payload is None:
                raise ValueError("resource_payload is required for RESOURCE_STATE event")
            if self.hospital_payload is not None:
                raise ValueError("hospital_payload must not be supplied for RESOURCE_STATE event")
        elif self.event_type == "HOSPITAL_STATE":
            if self.hospital_payload is None:
                raise ValueError("hospital_payload is required for HOSPITAL_STATE event")
            if self.resource_payload is not None:
                raise ValueError("resource_payload must not be supplied for HOSPITAL_STATE event")
        return self


class SimulationEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "EVENT_APPLIED"
    event_index: int
    event_type: str
    simulation: SimulationStatusRead
    reality: str = DataReality.SYNTHETIC.value
    details: dict[str, Any] = Field(default_factory=dict)


class SimulationControllerState:
    """Process-local lock-protected simulation demo controller state."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.loaded_scenario_id: str | None = None
        self.scenario_seed: int | None = None
        self.runtime_version: int = 1
        self.event_index: int = 0
        self.last_event_type: str | None = None
        self.reality: str = DataReality.SYNTHETIC.value

    def reset(self) -> None:
        with self._lock:
            self.loaded_scenario_id = None
            self.scenario_seed = None
            self.runtime_version += 1
            self.event_index = 0
            self.last_event_type = None
            self.reality = DataReality.SYNTHETIC.value

    def load_scenario(self, scenario_id: str, seed: int) -> None:
        with self._lock:
            self.loaded_scenario_id = scenario_id
            self.scenario_seed = seed
            self.runtime_version += 1
            self.event_index = 0
            self.last_event_type = None
            self.reality = DataReality.SYNTHETIC.value

    def record_event(self, event_type: str) -> int:
        with self._lock:
            self.event_index += 1
            self.last_event_type = event_type
            self.runtime_version += 1
            return self.event_index

    def get_status(self, enabled: bool) -> SimulationStatusRead:
        with self._lock:
            return SimulationStatusRead(
                enabled=enabled,
                loaded_scenario_id=self.loaded_scenario_id,
                seed=self.scenario_seed,
                runtime_version=self.runtime_version,
                event_index=self.event_index,
                last_event_type=self.last_event_type,
                reality=self.reality,
            )


simulation_controller = SimulationControllerState()


def _ensure_simulation_enabled() -> None:
    if not settings.simulation_controls_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SIMULATION_DISABLED",
        )


@router.get("/status", response_model=SimulationStatusRead)
def get_simulation_status() -> SimulationStatusRead:
    """Report simulation controller status; safe when disabled."""
    return simulation_controller.get_status(enabled=settings.simulation_controls_enabled)


@router.post("/reset", response_model=SimulationResetResponse)
def reset_simulation() -> SimulationResetResponse:
    """Reset simulation controller metadata to baseline; requires simulation enabled."""
    _ensure_simulation_enabled()
    simulation_controller.reset()
    return SimulationResetResponse(
        status="RESET",
        simulation=simulation_controller.get_status(enabled=True),
        reality=DataReality.SYNTHETIC.value,
    )


@router.post("/load/{scenario_id}", response_model=SimulationLoadResponse)
def load_simulation_scenario(scenario_id: str) -> SimulationLoadResponse:
    """Load deterministic benchmark scenario metadata; requires simulation enabled."""
    _ensure_simulation_enabled()
    manifest = load_scenario_manifest()
    scenario = next((s for s in manifest.scenarios if s.id == scenario_id), None)
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario '{scenario_id}' not found in benchmark manifest",
        )
    simulation_controller.load_scenario(scenario.id, scenario.seed)
    return SimulationLoadResponse(
        status="LOADED",
        scenario_id=scenario.id,
        seed=scenario.seed,
        master_plan_case=scenario.master_plan_case,
        simulation=simulation_controller.get_status(enabled=True),
        reality=DataReality.SYNTHETIC.value,
    )


@router.post("/events", response_model=SimulationEventResponse)
def apply_simulation_event(
    payload: SimulationEventRequest,
    db: Session = Depends(get_db),  # noqa: B008
) -> SimulationEventResponse:
    """Apply bounded deterministic demo event; reuses existing domain validation."""
    _ensure_simulation_enabled()

    details: dict[str, Any] = {}
    if payload.event_type == "RESOURCE_STATE":
        assert payload.resource_payload is not None
        p = payload.resource_payload
        resource = db.get(EmergencyResource, p.resource_id)
        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Emergency resource '{p.resource_id}' not found",
            )
        expected_ver = (
            p.expected_resource_version
            if p.expected_resource_version is not None
            else resource.version
        )
        patch_req = ResourceStatePatchRequest(
            status=p.status,
            expected_resource_version=expected_ver,
            incident_id=p.incident_id,
            operator_reference="simulation_controls",
        )
        details = patch_resource_state(
            resource_id=p.resource_id,
            payload=patch_req,
            db=db,
        )
    elif payload.event_type == "HOSPITAL_STATE":
        assert payload.hospital_payload is not None
        hp = payload.hospital_payload
        patch_payload = HospitalOperationalStatePatchRequest(
            expected_version=hp.expected_version,
            accepting_state=hp.accepting_state,
            simulated_load_ratio=hp.simulated_load_ratio,
            simulated_free_capacity=hp.simulated_free_capacity,
            operator_reference="simulation_controls",
        )
        details = patch_hospital_simulation_state(
            hospital_id=hp.hospital_id,
            payload=patch_payload,
            db=db,
        )

    event_idx = simulation_controller.record_event(payload.event_type)
    return SimulationEventResponse(
        status="EVENT_APPLIED",
        event_index=event_idx,
        event_type=payload.event_type,
        simulation=simulation_controller.get_status(enabled=True),
        reality=DataReality.SYNTHETIC.value,
        details=details,
    )
