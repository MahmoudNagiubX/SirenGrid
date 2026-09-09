from __future__ import annotations

import logging

import app.models as _models  # noqa: F401
import pytest
from app.db import init_db
from app.main import app
from app.mobile_auth import hash_pin, national_id_fingerprint
from app.models import CitizenProfile
from app.seed import seed_demo_citizen
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

# A synthetic 14-digit value. NOT a real Egyptian National ID.
SYNTHETIC_NID = "29001010123456"


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "display_name": "Registered Citizen",
        "phone": "01111222333",
        "national_id": SYNTHETIC_NID,
        "pin": "4321",
        "pin_confirm": "4321",
        "registered_address_text": "8 Test Street, Nasr City, Cairo",
        "registered_latitude": 30.05,
        "registered_longitude": 31.33,
    }
    body.update(overrides)
    return body


def _register(client: TestClient, **overrides: object):
    return client.post("/api/v1/mobile/auth/register", json=_payload(**overrides))


# --- happy path ------------------------------------------------------------


def test_valid_registration_returns_token_and_profile(client: TestClient) -> None:
    res = _register(client)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    profile = body["profile"]
    assert profile["display_name"] == "Registered Citizen"
    assert profile["phone"] == "01111222333"
    assert profile["national_id_masked"] == "**********3456"
    assert profile["registered_address"] == "8 Test Street, Nasr City, Cairo"
    assert profile["citizen_reference"].startswith("citizen-")


def test_token_from_registration_authenticates_me(client: TestClient) -> None:
    token = _register(client).json()["access_token"]
    res = client.get(
        "/api/v1/mobile/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    assert res.json()["phone"] == "01111222333"


def test_login_after_registration(client: TestClient) -> None:
    _register(client)
    res = client.post(
        "/api/v1/mobile/auth/login",
        json={"phone": "01111222333", "pin": "4321"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["profile"]["national_id_masked"] == "**********3456"


def test_logout_after_registration(client: TestClient) -> None:
    token = _register(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/mobile/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/mobile/me", headers=headers).status_code == 401


# --- persistence + privacy ----------------------------------------------------


def test_pin_stored_hashed_not_plaintext(
    client: TestClient, db_session: Session
) -> None:
    _register(client)
    row = db_session.scalars(
        select(CitizenProfile).where(CitizenProfile.phone == "01111222333")
    ).one()
    assert row.pin_hash not in ("4321", "")
    assert "4321" not in row.pin_hash
    assert row.pin_hash == hash_pin("4321", row.pin_salt)


def test_full_national_id_never_persisted(
    client: TestClient, db_session: Session
) -> None:
    _register(client)
    row = db_session.scalars(
        select(CitizenProfile).where(CitizenProfile.phone == "01111222333")
    ).one()
    assert row.national_id_last4 == "3456"
    assert SYNTHETIC_NID not in (str(vars(row)))
    assert row.national_id_fingerprint == national_id_fingerprint(SYNTHETIC_NID)
    # Fingerprint is not a plain SHA-256 of the digits.
    import hashlib

    assert row.national_id_fingerprint != hashlib.sha256(
        SYNTHETIC_NID.encode()
    ).hexdigest()


def test_full_national_id_never_returned(client: TestClient) -> None:
    body = _register(client).json()
    assert SYNTHETIC_NID not in str(body)
    assert body["profile"]["national_id_masked"] == "**********3456"


def test_registration_does_not_log_sensitive_data(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        _register(client)
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert SYNTHETIC_NID not in blob
    assert "4321" not in blob


def test_registered_location_is_separate_from_emergency_gps(
    client: TestClient, db_session: Session
) -> None:
    token = _register(
        client, registered_latitude=30.05, registered_longitude=31.33
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Emergency request carries its own fresh Device GPS — a different point.
    res = client.post(
        "/api/v1/mobile/emergency-requests",
        headers={**headers, "Idempotency-Key": "reg-sep-1"},
        json={
            "service": "AMBULANCE",
            "location": {"lat": 30.11, "lon": 31.40},
        },
    )
    assert res.status_code in (200, 201), res.text

    row = db_session.scalars(
        select(CitizenProfile).where(CitizenProfile.phone == "01111222333")
    ).one()
    # Registered account location is untouched by the emergency request.
    assert row.registered_latitude == pytest.approx(30.05)
    assert row.registered_longitude == pytest.approx(31.33)

    incident_id = res.json()["incident_id"]
    track = client.get(
        f"/api/v1/mobile/emergency-requests/{res.json()['request_id']}",
        headers=headers,
    )
    assert track.status_code == 200
    loc = track.json().get("emergency_location")
    assert loc is not None
    assert loc["lat"] == pytest.approx(30.11)
    assert loc["lon"] == pytest.approx(31.40)
    assert incident_id


# --- validation + duplicates -----------------------------------------------


def test_duplicate_phone_is_409(client: TestClient) -> None:
    assert _register(client).status_code == 201
    dup = _register(client, national_id="29001010999999")
    assert dup.status_code == 409


def test_duplicate_identity_fingerprint_is_409(client: TestClient) -> None:
    assert _register(client).status_code == 201
    dup = _register(client, phone="01999888777")
    assert dup.status_code == 409


def test_seeded_demo_phone_collision_is_409(
    client: TestClient, db_session: Session
) -> None:
    seed_demo_citizen(db_session)
    res = _register(client, phone="01000000000")
    assert res.status_code == 409


def test_invalid_phone_is_422(client: TestClient) -> None:
    assert _register(client, phone="12345").status_code == 422
    assert _register(client, phone="01234").status_code == 422


def test_invalid_national_id_is_422(client: TestClient) -> None:
    assert _register(client, national_id="123").status_code == 422
    assert _register(client, national_id="abcdefghijklmn").status_code == 422


def test_pin_mismatch_is_422(client: TestClient) -> None:
    assert _register(client, pin="4321", pin_confirm="0000").status_code == 422


def test_invalid_pin_is_422(client: TestClient) -> None:
    assert _register(client, pin="12", pin_confirm="12").status_code == 422
    assert _register(client, pin="abcd", pin_confirm="abcd").status_code == 422


def test_invalid_coordinates_is_422(client: TestClient) -> None:
    assert _register(client, registered_latitude=200.0).status_code == 422
    assert _register(client, registered_longitude=999.0).status_code == 422


def test_coordinates_optional(client: TestClient) -> None:
    res = _register(
        client, registered_latitude=None, registered_longitude=None
    )
    assert res.status_code == 201, res.text


def test_half_coordinates_rejected(client: TestClient) -> None:
    assert (
        _register(client, registered_longitude=None).status_code == 422
    )


def test_blank_name_is_422(client: TestClient) -> None:
    assert _register(client, display_name="   ").status_code == 422


def test_rejects_extra_fields(client: TestClient) -> None:
    res = client.post(
        "/api/v1/mobile/auth/register",
        json={**_payload(), "citizen_reference": "attacker-chosen"},
    )
    assert res.status_code == 422


def test_seeded_demo_account_still_logs_in(
    client: TestClient, db_session: Session
) -> None:
    seed_demo_citizen(db_session)
    res = client.post(
        "/api/v1/mobile/auth/login",
        json={"phone": "01000000000", "pin": "1234"},
    )
    assert res.status_code == 200, res.text
