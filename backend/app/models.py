from __future__ import annotations

from datetime import datetime, timezone
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.schemas import (
    ConfidenceLevel,
    DataReality,
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
]


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
    required_resources_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
    )
    current_plan_id: Mapped[str | None] = mapped_column(
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
        default=lambda: str(uuid.uuid4()),
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
