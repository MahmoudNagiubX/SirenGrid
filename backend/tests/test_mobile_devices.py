from __future__ import annotations

from datetime import datetime, timezone

import app.models as _models  # noqa: F401
import pytest
from app.db import init_db
from app.main import app
from app.mobile_auth import generate_pin_salt, hash_pin
from app.models import CitizenDeviceToken, CitizenProfile
from app.seed import seed_demo_citizen
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def citizen(db_session: Session) -> CitizenProfile:
    return seed_demo_citizen(db_session)


def _make_citizen(db: Session, *, reference: str, phone: str) -> CitizenProfile:
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
        pin_hash=hash_pin("1234", salt),
        pin_salt=salt,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    return row


def login(client: TestClient, phone: str = "01000000000", pin: str = "1234") -> dict:
    res = client.post("/api/v1/mobile/auth/login", json={"phone": phone, "pin": pin})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_authenticated_registration_upserts(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    res = client.post(
        "/api/v1/mobile/devices/register",
        headers=headers,
        json={"token": "tok-A", "platform": "ANDROID", "app_version": "1.0.0"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["registered"] is True
    assert body["platform"] == "ANDROID"

    rows = db_session.scalars(select(CitizenDeviceToken)).all()
    assert len(rows) == 1
    assert rows[0].citizen_reference == "demo-citizen-001"
    assert rows[0].is_active is True

    # Re-register the same token -> still one row, timestamps refreshed.
    first_seen = rows[0].last_seen_at
    res2 = client.post(
        "/api/v1/mobile/devices/register",
        headers=headers,
        json={"token": "tok-A", "platform": "ANDROID"},
    )
    assert res2.status_code == 200
    db_session.expire_all()
    rows = db_session.scalars(select(CitizenDeviceToken)).all()
    assert len(rows) == 1
    assert rows[0].last_seen_at >= first_seen


def test_registration_requires_authentication(client: TestClient, citizen) -> None:
    res = client.post(
        "/api/v1/mobile/devices/register",
        json={"token": "tok-A", "platform": "ANDROID"},
    )
    assert res.status_code == 401


def test_registration_rejects_identity_fields_and_bad_platform(
    client: TestClient, citizen
) -> None:
    headers = login(client)
    assert (
        client.post(
            "/api/v1/mobile/devices/register",
            headers=headers,
            json={
                "token": "tok",
                "platform": "ANDROID",
                "citizen_reference": "someone-else",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/mobile/devices/register",
            headers=headers,
            json={"token": "tok", "platform": "WINDOWS_PHONE"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/mobile/devices/register",
            headers=headers,
            json={"token": "", "platform": "ANDROID"},
        ).status_code
        == 422
    )


def test_token_reassociates_to_the_latest_authenticated_citizen(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    _make_citizen(db_session, reference="demo-citizen-002", phone="01099999999")
    headers_a = login(client)
    headers_b = login(client, phone="01099999999")

    client.post(
        "/api/v1/mobile/devices/register",
        headers=headers_a,
        json={"token": "shared-device", "platform": "ANDROID"},
    )
    client.post(
        "/api/v1/mobile/devices/register",
        headers=headers_b,
        json={"token": "shared-device", "platform": "ANDROID"},
    )

    rows = db_session.scalars(select(CitizenDeviceToken)).all()
    assert len(rows) == 1
    # Ownership moved to citizen B — citizen A stops receiving pushes here.
    assert rows[0].citizen_reference == "demo-citizen-002"


def test_unregister_deactivates_only_own_token(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    _make_citizen(db_session, reference="demo-citizen-003", phone="01088888888")
    headers_a = login(client)
    headers_b = login(client, phone="01088888888")
    client.post(
        "/api/v1/mobile/devices/register",
        headers=headers_a,
        json={"token": "tok-a", "platform": "ANDROID"},
    )
    client.post(
        "/api/v1/mobile/devices/register",
        headers=headers_b,
        json={"token": "tok-b", "platform": "ANDROID"},
    )

    # B tries to unregister A's token -> 204, but A's token stays active.
    res = client.post(
        "/api/v1/mobile/devices/unregister",
        headers=headers_b,
        json={"token": "tok-a"},
    )
    assert res.status_code == 204
    a_row = db_session.scalars(
        select(CitizenDeviceToken).where(CitizenDeviceToken.token == "tok-a")
    ).first()
    assert a_row.is_active is True

    # A unregisters its own -> deactivated.
    assert (
        client.post(
            "/api/v1/mobile/devices/unregister",
            headers=headers_a,
            json={"token": "tok-a"},
        ).status_code
        == 204
    )
    db_session.expire_all()
    a_row = db_session.scalars(
        select(CitizenDeviceToken).where(CitizenDeviceToken.token == "tok-a")
    ).first()
    assert a_row.is_active is False


def test_profile_response_never_exposes_device_tokens(
    client: TestClient, citizen: CitizenProfile
) -> None:
    headers = login(client)
    client.post(
        "/api/v1/mobile/devices/register",
        headers=headers,
        json={"token": "super-secret-token", "platform": "ANDROID"},
    )
    me = client.get("/api/v1/mobile/me", headers=headers)
    assert me.status_code == 200
    assert "super-secret-token" not in me.text
    assert "token" not in me.json()


def test_registration_has_no_effect_on_emergency_intake(
    client: TestClient, db_session: Session, citizen: CitizenProfile
) -> None:
    headers = login(client)
    client.post(
        "/api/v1/mobile/devices/register",
        headers=headers,
        json={"token": "tok", "platform": "ANDROID"},
    )
    res = client.post(
        "/api/v1/mobile/emergency-requests",
        headers=headers,
        json={"service": "AMBULANCE", "location": {"lat": 30.0561, "lon": 31.3452}},
    )
    assert res.status_code == 201
    assert res.json()["service"] == "AMBULANCE"
