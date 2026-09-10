from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db import Base, init_db
from app.models import (
    Approval,
    EmergencyResource,
    Incident,
    ResponsePlan,
    TimelineEvent,
)
from app.schemas import (
    ApprovePlanRequest,
    ConfidenceLevel,
    Coordinate,
    DataReality,
    FreshnessStatus,
    IncidentStatus,
    ManualIncidentCreate,
    ProvenanceMetadata,
    ResourceRequirement,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)


def test_exact_enum_values() -> None:
    """Verify all shared enums define the exact uppercase contract values."""
    assert {e.value for e in DataReality} == {
        "REAL_PUBLIC",
        "REAL_LIVE",
        "REAL_DERIVED",
        "SIMULATED",
        "SYNTHETIC",
    }
    assert {e.value for e in FreshnessStatus} == {
        "LIVE",
        "FRESH",
        "STALE",
        "STATIC",
        "UNKNOWN",
    }
    assert {e.value for e in Severity} == {
        "LOW",
        "MODERATE",
        "HIGH",
        "CRITICAL",
    }
    assert {e.value for e in ConfidenceLevel} == {
        "LOW",
        "MEDIUM",
        "HIGH",
    }
    assert {e.value for e in IncidentStatus} == {
        "RECEIVED",
        "INTERPRETING",
        "ACTIVE_UNCONFIRMED",
        "RESPONSE_PROPOSED",
        "AWAITING_APPROVAL",
        "RESPONSE_ACTIVE",
        "EN_ROUTE",
        "ON_SCENE",
        "TRANSPORT_ACTIVE",
        "HANDOVER",
        "CLOSED",
        "REQUIRES_REVIEW",
        "DUPLICATE_MERGED",
        "CANCELLED_FALSE_REPORT",
    }
    assert {e.value for e in ResourceType} == {
        "AMBULANCE",
        "FIRE_RESCUE",
    }
    assert {e.value for e in ResourceStatus} == {
        "AVAILABLE",
        "RESERVED",
        "ASSIGNED",
        "EN_ROUTE",
        "ON_SCENE",
        "TRANSPORTING",
        "OUT_OF_SERVICE",
    }
    assert {e.value for e in ResponsePlanStatus} == {
        "CANDIDATE",
        "RECOMMENDED",
        "ALTERNATIVE",
        "APPROVED",
        "REJECTED",
        "SUPERSEDED",
    }


def test_severity_confidence_distinction() -> None:
    """Verify Severity and ConfidenceLevel are distinct enum types despite overlapping values."""
    assert Severity.HIGH.value == ConfidenceLevel.HIGH.value == "HIGH"
    assert type(Severity.HIGH) is not type(ConfidenceLevel.HIGH)
    assert Severity.HIGH is not ConfidenceLevel.HIGH
    assert isinstance(Severity.HIGH, Severity)
    assert not isinstance(ConfidenceLevel.HIGH, Severity)
    assert isinstance(ConfidenceLevel.HIGH, ConfidenceLevel)
    assert not isinstance(Severity.HIGH, ConfidenceLevel)


def test_freshness_unknown_and_provenance_metadata() -> None:
    """Verify UNKNOWN freshness status and provenance metadata validation."""
    assert FreshnessStatus.UNKNOWN == "UNKNOWN"
    now = datetime.now(timezone.utc)
    metadata = ProvenanceMetadata(
        source="test-sensor",
        data_reality=DataReality.SIMULATED,
        last_updated=now,
        freshness_status=FreshnessStatus.UNKNOWN,
        source_reference="doc-123",
    )
    assert metadata.freshness_status == FreshnessStatus.UNKNOWN
    assert metadata.source_reference == "doc-123"

    metadata_no_ref = ProvenanceMetadata(
        source="manual-intake",
        data_reality=DataReality.REAL_LIVE,
        last_updated=now,
        freshness_status=FreshnessStatus.LIVE,
    )
    assert metadata_no_ref.source_reference is None


def test_coordinate_validation() -> None:
    """Verify Coordinate enforces latitude [-90, 90] and longitude [-180, 180]."""
    valid = Coordinate(lat=30.05, lon=31.35)
    assert valid.lat == 30.05
    assert valid.lon == 31.35

    # Boundary cases
    Coordinate(lat=-90.0, lon=-180.0)
    Coordinate(lat=90.0, lon=180.0)

    # Invalid latitude
    with pytest.raises(ValidationError):
        Coordinate(lat=90.001, lon=31.35)
    with pytest.raises(ValidationError):
        Coordinate(lat=-90.001, lon=31.35)

    # Invalid longitude
    with pytest.raises(ValidationError):
        Coordinate(lat=30.05, lon=180.001)
    with pytest.raises(ValidationError):
        Coordinate(lat=30.05, lon=-180.001)


def test_resource_requirement_validation() -> None:
    """Verify ResourceRequirement count range is 1..5."""
    req = ResourceRequirement(resource_type=ResourceType.AMBULANCE, count=1)
    assert req.count == 1

    tagged = ResourceRequirement(
        resource_type=ResourceType.AMBULANCE,
        count=1,
        required_capability_tags=["advanced_life_support"],
    )
    assert tagged.required_capability_tags == ["advanced_life_support"]

    with pytest.raises(ValidationError):
        ResourceRequirement(resource_type=ResourceType.AMBULANCE, count=1, required_capabilty_tags=[])

    req_max = ResourceRequirement(resource_type=ResourceType.FIRE_RESCUE, count=5)
    assert req_max.count == 5

    with pytest.raises(ValidationError):
        ResourceRequirement(resource_type=ResourceType.AMBULANCE, count=0)
    with pytest.raises(ValidationError):
        ResourceRequirement(resource_type=ResourceType.AMBULANCE, count=6)


def test_manual_incident_create_validation() -> None:
    """Verify ManualIncidentCreate handles unknown facts, defaults, and requirements."""
    # Successful minimal creation
    payload = ManualIncidentCreate(
        incident_type="TRAFFIC_COLLISION",
        severity=Severity.HIGH,
        location=Coordinate(lat=30.05, lon=31.35),
        required_resources=[
            ResourceRequirement(resource_type=ResourceType.AMBULANCE, count=1)
        ],
    )
    assert payload.confidence_level == ConfidenceLevel.HIGH
    assert payload.operator_reference == "demo-operator"
    # Unknown facts remain None
    assert payload.location_text is None
    assert payload.casualty_count is None
    assert payload.casualty_range is None
    assert payload.trapped_person is None
    assert payload.road_blockage is None

    # Valid non-negative casualty count
    payload_with_casualties = ManualIncidentCreate(
        incident_type="FIRE",
        severity=Severity.CRITICAL,
        location=Coordinate(lat=30.05, lon=31.35),
        casualty_count=0,
        required_resources=[
            ResourceRequirement(resource_type=ResourceType.FIRE_RESCUE, count=2)
        ],
    )
    assert payload_with_casualties.casualty_count == 0

    # Negative casualty count raises ValidationError
    with pytest.raises(ValidationError):
        ManualIncidentCreate(
            incident_type="FIRE",
            severity=Severity.LOW,
            location=Coordinate(lat=30.05, lon=31.35),
            casualty_count=-1,
            required_resources=[
                ResourceRequirement(resource_type=ResourceType.AMBULANCE, count=1)
            ],
        )

    # Empty required_resources raises ValidationError
    with pytest.raises(ValidationError):
        ManualIncidentCreate(
            incident_type="FIRE",
            severity=Severity.MODERATE,
            location=Coordinate(lat=30.05, lon=31.35),
            required_resources=[],
        )


def test_approve_plan_request_validation() -> None:
    """Verify ApprovePlanRequest requires positive versions and sets operator default."""
    valid_req = ApprovePlanRequest(
        expected_incident_version=1,
        expected_plan_version=2,
    )
    assert valid_req.expected_incident_version == 1
    assert valid_req.expected_plan_version == 2
    assert valid_req.operator_reference == "demo-operator"

    # Non-positive incident version
    with pytest.raises(ValidationError):
        ApprovePlanRequest(expected_incident_version=0, expected_plan_version=1)
    with pytest.raises(ValidationError):
        ApprovePlanRequest(expected_incident_version=-1, expected_plan_version=1)

    # Non-positive plan version
    with pytest.raises(ValidationError):
        ApprovePlanRequest(expected_incident_version=1, expected_plan_version=0)
    with pytest.raises(ValidationError):
        ApprovePlanRequest(expected_incident_version=1, expected_plan_version=-1)


def test_model_metadata_registers_all_five_tables(isolated_engine) -> None:
    """Verify Base.metadata registers all five models and init_db creates their tables."""
    expected_tables = {
        "incidents",
        "emergency_resources",
        "response_plans",
        "approvals",
        "timeline_events",
    }
    assert expected_tables.issubset(Base.metadata.tables.keys())

    init_db(target_engine=isolated_engine)
    inspector = inspect(isolated_engine)
    created_tables = set(inspector.get_table_names())
    assert expected_tables.issubset(created_tables)


def test_model_persistence_round_trip(db_session: Session, isolated_engine) -> None:
    """Verify small model persistence round-trip on an isolated database."""
    init_db(target_engine=isolated_engine)

    # 1. Incident persistence
    inc_id = str(uuid.uuid4())
    incident = Incident(
        id=inc_id,
        incident_type="TRAFFIC_COLLISION",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.MEDIUM,
        status=IncidentStatus.RECEIVED,
        latitude=30.05,
        longitude=31.35,
        location_text="El-Nasr Road",
        casualty_count=None,  # unknown fact remains None
        trapped_person=True,
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
        provenance_json={"source": "operator-phone"},
    )
    db_session.add(incident)
    db_session.commit()

    saved_inc = db_session.get(Incident, inc_id)
    assert saved_inc is not None
    assert saved_inc.version == 1
    assert saved_inc.severity == Severity.HIGH
    assert saved_inc.severity == "HIGH"
    assert saved_inc.confidence_level == ConfidenceLevel.MEDIUM
    assert saved_inc.status == IncidentStatus.RECEIVED
    assert saved_inc.casualty_count is None
    assert saved_inc.trapped_person is True
    assert saved_inc.created_at is not None
    assert saved_inc.updated_at is not None
    assert saved_inc.required_resources_json == [
        {"resource_type": "AMBULANCE", "count": 1}
    ]

    # Verify raw SQL stores exact uppercase enum values
    with isolated_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT severity, confidence_level, status FROM incidents WHERE id = :id"
            ),
            {"id": inc_id},
        ).fetchone()
        assert row is not None
        assert row[0] == "HIGH"
        assert row[1] == "MEDIUM"
        assert row[2] == "RECEIVED"

    # 2. EmergencyResource persistence
    res_id = str(uuid.uuid4())
    resource = EmergencyResource(
        id=res_id,
        name="Ambulance-101",
        resource_type=ResourceType.AMBULANCE,
        capability_tags_json=["basic_life_support"],
        status=ResourceStatus.AVAILABLE,
        latitude=30.06,
        longitude=31.34,
        home_zone="Nasr City Zone 1",
        provenance_json={"data_reality": "SIMULATED"},
    )
    db_session.add(resource)
    db_session.commit()

    saved_res = db_session.get(EmergencyResource, res_id)
    assert saved_res is not None
    assert saved_res.version == 1
    assert saved_res.resource_type == ResourceType.AMBULANCE
    assert saved_res.resource_type == "AMBULANCE"
    assert saved_res.status == ResourceStatus.AVAILABLE
    assert saved_res.assigned_incident_id is None
    assert saved_res.last_updated is not None

    # 3. ResponsePlan persistence
    plan_id = str(uuid.uuid4())
    plan = ResponsePlan(
        id=plan_id,
        incident_id=inc_id,
        incident_version=1,
        plan_version=1,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids_json=[res_id],
        routes_json=[{"resource_id": res_id, "route": []}],
        metrics_json={"eta_seconds": 360},
        score_breakdown_json={"time_penalty": 12.5},
    )
    db_session.add(plan)
    db_session.commit()

    saved_plan = db_session.get(ResponsePlan, plan_id)
    assert saved_plan is not None
    assert saved_plan.status == ResponsePlanStatus.RECOMMENDED
    assert saved_plan.resource_ids_json == [res_id]
    assert saved_plan.created_at is not None

    # 4. Approval persistence
    approval_id = str(uuid.uuid4())
    approval = Approval(
        id=approval_id,
        plan_id=plan_id,
        incident_id=inc_id,
        operator_reference="demo-operator",
        action="APPROVE",
        expected_incident_version=1,
        expected_plan_version=1,
    )
    db_session.add(approval)
    db_session.commit()

    saved_approval = db_session.get(Approval, approval_id)
    assert saved_approval is not None
    assert saved_approval.action == "APPROVE"
    assert saved_approval.expected_incident_version == 1

    # 5. TimelineEvent persistence
    event_id = str(uuid.uuid4())
    event = TimelineEvent(
        id=event_id,
        incident_id=inc_id,
        event_type="INCIDENT_REPORTED",
        details_json={"source": "manual_intake"},
    )
    db_session.add(event)
    db_session.commit()

    saved_event = db_session.get(TimelineEvent, event_id)
    assert saved_event is not None
    assert saved_event.event_type == "INCIDENT_REPORTED"
    assert saved_event.details_json == {"source": "manual_intake"}
    assert saved_event.created_at is not None
