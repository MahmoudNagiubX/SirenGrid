from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
    "IncidentRead",
    "ResourceRead",
    "ResponsePlanRead",
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
    required_resources: list[ResourceRequirement] = Field(default_factory=list)
    required_resources_json: list[ResourceRequirement] = Field(default_factory=list)
    current_plan_id: str | None = None
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
