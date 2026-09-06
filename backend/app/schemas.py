from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

__all__ = [
    "DataReality",
    "FreshnessStatus",
    "Severity",
    "ConfidenceLevel",
    "IncidentStatus",
    "ResourceType",
    "ResourceStatus",
    "ResponsePlanStatus",
    "Coordinate",
    "ProvenanceMetadata",
    "ResourceRequirement",
    "ManualIncidentCreate",
    "ApprovePlanRequest",
]


class DataReality(str, Enum):
    REAL_PUBLIC = "REAL_PUBLIC"
    REAL_LIVE = "REAL_LIVE"
    REAL_DERIVED = "REAL_DERIVED"
    SIMULATED = "SIMULATED"
    SYNTHETIC = "SYNTHETIC"


class FreshnessStatus(str, Enum):
    LIVE = "LIVE"
    FRESH = "FRESH"
    STALE = "STALE"
    STATIC = "STATIC"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ConfidenceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class IncidentStatus(str, Enum):
    RECEIVED = "RECEIVED"
    INTERPRETING = "INTERPRETING"
    ACTIVE_UNCONFIRMED = "ACTIVE_UNCONFIRMED"
    RESPONSE_PROPOSED = "RESPONSE_PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RESPONSE_ACTIVE = "RESPONSE_ACTIVE"
    EN_ROUTE = "EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    TRANSPORT_ACTIVE = "TRANSPORT_ACTIVE"
    HANDOVER = "HANDOVER"
    CLOSED = "CLOSED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    DUPLICATE_MERGED = "DUPLICATE_MERGED"
    CANCELLED_FALSE_REPORT = "CANCELLED_FALSE_REPORT"


class ResourceType(str, Enum):
    AMBULANCE = "AMBULANCE"
    FIRE_RESCUE = "FIRE_RESCUE"


class ResourceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE = "EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    TRANSPORTING = "TRANSPORTING"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class ResponsePlanStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    RECOMMENDED = "RECOMMENDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class Coordinate(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


class ProvenanceMetadata(BaseModel):
    source: str
    data_reality: DataReality
    last_updated: datetime
    freshness_status: FreshnessStatus
    source_reference: str | None = None


class ResourceRequirement(BaseModel):
    resource_type: ResourceType
    count: int = Field(ge=1, le=5)


class ManualIncidentCreate(BaseModel):
    incident_type: str
    severity: Severity
    confidence_level: ConfidenceLevel = ConfidenceLevel.HIGH
    location: Coordinate
    location_text: str | None = None
    casualty_count: int | None = Field(default=None, ge=0)
    casualty_range: str | None = None
    trapped_person: bool | None = None
    road_blockage: bool | None = None
    required_resources: list[ResourceRequirement] = Field(min_length=1)
    operator_reference: str = "demo-operator"


class ApprovePlanRequest(BaseModel):
    expected_incident_version: int = Field(gt=0)
    expected_plan_version: int = Field(gt=0)
    operator_reference: str = "demo-operator"
