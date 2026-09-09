"""Outbound citizen push transport — the ONLY place Firebase Admin is touched.

SirenGrid backend state is canonical. A push is a best-effort "something
changed, refresh" signal (addendum §14/§19). Every failure here is swallowed by
callers: a push that does not send must never roll back an incident, approval,
routing decision or resource assignment.

Gateway selection:
  * ``FIREBASE_SERVICE_ACCOUNT_PATH`` env set and ``firebase_admin`` importable
    -> :class:`FirebaseAdminPushGateway` (real FCM).
  * otherwise -> :class:`NullPushGateway` (no-op; the default so nothing changes
    for environments / tests without credentials).

Tests inject a recording fake via :func:`set_push_gateway`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger("sirengrid.mobile_push")

__all__ = [
    "PushMessage",
    "PushResult",
    "MobilePushGateway",
    "NullPushGateway",
    "FirebaseAdminPushGateway",
    "RecordingPushGateway",
    "get_push_gateway",
    "set_push_gateway",
    "reset_push_gateway",
]


@dataclass(frozen=True)
class PushMessage:
    """A citizen-safe notification. ``data`` values must all be strings (FCM)."""

    tokens: tuple[str, ...]
    notification_type: str
    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)

    def payload_data(self) -> dict[str, str]:
        merged = {"type": self.notification_type, **self.data}
        return {k: str(v) for k, v in merged.items() if v is not None}


@dataclass(frozen=True)
class PushResult:
    attempted: int
    succeeded: int
    invalid_tokens: tuple[str, ...] = ()


class MobilePushGateway(Protocol):
    @property
    def is_real(self) -> bool: ...

    def send(self, message: PushMessage) -> PushResult: ...


class NullPushGateway:
    """Default. Logs intent, sends nothing."""

    is_real = False

    def send(self, message: PushMessage) -> PushResult:
        logger.info(
            "push suppressed (no Firebase Admin credential): type=%s tokens=%d",
            message.notification_type,
            len(message.tokens),
        )
        return PushResult(attempted=len(message.tokens), succeeded=0)


@dataclass
class RecordingPushGateway:
    """Test double — records messages, reports every token as delivered."""

    is_real = False
    sent: list[PushMessage] = field(default_factory=list)
    fail: bool = False

    def send(self, message: PushMessage) -> PushResult:
        self.sent.append(message)
        if self.fail:
            raise RuntimeError("simulated push provider failure")
        return PushResult(attempted=len(message.tokens), succeeded=len(message.tokens))


class FirebaseAdminPushGateway:
    """Real FCM via the Firebase Admin SDK.

    The service-account JSON is a server secret and is loaded from a path in
    ``FIREBASE_SERVICE_ACCOUNT_PATH`` (or Application Default Credentials). It is
    never committed and never sent to the client.
    """

    is_real = True

    def __init__(self, service_account_path: str | None = None) -> None:
        import firebase_admin  # noqa: PLC0415  (lazy: optional dependency)
        from firebase_admin import credentials

        self._firebase_admin = firebase_admin
        if not firebase_admin._apps:  # noqa: SLF001  (documented Admin API gap)
            cred = (
                credentials.Certificate(service_account_path)
                if service_account_path
                else credentials.ApplicationDefault()
            )
            firebase_admin.initialize_app(cred)

    def send(self, message: PushMessage) -> PushResult:
        from firebase_admin import messaging  # noqa: PLC0415

        if not message.tokens:
            return PushResult(attempted=0, succeeded=0)

        multicast = messaging.MulticastMessage(
            tokens=list(message.tokens),
            notification=messaging.Notification(
                title=message.title, body=message.body
            ),
            data=message.payload_data(),
            android=messaging.AndroidConfig(priority="high"),
        )
        response = messaging.send_each_for_multicast(multicast)
        invalid: list[str] = []
        for token, resp in zip(message.tokens, response.responses, strict=False):
            if resp.success:
                continue
            exc = resp.exception
            code = getattr(exc, "code", "") or ""
            if code in {
                "UNREGISTERED",
                "registration-token-not-registered",
                "INVALID_ARGUMENT",
                "invalid-registration-token",
            }:
                invalid.append(token)
        return PushResult(
            attempted=len(message.tokens),
            succeeded=response.success_count,
            invalid_tokens=tuple(invalid),
        )


def _build_default_gateway() -> MobilePushGateway:
    path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
    use_adc = os.getenv("FIREBASE_USE_APPLICATION_DEFAULT", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if not path and not use_adc:
        return NullPushGateway()
    try:
        return FirebaseAdminPushGateway(service_account_path=path)
    except Exception as exc:  # pragma: no cover - depends on optional dep/creds
        logger.warning(
            "Firebase Admin init failed (%s); citizen push disabled.", exc
        )
        return NullPushGateway()


_gateway: MobilePushGateway | None = None


def get_push_gateway() -> MobilePushGateway:
    global _gateway
    if _gateway is None:
        _gateway = _build_default_gateway()
    return _gateway


def set_push_gateway(gateway: MobilePushGateway) -> None:
    global _gateway
    _gateway = gateway


def reset_push_gateway() -> None:
    global _gateway
    _gateway = None
