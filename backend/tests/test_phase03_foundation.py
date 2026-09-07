from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.db import init_db
from app.main import app
from app.models import EmergencyResource, Incident, Report, ResponsePlan, TimelineEvent  # noqa: F401
from app.schemas import (
    ConfidenceLevel,
    DataReality,
    FreshnessStatus,
    IncidentStatus,
    Severity,
)
from app.seed import seed_resources


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    """Initialize all model tables on the isolated test engine."""
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def create_test_incident(
    db: Session,
    incident_id: str | None = None,
    version: int = 1,
    status: IncidentStatus = IncidentStatus.ACTIVE_UNCONFIRMED,
    lat: float = 30.0561,
    lon: float = 31.3452,
) -> Incident:
    if incident_id is None:
        incident_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)
    inc = Incident(
        id=incident_id,
        version=version,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=status,
        latitude=lat,
        longitude=lon,
        location_text="Nasr City intersection",
        casualty_count=2,
        casualty_range="2-3",
        trapped_person=True,
        road_blockage=True,
        required_resources_json=[
            {"resource_type": "AMBULANCE", "count": 1},
            {"resource_type": "FIRE_RESCUE", "count": 1},
        ],
        current_plan_id=None,
        created_at=now_utc,
        updated_at=now_utc,
        provenance_json={
            "source": "operator_manual_entry",
            "data_reality": DataReality.SIMULATED.value,
            "freshness_status": FreshnessStatus.FRESH.value,
            "last_updated": now_utc.isoformat(),
            "source_reference": "test-op",
        },
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return inc


# =============================================================================
# 1. REPORT & EVIDENCE METADATA FOUNDATION
# =============================================================================


def test_create_manual_report_attached_to_incident(client: TestClient, db_session: Session) -> None:
    """A manual report attached to an incident preserves all required metadata and appends a timeline event."""
    inc = create_test_incident(db_session, status=IncidentStatus.ACTIVE_UNCONFIRMED)

    payload = {
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
        ],
    }

    res = client.post(f"/api/v1/incidents/{inc.id}/reports", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["incident_id"] == inc.id
    assert data["source_type"] == "operator_manual_entry"
    assert data["source_reference"] == "disp-01"
    assert data["raw_text"] == payload["raw_text"]
    assert data["location_text"] == payload["location_text"]
    assert data["data_reality"] == "SIMULATED"
    assert data["processing_status"] == "PROCESSED"
    assert len(data["evidence_items"]) == 1
    assert data["evidence_items"][0]["uri_or_reference"] == "call-log-8812"
    assert data["evidence_items"][0]["confidence_support"] == "HIGH"

    # Verify DB persistence
    report = db_session.get(Report, data["id"])
    assert report is not None
    assert report.incident_id == inc.id
    assert report.data_reality == DataReality.SIMULATED
    assert report.provenance_json.get("data_reality") == "SIMULATED"

    # Verify TimelineEvent appended in same transaction
    events = (
        db_session.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.incident_id == inc.id)
            .where(TimelineEvent.event_type == "REPORT_CREATED")
        )
        .all()
    )
    assert len(events) == 1
    ev = events[0]
    assert ev.details_json["report_id"] == data["id"]
    assert ev.details_json["source_type"] == "operator_manual_entry"


def test_create_standalone_manual_report(client: TestClient, db_session: Session) -> None:
    """A report can be created standalone with incident_id nullable until fusion/attachment."""
    payload = {
        "source_type": "phone_call",
        "source_reference": "call-999-001",
        "raw_text": "Emergency call received reporting smoke near residential block.",
        "location_text": "Tayaran St, Nasr City",
        "data_reality": "SIMULATED",
        "processing_status": "PENDING",
        "evidence_items": [],
    }

    res = client.post("/api/v1/reports", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["id"] is not None
    assert data["incident_id"] is None
    assert data["source_reference"] == "call-999-001"

    report = db_session.get(Report, data["id"])
    assert report is not None
    assert report.incident_id is None


def test_create_report_for_nonexistent_incident_returns_404(client: TestClient) -> None:
    """Attaching a report to a non-existent incident returns 404 with zero mutation."""
    payload = {
        "source_type": "operator_manual_entry",
        "source_reference": "op-404",
        "raw_text": "Missing incident report text",
    }
    res = client.post("/api/v1/incidents/non-existent-id/reports", json=payload)
    assert res.status_code == 404


def test_list_incident_reports(client: TestClient, db_session: Session) -> None:
    """Listing reports for an incident returns all linked reports in deterministic order."""
    inc = create_test_incident(db_session)

    for i in range(2):
        client.post(
            f"/api/v1/incidents/{inc.id}/reports",
            json={
                "source_type": "operator_manual_entry",
                "source_reference": f"op-{i}",
                "raw_text": f"Report narrative #{i}",
            },
        )

    res = client.get(f"/api/v1/incidents/{inc.id}/reports")
    assert res.status_code == 200
    reports = res.json()
    assert len(reports) == 2
    assert {r["source_reference"] for r in reports} == {"op-0", "op-1"}


# =============================================================================
# 2. DETERMINISTIC LIFECYCLE TRANSITION FOUNDATION
# =============================================================================


def test_full_forward_lifecycle_transport_flow(client: TestClient, db_session: Session) -> None:
    """Test the complete legal forward lifecycle matrix with medical transport."""
    # 1. Start at RECEIVED (v1)
    inc = create_test_incident(db_session, status=IncidentStatus.RECEIVED, version=1)

    forward_steps = [
        (IncidentStatus.INTERPRETING, 1, 2),
        (IncidentStatus.ACTIVE_UNCONFIRMED, 2, 3),
        (IncidentStatus.RESPONSE_PROPOSED, 3, 4),
        (IncidentStatus.AWAITING_APPROVAL, 4, 5),
        (IncidentStatus.RESPONSE_ACTIVE, 5, 6),
        (IncidentStatus.EN_ROUTE, 6, 7),
        (IncidentStatus.ON_SCENE, 7, 8),
        (IncidentStatus.TRANSPORT_ACTIVE, 8, 9),
        (IncidentStatus.HANDOVER, 9, 10),
        (IncidentStatus.CLOSED, 10, 11),
    ]

    for target_status, expected_ver, new_ver in forward_steps:
        req = {
            "target_status": target_status.value,
            "expected_incident_version": expected_ver,
            "operator_reference": "dispatcher-01",
            "reason": f"Advancing to {target_status.value}",
        }
        res = client.post(f"/api/v1/incidents/{inc.id}/transition", json=req)
        assert res.status_code == 200, f"Failed transition to {target_status.value}: {res.text}"
        data = res.json()
        assert data["status"] == target_status.value
        assert data["version"] == new_ver

    # Verify DB state
    db_session.expire_all()
    reloaded = db_session.get(Incident, inc.id)
    assert reloaded.status == IncidentStatus.CLOSED
    assert reloaded.version == 11

    # Verify timeline events appended for all 10 transitions
    events = (
        db_session.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.incident_id == inc.id)
            .where(TimelineEvent.event_type == "LIFECYCLE_TRANSITION")
            .order_by(TimelineEvent.created_at.asc(), TimelineEvent.id.asc())
        )
        .all()
    )
    assert len(events) == 10
    assert events[0].details_json["from_status"] == IncidentStatus.RECEIVED.value
    assert events[0].details_json["to_status"] == IncidentStatus.INTERPRETING.value
    assert events[-1].details_json["to_status"] == IncidentStatus.CLOSED.value


def test_forward_lifecycle_non_transport_flow(client: TestClient, db_session: Session) -> None:
    """Non-transport incidents transition ON_SCENE -> HANDOVER -> CLOSED."""
    inc = create_test_incident(db_session, status=IncidentStatus.ON_SCENE, version=4)

    # ON_SCENE -> HANDOVER
    res1 = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={
            "target_status": IncidentStatus.HANDOVER.value,
            "expected_incident_version": 4,
            "operator_reference": "dispatcher-01",
        },
    )
    assert res1.status_code == 200, res1.text
    assert res1.json()["status"] == IncidentStatus.HANDOVER.value
    assert res1.json()["version"] == 5

    # HANDOVER -> CLOSED
    res2 = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={
            "target_status": IncidentStatus.CLOSED.value,
            "expected_incident_version": 5,
            "operator_reference": "dispatcher-01",
        },
    )
    assert res2.status_code == 200, res2.text
    assert res2.json()["status"] == IncidentStatus.CLOSED.value
    assert res2.json()["version"] == 6


def test_stale_incident_version_returns_409_zero_mutation(client: TestClient, db_session: Session) -> None:
    """Transitions with stale expected version return 409 with zero mutation."""
    inc = create_test_incident(db_session, status=IncidentStatus.EN_ROUTE, version=3)

    res = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={
            "target_status": IncidentStatus.ON_SCENE.value,
            "expected_incident_version": 1,  # Stale!
            "operator_reference": "dispatcher-01",
        },
    )
    assert res.status_code == 409
    assert "version" in res.json()["detail"].lower()

    # Verify zero DB mutation
    db_session.expire_all()
    reloaded = db_session.get(Incident, inc.id)
    assert reloaded.status == IncidentStatus.EN_ROUTE
    assert reloaded.version == 3

    # No transition timeline event created
    events = db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.incident_id == inc.id)
    ).all()
    assert len(events) == 0


def test_backward_transition_returns_409_zero_mutation(client: TestClient, db_session: Session) -> None:
    """Backward transitions in the matrix are rejected with 409 and zero mutation."""
    inc = create_test_incident(db_session, status=IncidentStatus.ON_SCENE, version=5)

    for backward_status in [
        IncidentStatus.EN_ROUTE,
        IncidentStatus.RESPONSE_ACTIVE,
        IncidentStatus.AWAITING_APPROVAL,
        IncidentStatus.ACTIVE_UNCONFIRMED,
        IncidentStatus.RECEIVED,
    ]:
        res = client.post(
            f"/api/v1/incidents/{inc.id}/transition",
            json={
                "target_status": backward_status.value,
                "expected_incident_version": 5,
                "operator_reference": "dispatcher-01",
            },
        )
        assert res.status_code == 409, f"Expected 409 for backward {backward_status.value}, got {res.status_code}"

    # Verify zero DB mutation
    db_session.expire_all()
    reloaded = db_session.get(Incident, inc.id)
    assert reloaded.status == IncidentStatus.ON_SCENE
    assert reloaded.version == 5


def test_skipping_transition_returns_409_zero_mutation(client: TestClient, db_session: Session) -> None:
    """Skipping lifecycle stages is rejected with 409 and zero mutation."""
    inc = create_test_incident(db_session, status=IncidentStatus.RECEIVED, version=1)

    for invalid_target in [
        IncidentStatus.ACTIVE_UNCONFIRMED,
        IncidentStatus.RESPONSE_ACTIVE,
        IncidentStatus.ON_SCENE,
        IncidentStatus.CLOSED,
    ]:
        res = client.post(
            f"/api/v1/incidents/{inc.id}/transition",
            json={
                "target_status": invalid_target.value,
                "expected_incident_version": 1,
                "operator_reference": "dispatcher-01",
            },
        )
        assert res.status_code == 409, f"Expected 409 for skipping to {invalid_target.value}"

    db_session.expire_all()
    reloaded = db_session.get(Incident, inc.id)
    assert reloaded.status == IncidentStatus.RECEIVED
    assert reloaded.version == 1


def test_self_transition_returns_409_zero_mutation(client: TestClient, db_session: Session) -> None:
    """Transitioning to the current status is not permitted and returns 409."""
    inc = create_test_incident(db_session, status=IncidentStatus.EN_ROUTE, version=2)

    res = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={
            "target_status": IncidentStatus.EN_ROUTE.value,
            "expected_incident_version": 2,
            "operator_reference": "dispatcher-01",
        },
    )
    assert res.status_code == 409

    db_session.expire_all()
    reloaded = db_session.get(Incident, inc.id)
    assert reloaded.status == IncidentStatus.EN_ROUTE
    assert reloaded.version == 2


def test_transition_from_closed_terminal_returns_409(client: TestClient, db_session: Session) -> None:
    """CLOSED is terminal; any transition from CLOSED returns 409."""
    inc = create_test_incident(db_session, status=IncidentStatus.CLOSED, version=10)

    for target in [IncidentStatus.RECEIVED, IncidentStatus.ACTIVE_UNCONFIRMED, IncidentStatus.RESPONSE_ACTIVE]:
        res = client.post(
            f"/api/v1/incidents/{inc.id}/transition",
            json={
                "target_status": target.value,
                "expected_incident_version": 10,
                "operator_reference": "dispatcher-01",
            },
        )
        assert res.status_code == 409

    db_session.expire_all()
    reloaded = db_session.get(Incident, inc.id)
    assert reloaded.status == IncidentStatus.CLOSED
    assert reloaded.version == 10


def test_exceptional_states_rejected_with_409(client: TestClient, db_session: Session) -> None:
    """Client-supplied transitions to exceptional states or from exceptional states return 409."""
    inc = create_test_incident(db_session, status=IncidentStatus.ACTIVE_UNCONFIRMED, version=1)

    for exceptional in [
        IncidentStatus.REQUIRES_REVIEW,
        IncidentStatus.DUPLICATE_MERGED,
        IncidentStatus.CANCELLED_FALSE_REPORT,
    ]:
        res = client.post(
            f"/api/v1/incidents/{inc.id}/transition",
            json={
                "target_status": exceptional.value,
                "expected_incident_version": 1,
                "operator_reference": "dispatcher-01",
            },
        )
        assert res.status_code == 409, f"Expected 409 for {exceptional.value}"

    # Also verify transition out of exceptional state is rejected
    inc_review = create_test_incident(db_session, status=IncidentStatus.REQUIRES_REVIEW, version=2)
    res_out = client.post(
        f"/api/v1/incidents/{inc_review.id}/transition",
        json={
            "target_status": IncidentStatus.ACTIVE_UNCONFIRMED.value,
            "expected_incident_version": 2,
            "operator_reference": "dispatcher-01",
        },
    )
    assert res_out.status_code == 409


def test_incident_close_endpoint_contract(client: TestClient, db_session: Session) -> None:
    """POST /incidents/{id}/close convenience endpoint enforces lifecycle check from HANDOVER to CLOSED."""
    # Cannot close directly from EN_ROUTE
    inc_enroute = create_test_incident(db_session, status=IncidentStatus.EN_ROUTE, version=2)
    res_bad = client.post(
        f"/api/v1/incidents/{inc_enroute.id}/close",
        json={
            "expected_incident_version": 2,
            "operator_reference": "dispatcher-01",
            "reason": "Premature close",
        },
    )
    assert res_bad.status_code == 409

    # Can close from HANDOVER
    inc_handover = create_test_incident(db_session, status=IncidentStatus.HANDOVER, version=5)
    res_ok = client.post(
        f"/api/v1/incidents/{inc_handover.id}/close",
        json={
            "expected_incident_version": 5,
            "operator_reference": "dispatcher-01",
            "reason": "Incident successfully resolved",
        },
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == IncidentStatus.CLOSED.value
    assert res_ok.json()["version"] == 6


# =============================================================================
# 3. MANUAL INTAKE & GOLDEN FLOW COMPATIBILITY
# =============================================================================


def test_manual_intake_compatibility_and_subsequent_transitions(
    client: TestClient,
    db_session: Session,
) -> None:
    """Manual intake still creates ACTIVE_UNCONFIRMED at v1 and transitions cleanly forward."""
    payload = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Tayaran St, Nasr City",
        "casualty_count": 2,
        "required_resources": [
            {"resource_type": "AMBULANCE", "count": 1},
        ],
        "operator_reference": "dispatcher-01",
    }

    res = client.post("/api/v1/intake/manual", json=payload)
    assert res.status_code == 201
    inc_data = res.json()
    assert inc_data["status"] == IncidentStatus.ACTIVE_UNCONFIRMED.value
    assert inc_data["version"] == 1

    # Transition to RESPONSE_PROPOSED
    res_prop = client.post(
        f"/api/v1/incidents/{inc_data['id']}/transition",
        json={
            "target_status": IncidentStatus.RESPONSE_PROPOSED.value,
            "expected_incident_version": 1,
            "operator_reference": "dispatcher-01",
        },
    )
    assert res_prop.status_code == 200
    assert res_prop.json()["status"] == IncidentStatus.RESPONSE_PROPOSED.value
    assert res_prop.json()["version"] == 2


def test_plan_generation_and_approval_transition_compatibility(
    client: TestClient,
    db_session: Session,
) -> None:
    """Plan generation still moves to AWAITING_APPROVAL and approval to RESPONSE_ACTIVE, followed by transitions."""
    seed_resources(db_session)
    inc = create_test_incident(db_session, status=IncidentStatus.ACTIVE_UNCONFIRMED, version=1)

    # 1. Plan generation
    plan_res = client.post(f"/api/v1/incidents/{inc.id}/plans/generate")
    assert plan_res.status_code == 201, plan_res.text
    plan_data = plan_res.json()
    plan_id = plan_data["id"]
    gen_inc_ver = plan_data["incident_version"]
    assert gen_inc_ver == 2

    # Incident is now AWAITING_APPROVAL at version 2
    inc_get = client.get(f"/api/v1/incidents/{inc.id}").json()
    assert inc_get["status"] == IncidentStatus.AWAITING_APPROVAL.value
    assert inc_get["version"] == 2

    # 2. Plan approval
    app_res = client.post(
        f"/api/v1/plans/{plan_id}/approve",
        json={
            "operator_reference": "dispatcher-01",
            "expected_incident_version": 2,
            "expected_plan_version": 1,
        },
    )
    assert app_res.status_code == 200, app_res.text
    app_data = app_res.json()
    assert app_data["incident_status"] == IncidentStatus.RESPONSE_ACTIVE.value
    assert app_data["incident"]["version"] == 3

    # 3. Subsequent lifecycle transition: RESPONSE_ACTIVE -> EN_ROUTE
    t_res = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={
            "target_status": IncidentStatus.EN_ROUTE.value,
            "expected_incident_version": 3,
            "operator_reference": "dispatcher-01",
        },
    )
    assert t_res.status_code == 200
    assert t_res.json()["status"] == IncidentStatus.EN_ROUTE.value
    assert t_res.json()["version"] == 4


# =============================================================================
# 4. TIMELINE RETRIEVAL CONTRACT
# =============================================================================


def test_timeline_endpoint_unknown_incident_returns_404(client: TestClient) -> None:
    """GET /api/v1/incidents/{id}/timeline returns 404 for an unknown incident."""
    res = client.get("/api/v1/incidents/inc-nonexistent-00000000/timeline")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_timeline_endpoint_deterministic_order_and_structure(
    client: TestClient,
    db_session: Session,
) -> None:
    """Timeline returns events in deterministic ascending created_at then id order with complete fields."""
    inc = create_test_incident(db_session, status=IncidentStatus.ACTIVE_UNCONFIRMED, version=1)

    # Add a lifecycle transition to have at least two events
    t_res = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={
            "target_status": IncidentStatus.RESPONSE_PROPOSED.value,
            "expected_incident_version": 1,
            "operator_reference": "dispatcher-01",
            "reason": "Units proposed",
        },
    )
    assert t_res.status_code == 200

    # Add a report attached to incident to have a third event
    rep_res = client.post(
        f"/api/v1/incidents/{inc.id}/reports",
        json={
            "source_type": "operator_manual_entry",
            "source_reference": "disp-02",
            "raw_text": "Follow-up bystander report",
            "data_reality": "SIMULATED",
        },
    )
    assert rep_res.status_code == 201

    res = client.get(f"/api/v1/incidents/{inc.id}/timeline")
    assert res.status_code == 200
    events = res.json()
    assert isinstance(events, list)
    assert len(events) >= 2

    # Verify deterministic ordering: created_at ascending, then id ascending
    for i in range(len(events) - 1):
        e1 = events[i]
        e2 = events[i + 1]
        assert (e1["created_at"], e1["id"]) <= (e2["created_at"], e2["id"])

    # Verify event structure
    for evt in events:
        assert "id" in evt
        assert evt["incident_id"] == inc.id
        assert "event_type" in evt
        assert "details" in evt
        assert "details_json" in evt
        assert "created_at" in evt

    event_types = [e["event_type"] for e in events]
    assert "LIFECYCLE_TRANSITION" in event_types
    assert "REPORT_CREATED" in event_types


# =============================================================================
# 5. MANUAL FACTS CORRECTION CONTRACT
# =============================================================================


def test_facts_patch_stale_version_returns_409_without_mutation(
    client: TestClient,
    db_session: Session,
) -> None:
    """Stale expected_incident_version returns 409 and leaves incident and timeline unchanged."""
    inc = create_test_incident(db_session, version=1)

    res = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 99,
            "operator_reference": "disp-stale",
            "casualty_count": 9,
            "severity": Severity.CRITICAL.value,
        },
    )
    assert res.status_code == 409
    assert "version mismatch" in res.json()["detail"].lower()

    # Verify zero DB mutation
    db_session.refresh(inc)
    assert inc.version == 1
    assert inc.casualty_count == 2
    assert inc.severity == Severity.HIGH

    # Verify no FACTS_CORRECTED timeline event was created
    stmt = select(TimelineEvent).where(
        TimelineEvent.incident_id == inc.id,
        TimelineEvent.event_type == "FACTS_CORRECTED",
    )
    events = db_session.scalars(stmt).all()
    assert len(events) == 0


def test_facts_patch_semantic_noop_returns_200_no_version_or_event(
    client: TestClient,
    db_session: Session,
) -> None:
    """Semantic no-op returns 200 with changed_fields [] and does not mutate version or timeline."""
    inc = create_test_incident(db_session, version=1)

    res = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-noop",
            "casualty_count": 2,
            "severity": Severity.HIGH.value,
            "location_text": "Nasr City intersection",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["changed_fields"] == []
    assert data["downstream_inputs_dirty"] is False
    assert data["incident"]["version"] == 1
    assert data["incident"]["casualty_count"] == 2

    # Verify DB state unchanged
    db_session.refresh(inc)
    assert inc.version == 1

    # Verify no FACTS_CORRECTED event appended
    stmt = select(TimelineEvent).where(
        TimelineEvent.incident_id == inc.id,
        TimelineEvent.event_type == "FACTS_CORRECTED",
    )
    assert len(db_session.scalars(stmt).all()) == 0


def test_facts_patch_successful_multi_field_correction(
    client: TestClient,
    db_session: Session,
) -> None:
    """Valid multi-field correction increments version once, writes per-field provenance, and appends audit event."""
    inc = create_test_incident(db_session, version=1)

    res = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-op-99",
            "casualty_count": 5,
            "severity": Severity.CRITICAL.value,
            "location_text": "Corrected: Rabaa Al-Adawiya square",
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()

    assert sorted(data["changed_fields"]) == ["casualty_count", "location_text", "severity"]
    assert data["downstream_inputs_dirty"] is False
    assert data["incident"]["version"] == 2
    assert data["incident"]["casualty_count"] == 5
    assert data["incident"]["severity"] == Severity.CRITICAL.value
    assert data["incident"]["location_text"] == "Corrected: Rabaa Al-Adawiya square"

    # Verify provenance_json operator-corrected field map
    prov = data["incident"]["provenance"]
    assert "corrected_fields" in prov
    corrected_map = prov["corrected_fields"]
    for f in ["casualty_count", "severity", "location_text"]:
        assert f in corrected_map
        assert corrected_map[f]["source"] == "operator_correction"
        assert corrected_map[f]["operator_reference"] == "disp-op-99"
        assert corrected_map[f]["data_reality"] == DataReality.SIMULATED.value
        assert corrected_map[f]["freshness_status"] == FreshnessStatus.FRESH.value
        assert "timestamp" in corrected_map[f]

    # Verify timeline event
    t_res = client.get(f"/api/v1/incidents/{inc.id}/timeline")
    assert t_res.status_code == 200
    corr_events = [e for e in t_res.json() if e["event_type"] == "FACTS_CORRECTED"]
    assert len(corr_events) == 1
    evt = corr_events[0]
    assert evt["details"]["operator_reference"] == "disp-op-99"
    assert "correction_timestamp" in evt["details"] or "timestamp" in evt["details"]

    changes = evt["details"]["changes"]
    assert changes["casualty_count"]["old_value"] == 2
    assert changes["casualty_count"]["new_value"] == 5
    assert changes["severity"]["old_value"] == Severity.HIGH.value
    assert changes["severity"]["new_value"] == Severity.CRITICAL.value
    assert changes["location_text"]["old_value"] == "Nasr City intersection"
    assert changes["location_text"]["new_value"] == "Corrected: Rabaa Al-Adawiya square"


def test_facts_patch_planning_input_marks_downstream_inputs_dirty(
    client: TestClient,
    db_session: Session,
) -> None:
    """Patching location or required_resources marks downstream_inputs_dirty true without replanning."""
    inc = create_test_incident(db_session, version=1)

    # 1. Patch location -> dirty = True
    res_loc = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-geo",
            "location": {"lat": 30.0650, "lon": 31.3550},
        },
    )
    assert res_loc.status_code == 200
    data_loc = res_loc.json()
    assert data_loc["changed_fields"] == ["location"]
    assert data_loc["downstream_inputs_dirty"] is True
    assert data_loc["incident"]["version"] == 2
    assert data_loc["incident"]["location"] == {"lat": 30.0650, "lon": 31.3550}

    # 2. Patch required_resources -> dirty = True
    res_req = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 2,
            "operator_reference": "disp-res",
            "required_resources": [
                {"resource_type": "AMBULANCE", "count": 3},
                {"resource_type": "FIRE_RESCUE", "count": 2},
            ],
        },
    )
    assert res_req.status_code == 200
    data_req = res_req.json()
    assert data_req["changed_fields"] == ["required_resources"]
    assert data_req["downstream_inputs_dirty"] is True
    assert data_req["incident"]["version"] == 3
    assert len(data_req["incident"]["required_resources"]) == 2


def test_facts_patch_explicit_nullable_vs_omitted(
    client: TestClient,
    db_session: Session,
) -> None:
    """Omitted fields remain unchanged while explicit null values clear nullable fields."""
    inc = create_test_incident(db_session, version=1)
    assert inc.casualty_count == 2
    assert inc.location_text == "Nasr City intersection"

    # Explicit null on casualty_count; location_text omitted
    res = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-null",
            "casualty_count": None,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["changed_fields"] == ["casualty_count"]
    assert data["incident"]["casualty_count"] is None
    assert data["incident"]["location_text"] == "Nasr City intersection"
    assert data["incident"]["version"] == 2


def test_facts_patch_invalid_patch_no_mutation(
    client: TestClient,
    db_session: Session,
) -> None:
    """Invalid facts patch fails validation and leaves DB completely unchanged."""
    inc = create_test_incident(db_session, version=1)

    # Coordinate latitude > 90
    r1 = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-inv",
            "location": {"lat": 999.0, "lon": 31.3452},
        },
    )
    assert r1.status_code == 422

    # Negative casualty count
    r2 = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-inv",
            "casualty_count": -5,
        },
    )
    assert r2.status_code == 422

    # Forbidden client-assigned field (e.g. status)
    r3 = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-inv",
            "status": "CLOSED",
        },
    )
    assert r3.status_code == 422

    # Non-nullable field passed as null
    r4 = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-inv",
            "incident_type": None,
        },
    )
    assert r4.status_code == 422

    # Empty required resources
    r5 = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-inv",
            "required_resources": [],
        },
    )
    assert r5.status_code == 422

    # Verify zero DB mutation
    db_session.refresh(inc)
    assert inc.version == 1
    stmt = select(TimelineEvent).where(
        TimelineEvent.incident_id == inc.id,
        TimelineEvent.event_type == "FACTS_CORRECTED",
    )
    assert len(db_session.scalars(stmt).all()) == 0


def test_facts_patch_preserves_provenance_across_sequential_corrections(
    client: TestClient,
    db_session: Session,
) -> None:
    """Sequential corrections retain previously corrected fields in provenance."""
    inc = create_test_incident(db_session, version=1)

    # Patch 1: casualty_count
    r1 = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-01",
            "casualty_count": 4,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["incident"]["version"] == 2

    # Patch 2: road_blockage (with expected_incident_version=2)
    r2 = client.patch(
        f"/api/v1/incidents/{inc.id}/facts",
        json={
            "expected_incident_version": 2,
            "operator_reference": "disp-02",
            "road_blockage": False,
        },
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["incident"]["version"] == 3

    # Both casualty_count and road_blockage are retained in provenance
    corr_map = data2["incident"]["provenance"]["corrected_fields"]
    assert "casualty_count" in corr_map
    assert corr_map["casualty_count"]["operator_reference"] == "disp-01"
    assert "road_blockage" in corr_map
    assert corr_map["road_blockage"]["operator_reference"] == "disp-02"

    # Timeline has both FACTS_CORRECTED events in ascending order
    t_res = client.get(f"/api/v1/incidents/{inc.id}/timeline")
    assert t_res.status_code == 200
    events = [e for e in t_res.json() if e["event_type"] == "FACTS_CORRECTED"]
    assert len(events) == 2
    assert events[0]["details"]["operator_reference"] == "disp-01"
    assert events[1]["details"]["operator_reference"] == "disp-02"


def test_facts_patch_preserves_golden_flow_compatibility(
    client: TestClient,
    db_session: Session,
) -> None:
    """Corrected incident seamlessly proceeds through plan generation, approval, and transitions."""
    seed_resources(db_session)

    # 1. Manual intake (version 1)
    intake_res = client.post(
        "/api/v1/intake/manual",
        json={
            "incident_type": "traffic_collision",
            "severity": "HIGH",
            "confidence_level": "HIGH",
            "location": {"lat": 30.0561, "lon": 31.3452},
            "location_text": "Initial location",
            "casualty_count": 1,
            "required_resources": [
                {"resource_type": "AMBULANCE", "count": 1},
                {"resource_type": "FIRE_RESCUE", "count": 1},
            ],
            "operator_reference": "disp-flow",
        },
    )
    assert intake_res.status_code == 201
    inc_data = intake_res.json()
    inc_id = inc_data["id"]
    assert inc_data["version"] == 1

    # 2. Patch facts (version 1 -> 2)
    patch_res = client.patch(
        f"/api/v1/incidents/{inc_id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "disp-flow",
            "casualty_count": 3,
            "severity": "CRITICAL",
        },
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["incident"]["version"] == 2

    # 3. Generate response plan (version 2 -> 3, status AWAITING_APPROVAL)
    plan_res = client.post(f"/api/v1/incidents/{inc_id}/plans/generate")
    assert plan_res.status_code == 201
    plan_data = plan_res.json()
    plan_id = plan_data["id"]
    assert plan_data["incident_version"] == 3

    # 4. Approve plan (version 3 -> 4, status RESPONSE_ACTIVE)
    app_res = client.post(
        f"/api/v1/plans/{plan_id}/approve",
        json={
            "operator_reference": "disp-flow",
            "expected_incident_version": 3,
            "expected_plan_version": 1,
        },
    )
    assert app_res.status_code == 200
    app_data = app_res.json()
    assert app_data["incident_status"] == IncidentStatus.RESPONSE_ACTIVE.value
    assert app_data["incident"]["version"] == 4

    # 5. Timeline audit check
    timeline_res = client.get(f"/api/v1/incidents/{inc_id}/timeline")
    assert timeline_res.status_code == 200
    event_types = [e["event_type"] for e in timeline_res.json()]
    assert "INCIDENT_CREATED" in event_types
    assert "FACTS_CORRECTED" in event_types
    assert "PLAN_GENERATED" in event_types
    assert "PLAN_APPROVED" in event_types
    assert "RESOURCES_ASSIGNED" in event_types
