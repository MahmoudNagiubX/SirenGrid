from __future__ import annotations

from datetime import datetime, timezone

import app.models as _models  # noqa: F401
import pytest
from app.db import init_db
from app.mobile_notifications import (
    notify_clear_the_way,
    notify_incident_response_state,
)
from app.mobile_push import (
    NullPushGateway,
    PushMessage,
    RecordingPushGateway,
    reset_push_gateway,
    set_push_gateway,
)
from app.models import (
    CitizenDeviceToken,
    Incident,
    MobileNotificationLog,
    Report,
)
from app.schemas import (
    ConfidenceLevel,
    DataReality,
    IncidentStatus,
    Severity,
)
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture(autouse=True)
def _gateway() -> RecordingPushGateway:
    gw = RecordingPushGateway()
    set_push_gateway(gw)
    yield gw
    reset_push_gateway()


def _mobile_incident(
    db: Session,
    *,
    status: IncidentStatus,
    citizen_reference: str = "demo-citizen-001",
) -> tuple[Incident, Report]:
    now = datetime.now(timezone.utc)
    incident = Incident(
        id="inc-1",
        version=3,
        incident_type="mobile_ambulance_request",
        severity=Severity.MODERATE,
        confidence_level=ConfidenceLevel.LOW,
        status=status,
        latitude=30.05,
        longitude=31.34,
    )
    report = Report(
        id="req-1",
        incident_id="inc-1",
        source_type="MOBILE_APP",
        source_reference=citizen_reference,
        raw_text="x",
        received_at=now,
        data_reality=DataReality.SYNTHETIC,
        processing_status="PROCESSED",
        created_at=now,
    )
    db.add_all([incident, report])
    db.commit()
    return incident, report


def _register_token(db: Session, ref: str, token: str) -> None:
    db.add(
        CitizenDeviceToken(
            token=token,
            citizen_reference=ref,
            platform="ANDROID",
            is_active=True,
        )
    )
    db.commit()


def test_null_gateway_is_the_default_and_sends_nothing() -> None:
    reset_push_gateway()
    from app.mobile_push import get_push_gateway

    assert isinstance(get_push_gateway(), NullPushGateway)
    result = get_push_gateway().send(
        PushMessage(tokens=("a", "b"), notification_type="X", title="t", body="b")
    )
    assert result.succeeded == 0


def test_response_assigned_push_once_with_safe_payload(
    db_session: Session, _gateway: RecordingPushGateway
) -> None:
    _mobile_incident(db_session, status=IncidentStatus.RESPONSE_ACTIVE)
    _register_token(db_session, "demo-citizen-001", "tok-1")

    assert notify_incident_response_state(db_session, incident_id="inc-1") is True
    assert len(_gateway.sent) == 1
    msg = _gateway.sent[0]
    assert msg.notification_type == "RESPONSE_ASSIGNED"
    assert msg.tokens == ("tok-1",)
    data = msg.payload_data()
    assert data["request_id"] == "req-1"
    assert data["incident_id"] == "inc-1"
    # no patient / planner / internal fields
    blob = str(data) + msg.title + msg.body
    for forbidden in ("score", "coverage", "national", "pin", "hospital", "operator"):
        assert forbidden not in blob.lower()

    # Second call for the same transition is deduped.
    assert notify_incident_response_state(db_session, incident_id="inc-1") is False
    assert len(_gateway.sent) == 1


@pytest.mark.parametrize(
    ("status", "ntype"),
    [
        (IncidentStatus.RESPONSE_ACTIVE, "RESPONSE_ASSIGNED"),
        (IncidentStatus.EN_ROUTE, "RESPONDER_EN_ROUTE"),
        (IncidentStatus.ON_SCENE, "RESPONDER_ARRIVED"),
        (IncidentStatus.CLOSED, "REQUEST_COMPLETED"),
    ],
)
def test_status_maps_to_notification_type(
    db_session: Session,
    _gateway: RecordingPushGateway,
    status: IncidentStatus,
    ntype: str,
) -> None:
    _mobile_incident(db_session, status=status)
    _register_token(db_session, "demo-citizen-001", "tok-1")
    assert notify_incident_response_state(db_session, incident_id="inc-1") is True
    assert _gateway.sent[0].notification_type == ntype


def test_no_notification_for_non_mapped_status(
    db_session: Session, _gateway: RecordingPushGateway
) -> None:
    _mobile_incident(db_session, status=IncidentStatus.AWAITING_APPROVAL)
    _register_token(db_session, "demo-citizen-001", "tok-1")
    assert notify_incident_response_state(db_session, incident_id="inc-1") is False
    assert _gateway.sent == []


def test_no_tokens_records_but_does_not_send(
    db_session: Session, _gateway: RecordingPushGateway
) -> None:
    _mobile_incident(db_session, status=IncidentStatus.RESPONSE_ACTIVE)
    assert notify_incident_response_state(db_session, incident_id="inc-1") is False
    assert _gateway.sent == []
    # recorded so we don't reconsider it forever
    assert db_session.scalars(select(MobileNotificationLog)).all() != []


def test_non_mobile_incident_is_ignored(
    db_session: Session, _gateway: RecordingPushGateway
) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        Incident(
            id="inc-op",
            version=1,
            incident_type="traffic_collision",
            severity=Severity.HIGH,
            confidence_level=ConfidenceLevel.HIGH,
            status=IncidentStatus.RESPONSE_ACTIVE,
            latitude=30.0,
            longitude=31.0,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    assert notify_incident_response_state(db_session, incident_id="inc-op") is False
    assert _gateway.sent == []


def test_push_provider_failure_never_propagates(db_session: Session) -> None:
    failing = RecordingPushGateway(fail=True)
    set_push_gateway(failing)
    _mobile_incident(db_session, status=IncidentStatus.RESPONSE_ACTIVE)
    _register_token(db_session, "demo-citizen-001", "tok-1")
    # must not raise
    assert notify_incident_response_state(db_session, incident_id="inc-1") is True
    # still recorded so it is not retried in a loop
    assert db_session.scalars(select(MobileNotificationLog)).all() != []


def test_clear_the_way_broadcasts_and_dedupes(
    db_session: Session, _gateway: RecordingPushGateway
) -> None:
    _register_token(db_session, "demo-citizen-001", "tok-1")
    _register_token(db_session, "demo-citizen-002", "tok-2")

    dispatched = notify_clear_the_way(db_session, alert_id="alert-1")
    assert dispatched == 2
    assert {m.notification_type for m in _gateway.sent} == {
        "EMERGENCY_VEHICLE_APPROACHING"
    }
    for m in _gateway.sent:
        assert "incident_id" not in m.payload_data()
        assert m.payload_data()["alert_id"] == "alert-1"

    # Same alert again -> deduped for both citizens.
    assert notify_clear_the_way(db_session, alert_id="alert-1") == 0
    assert len(_gateway.sent) == 2
