from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401 - ensure all ORM models are registered
from app.db import init_db
from app.main import app
from app.models import Incident, TimelineEvent
from app.schemas import ConfidenceLevel, DataReality, FreshnessStatus, IncidentStatus, Severity


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    """Initialize all model tables on the isolated test engine."""
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_manual_intake_creates_and_activates_immediately(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify one manual report creates and activates immediately with HTTP 201,

    status ACTIVE_UNCONFIRMED, version 1, UUID id, copied fields, required resources,
    provenance reality/freshness/source, and one INCIDENT_CREATED timeline event.
    """
    payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "El-Nasr Road intersection with Abbas El-Akkad",
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

    response = client.post("/api/v1/intake/manual", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    # Verify ID is a valid UUID
    incident_uuid = uuid.UUID(data["id"])
    assert str(incident_uuid) == data["id"]

    # Verify initial lifecycle state and version
    assert data["status"] == IncidentStatus.ACTIVE_UNCONFIRMED.value
    assert data["version"] == 1

    # Verify copied incident fields
    assert data["incident_type"] == "traffic_collision"
    assert data["severity"] == Severity.HIGH.value
    assert data["confidence_level"] == ConfidenceLevel.HIGH.value
    assert data["location"]["lat"] == 30.0561
    assert data["location"]["lon"] == 31.3452
    assert data["latitude"] == 30.0561
    assert data["longitude"] == 31.3452
    assert data["location_text"] == "El-Nasr Road intersection with Abbas El-Akkad"
    assert data["casualty_count"] == 2
    assert data["casualty_range"] == "2-3"
    assert data["trapped_person"] is True
    assert data["road_blockage"] is True

    # Verify required resources as JSON-safe enum values
    expected_resources = [
        {"resource_type": "AMBULANCE", "count": 2},
        {"resource_type": "FIRE_RESCUE", "count": 1},
    ]
    assert data["required_resources"] == expected_resources
    assert data["required_resources_json"] == expected_resources

    # Verify provenance
    provenance = data["provenance"]
    assert provenance["data_reality"] == DataReality.SIMULATED.value
    assert provenance["freshness_status"] == FreshnessStatus.FRESH.value
    assert provenance["source"] == "operator_manual_entry"
    assert provenance["source_reference"] == "dispatcher-op-01"
    # Ensure last_updated is a valid ISO-8601 timestamp
    parsed_dt = datetime.datetime.fromisoformat(provenance["last_updated"])
    assert parsed_dt is not None

    # Verify DB state directly in the isolated database session
    db_incident = db_session.get(Incident, data["id"])
    assert db_incident is not None
    assert db_incident.version == 1
    assert db_incident.status == IncidentStatus.ACTIVE_UNCONFIRMED
    assert db_incident.latitude == 30.0561
    assert db_incident.longitude == 31.3452
    assert db_incident.casualty_count == 2
    assert db_incident.trapped_person is True
    assert db_incident.road_blockage is True
    assert db_incident.required_resources_json == expected_resources
    assert db_incident.provenance_json["data_reality"] == "SIMULATED"
    assert db_incident.provenance_json["freshness_status"] == "FRESH"

    # Verify TimelineEvent created and committed in the same transaction
    events = (
        db_session.query(TimelineEvent)
        .filter_by(incident_id=data["id"])
        .all()
    )
    assert len(events) == 1
    event = events[0]
    uuid.UUID(event.id)
    assert event.event_type == "INCIDENT_CREATED"
    assert event.details_json["operator_reference"] == "dispatcher-op-01"
    assert event.details_json["status"] == IncidentStatus.ACTIVE_UNCONFIRMED.value


def test_single_report_activates_immediately_no_second_report_needed(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify immediate activation rule: a single credible operator manual report

    immediately transitions into ACTIVE_UNCONFIRMED with no second report required.
    """
    payload: dict[str, Any] = {
        "incident_type": "structure_fire",
        "severity": "CRITICAL",
        "location": {"lat": 30.0610, "lon": 31.3320},
        "required_resources": [
            {"resource_type": "FIRE_RESCUE", "count": 2},
        ],
    }

    response = client.post("/api/v1/intake/manual", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["status"] == "ACTIVE_UNCONFIRMED"
    assert data["version"] == 1

    # Confirmed in database without any secondary reports
    db_incident = db_session.get(Incident, data["id"])
    assert db_incident is not None
    assert db_incident.status == IncidentStatus.ACTIVE_UNCONFIRMED


def test_omitted_optional_fields_remain_null(
    client: TestClient,
    db_session: Session,
) -> None:
    """Verify omitted casualty_count/trapped_person/road_blockage/location_text remain null."""
    payload: dict[str, Any] = {
        "incident_type": "medical_emergency",
        "severity": "MODERATE",
        "location": {"lat": 30.0500, "lon": 31.3400},
        "required_resources": [
            {"resource_type": "AMBULANCE", "count": 1},
        ],
    }

    response = client.post("/api/v1/intake/manual", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["casualty_count"] is None
    assert data["casualty_range"] is None
    assert data["trapped_person"] is None
    assert data["road_blockage"] is None
    assert data["location_text"] is None

    # Check persistence directly
    db_incident = db_session.get(Incident, data["id"])
    assert db_incident is not None
    assert db_incident.casualty_count is None
    assert db_incident.casualty_range is None
    assert db_incident.trapped_person is None
    assert db_incident.road_blockage is None
    assert db_incident.location_text is None


def test_invalid_coordinates_return_422(client: TestClient) -> None:
    """Verify invalid coordinate latitude or longitude returns 422 Unprocessable Entity."""
    base_payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "LOW",
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
    }

    # Latitude > 90
    res_lat_high = client.post(
        "/api/v1/intake/manual",
        json={**base_payload, "location": {"lat": 91.0, "lon": 31.34}},
    )
    assert res_lat_high.status_code == 422

    # Latitude < -90
    res_lat_low = client.post(
        "/api/v1/intake/manual",
        json={**base_payload, "location": {"lat": -95.0, "lon": 31.34}},
    )
    assert res_lat_low.status_code == 422

    # Longitude > 180
    res_lon_high = client.post(
        "/api/v1/intake/manual",
        json={**base_payload, "location": {"lat": 30.05, "lon": 181.0}},
    )
    assert res_lon_high.status_code == 422

    # Longitude < -180
    res_lon_low = client.post(
        "/api/v1/intake/manual",
        json={**base_payload, "location": {"lat": 30.05, "lon": -185.0}},
    )
    assert res_lon_low.status_code == 422


def test_empty_required_resources_returns_422(client: TestClient) -> None:
    """Verify empty or missing required_resources returns 422 Unprocessable Entity."""
    # Empty list
    payload_empty: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "LOW",
        "location": {"lat": 30.05, "lon": 31.34},
        "required_resources": [],
    }
    res_empty = client.post("/api/v1/intake/manual", json=payload_empty)
    assert res_empty.status_code == 422

    # Missing required_resources
    payload_missing: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "LOW",
        "location": {"lat": 30.05, "lon": 31.34},
    }
    res_missing = client.post("/api/v1/intake/manual", json=payload_missing)
    assert res_missing.status_code == 422


def test_no_ai_or_provider_call_involved(client: TestClient) -> None:
    """Verify manual intake does not invoke any external AI, LLM, or provider systems."""
    payload: dict[str, Any] = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
    }

    # Verify no network or provider module is called
    with patch("urllib.request.urlopen") as mock_url:
        response = client.post("/api/v1/intake/manual", json=payload)
        assert response.status_code == 201
        assert mock_url.call_count == 0


def test_incident_can_be_activated_before_its_location_is_known(
    client: TestClient,
    db_session: Session,
) -> None:
    """A credible urgent report activates even when coordinates are unknown."""
    response = client.post(
        "/api/v1/intake/manual",
        json={
            "incident_type": "traffic_collision",
            "severity": "HIGH",
            "confidence_level": "MEDIUM",
            "location_text": "somewhere on Abbas El-Akkad, exact point unclear",
            "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
            "operator_reference": "dispatcher-op-01",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()

    # Unresolved location is null, never a sentinel coordinate.
    assert body["location"] is None
    assert body["latitude"] is None
    assert body["longitude"] is None
    assert body["location_text"] == "somewhere on Abbas El-Akkad, exact point unclear"
    assert body["status"] == IncidentStatus.ACTIVE_UNCONFIRMED.value
    assert body["provenance"]["location_resolved"] is False

    stored = db_session.get(Incident, body["id"])
    assert stored is not None
    assert stored.latitude is None and stored.longitude is None


def test_planning_blocked_until_location_is_confirmed(
    client: TestClient,
    db_session: Session,
) -> None:
    """Coordinate-dependent work fails visibly, then unlocks after correction."""
    created = client.post(
        "/api/v1/intake/manual",
        json={
            "incident_type": "traffic_collision",
            "severity": "HIGH",
            "confidence_level": "MEDIUM",
            "location_text": "unclear",
            "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
            "operator_reference": "dispatcher-op-01",
        },
    )
    incident_id = created.json()["id"]

    blocked = client.post(f"/api/v1/incidents/{incident_id}/plans/generate")
    assert blocked.status_code == 422, blocked.text
    assert "INCIDENT_LOCATION_REQUIRED" in blocked.json()["detail"]

    # An operator correction resolves the location and bumps the version once.
    patched = client.patch(
        f"/api/v1/incidents/{incident_id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "dispatcher-op-01",
            "location": {"lat": 30.0561, "lon": 31.3452},
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["changed_fields"] == ["location"]
    assert patched.json()["incident"]["version"] == 2
    assert patched.json()["incident"]["location"] == {"lat": 30.0561, "lon": 31.3452}
    assert patched.json()["downstream_inputs_dirty"] is True

    db_session.expire_all()
    stored = db_session.get(Incident, incident_id)
    assert stored is not None
    assert stored.latitude == 30.0561
    assert stored.longitude == 31.3452

    correction = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident_id,
            TimelineEvent.event_type == "FACTS_CORRECTED",
        )
    ).all()
    assert len(correction) == 1
    assert correction[0].details_json["changes"]["location"]["old"] is None


def test_existing_database_with_not_null_location_is_migrated_without_data_loss(
    tmp_path,
) -> None:
    """An older local database keeps its rows when coordinates become nullable."""
    database_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        # The pre-change schema, matching what SQLAlchemy emitted before
        # coordinates became nullable: latitude/longitude declared NOT NULL
        # alongside the other required columns.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE incidents ("
                    "id VARCHAR(36) NOT NULL PRIMARY KEY, "
                    "version INTEGER NOT NULL, "
                    "incident_type VARCHAR NOT NULL, "
                    "severity VARCHAR(8) NOT NULL, "
                    "confidence_level VARCHAR(6) NOT NULL, "
                    "status VARCHAR(22) NOT NULL, "
                    "latitude FLOAT NOT NULL, longitude FLOAT NOT NULL, "
                    "location_text VARCHAR, casualty_count INTEGER, "
                    "casualty_range VARCHAR, trapped_person BOOLEAN, "
                    "road_blockage BOOLEAN, transport_required BOOLEAN, "
                    "required_hospital_capabilities_json JSON NOT NULL, "
                    "required_resources_json JSON NOT NULL, "
                    "current_plan_id VARCHAR(36), "
                    "pending_replan_plan_id VARCHAR(36), "
                    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
                    "provenance_json JSON NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO incidents (id, version, incident_type, severity, "
                    "confidence_level, status, latitude, longitude, "
                    "location_text, required_hospital_capabilities_json, "
                    "required_resources_json, created_at, updated_at, "
                    "provenance_json) VALUES "
                    "('legacy-1', 3, 'traffic_collision', 'HIGH', 'HIGH', "
                    "'RESPONSE_ACTIVE', 30.0561, 31.3452, 'El-Nasr Road', "
                    "'[]', '[]', '2026-09-07 10:00:00', '2026-09-07 10:00:00', "
                    "'{}')"
                )
            )

        init_db(engine)

        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    "SELECT id, version, latitude, longitude, status, location_text "
                    "FROM incidents"
                )
            ).all()
            nullable = {
                row[1]: not row[3]
                for row in connection.execute(
                    text("PRAGMA table_info(incidents)")
                ).all()
            }

        # The pre-existing row survives verbatim and the constraint is relaxed.
        assert rows == [
            ("legacy-1", 3, 30.0561, 31.3452, "RESPONSE_ACTIVE", "El-Nasr Road")
        ]
        assert nullable["latitude"] is True
        assert nullable["longitude"] is True

        # And an unresolved location can now be stored.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO incidents (id, version, incident_type, severity, "
                    "confidence_level, status, "
                    "required_hospital_capabilities_json, required_resources_json, "
                    "created_at, updated_at, provenance_json) VALUES "
                    "('legacy-2', 1, 'traffic_collision', 'HIGH', 'HIGH', "
                    "'ACTIVE_UNCONFIRMED', '[]', '[]', "
                    "'2026-09-07 10:00:00', '2026-09-07 10:00:00', '{}')"
                )
            )
            stored = connection.execute(
                text("SELECT latitude, longitude FROM incidents WHERE id='legacy-2'")
            ).one()
        assert stored == (None, None)

        # Re-running init_db must be a no-op once the schema is current.
        init_db(engine)
        with engine.begin() as connection:
            assert (
                connection.execute(text("SELECT COUNT(*) FROM incidents")).scalar() == 2
            )
    finally:
        engine.dispose()


def _transition(
    client: TestClient, incident_id: str, target: IncidentStatus, version: int
) -> Any:
    return client.post(
        f"/api/v1/incidents/{incident_id}/transition",
        json={
            "target_status": target.value,
            "expected_incident_version": version,
            "operator_reference": "dispatcher-lifecycle",
        },
    )


def _new_incident(db: Session, status: IncidentStatus) -> Incident:
    incident = Incident(
        id=str(uuid.uuid4()),
        version=1,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=status,
        latitude=30.0561,
        longitude=31.3452,
        required_resources_json=[],
        provenance_json={},
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def test_active_unconfirmed_reaches_awaiting_approval_without_response_proposed(
    client: TestClient,
    db_session: Session,
) -> None:
    """The canonical planning transition must be legal on the lifecycle itself.

    Production persists ACTIVE_UNCONFIRMED -> AWAITING_APPROVAL directly, so
    the operator transition table must not require the deprecated
    RESPONSE_PROPOSED hop.
    """
    incident = _new_incident(db_session, IncidentStatus.ACTIVE_UNCONFIRMED)

    response = _transition(client, incident.id, IncidentStatus.AWAITING_APPROVAL, 1)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == IncidentStatus.AWAITING_APPROVAL.value
    assert response.json()["version"] == 2


def test_review_hold_round_trip_and_terminal_states_are_closed(
    client: TestClient,
    db_session: Session,
) -> None:
    """REQUIRES_REVIEW is an exitable pre-dispatch hold; merges are terminal."""
    incident = _new_incident(db_session, IncidentStatus.ACTIVE_UNCONFIRMED)

    held = _transition(client, incident.id, IncidentStatus.REQUIRES_REVIEW, 1)
    assert held.status_code == 200, held.text
    assert held.json()["status"] == IncidentStatus.REQUIRES_REVIEW.value

    # A review hold must stop automated planning until it is resolved.
    blocked = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert blocked.status_code == 409

    released = _transition(client, incident.id, IncidentStatus.ACTIVE_UNCONFIRMED, 2)
    assert released.status_code == 200, released.text
    assert released.json()["status"] == IncidentStatus.ACTIVE_UNCONFIRMED.value

    # Cancellation is owned by the cancel command, not a bare transition, so
    # that its committed-response guard cannot be bypassed.
    bypass = _transition(
        client, incident.id, IncidentStatus.CANCELLED_FALSE_REPORT, 3
    )
    assert bypass.status_code == 409

    merged = _new_incident(db_session, IncidentStatus.DUPLICATE_MERGED)
    for target in (
        IncidentStatus.ACTIVE_UNCONFIRMED,
        IncidentStatus.AWAITING_APPROVAL,
    ):
        assert _transition(client, merged.id, target, 1).status_code == 409


def test_timeline_event_ids_are_time_ordered_and_valid_uuids() -> None:
    """Audit event identifiers must sort by creation order.

    Timeline reads order by created_at then id. Wall-clock resolution is coarse
    enough that consecutive operator commands share a created_at value, so a
    random identifier would return the audit trail in arbitrary order.
    """
    from app.models import new_timeline_event_id

    generated = [new_timeline_event_id() for _ in range(2000)]

    assert generated == sorted(generated), "identifiers must be monotonically ordered"
    assert len(set(generated)) == len(generated), "identifiers must be unique"
    for value in (generated[0], generated[-1]):
        parsed = uuid.UUID(value)
        assert str(parsed) == value
        assert parsed.version == 7


def test_incident_timeline_preserves_insertion_order_within_one_timestamp(
    client: TestClient,
    db_session: Session,
) -> None:
    """Events sharing an identical created_at must still read back in order."""
    incident = Incident(
        id=str(uuid.uuid4()),
        version=1,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=30.0561,
        longitude=31.3452,
        required_resources_json=[],
        provenance_json={},
    )
    db_session.add(incident)
    db_session.commit()

    # Force the exact collision the coarse wall clock produces in production.
    shared_timestamp = datetime.datetime(2026, 9, 8, tzinfo=datetime.timezone.utc)
    expected = [f"STEP_{index:02d}" for index in range(12)]
    for event_type in expected:
        db_session.add(
            TimelineEvent(
                incident_id=incident.id,
                event_type=event_type,
                details_json={},
                created_at=shared_timestamp,
            )
        )
        db_session.commit()

    response = client.get(f"/api/v1/incidents/{incident.id}/timeline")
    assert response.status_code == 200, response.text
    assert [event["event_type"] for event in response.json()] == expected
