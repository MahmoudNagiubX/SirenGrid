from __future__ import annotations

from datetime import datetime, timezone

import app.models as _models  # noqa: F401
import pytest
from app import mobile_api
from app.db import init_db
from app.main import app
from app.mobile_auth import generate_pin_salt, hash_pin
from app.models import (
    CitizenIdempotencyRecord,
    CitizenProfile,
    EmergencyResource,
    Incident,
    Report,
    TimelineEvent,
)
from app.schemas import IncidentStatus, ResourceType, Severity
from app.seed import seed_demo_citizen, seed_resources
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

NASR_CITY = {"lat": 30.0561, "lon": 31.3452}


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def citizen(db_session: Session) -> CitizenProfile:
    return seed_demo_citizen(db_session)


def make_citizen(
    db: Session,
    *,
    reference: str,
    phone: str,
    pin: str = "1234",
) -> CitizenProfile:
    salt = generate_pin_salt()
    now = datetime.now(timezone.utc)
    row = CitizenProfile(
        citizen_reference=reference,
        display_name=f"Citizen {reference}",
        phone=phone,
        registered_address_text="9 Other Street, Heliopolis, Cairo",
        national_id_last4="9876",
        identity_status="DEMO_VERIFIED",
        identity_provider="SYNTHETIC_DEMO_IDENTITY",
        pin_hash=hash_pin(pin, salt),
        pin_salt=salt,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def login(client: TestClient, phone: str = "01000000000", pin: str = "1234") -> dict:
    res = client.post(
        "/api/v1/mobile/auth/login", json={"phone": phone, "pin": pin}
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def create_request(
    client: TestClient,
    headers: dict,
    *,
    service: str = "AMBULANCE",
    location: dict | None = NASR_CITY,
    key: str | None = None,
    **extra: object,
):
    body: dict = {"service": service}
    if location is not None:
        body["location"] = location
    body.update(extra)
    hdrs = dict(headers)
    if key is not None:
        hdrs["Idempotency-Key"] = key
    return client.post("/api/v1/mobile/emergency-requests", json=body, headers=hdrs)


# ======================================================================
# Phase C — mobile emergency intake
# ======================================================================


def test_intake_requires_authentication(client: TestClient, citizen: CitizenProfile) -> None:
    res = client.post(
        "/api/v1/mobile/emergency-requests",
        json={"service": "AMBULANCE", "location": NASR_CITY},
    )
    assert res.status_code == 401


def test_ambulance_request_creates_incident_and_report(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    res = create_request(client, headers, service="AMBULANCE")
    assert res.status_code == 201, res.text
    body = res.json()

    assert body["status"] == "RECEIVED"
    assert body["service"] == "AMBULANCE"
    assert body["tracking_available"] is False
    assert body["request_id"] and body["incident_id"]

    report = db_session.get(Report, body["request_id"])
    assert report is not None
    assert report.id == body["request_id"]  # request_id == Report id
    assert report.source_type == "MOBILE_APP"
    assert report.source_reference == "demo-citizen-001"
    assert report.data_reality.value == "SYNTHETIC"
    assert report.incident_id == body["incident_id"]
    assert report.location_json == NASR_CITY

    incident = db_session.get(Incident, body["incident_id"])
    assert incident is not None
    assert incident.latitude == NASR_CITY["lat"]
    assert incident.longitude == NASR_CITY["lon"]
    assert incident.severity == Severity.MODERATE
    assert incident.required_resources_json == [
        {"resource_type": "AMBULANCE", "count": 1}
    ]
    assert incident.status == IncidentStatus.ACTIVE_UNCONFIRMED


def test_intake_derives_citizen_context_and_masks_identity(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    body = create_request(client, headers).json()
    report = db_session.get(Report, body["request_id"])
    prov = report.provenance_json

    assert prov["source_type"] == "MOBILE_APP"
    assert prov["source_reference"] == "demo-citizen-001"
    assert prov["severity_authority"] == "UNCONFIRMED_MOBILE_PLACEHOLDER"
    assert prov["location_source"] == "DEVICE_GPS"
    ctx = prov["citizen_context"]
    assert ctx["registered_address"] == "12 Demo Street, Nasr City, Cairo"
    assert ctx["national_id_masked"] == "**********1234"
    assert ctx["display_name"] == "Demo Citizen"
    # No secret / full identity material anywhere in provenance.
    blob = str(prov)
    for leaked in ("pin_hash", "pin_salt", "token", "pin_iterations"):
        assert leaked not in blob


def test_fire_request_maps_to_fire_rescue_requirement(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    body = create_request(client, headers, service="FIRE").json()
    incident = db_session.get(Incident, body["incident_id"])
    assert incident.required_resources_json == [
        {"resource_type": "FIRE_RESCUE", "count": 1}
    ]
    assert incident.incident_type == "mobile_fire_request"


def test_police_request_creates_no_fake_resource_requirement(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    body = create_request(client, headers, service="POLICE").json()
    incident = db_session.get(Incident, body["incident_id"])
    assert incident.required_resources_json == []
    assert incident.status == IncidentStatus.REQUIRES_REVIEW
    assert incident.provenance_json["operator_handoff_required"] is True
    assert "POLICE" not in str(incident.required_resources_json)


def test_general_request_fabricates_no_requirements(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    body = create_request(client, headers, service="GENERAL").json()
    incident = db_session.get(Incident, body["incident_id"])
    assert incident.required_resources_json == []
    assert incident.status == IncidentStatus.REQUIRES_REVIEW
    assert incident.provenance_json["operator_review_required"] is True


def test_request_body_cannot_override_citizen(
    client: TestClient, citizen: CitizenProfile
) -> None:
    headers = login(client)
    res = create_request(client, headers, citizen_reference="someone-else")
    assert res.status_code == 422


def test_unknown_service_rejected(client: TestClient, citizen: CitizenProfile) -> None:
    headers = login(client)
    res = create_request(client, headers, service="COASTGUARD")
    assert res.status_code == 422


def test_live_gps_becomes_incident_coordinates_not_registered_address(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    here = {"lat": 30.1122, "lon": 31.4455}
    body = create_request(client, headers, location=here).json()
    incident = db_session.get(Incident, body["incident_id"])
    assert incident.latitude == here["lat"]
    assert incident.longitude == here["lon"]
    # Registered address text is never used as a coordinate / location_text.
    assert incident.location_text is None
    assert "Demo Street" not in str(incident.latitude)


def test_missing_gps_fails_with_current_location_required(
    client: TestClient, citizen: CitizenProfile
) -> None:
    headers = login(client)
    res = create_request(client, headers, location=None)
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "CURRENT_LOCATION_REQUIRED"


def test_missing_gps_does_not_create_incident(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    create_request(client, headers, location=None)
    assert db_session.scalars(select(Incident)).all() == []
    assert db_session.scalars(select(Report)).all() == []


def test_invalid_coordinates_rejected(client: TestClient, citizen: CitizenProfile) -> None:
    headers = login(client)
    assert create_request(client, headers, location={"lat": 200, "lon": 31.3}).status_code == 422
    assert create_request(client, headers, location={"lat": 30.0, "lon": "abc"}).status_code == 422


def test_placeholder_severity_marked_unconfirmed(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    body = create_request(client, headers).json()
    incident = db_session.get(Incident, body["incident_id"])
    assert incident.severity == Severity.MODERATE
    assert (
        incident.provenance_json["severity_authority"]
        == "UNCONFIRMED_MOBILE_PLACEHOLDER"
    )


def test_explicit_requirement_is_independent_of_placeholder_severity(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    body = create_request(client, headers, service="AMBULANCE").json()
    incident = db_session.get(Incident, body["incident_id"])
    # Severity is only a placeholder; the explicit AMBULANCE requirement is what
    # a planner would consume.
    assert incident.severity == Severity.MODERATE
    assert incident.required_resources_json == [
        {"resource_type": "AMBULANCE", "count": 1}
    ]


def test_timeline_events_created(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    body = create_request(client, headers).json()
    events = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == body["incident_id"]
        )
    ).all()
    types = {e.event_type for e in events}
    assert "INCIDENT_CREATED" in types
    assert "REPORT_CREATED" in types


def test_operations_event_published_after_commit(
    client: TestClient,
    db_session: Session,
    citizen: CitizenProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def _capture(**kwargs: object) -> dict:
        # The incident must already be persisted when the event fires.
        assert db_session.get(Incident, kwargs["incident_id"]) is not None
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(mobile_api, "publish_operations_event", _capture)
    headers = login(client)
    body = create_request(client, headers).json()

    assert len(calls) == 1
    assert calls[0]["event"] == "incident.created"
    assert calls[0]["incident_id"] == body["incident_id"]


def test_failed_transaction_leaves_no_partial_state_and_no_event(
    client: TestClient,
    db_session: Session,
    citizen: CitizenProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    monkeypatch.setattr(
        mobile_api, "publish_operations_event", lambda **k: events.append(k)
    )

    def _boom() -> str:
        raise RuntimeError("simulated id generator failure")

    monkeypatch.setattr(mobile_api, "new_timeline_event_id", _boom)

    safe_client = TestClient(app, raise_server_exceptions=False)
    headers = login(safe_client)
    res = create_request(safe_client, headers)
    assert res.status_code == 500

    assert db_session.scalars(select(Incident)).all() == []
    assert db_session.scalars(select(Report)).all() == []
    assert events == []


# ======================================================================
# Phase D — idempotency
# ======================================================================


def test_same_key_same_payload_returns_original_ids(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    first = create_request(client, headers, key="k-1")
    assert first.status_code == 201
    second = create_request(client, headers, key="k-1")
    assert second.status_code == 200
    assert second.json()["request_id"] == first.json()["request_id"]
    assert second.json()["incident_id"] == first.json()["incident_id"]
    assert len(db_session.scalars(select(Incident)).all()) == 1
    assert len(db_session.scalars(select(Report)).all()) == 1


def test_same_key_changed_service_conflicts(
    client: TestClient, citizen: CitizenProfile
) -> None:
    headers = login(client)
    assert create_request(client, headers, service="AMBULANCE", key="k-2").status_code == 201
    res = create_request(client, headers, service="FIRE", key="k-2")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_same_key_changed_location_conflicts(
    client: TestClient, citizen: CitizenProfile
) -> None:
    headers = login(client)
    assert create_request(client, headers, key="k-3").status_code == 201
    res = create_request(client, headers, location={"lat": 30.2, "lon": 31.5}, key="k-3")
    assert res.status_code == 409


def test_different_key_creates_new_request(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    a = create_request(client, headers, key="k-a")
    b = create_request(client, headers, key="k-b")
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["incident_id"] != b.json()["incident_id"]
    assert len(db_session.scalars(select(Incident)).all()) == 2


def test_no_key_still_creates_request(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    assert create_request(client, headers).status_code == 201
    assert create_request(client, headers).status_code == 201
    assert len(db_session.scalars(select(Incident)).all()) == 2
    assert db_session.scalars(select(CitizenIdempotencyRecord)).all() == []


def test_idempotency_key_is_scoped_per_citizen(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    make_citizen(db_session, reference="demo-citizen-002", phone="01099999999")
    headers_a = login(client)
    headers_b = login(client, phone="01099999999")

    a = create_request(client, headers_a, key="shared-key")
    b = create_request(client, headers_b, key="shared-key")
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["incident_id"] != b.json()["incident_id"]


# ======================================================================
# Phase E — citizen-safe tracking
# ======================================================================


def test_tracking_requires_authentication(client: TestClient, citizen: CitizenProfile) -> None:
    headers = login(client)
    body = create_request(client, headers).json()
    res = client.get(f"/api/v1/mobile/emergency-requests/{body['request_id']}")
    assert res.status_code == 401


def test_owner_can_read_own_request(
    client: TestClient, citizen: CitizenProfile
) -> None:
    headers = login(client)
    body = create_request(client, headers).json()
    res = client.get(
        f"/api/v1/mobile/emergency-requests/{body['request_id']}", headers=headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["request_id"] == body["request_id"]
    assert data["incident_id"] == body["incident_id"]
    assert data["service"] == "AMBULANCE"
    assert data["status"] == "UNDER_REVIEW"
    assert data["eta_seconds"] is None
    assert data["responder"] is None


def test_other_citizen_request_is_404(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    owner_headers = login(client)
    body = create_request(client, owner_headers).json()

    make_citizen(db_session, reference="demo-citizen-003", phone="01088888888")
    other_headers = login(client, phone="01088888888")
    res = client.get(
        f"/api/v1/mobile/emergency-requests/{body['request_id']}",
        headers=other_headers,
    )
    assert res.status_code == 404


def test_nonexistent_request_is_404(client: TestClient, citizen: CitizenProfile) -> None:
    headers = login(client)
    res = client.get(
        "/api/v1/mobile/emergency-requests/does-not-exist", headers=headers
    )
    assert res.status_code == 404
    # Same shape as the not-owned case (anti-enumeration).
    assert res.json()["detail"] == "Emergency request not found"


@pytest.mark.parametrize(
    ("internal", "expected"),
    [
        (IncidentStatus.ACTIVE_UNCONFIRMED, "UNDER_REVIEW"),
        (IncidentStatus.AWAITING_APPROVAL, "UNDER_REVIEW"),
        (IncidentStatus.RESPONSE_ACTIVE, "RESPONSE_ASSIGNED"),
        (IncidentStatus.EN_ROUTE, "EN_ROUTE"),
        (IncidentStatus.ON_SCENE, "ARRIVED"),
        (IncidentStatus.HANDOVER, "ARRIVED"),
        (IncidentStatus.CLOSED, "COMPLETED"),
        (IncidentStatus.CANCELLED_FALSE_REPORT, "CANCELLED"),
        (IncidentStatus.REQUIRES_REVIEW, "UNDER_REVIEW"),
    ],
)
def test_status_projection_mapping(
    client: TestClient,
    db_session: Session,
    citizen: CitizenProfile,
    internal: IncidentStatus,
    expected: str,
) -> None:
    headers = login(client)
    body = create_request(client, headers).json()
    incident = db_session.get(Incident, body["incident_id"])
    incident.status = internal
    db_session.commit()

    res = client.get(
        f"/api/v1/mobile/emergency-requests/{body['request_id']}", headers=headers
    )
    assert res.status_code == 200
    assert res.json()["status"] == expected


def test_tracking_never_leaks_internal_planning_data(
    client: TestClient, citizen: CitizenProfile
) -> None:
    headers = login(client)
    body = create_request(client, headers).json()
    data = client.get(
        f"/api/v1/mobile/emergency-requests/{body['request_id']}", headers=headers
    ).json()
    assert set(data.keys()) == {
        "request_id",
        "incident_id",
        "service",
        "status",
        "eta_seconds",
        "responder",
        "last_updated",
    }
    blob = str(data)
    for forbidden in (
        "score_breakdown",
        "coverage",
        "reserve",
        "provenance",
        "metrics",
        "evidence",
        "operator",
    ):
        assert forbidden not in blob


def test_ambulance_intake_planning_and_tracking_end_to_end(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    """Explicit AMBULANCE requirement drives real planning; tracking then
    projects a simulated responder + route ETA without leaking internals."""
    seed_resources(db=db_session)
    headers = login(client)
    body = create_request(client, headers, service="AMBULANCE").json()
    incident_id = body["incident_id"]

    gen = client.post(f"/api/v1/incidents/{incident_id}/plans/generate")
    assert gen.status_code == 201, gen.text
    plan = gen.json()
    # The generated plan selected an ambulance (requirement-driven, not severity).
    seeded = {
        r.id: r
        for r in db_session.scalars(select(EmergencyResource)).all()
    }
    assert any(
        seeded[rid].resource_type == ResourceType.AMBULANCE
        for rid in plan["resource_ids"]
    )

    approve = client.post(
        f"/api/v1/plans/{plan['id']}/approve",
        json={
            "expected_incident_version": plan["incident_version"],
            "expected_plan_version": plan["plan_version"],
            "operator_reference": "dispatcher-op-01",
        },
    )
    assert approve.status_code == 200, approve.text

    track = client.get(
        f"/api/v1/mobile/emergency-requests/{body['request_id']}", headers=headers
    )
    assert track.status_code == 200
    data = track.json()
    assert data["status"] == "RESPONSE_ASSIGNED"
    assert data["responder"] is not None
    assert data["responder"]["data_reality"] == "SIMULATED"
    assert data["responder"]["id"] in plan["resource_ids"]
    assert data["eta_seconds"] is None or data["eta_seconds"] > 0
