from __future__ import annotations

from datetime import datetime

from app.config import settings
from app.schemas import FreshnessStatus
from app.traffic.models import TrafficSnapshot


def freshness_origin(snapshot: TrafficSnapshot) -> datetime | None:
    """Return the validated provider timestamp or truthful local retrieval time."""
    return snapshot.provider_last_updated or snapshot.retrieved_at


def evaluate_freshness_origin(
    origin: datetime | None,
    now: datetime,
) -> FreshnessStatus:
    """Evaluate the locked inclusive 60/120-second freshness boundaries."""
    if origin is None:
        return FreshnessStatus.UNKNOWN
    if origin.tzinfo is None or origin.utcoffset() is None:
        raise ValueError("freshness origin must be timezone-aware")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("freshness evaluation time must be timezone-aware")
    if now < origin:
        return FreshnessStatus.UNKNOWN

    age_seconds = (now - origin).total_seconds()
    if age_seconds <= settings.TOMTOM_REFRESH_INTERVAL_SECONDS:
        return FreshnessStatus.LIVE
    if age_seconds <= settings.TOMTOM_FRESH_MAX_AGE_SECONDS:
        return FreshnessStatus.FRESH
    return FreshnessStatus.STALE


def evaluate_freshness(
    snapshot: TrafficSnapshot,
    now: datetime,
) -> FreshnessStatus:
    return evaluate_freshness_origin(freshness_origin(snapshot), now)
