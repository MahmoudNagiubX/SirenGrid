from __future__ import annotations

from datetime import datetime, timedelta, timezone

import app.models as _models  # noqa: F401
import pytest
from app.db import init_db
from app.main import app
from app.mobile_auth import hash_token
from app.models import CitizenProfile, CitizenSession
from app.seed import DEMO_CITIZEN_PIN, seed_demo_citizen
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
def seeded_citizen(db_session: Session) -> CitizenProfile:
    return seed_demo_citizen(db_session)


def _login(client: TestClient, phone: str = "01000000000", pin: str = "1234"):
    return client.post(
        "/api/v1/mobile/auth/login", json={"phone": phone, "pin": pin}
    )


# --- seed -------------------------------------------------------------------


def test_seed_creates_demo_citizen(db_session: Session) -> None:
    citizen = seed_demo_citizen(db_session)
    assert citizen.citizen_reference == "demo-citizen-001"
    assert citizen.phone == "01000000000"
    assert citizen.registered_address_text == "12 Demo Street, Nasr City, Cairo"
    assert citizen.national_id_last4 == "1234"
    assert citizen.identity_status == "DEMO_VERIFIED"
    assert citizen.identity_provider == "SYNTHETIC_DEMO_IDENTITY"
    assert citizen.is_active is True
    assert citizen.data_reality.value == "SYNTHETIC"


def test_seed_is_idempotent(db_session: Session) -> None:
    first = seed_demo_citizen(db_session)
    first_id = first.id
    second = seed_demo_citizen(db_session)
    assert second.id == first_id
    rows = db_session.scalars(select(CitizenProfile)).all()
    assert len(rows) == 1


def test_seed_does_not_overwrite_active_state(db_session: Session) -> None:
    citizen = seed_demo_citizen(db_session)
    citizen.is_active = False
    original_hash = citizen.pin_hash
    db_session.commit()

    again = seed_demo_citizen(db_session)
    assert again.is_active is False
    assert again.pin_hash == original_hash


def test_pin_is_not_stored_plaintext(db_session: Session) -> None:
    citizen = seed_demo_citizen(db_session)
    assert citizen.pin_hash != DEMO_CITIZEN_PIN
    assert DEMO_CITIZEN_PIN not in citizen.pin_hash
    assert len(citizen.pin_hash) >= 32


# --- login ----------------------------------------------------------------


def test_valid_login_returns_token_and_profile(
    client: TestClient, seeded_citizen: CitizenProfile
) -> None:
    res = _login(client)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert "expires_at" in body
    profile = body["profile"]
    assert profile["citizen_reference"] == "demo-citizen-001"
    assert profile["display_name"] == "Demo Citizen"
    assert profile["phone"] == "01000000000"
    assert profile["registered_address"] == "12 Demo Street, Nasr City, Cairo"
    assert profile["national_id_masked"] == "**********1234"
    assert profile["identity_status"] == "DEMO_VERIFIED"


def test_login_response_has_no_auth_internals(
    client: TestClient, seeded_citizen: CitizenProfile
) -> None:
    body = _login(client).json()
    blob = str(body)
    for leaked in ("pin_hash", "pin_salt", "token_hash", "national_id_last4"):
        assert leaked not in blob
    assert "1234" not in body["profile"]["national_id_masked"].replace(
        "**********1234", ""
    )


def test_login_wrong_pin_is_401_generic(
    client: TestClient, seeded_citizen: CitizenProfile
) -> None:
    res = _login(client, pin="9999")
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid credentials"


def test_login_unknown_phone_is_401_generic(
    client: TestClient, seeded_citizen: CitizenProfile
) -> None:
    res = _login(client, phone="01555555555")
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid credentials"


def test_login_inactive_account_is_403(
    client: TestClient, db_session: Session
) -> None:
    citizen = seed_demo_citizen(db_session)
    citizen.is_active = False
    db_session.commit()
    res = _login(client)
    assert res.status_code == 403


def test_login_empty_pin_is_422(
    client: TestClient, seeded_citizen: CitizenProfile
) -> None:
    res = client.post(
        "/api/v1/mobile/auth/login", json={"phone": "01000000000", "pin": ""}
    )
    assert res.status_code == 422


def test_login_rejects_extra_fields(
    client: TestClient, seeded_citizen: CitizenProfile
) -> None:
    res = client.post(
        "/api/v1/mobile/auth/login",
        json={"phone": "01000000000", "pin": "1234", "citizen_reference": "x"},
    )
    assert res.status_code == 422


# --- session storage ----------------------------------------------------------


def test_session_token_persisted_hashed_only(
    client: TestClient, db_session: Session, seeded_citizen: CitizenProfile
) -> None:
    raw = _login(client).json()["access_token"]
    sessions = db_session.scalars(select(CitizenSession)).all()
    assert len(sessions) == 1
    stored = sessions[0].token_hash
    assert stored != raw
    assert len(stored) == 64
    assert stored == hash_token(raw)


# --- /mobile/me -------------------------------------------------------------


def test_me_with_bearer_token(
    client: TestClient, seeded_citizen: CitizenProfile
) -> None:
    token = _login(client).json()["access_token"]
    res = client.get(
        "/api/v1/mobile/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["citizen_reference"] == "demo-citizen-001"
    assert body["national_id_masked"] == "**********1234"
    assert body["registered_address"] == "12 Demo Street, Nasr City, Cairo"
    for leaked in ("pin", "pin_hash", "pin_salt", "token", "national_id_last4"):
        assert leaked not in body


def test_me_requires_token(client: TestClient) -> None:
    assert client.get("/api/v1/mobile/me").status_code == 401


def test_me_malformed_authorization_header(
    client: TestClient, seeded_citizen: CitizenProfile
) -> None:
    token = _login(client).json()["access_token"]
    res = client.get(
        "/api/v1/mobile/me", headers={"Authorization": token}
    )
    assert res.status_code == 401


def test_me_blank_bearer_token(client: TestClient) -> None:
    res = client.get(
        "/api/v1/mobile/me", headers={"Authorization": "Bearer "}
    )
    assert res.status_code == 401


def test_me_rejects_expired_session(
    client: TestClient, db_session: Session, seeded_citizen: CitizenProfile
) -> None:
    token = _login(client).json()["access_token"]
    session = db_session.scalars(select(CitizenSession)).first()
    session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    res = client.get(
        "/api/v1/mobile/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 401


def test_me_rejects_when_account_deactivated_after_issue(
    client: TestClient, db_session: Session, seeded_citizen: CitizenProfile
) -> None:
    token = _login(client).json()["access_token"]
    seeded_citizen.is_active = False
    db_session.commit()
    res = client.get(
        "/api/v1/mobile/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 403


# --- logout ---------------------------------------------------------------


def test_logout_revokes_session(
    client: TestClient, db_session: Session, seeded_citizen: CitizenProfile
) -> None:
    token = _login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/v1/mobile/auth/logout", headers=headers)
    assert res.status_code == 204

    session = db_session.scalars(select(CitizenSession)).first()
    db_session.refresh(session)
    assert session.revoked_at is not None

    assert client.get("/api/v1/mobile/me", headers=headers).status_code == 401
    assert (
        client.post("/api/v1/mobile/auth/logout", headers=headers).status_code
        == 401
    )
