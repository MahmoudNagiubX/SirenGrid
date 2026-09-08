from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "DataReality",
    "FreshnessStatus",
    "Severity",
    "ConfidenceLevel",
    "IncidentStatus",
    "ResourceType",
    "ResourceStatus",
    "ResponsePlanStatus",
    "HospitalAcceptingState",
    "HospitalPreAlertStatus",
    "CorridorSignalState",
    "DriverAlertStatus",
    "Coordinate",
    "ProvenanceMetadata",
    "ResourceRequirement",
    "ManualIncidentCreate",
    "IncidentRead",
    "ResourceRead",
    "ResponsePlanRead",
    "SelectAlternativePlanRequest",
    "PlanIncidentSummary",
    "ApprovalRecordRead",
    "ApprovalResult",
    "ApprovePlanRequest",
    "RoutePreviewRequest",
    "RoutePreviewResponse",
    "RouteAlternativeRead",
    "TrafficPrototypePolicyRead",
    "TrafficSnapshotRead",
    "MapLayerResponse",
    "EvidenceItemCreate",
    "EvidenceItemRead",
    "ReportCreate",
    "ReportRead",
    "IncidentTransitionRequest",
    "IncidentCloseRequest",
    "TimelineEventRead",
    "IncidentFactsPatchRequest",
    "IncidentFactsPatchResponse",
    "ResourceAssignRequest",
    "ResourceStatePatchRequest",
    "ResourceReleaseRequest",
    "ResourceMovementRequest",
    "OperationsEventEnvelope",
    "HospitalRead",
    "HospitalOperationalStatePatchRequest",
    "HospitalOptionRead",
    "HospitalOptionsResponse",
    "SelectHospitalDestinationRequest",
    "HospitalDestinationRead",
    "HospitalPreAlertRequest",
    "HospitalPreAlertRead",
    "CorridorGenerateRequest",
    "CorridorSignalRead",
    "CorridorRead",
    "CorridorPriorityRequest",
    "DriverAlertRefreshRequest",
    "DriverAlertRead",
    "IncidentOperationalStateRead",
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
    ALTERNATIVE = "ALTERNATIVE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class HospitalAcceptingState(str, Enum):
    ACCEPTING = "ACCEPTING"
    NOT_ACCEPTING = "NOT_ACCEPTING"
    UNKNOWN = "UNKNOWN"


class HospitalPreAlertStatus(str, Enum):
    REQUESTED = "REQUESTED"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"


class CorridorSignalState(str, Enum):
    NORMAL = "NORMAL"
    REQUESTED = "REQUESTED"
    PREPARING = "PREPARING"
    PRIORITY_ACTIVE = "PRIORITY_ACTIVE"
    PASSED = "PASSED"
    FAILED = "FAILED"


class DriverAlertStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


class Coordinate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lat": 30.0561,
                "lon": 31.3452,
            }
        }
    )

    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


class ProvenanceMetadata(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source": "operator_manual_entry",
                "data_reality": "SIMULATED",
                "freshness_status": "FRESH",
                "last_updated": "2026-09-06T18:00:00Z",
                "source_reference": "dispatcher-op-01",
            }
        }
    )

    source: str
    data_reality: DataReality
    last_updated: datetime
    freshness_status: FreshnessStatus
    source_reference: str | None = None


class ResourceRequirement(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resource_type": "AMBULANCE",
                "count": 2,
            }
        }
    )

    resource_type: ResourceType
    count: int = Field(ge=1, le=5)


class ManualIncidentCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "incident_type": "traffic_collision",
                "severity": "HIGH",
                "confidence_level": "HIGH",
                "location": {"lat": 30.0561, "lon": 31.3452},
                "location_text": "El-Nasr Road intersection with Abbas El-Akkad, Nasr City",
                "casualty_count": 2,
                "casualty_range": "2-3",
                "trapped_person": True,
                "road_blockage": True,
                "required_resources": [
                    {"resource_type": "AMBULANCE", "count": 2},
                    {"resource_type": "FIRE_RESCUE", "count": 1},
                ],
                "operator_reference": "dispatcher-op-01",
            }
        }
    )

    incident_type: str
    severity: Severity
    confidence_level: ConfidenceLevel = ConfidenceLevel.HIGH
    location: Coordinate
    location_text: str | None = None
    casualty_count: int | None = Field(default=None, ge=0)
    casualty_range: str | None = None
    trapped_person: bool | None = None
    road_blockage: bool | None = None
    transport_required: bool | None = None
    required_hospital_capabilities: list[str] = Field(default_factory=list)
    required_resources: list[ResourceRequirement] = Field(min_length=1)
    operator_reference: str = "demo-operator"


class IncidentRead(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                "version": 1,
                "status": "ACTIVE_UNCONFIRMED",
                "incident_type": "traffic_collision",
                "severity": "HIGH",
                "confidence_level": "HIGH",
                "location": {"lat": 30.0561, "lon": 31.3452},
                "latitude": 30.0561,
                "longitude": 31.3452,
                "location_text": "El-Nasr Road intersection with Abbas El-Akkad, Nasr City",
                "casualty_count": 2,
                "casualty_range": "2-3",
                "trapped_person": True,
                "road_blockage": True,
                "required_resources": [
                    {"resource_type": "AMBULANCE", "count": 2},
                    {"resource_type": "FIRE_RESCUE", "count": 1},
                ],
                "required_resources_json": [
                    {"resource_type": "AMBULANCE", "count": 2},
                    {"resource_type": "FIRE_RESCUE", "count": 1},
                ],
                "current_plan_id": None,
                "created_at": "2026-09-06T18:00:00Z",
                "updated_at": "2026-09-06T18:00:00Z",
                "provenance": {
                    "source": "operator_manual_entry",
                    "data_reality": "SIMULATED",
                    "freshness_status": "FRESH",
                    "last_updated": "2026-09-06T18:00:00Z",
                    "source_reference": "dispatcher-op-01",
                },
                "provenance_json": {
                    "source": "operator_manual_entry",
                    "data_reality": "SIMULATED",
                    "freshness_status": "FRESH",
                    "last_updated": "2026-09-06T18:00:00Z",
                    "source_reference": "dispatcher-op-01",
                },
            }
        }
    )

    id: str
    version: int
    status: IncidentStatus
    incident_type: str
    severity: Severity
    confidence_level: ConfidenceLevel
    location: Coordinate
    latitude: float
    longitude: float
    location_text: str | None = None
    casualty_count: int | None = None
    casualty_range: str | None = None
    trapped_person: bool | None = None
    road_blockage: bool | None = None
    transport_required: bool | None = None
    required_hospital_capabilities: list[str] = Field(default_factory=list)
    required_resources: list[ResourceRequirement] = Field(default_factory=list)
    required_resources_json: list[ResourceRequirement] = Field(default_factory=list)
    current_plan_id: str | None = None
    pending_replan_plan_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    provenance_json: dict[str, Any] = Field(default_factory=dict)


class ResourceRead(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "res-amb-01",
                "version": 1,
                "name": "Ambulance Unit 01",
                "resource_type": "AMBULANCE",
                "type": "AMBULANCE",
                "capabilities": ["BLS", "OXYGEN"],
                "capability_tags": ["BLS", "OXYGEN"],
                "capability_tags_json": ["BLS", "OXYGEN"],
                "status": "AVAILABLE",
                "operational_status": "AVAILABLE",
                "latitude": 30.0621,
                "longitude": 31.3398,
                "location": {"lat": 30.0621, "lon": 31.3398},
                "home_zone": "zone-nasr-city-north",
                "assigned_incident_id": None,
                "assignment": None,
                "last_updated": "2026-09-06T18:00:00Z",
                "provenance": {
                    "source": "simulated_station_feed",
                    "data_reality": "SIMULATED",
                    "freshness_status": "FRESH",
                    "last_updated": "2026-09-06T18:00:00Z",
                    "source_reference": "station-nasr-01",
                },
                "provenance_json": {
                    "source": "simulated_station_feed",
                    "data_reality": "SIMULATED",
                    "freshness_status": "FRESH",
                    "last_updated": "2026-09-06T18:00:00Z",
                    "source_reference": "station-nasr-01",
                },
                "is_planner_eligible": True,
            }
        }
    )

    id: str
    version: int
    name: str
    resource_type: ResourceType
    type: ResourceType
    capabilities: list[str] = Field(default_factory=list)
    capability_tags: list[str] = Field(default_factory=list)
    capability_tags_json: list[str] = Field(default_factory=list)
    status: ResourceStatus
    operational_status: ResourceStatus
    latitude: float
    longitude: float
    location: Coordinate
    home_zone: str | None = None
    assigned_incident_id: str | None = None
    assignment: str | None = None
    last_updated: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    provenance_json: dict[str, Any] = Field(default_factory=dict)
    is_planner_eligible: bool
    route_progress: float | None = None


class ResponsePlanRead(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "plan-5f2b8492-4f38-4ce6-993d-83b6b19a771e",
                "plan_id": "plan-5f2b8492-4f38-4ce6-993d-83b6b19a771e",
                "incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                "incident_version": 1,
                "plan_version": 1,
                "version": 1,
                "status": "RECOMMENDED",
                "resource_ids": ["res-amb-01"],
                "resource_ids_json": ["res-amb-01"],
                "routes": [
                    {
                        "resource_id": "res-amb-01",
                        "resource_type": "AMBULANCE",
                        "resource_name": "Ambulance Unit 01",
                        "origin": {"lat": 30.0621, "lon": 31.3398},
                        "destination": {"lat": 30.0561, "lon": 31.3452},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[31.3398, 30.0621], [31.3452, 30.0561]],
                        },
                        "distance_m": 1250.5,
                        "eta_seconds": 187.5,
                        "origin_snap_distance_m": 12.3,
                        "destination_snap_distance_m": 8.7,
                        "snap_distances": {
                            "origin_snap_distance_m": 12.3,
                            "destination_snap_distance_m": 8.7,
                        },
                        "routing_source": "OSM_BASE_TRAVEL_TIME",
                        "nodes": [101, 102, 103],
                    }
                ],
                "routes_json": [
                    {
                        "resource_id": "res-amb-01",
                        "resource_type": "AMBULANCE",
                        "resource_name": "Ambulance Unit 01",
                        "origin": {"lat": 30.0621, "lon": 31.3398},
                        "destination": {"lat": 30.0561, "lon": 31.3452},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[31.3398, 30.0621], [31.3452, 30.0561]],
                        },
                        "distance_m": 1250.5,
                        "eta_seconds": 187.5,
                        "origin_snap_distance_m": 12.3,
                        "destination_snap_distance_m": 8.7,
                        "snap_distances": {
                            "origin_snap_distance_m": 12.3,
                            "destination_snap_distance_m": 8.7,
                        },
                        "routing_source": "OSM_BASE_TRAVEL_TIME",
                        "nodes": [101, 102, 103],
                    }
                ],
                "metrics": {
                    "max_arrival_eta_seconds": 187.5,
                    "mean_arrival_eta_seconds": 187.5,
                    "selected_resource_count": 1,
                    "routing_source": "OSM_BASE_TRAVEL_TIME",
                },
                "metrics_json": {
                    "max_arrival_eta_seconds": 187.5,
                    "mean_arrival_eta_seconds": 187.5,
                    "selected_resource_count": 1,
                    "routing_source": "OSM_BASE_TRAVEL_TIME",
                },
                "score_breakdown": {
                    "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
                    "coverage_considered": False,
                    "traffic_source": "OSM_BASE_TRAVEL_TIME",
                    "note": "Phase 01 minimal plan. Coverage-aware optimization arrives in Phase 04.",
                },
                "score_breakdown_json": {
                    "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
                    "coverage_considered": False,
                    "traffic_source": "OSM_BASE_TRAVEL_TIME",
                    "note": "Phase 01 minimal plan. Coverage-aware optimization arrives in Phase 04.",
                },
                "created_at": "2026-09-06T18:05:00Z",
            }
        }
    )

    id: str
    plan_id: str
    incident_id: str
    incident_version: int
    plan_version: int
    version: int
    status: ResponsePlanStatus
    resource_ids: list[str] = Field(default_factory=list)
    resource_ids_json: list[str] = Field(default_factory=list)
    routes: list[dict[str, Any]] = Field(default_factory=list)
    routes_json: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    score_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    candidate_set_id: str | None = None
    candidate_rank: int | None = None
    candidate_count: int | None = None


class ReplanTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_incident_version: int = Field(ge=1)
    trigger_reasons: list[str] = Field(min_length=1, max_length=16)
    input_references: dict[str, Any] = Field(default_factory=dict)


class ReplanEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_incident_version: int = Field(ge=1)


class ReplanEvaluationRead(BaseModel):
    id: str
    incident_id: str
    active_plan_id: str
    pending_plan_id: str | None = None
    input_fingerprint: str
    status: str
    trigger_reasons: list[str] = Field(default_factory=list)
    input_references: dict[str, Any] = Field(default_factory=dict)
    explanation: dict[str, Any] = Field(default_factory=dict)
    first_triggered_at: str | None = None
    last_triggered_at: str | None = None
    debounce_until: str | None = None
    evaluated_at: str | None = None
    incident_version: int
    idempotent: bool = False


class ReplanEvaluationResponse(BaseModel):
    incident_id: str
    incident_version: int
    active_plan_id: str
    pending_plan_id: str | None = None
    status: str
    material: bool
    idempotent: bool = False
    trigger_reasons: list[str] = Field(default_factory=list)
    input_fingerprint: str | None = None
    explanation: dict[str, Any] = Field(default_factory=dict)
    evaluation: ReplanEvaluationRead | None = None
    plans: list[ResponsePlanRead] = Field(default_factory=list)


class PlanIncidentSummary(BaseModel):
    id: str
    status: IncidentStatus
    version: int


class ApprovalRecordRead(BaseModel):
    id: str
    plan_id: str
    incident_id: str
    action: str
    operator_reference: str
    expected_incident_version: int
    expected_plan_version: int
    created_at: str | None = None


class ApprovalResult(ResponsePlanRead):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "plan-5f2b8492-4f38-4ce6-993d-83b6b19a771e",
                "plan_id": "plan-5f2b8492-4f38-4ce6-993d-83b6b19a771e",
                "incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                "incident_version": 1,
                "plan_version": 1,
                "version": 1,
                "status": "APPROVED",
                "resource_ids": ["res-amb-01"],
                "resource_ids_json": ["res-amb-01"],
                "routes": [
                    {
                        "resource_id": "res-amb-01",
                        "distance_m": 1250.5,
                        "eta_seconds": 187.5,
                        "routing_source": "OSM_BASE_TRAVEL_TIME",
                    }
                ],
                "routes_json": [
                    {
                        "resource_id": "res-amb-01",
                        "distance_m": 1250.5,
                        "eta_seconds": 187.5,
                        "routing_source": "OSM_BASE_TRAVEL_TIME",
                    }
                ],
                "metrics": {
                    "max_arrival_eta_seconds": 187.5,
                    "mean_arrival_eta_seconds": 187.5,
                    "selected_resource_count": 1,
                    "routing_source": "OSM_BASE_TRAVEL_TIME",
                },
                "metrics_json": {
                    "max_arrival_eta_seconds": 187.5,
                    "mean_arrival_eta_seconds": 187.5,
                    "selected_resource_count": 1,
                    "routing_source": "OSM_BASE_TRAVEL_TIME",
                },
                "score_breakdown": {
                    "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
                    "traffic_source": "OSM_BASE_TRAVEL_TIME",
                },
                "score_breakdown_json": {
                    "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
                    "traffic_source": "OSM_BASE_TRAVEL_TIME",
                },
                "created_at": "2026-09-06T18:05:00Z",
                "incident_status": "RESPONSE_ACTIVE",
                "incident": {
                    "id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                    "status": "RESPONSE_ACTIVE",
                    "version": 2,
                },
                "resources": [
                    {
                        "id": "res-amb-01",
                        "version": 2,
                        "name": "Ambulance Unit 01",
                        "resource_type": "AMBULANCE",
                        "type": "AMBULANCE",
                        "capabilities": ["BLS"],
                        "capability_tags": ["BLS"],
                        "capability_tags_json": ["BLS"],
                        "status": "ASSIGNED",
                        "operational_status": "ASSIGNED",
                        "latitude": 30.0621,
                        "longitude": 31.3398,
                        "location": {"lat": 30.0621, "lon": 31.3398},
                        "assigned_incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                        "assignment": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                        "last_updated": "2026-09-06T18:06:00Z",
                        "provenance": {
                            "source": "simulated_station_feed",
                            "data_reality": "SIMULATED",
                        },
                        "provenance_json": {
                            "source": "simulated_station_feed",
                            "data_reality": "SIMULATED",
                        },
                        "is_planner_eligible": False,
                    }
                ],
                "approval": {
                    "id": "appr-12345",
                    "plan_id": "plan-5f2b8492-4f38-4ce6-993d-83b6b19a771e",
                    "incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                    "action": "APPROVE_PLAN",
                    "operator_reference": "dispatcher-op-01",
                    "expected_incident_version": 1,
                    "expected_plan_version": 1,
                    "created_at": "2026-09-06T18:06:00Z",
                },
            }
        }
    )

    incident_status: IncidentStatus
    incident: PlanIncidentSummary
    resources: list[ResourceRead] = Field(default_factory=list)
    approval: ApprovalRecordRead


class ApprovePlanRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "expected_incident_version": 2,
                "expected_plan_version": 1,
                "operator_reference": "dispatcher-op-01",
            }
        }
    )

    expected_incident_version: int = Field(gt=0)
    expected_plan_version: int = Field(gt=0)
    operator_reference: str = "demo-operator"


class SelectAlternativePlanRequest(BaseModel):
    expected_incident_version: int = Field(gt=0)
    expected_plan_version: int = Field(gt=0)
    operator_reference: str = "demo-operator"


class RoutePreviewRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "origin": {"lat": 30.0621, "lon": 31.3398},
                "destination": {"lat": 30.0561, "lon": 31.3452},
            }
        }
    )

    origin: Coordinate
    destination: Coordinate


class RouteAlternativeRead(BaseModel):
    nodes: list[Any]
    edge_keys: list[tuple[str, str, str]]
    geometry: dict[str, Any]
    distance_m: float = Field(gt=0)
    effective_eta: float = Field(gt=0)


class RoutePreviewResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "origin": {"lat": 30.0621, "lon": 31.3398},
                "destination": {"lat": 30.0561, "lon": 31.3452},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [31.3398, 30.0621],
                        [31.3420, 30.0590],
                        [31.3452, 30.0561],
                    ],
                },
                "distance_m": 1250.5,
                "eta_seconds": 187.5,
                "origin_snap_distance_m": 12.3,
                "destination_snap_distance_m": 8.7,
                "nodes": [101, 102, 103],
                "routing_source": "OSM_BASE_TRAVEL_TIME",
                "base_eta": 187.5,
                "effective_eta": 187.5,
                "traffic_selected_path_base_eta": 187.5,
                "edge_keys": [["101", "102", "0"], ["102", "103", "0"]],
                "matched_traversed_edge_count": 0,
                "total_traversed_edge_count": 2,
                "traffic_coverage_ratio": 0,
                "traffic_fallback_reason": "TOMTOM_API_KEY_MISSING",
                "traffic_snapshot_id": "traffic-snapshot-example",
                "traffic_snapshot_version": 1,
                "traffic_freshness_status": "UNKNOWN",
                "traffic_weight_affected_path_selection": False,
                "traffic_closure_affected_path_selection": False,
                "alternatives": [],
            }
        }
    )

    origin: Coordinate
    destination: Coordinate
    geometry: dict[str, Any]
    distance_m: float = Field(gt=0)
    eta_seconds: float = Field(gt=0)
    origin_snap_distance_m: float = Field(ge=0)
    destination_snap_distance_m: float = Field(ge=0)
    nodes: list[Any]
    edge_keys: list[tuple[str, str, str]]
    routing_source: str = "OSM_BASE_TRAVEL_TIME"
    base_eta: float = Field(gt=0)
    effective_eta: float = Field(gt=0)
    traffic_selected_path_base_eta: float = Field(gt=0)
    traffic_snapshot_id: str | None = None
    traffic_snapshot_version: int | None = None
    traffic_freshness_status: FreshnessStatus | None = None
    matched_traversed_edge_count: int = Field(ge=0)
    total_traversed_edge_count: int = Field(ge=1)
    traffic_coverage_ratio: float = Field(ge=0, le=1)
    traffic_weight_affected_path_selection: bool = False
    traffic_closure_affected_path_selection: bool = False
    traffic_fallback_reason: str | None = None
    alternatives: list[RouteAlternativeRead] = Field(default_factory=list)


class TrafficPrototypePolicyRead(BaseModel):
    refresh_interval_seconds: int
    fresh_max_age_seconds: int
    refresh_timeout_seconds: int
    min_provider_confidence: float
    max_geometry_separation_m: int
    max_direction_difference_degrees: int


class TrafficSnapshotRead(BaseModel):
    snapshot_id: str | None
    version: int | None
    provider_state: str | None
    refresh_attempted_at: datetime | None
    retrieved_at: datetime | None
    provider_last_updated: datetime | None
    freshness_status: FreshnessStatus
    source: str
    source_reference: str | None
    data_reality: DataReality | None
    flow_style: str
    flow_zoom: int
    units: str
    observation_count: int = Field(ge=0)
    match_count: int = Field(ge=0)
    matched_edge_count: int = Field(ge=0)
    failure_reason: str | None
    prototype_policy: TrafficPrototypePolicyRead


class MapLayerResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "layer": "boundary",
                "geojson": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [
                                        [31.3100, 30.0400],
                                        [31.3600, 30.0400],
                                        [31.3600, 30.0800],
                                        [31.3100, 30.0800],
                                        [31.3100, 30.0400],
                                    ]
                                ],
                            },
                            "properties": {
                                "name": "Nasr City",
                                "admin_level": 9,
                            },
                        }
                    ],
                },
                "provenance": {
                    "source": "openstreetmap_overpass_export",
                    "data_reality": "REAL_DERIVED",
                    "freshness_status": "STATIC",
                    "last_updated": "2026-09-01T00:00:00Z",
                    "source_reference": "nasr_city_boundary.geojson",
                },
            }
        }
    )

    layer: str
    geojson: dict[str, Any]
    provenance: dict[str, Any]


class EvidenceItemCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "operator_entry",
                "uri_or_reference": "call-log-8812",
                "extracted_facts": {
                    "reported_casualties": 2,
                    "vehicle_type": "sedan",
                },
                "provenance": {
                    "source": "operator_manual_entry",
                    "data_reality": "SIMULATED",
                },
                "confidence_support": "HIGH",
            }
        }
    )

    type: str
    uri_or_reference: str | None = None
    extracted_facts: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    confidence_support: str | None = None
    created_at: datetime | None = None


class EvidenceItemRead(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "operator_entry",
                "uri_or_reference": "call-log-8812",
                "extracted_facts": {
                    "reported_casualties": 2,
                },
                "provenance": {
                    "source": "operator_manual_entry",
                    "data_reality": "SIMULATED",
                },
                "confidence_support": "HIGH",
                "created_at": "2026-09-07T12:00:00Z",
            }
        }
    )

    type: str
    uri_or_reference: str | None = None
    extracted_facts: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    confidence_support: str | None = None
    created_at: str | None = None


class ReportCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "incident_id": None,
                "source_type": "operator_manual_entry",
                "source_reference": "disp-01",
                "raw_text": "Eyewitness called control room reporting two injured passengers in vehicle collision.",
                "location_text": "Corner of Abbas El Akkad and El Nasr Road",
                "location": {"lat": 30.0561, "lon": 31.3452},
                "data_reality": "SIMULATED",
                "processing_status": "PROCESSED",
                "evidence_items": [
                    {
                        "type": "operator_entry",
                        "uri_or_reference": "call-log-8812",
                        "extracted_facts": {"reported_casualties": 2},
                        "provenance": {
                            "source": "operator_manual_entry",
                            "data_reality": "SIMULATED",
                        },
                        "confidence_support": "HIGH",
                    }
                ],
            }
        }
    )

    incident_id: str | None = None
    source_type: str = "operator_manual_entry"
    source_reference: str = "demo-operator"
    raw_text: str
    location_text: str | None = None
    location: Coordinate | None = None
    received_at: datetime | None = None
    data_reality: DataReality = DataReality.SIMULATED
    processing_status: str = "PROCESSED"
    provenance: dict[str, Any] | None = None
    evidence_items: list[EvidenceItemCreate] = Field(default_factory=list)


class ReportRead(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "rep-4f81c9a1-0d32-4e78-9e6b-bfa1b3b19451",
                "incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                "source_type": "operator_manual_entry",
                "source_reference": "disp-01",
                "raw_text": "Eyewitness called control room reporting two injured passengers.",
                "location_text": "Corner of Abbas El Akkad and El Nasr Road",
                "location": {"lat": 30.0561, "lon": 31.3452},
                "location_json": {"lat": 30.0561, "lon": 31.3452},
                "received_at": "2026-09-07T12:00:00Z",
                "data_reality": "SIMULATED",
                "provenance": {
                    "source": "operator_manual_entry",
                    "data_reality": "SIMULATED",
                    "freshness_status": "FRESH",
                    "last_updated": "2026-09-07T12:00:00Z",
                    "source_reference": "disp-01",
                },
                "provenance_json": {
                    "source": "operator_manual_entry",
                    "data_reality": "SIMULATED",
                    "freshness_status": "FRESH",
                    "last_updated": "2026-09-07T12:00:00Z",
                    "source_reference": "disp-01",
                },
                "processing_status": "PROCESSED",
                "evidence_items": [],
                "evidence_items_json": [],
                "created_at": "2026-09-07T12:00:00Z",
            }
        }
    )

    id: str
    incident_id: str | None = None
    source_type: str
    source_reference: str
    raw_text: str
    location_text: str | None = None
    location: Coordinate | None = None
    location_json: dict[str, Any] | None = None
    received_at: str
    data_reality: DataReality
    provenance: dict[str, Any] = Field(default_factory=dict)
    provenance_json: dict[str, Any] = Field(default_factory=dict)
    processing_status: str
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    evidence_items_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class IncidentTransitionRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "target_status": "EN_ROUTE",
                "expected_incident_version": 3,
                "operator_reference": "dispatcher-op-01",
                "reason": "Units dispatched and moving to scene",
            }
        }
    )

    target_status: IncidentStatus
    expected_incident_version: int = Field(ge=1)
    operator_reference: str = "demo-operator"
    reason: str | None = None

class IncidentCloseRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "expected_incident_version": 5,
                "operator_reference": "dispatcher-op-01",
                "reason": "Incident resolution completed",
            }
        }
    )

    expected_incident_version: int = Field(ge=1)
    operator_reference: str = "demo-operator"
    reason: str | None = None


class IncidentCancelRequest(BaseModel):
    """Operator cancellation for a report confirmed to be false."""

    expected_incident_version: int = Field(ge=1)
    operator_reference: str = Field(min_length=1)
    reason_code: str = Field(default="FALSE_REPORT", min_length=1, max_length=64)
    reason: str | None = Field(default=None, max_length=500)


class TimelineEventRead(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "evt-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                "incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                "event_type": "FACTS_CORRECTED",
                "details": {
                    "operator_reference": "dispatcher-op-01",
                    "correction_timestamp": "2026-09-07T12:00:00Z",
                    "changed_fields": ["casualty_count"],
                },
                "details_json": {
                    "operator_reference": "dispatcher-op-01",
                    "correction_timestamp": "2026-09-07T12:00:00Z",
                    "changed_fields": ["casualty_count"],
                },
                "created_at": "2026-09-07T12:00:00Z",
            }
        }
    )

    id: str
    incident_id: str
    event_type: str
    details: dict[str, Any] = Field(default_factory=dict)
    details_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class IncidentFactsPatchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "expected_incident_version": 1,
                "operator_reference": "dispatcher-op-01",
                "casualty_count": 3,
                "location_text": "Updated location description",
            }
        },
    )

    expected_incident_version: int = Field(ge=1)
    operator_reference: str = Field(min_length=1)
    incident_type: str | None = None
    severity: Severity | None = None
    confidence_level: ConfidenceLevel | None = None
    location: Coordinate | None = None
    location_text: str | None = None
    casualty_count: int | None = Field(default=None, ge=0)
    casualty_range: str | None = None
    trapped_person: bool | None = None
    road_blockage: bool | None = None
    transport_required: bool | None = None
    required_hospital_capabilities: list[str] | None = None
    required_resources: list[ResourceRequirement] | None = None

    @field_validator("incident_type", mode="before")
    @classmethod
    def validate_incident_type(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("incident_type cannot be null")
        if isinstance(v, str) and not v.strip():
            raise ValueError("incident_type cannot be empty")
        return v

    @field_validator("severity", mode="before")
    @classmethod
    def validate_severity(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("severity cannot be null")
        return v

    @field_validator("confidence_level", mode="before")
    @classmethod
    def validate_confidence_level(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("confidence_level cannot be null")
        return v

    @field_validator("location", mode="before")
    @classmethod
    def validate_location(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("location cannot be null")
        return v

    @field_validator("required_resources", mode="before")
    @classmethod
    def validate_required_resources(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("required_resources cannot be null")
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("required_resources cannot be empty")
        return v


class IncidentFactsPatchResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "incident": {
                    "id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                    "version": 2,
                    "status": "ACTIVE_UNCONFIRMED",
                },
                "changed_fields": ["casualty_count"],
                "downstream_inputs_dirty": False,
            }
        }
    )

    incident: IncidentRead
    changed_fields: list[str] = Field(default_factory=list)
    downstream_inputs_dirty: bool = False


class ResourceAssignRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                "expected_resource_version": 1,
                "operator_reference": "dispatcher-op-01",
            }
        }
    )

    incident_id: str
    expected_resource_version: int = Field(ge=1)
    operator_reference: str

    @field_validator("incident_id", mode="before")
    @classmethod
    def validate_incident_id(cls, v: Any) -> Any:
        if not v or not str(v).strip():
            raise ValueError("incident_id must be a non-empty string")
        return str(v).strip()

    @field_validator("operator_reference", mode="before")
    @classmethod
    def validate_operator_reference(cls, v: Any) -> Any:
        if not v or not str(v).strip():
            raise ValueError("operator_reference must be a non-empty string")
        return str(v).strip()


class ResourceStatePatchRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "expected_resource_version": 1,
                "status": "OUT_OF_SERVICE",
                "operator_reference": "dispatcher-op-01",
                "incident_id": None,
            }
        }
    )

    expected_resource_version: int = Field(ge=1)
    status: ResourceStatus
    operator_reference: str
    incident_id: str | None = None

    @field_validator("operator_reference", mode="before")
    @classmethod
    def validate_operator_reference(cls, v: Any) -> Any:
        if not v or not str(v).strip():
            raise ValueError("operator_reference must be a non-empty string")
        return str(v).strip()

    @field_validator("incident_id", mode="before")
    @classmethod
    def validate_incident_id(cls, v: Any) -> Any:
        if v is not None and not str(v).strip():
            return None
        return v


class ResourceReleaseRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                "expected_resource_version": 2,
                "operator_reference": "dispatcher-op-01",
            }
        }
    )

    incident_id: str
    expected_resource_version: int = Field(ge=1)
    operator_reference: str

    @field_validator("incident_id", mode="before")
    @classmethod
    def validate_incident_id(cls, v: Any) -> Any:
        if not v or not str(v).strip():
            raise ValueError("incident_id must be a non-empty string")
        return str(v).strip()

    @field_validator("operator_reference", mode="before")
    @classmethod
    def validate_operator_reference(cls, v: Any) -> Any:
        if not v or not str(v).strip():
            raise ValueError("operator_reference must be a non-empty string")
        return str(v).strip()


class ResourceMovementRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
                "expected_resource_version": 1,
                "route_progress": 0.5,
                "operator_reference": "dispatcher-op-01",
            }
        }
    )

    incident_id: str
    expected_resource_version: int = Field(ge=1)
    route_progress: float = Field(ge=0.0, le=1.0)
    operator_reference: str

    @field_validator("incident_id", mode="before")
    @classmethod
    def validate_incident_id(cls, v: Any) -> Any:
        if not v or not str(v).strip():
            raise ValueError("incident_id must be a non-empty string")
        return str(v).strip()

    @field_validator("operator_reference", mode="before")
    @classmethod
    def validate_operator_reference(cls, v: Any) -> Any:
        if not v or not str(v).strip():
            raise ValueError("operator_reference must be a non-empty string")
        return str(v).strip()

    @field_validator("route_progress")
    @classmethod
    def validate_route_progress(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("route_progress must be a finite number between 0.0 and 1.0")
        if v < 0.0 or v > 1.0:
            raise ValueError("route_progress must be between 0.0 and 1.0")
        return v

    @field_validator("route_progress", mode="before")
    @classmethod
    def reject_boolean_route_progress(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("route_progress must be a number between 0.0 and 1.0")
        return v


class OperationsEventEnvelope(BaseModel):
    """Authoritative envelope for all events delivered over /api/v1/ws/operations."""

    event: str
    incident_id: str | None = None
    timestamp: str
    version: int = Field(ge=1)
    payload: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


class HospitalRead(BaseModel):
    id: str
    source_id: str
    name: str | None = None
    latitude: float
    longitude: float
    static_capabilities: list[str] = Field(default_factory=list)
    static_capacity: int | None = None
    operational_version: int = Field(ge=0)
    accepting_state: HospitalAcceptingState
    simulated_load_ratio: float | None = None
    simulated_free_capacity: int | None = None
    incoming_cases: int | None = None
    operational_freshness_status: FreshnessStatus
    static_provenance: dict[str, Any] = Field(default_factory=dict)
    operational_provenance: dict[str, Any] = Field(default_factory=dict)


class HospitalOperationalStatePatchRequest(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    accepting_state: HospitalAcceptingState | None = None
    simulated_load_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    simulated_free_capacity: int | None = Field(default=None, ge=0)
    incoming_cases: int | None = Field(default=None, ge=0)
    freshness_status: FreshnessStatus | None = None
    operator_reference: str = Field(min_length=1)


class HospitalOptionRead(BaseModel):
    option_id: str
    option_set_id: str
    option_version: int
    rank: int
    hospital: HospitalRead
    route: dict[str, Any] = Field(default_factory=dict)
    score: float
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class HospitalOptionsResponse(BaseModel):
    incident_id: str
    plan_id: str
    incident_version: int
    plan_version: int
    option_set_id: str
    option_set_version: int
    transport_required: bool
    required_hospital_capabilities: list[str] = Field(default_factory=list)
    options: list[HospitalOptionRead] = Field(default_factory=list)
    excluded_hospitals: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class SelectHospitalDestinationRequest(BaseModel):
    expected_incident_version: int = Field(ge=1)
    expected_plan_version: int = Field(ge=1)
    expected_option_set_version: int = Field(ge=1)
    hospital_id: str = Field(min_length=1)
    operator_reference: str = Field(min_length=1)


class HospitalDestinationRead(BaseModel):
    id: str
    incident_id: str
    plan_id: str
    option_set_id: str
    hospital_id: str
    status: str
    incident_version: int
    plan_version: int
    selected_at: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class HospitalPreAlertRequest(BaseModel):
    expected_incident_version: int = Field(ge=1)
    expected_plan_version: int = Field(ge=1)
    operator_reference: str = Field(min_length=1)
    simulate_failure: bool = False


class HospitalPreAlertRead(BaseModel):
    id: str
    incident_id: str
    plan_id: str
    destination_id: str
    status: HospitalPreAlertStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_at: str
    sent_at: str | None = None
    acknowledged_at: str | None = None
    failed_at: str | None = None
    failure_reason: str | None = None
    data_reality: DataReality
    provenance: dict[str, Any] = Field(default_factory=dict)


class CorridorSignalRead(BaseModel):
    signal_id: str
    latitude: float
    longitude: float
    distance_along_route_m: float
    estimated_arrival_seconds: float
    request_time: str | None = None
    state: CorridorSignalState
    provenance: dict[str, Any] = Field(default_factory=dict)


class CorridorRead(BaseModel):
    id: str
    incident_id: str
    plan_id: str
    route_reference: str
    route_geometry: dict[str, Any]
    signals: list[CorridorSignalRead] = Field(default_factory=list)
    state: CorridorSignalState
    safety_lead_time_seconds: int
    data_reality: DataReality
    provenance: dict[str, Any] = Field(default_factory=dict)
    updated_at: str


class CorridorGenerateRequest(BaseModel):
    resource_id: str = Field(min_length=1)


class CorridorPriorityRequest(BaseModel):
    expected_incident_version: int = Field(ge=1)
    expected_plan_version: int = Field(ge=1)
    operator_reference: str = Field(min_length=1)
    state: CorridorSignalState = CorridorSignalState.REQUESTED


class DriverAlertRefreshRequest(BaseModel):
    expected_resource_version: int = Field(ge=1)
    operator_reference: str = Field(min_length=1)


class DriverAlertRead(BaseModel):
    id: str
    incident_id: str
    plan_id: str
    resource_id: str
    route_reference: str
    route_progress: float
    geometry: dict[str, Any] | None = None
    created_at: str
    expires_at: str
    status: DriverAlertStatus
    data_reality: DataReality
    provenance: dict[str, Any] = Field(default_factory=dict)


class IncidentOperationalStateRead(BaseModel):
    incident_id: str
    incident_version: int
    plan_id: str | None = None
    hospital_options: HospitalOptionsResponse | None = None
    selected_destination: HospitalDestinationRead | None = None
    hospital_pre_alert: HospitalPreAlertRead | None = None
    corridor: CorridorRead | None = None
    corridors: list[CorridorRead] = Field(default_factory=list)
    driver_alert: DriverAlertRead | None = None
    driver_alerts: list[DriverAlertRead] = Field(default_factory=list)
