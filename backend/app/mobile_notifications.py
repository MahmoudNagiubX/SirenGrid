"""Citizen-facing push projection.

Maps a committed operational state change to a citizen-safe push and hands it to
:mod:`app.mobile_push`. Push is transport only — the app always refetches the
canonical REST state (addendum §14/§19).

Design rules enforced here:
  * Every call site wraps this in a try/except: a push failure never affects the
    operational transaction (addendum §14).
  * Payloads carry a ``type`` + identifiers + short generic copy — no patient
    data, no incident internals, no planner detail (addendum §13/§19).
  * Dedupe per (citizen, event key) via ``MobileNotificationLog`` so a repeated
    state read / retry does not spam the same transition (addendum §16).
  * Tokens FCM reports as invalid are deactivated.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mobile_push import PushMessage, get_push_gateway
from app.models import (
    CitizenDeviceToken,
    Incident,
    MobileNotificationLog,
    Report,
)
from app.schemas import IncidentStatus

logger = logging.getLogger("sirengrid.mobile_notifications")

MOBILE_SOURCE_TYPE = "MOBILE_APP"

# Citizen-safe notification copy. Kept tiny and generic on purpose.
_RESPONSE_STATE_NOTIFICATIONS: dict[IncidentStatus, tuple[str, str, str]] = {
    IncidentStatus.RESPONSE_ACTIVE: (
        "RESPONSE_ASSIGNED",
        "Response assigned",
        "Emergency assistance has been assigned to your request.",
    ),
    IncidentStatus.EN_ROUTE: (
        "RESPONDER_EN_ROUTE",
        "Help is on the way",
        "Your assigned responder is en route.",
    ),
    IncidentStatus.ON_SCENE: (
        "RESPONDER_ARRIVED",
        "Your responder has arrived",
        "The responder has reached your location.",
    ),
    IncidentStatus.CLOSED: (
        "REQUEST_COMPLETED",
        "Response complete",
        "This emergency response has been completed.",
    ),
}

CLEAR_THE_WAY = (
    "EMERGENCY_VEHICLE_APPROACHING",
    "Emergency vehicle approaching",
    "Please keep the route clear and move safely aside.",
)


def _active_tokens(db: Session, citizen_reference: str) -> list[CitizenDeviceToken]:
    return list(
        db.scalars(
            select(CitizenDeviceToken).where(
                CitizenDeviceToken.citizen_reference == citizen_reference,
                CitizenDeviceToken.is_active.is_(True),
            )
        )
    )


def _already_sent(db: Session, citizen_reference: str, event_key: str) -> bool:
    return (
        db.scalars(
            select(MobileNotificationLog).where(
                MobileNotificationLog.citizen_reference == citizen_reference,
                MobileNotificationLog.event_key == event_key,
            )
        ).first()
        is not None
    )


def _record_sent(
    db: Session,
    *,
    citizen_reference: str,
    event_key: str,
    notification_type: str,
    request_id: str | None,
) -> None:
    db.add(
        MobileNotificationLog(
            citizen_reference=citizen_reference,
            event_key=event_key,
            notification_type=notification_type,
            request_id=request_id,
        )
    )
    db.commit()


def _deactivate_tokens(db: Session, tokens: tuple[str, ...]) -> None:
    if not tokens:
        return
    rows = db.scalars(
        select(CitizenDeviceToken).where(CitizenDeviceToken.token.in_(tokens))
    ).all()
    for row in rows:
        row.is_active = False
    db.commit()


def _dispatch(
    db: Session,
    *,
    citizen_reference: str,
    event_key: str,
    notification_type: str,
    title: str,
    body: str,
    data: dict[str, str],
    request_id: str | None,
) -> bool:
    """Send one push if not already sent for this (citizen, event). Best effort."""
    if _already_sent(db, citizen_reference, event_key):
        return False
    tokens = _active_tokens(db, citizen_reference)
    if not tokens:
        # Still record so we don't reconsider this transition endlessly.
        _record_sent(
            db,
            citizen_reference=citizen_reference,
            event_key=event_key,
            notification_type=notification_type,
            request_id=request_id,
        )
        return False

    message = PushMessage(
        tokens=tuple(t.token for t in tokens),
        notification_type=notification_type,
        title=title,
        body=body,
        data={k: str(v) for k, v in data.items() if v is not None},
    )
    try:
        result = get_push_gateway().send(message)
        _deactivate_tokens(db, result.invalid_tokens)
    except Exception as exc:  # never propagate to the operational caller
        logger.warning("citizen push failed (%s): %s", notification_type, exc)
    _record_sent(
        db,
        citizen_reference=citizen_reference,
        event_key=event_key,
        notification_type=notification_type,
        request_id=request_id,
    )
    return True


def notify_incident_response_state(db: Session, *, incident_id: str) -> bool:
    """Push the current citizen-safe response state for a mobile-origin incident.

    Safe to call after any approval / status commit. No-op when the incident is
    not mobile-origin, the status has no citizen notification, or it was already
    pushed.
    """
    try:
        incident = db.get(Incident, incident_id)
        if incident is None:
            return False
        mapping = _RESPONSE_STATE_NOTIFICATIONS.get(incident.status)
        if mapping is None:
            return False
        report = db.scalars(
            select(Report).where(
                Report.incident_id == incident_id,
                Report.source_type == MOBILE_SOURCE_TYPE,
            )
        ).first()
        if report is None or not report.source_reference:
            return False

        n_type, title, body = mapping
        return _dispatch(
            db,
            citizen_reference=report.source_reference,
            event_key=f"req:{report.id}:{n_type}",
            notification_type=n_type,
            title=title,
            body=body,
            data={
                "request_id": report.id,
                "incident_id": incident_id,
            },
            request_id=report.id,
        )
    except Exception as exc:  # pragma: no cover - defensive belt
        logger.warning("notify_incident_response_state failed: %s", exc)
        return False


def notify_clear_the_way(
    db: Session,
    *,
    alert_id: str,
    incident_id: str | None = None,
) -> int:
    """Broadcast a clear-the-way push to every registered citizen device.

    Reuses existing DriverAlert / corridor state as the trigger (addendum §13.C
    / §21). Carries no incident or patient identity. Deduped per alert so the
    same alert is not re-sent. Returns how many citizens were dispatched to.

    Demo simplification: SirenGrid does not yet map other citizens' live
    positions onto a corridor, so this broadcasts rather than geo-targets.
    """
    try:
        references = list(
            db.scalars(
                select(CitizenDeviceToken.citizen_reference)
                .where(CitizenDeviceToken.is_active.is_(True))
                .distinct()
            )
        )
        n_type, title, body = CLEAR_THE_WAY
        dispatched = 0
        for ref in references:
            if _dispatch(
                db,
                citizen_reference=ref,
                event_key=f"alert:{alert_id}",
                notification_type=n_type,
                title=title,
                body=body,
                data={"alert_id": alert_id},
                request_id=None,
            ):
                dispatched += 1
        return dispatched
    except Exception as exc:  # pragma: no cover - defensive belt
        logger.warning("notify_clear_the_way failed: %s", exc)
        return 0
