"""SirenGrid Citizen (mobile) authentication boundary.

Small, standard-library-only auth for a pre-registered synthetic citizen:

- PIN verification with PBKDF2-HMAC-SHA256 (unique per-user salt,
  ``hmac.compare_digest`` for the derived-hash comparison).
- Opaque bearer session tokens from ``secrets.token_urlsafe``; only the
  SHA-256 hash of a token is persisted. The raw token is shown once at login.
- ``authenticate_citizen`` / ``get_current_citizen`` FastAPI dependencies for
  the mobile router only. These are never applied to institutional routes.

No JWT/OAuth/Firebase/Auth0/Redis or external identity services. Nothing here
logs the PIN, bearer token, National ID, or the full profile.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CitizenProfile, CitizenSession

__all__ = [
    "PIN_PBKDF2_ITERATIONS",
    "SESSION_TTL_HOURS",
    "CitizenAuthContext",
    "authenticate_citizen",
    "generate_pin_salt",
    "get_current_citizen",
    "hash_pin",
    "hash_token",
    "issue_session",
    "mask_national_id",
    "verify_pin",
]

PIN_PBKDF2_ITERATIONS = 120_000
SESSION_TTL_HOURS = 12
_TOKEN_BYTES = 32


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_pin_salt() -> str:
    """Return a fresh random salt as a hex string."""
    return secrets.token_hex(16)


def hash_pin(pin: str, salt: str, *, iterations: int = PIN_PBKDF2_ITERATIONS) -> str:
    """Derive the PBKDF2-HMAC-SHA256 hex digest for a PIN and salt."""
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        bytes.fromhex(salt),
        iterations,
    )
    return derived.hex()


def verify_pin(
    pin: str,
    *,
    salt: str,
    expected_hash: str,
    iterations: int = PIN_PBKDF2_ITERATIONS,
) -> bool:
    """Constant-time check of a candidate PIN against a stored derived hash."""
    candidate = hash_pin(pin, salt, iterations=iterations)
    return hmac.compare_digest(candidate, expected_hash)


def hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest persisted for an opaque bearer token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def mask_national_id(national_id_last4: str) -> str:
    """Return the client-safe masked National ID, e.g. ``**********1234``."""
    return "*" * 10 + (national_id_last4 or "")


def issue_session(db: Session, citizen: CitizenProfile) -> tuple[str, CitizenSession]:
    """Create and persist a session, returning ``(raw_token, session)``.

    The raw token is returned to the caller once; only its hash is stored.
    """
    raw_token = secrets.token_urlsafe(_TOKEN_BYTES)
    now = _utcnow()
    session = CitizenSession(
        citizen_id=citizen.id,
        token_hash=hash_token(raw_token),
        created_at=now,
        expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
        revoked_at=None,
    )
    db.add(session)
    return raw_token, session


@dataclass(frozen=True)
class CitizenAuthContext:
    """Resolved authenticated citizen and the session that authorised it."""

    session: CitizenSession
    profile: CitizenProfile


def _unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticate_citizen(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> CitizenAuthContext:
    """Resolve the current citizen from an ``Authorization: Bearer <token>`` header.

    Rejects a missing/malformed/blank token, an unknown/revoked/expired session,
    and a citizen whose account is no longer active (``403``).
    """
    if not authorization:
        raise _unauthorized()
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise _unauthorized("Malformed Authorization header")
    raw_token = parts[1].strip()
    if not raw_token:
        raise _unauthorized("Empty bearer token")

    session = db.scalars(
        select(CitizenSession).where(
            CitizenSession.token_hash == hash_token(raw_token)
        )
    ).first()
    if session is None or session.revoked_at is not None:
        raise _unauthorized("Invalid or revoked session")

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _utcnow():
        raise _unauthorized("Session expired")

    citizen = db.get(CitizenProfile, session.citizen_id)
    if citizen is None:
        raise _unauthorized("Invalid or revoked session")
    if not citizen.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    return CitizenAuthContext(session=session, profile=citizen)


def get_current_citizen(
    context: Annotated[CitizenAuthContext, Depends(authenticate_citizen)],
) -> CitizenProfile:
    """FastAPI dependency returning only the authenticated ``CitizenProfile``."""
    return context.profile
