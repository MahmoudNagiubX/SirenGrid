from __future__ import annotations

from datetime import datetime, timezone
import secrets
import threading
import time
from typing import Any
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Enum as SAEnum,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.schemas import (
    ConfidenceLevel,
    DataReality,
    HospitalAcceptingState,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)

__all__ = [
    "Incident",
    "EmergencyResource",
    "ResponsePlan",
    "Approval",
    "TimelineEvent",
    "Report",
    "HospitalOperationalState",
    "HospitalOptionSet",
    "HospitalDestination",
    "HospitalPreAlert",
    "CorridorState",
    "DriverAlert",
    "ReplanEvaluation",
    "new_timeline_event_id",
]


_EVENT_ID_LOCK = threading.Lock()
_EVENT_ID_LAST_MS = 0
_EVENT_ID_COUNTER = 0
_EVENT_ID_MAX_COUNTER = 0xFFF


def new_timeline_event_id() -> str:
    """Return a time-ordered UUIDv7 identifier for an audit timeline event.

    Timeline reads order by ``created_at`` then ``id``. Wall-clock resolution
    is coarse enough that consecutive operator commands can share a
    ``created_at`` value, and a random UUID4 tiebreak then returns the audit
    trail in arbitrary order. A UUIDv7 keeps the identifier a valid UUID while
    making lexicographic order match insertion order.

    The 12 bits after the millisecond timestamp hold a monotonic counter, so
    events created inside one millisecond still order correctly. The counter
    also absorbs a backwards clock step rather than reissuing a lower
    identifier.
    """
    global _EVENT_ID_LAST_MS, _EVENT_ID_COUNTER
    with _EVENT_ID_LOCK:
        now_ms = time.time_ns() // 1_000_000
        if now_ms > _EVENT_ID_LAST_MS:
            _EVENT_ID_LAST_MS = now_ms
            _EVENT_ID_COUNTER = 0
        else:
            _EVENT_ID_COUNTER += 1
            if _EVENT_ID_COUNTER > _EVENT_ID_MAX_COUNTER:
                _EVENT_ID_LAST_MS += 1
                _EVENT_ID_COUNTER = 0
        milliseconds = _EVENT_ID_LAST_MS
        counter = _EVENT_ID_COUNTER

    value = (milliseconds & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76
    value |= counter << 64
    value |= 0b10 << 62
    value |= secrets.randbits(62)
    return str(uuid.UUID(int=value))


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    incident_type: Mapped[str] = mapped_column(String)
    severity: Mapped[Severity] = mapped_column(
        SAEnum(
            Severity,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        )
    )
    confidence_level: Mapped[ConfidenceLevel] = mapped_column(
        SAEnum(
            ConfidenceLevel,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        )
    )
    status: Mapped[IncidentStatus] = mapped_column(
        SAEnum(
            IncidentStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        )
    )
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    location_text: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )
    casualty_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    casualty_range: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )
    trapped_person: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        default=None,
    )
    road_blockage: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        default=None,
    )
    transport_required: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        default=None,
    )
    required_hospital_capabilities_json: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
    )
    required_resources_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
    )
    current_plan_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        default=None,
    )
    pending_replan_plan_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
    )


class EmergencyResource(Base):
    __tablename__ = "emergency_resources"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String)
    resource_type: Mapped[ResourceType] = mapped_column(
        SAEnum(
            ResourceType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        )
    )
    capability_tags_json: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
    )
    status: Mapped[ResourceStatus] = mapped_column(
        SAEnum(
            ResourceStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        )
    )
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    home_zone: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )
    assigned_incident_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        default=None,
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
    )


class ResponsePlan(Base):
    __tablename__ = "response_plans"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    incident_id: Mapped[str] = mapped_column(String(36))
    incident_version: Mapped[int] = mapped_column(Integer)
    plan_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[ResponsePlanStatus] = mapped_column(
        SAEnum(
            ResponsePlanStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        )
    )
    resource_ids_json: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
    )
    routes_json: Mapped[list[dict[str, Any]] | dict[str, Any]] = mapped_column(
        JSON,
        default=list,
    )
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
    )
    score_breakdown_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ReplanEvaluation(Base):
    __tablename__ = "replan_evaluations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    incident_id: Mapped[str] = mapped_column(String(36))
    active_plan_id: Mapped[str] = mapped_column(String(36))
    pending_plan_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        default=None,
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String, default="PENDING")
    trigger_reasons_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    input_references_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    explanation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    first_triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    last_triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    debounce_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    plan_id: Mapped[str] = mapped_column(String(36))
    incident_id: Mapped[str] = mapped_column(String(36))
    operator_reference: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    expected_incident_version: Mapped[int] = mapped_column(Integer)
    expected_plan_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_timeline_event_id,
    )
    incident_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String)
    details_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    incident_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        default=None,
    )
    source_type: Mapped[str] = mapped_column(String)
    source_reference: Mapped[str] = mapped_column(String)
    raw_text: Mapped[str] = mapped_column(String)
    location_text: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )
    location_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    data_reality: Mapped[DataReality] = mapped_column(
        SAEnum(
            DataReality,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DataReality.SIMULATED,
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
    )
    processing_status: Mapped[str] = mapped_column(
        String,
        default="PROCESSED",
    )
    evidence_items_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class HospitalOperationalState(Base):
    __tablename__ = "hospital_operational_states"

    hospital_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    accepting_state: Mapped[str] = mapped_column(
        String,
        default=HospitalAcceptingState.UNKNOWN.value,
    )
    simulated_load_ratio: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    simulated_free_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    incoming_cases: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    freshness_status: Mapped[str] = mapped_column(String, default="UNKNOWN")
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    source: Mapped[str] = mapped_column(String, default="SIMULATED_HOSPITAL_GATEWAY")
    data_reality: Mapped[DataReality] = mapped_column(
        SAEnum(
            DataReality,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DataReality.SIMULATED,
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class HospitalOptionSet(Base):
    __tablename__ = "hospital_option_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(36))
    plan_id: Mapped[str] = mapped_column(String(36))
    incident_version: Mapped[int] = mapped_column(Integer)
    plan_version: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    options_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    excluded_hospitals_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class HospitalDestination(Base):
    __tablename__ = "hospital_destinations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(36))
    plan_id: Mapped[str] = mapped_column(String(36))
    option_set_id: Mapped[str] = mapped_column(String(36))
    hospital_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String, default="SELECTED")
    incident_version: Mapped[int] = mapped_column(Integer)
    plan_version: Mapped[int] = mapped_column(Integer)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class HospitalPreAlert(Base):
    __tablename__ = "hospital_pre_alerts"
    __table_args__ = (UniqueConstraint("destination_id", name="uq_hospital_pre_alert_destination"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(36))
    plan_id: Mapped[str] = mapped_column(String(36))
    destination_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    data_reality: Mapped[DataReality] = mapped_column(
        SAEnum(
            DataReality,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DataReality.SIMULATED,
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class CorridorState(Base):
    __tablename__ = "corridor_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(36))
    plan_id: Mapped[str] = mapped_column(String(36))
    route_reference: Mapped[str] = mapped_column(String)
    route_geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    signals_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String, default="NORMAL")
    safety_lead_time_seconds: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    data_reality: Mapped[DataReality] = mapped_column(
        SAEnum(
            DataReality,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DataReality.SIMULATED,
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DriverAlert(Base):
    __tablename__ = "driver_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(36))
    plan_id: Mapped[str] = mapped_column(String(36))
    resource_id: Mapped[str] = mapped_column(String(36))
    route_reference: Mapped[str] = mapped_column(String)
    route_progress: Mapped[float] = mapped_column(Float)
    geometry_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    data_reality: Mapped[DataReality] = mapped_column(
        SAEnum(
            DataReality,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DataReality.SIMULATED,
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
