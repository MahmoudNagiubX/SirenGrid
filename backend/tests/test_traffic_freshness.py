from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas import DataReality, FreshnessStatus
from app.traffic.freshness import evaluate_freshness, freshness_origin
from app.traffic.models import TrafficProviderState, TrafficSnapshot


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def make_snapshot(
    *,
    retrieved_at: datetime | None,
    provider_last_updated: datetime | None = None,
    refresh_attempted_at: datetime | None = None,
) -> TrafficSnapshot:
    return TrafficSnapshot(
        snapshot_id="traffic-test-1",
        version=1,
        graph_fingerprint="graph-sha256",
        sample_points_fingerprint="sample-sha256",
        provider_state=TrafficProviderState.AVAILABLE,
        refresh_attempted_at=refresh_attempted_at
        or retrieved_at
        or NOW - timedelta(seconds=1),
        retrieved_at=retrieved_at,
        provider_last_updated=provider_last_updated,
        freshness_status=(
            FreshnessStatus.LIVE if retrieved_at else FreshnessStatus.UNKNOWN
        ),
        source="TomTom Traffic Flow Segment Data",
        source_reference="traffic-flow-snapshot:traffic-test-1",
        data_reality=DataReality.REAL_LIVE if retrieved_at else None,
        flow_style="absolute",
        flow_zoom=22,
        units="kmph",
    )


def test_phase02_tomtom_defaults_are_explicit() -> None:
    configured = Settings()

    assert configured.TOMTOM_REFRESH_INTERVAL_SECONDS == 60
    assert configured.TOMTOM_FRESH_MAX_AGE_SECONDS == 120
    assert configured.TOMTOM_REFRESH_TIMEOUT_SECONDS == 10
    assert configured.TOMTOM_FLOW_STYLE == "absolute"
    assert configured.TOMTOM_FLOW_ZOOM == 22
    assert configured.TOMTOM_FLOW_UNITS == "kmph"
    assert configured.TOMTOM_MIN_PROVIDER_CONFIDENCE == 0.80
    assert configured.TOMTOM_MAX_GEOMETRY_SEPARATION_M == 30
    assert configured.TOMTOM_MAX_DIRECTION_DIFFERENCE_DEGREES == 30


@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [
        (0, FreshnessStatus.LIVE),
        (60, FreshnessStatus.LIVE),
        (60.001, FreshnessStatus.FRESH),
        (120, FreshnessStatus.FRESH),
        (120.001, FreshnessStatus.STALE),
    ],
)
def test_freshness_boundaries(
    age_seconds: float,
    expected: FreshnessStatus,
) -> None:
    snapshot = make_snapshot(
        retrieved_at=NOW - timedelta(seconds=age_seconds),
    )

    assert evaluate_freshness(snapshot, NOW) is expected


def test_valid_provider_timestamp_is_the_freshness_origin() -> None:
    snapshot = make_snapshot(
        retrieved_at=NOW - timedelta(seconds=10),
        provider_last_updated=NOW - timedelta(seconds=70),
    )

    assert freshness_origin(snapshot) == NOW - timedelta(seconds=70)
    assert evaluate_freshness(snapshot, NOW) is FreshnessStatus.FRESH


def test_local_retrieval_time_is_used_without_provider_timestamp() -> None:
    snapshot = make_snapshot(retrieved_at=NOW - timedelta(seconds=10))

    assert snapshot.provider_last_updated is None
    assert freshness_origin(snapshot) == snapshot.retrieved_at
    assert evaluate_freshness(snapshot, NOW) is FreshnessStatus.LIVE


def test_future_provider_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_snapshot(
            retrieved_at=NOW - timedelta(seconds=10),
            provider_last_updated=NOW,
        )


def test_retrieval_before_refresh_attempt_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_snapshot(
            refresh_attempted_at=NOW,
            retrieved_at=NOW - timedelta(seconds=1),
        )


def test_failed_attempt_without_retrieval_has_unknown_freshness() -> None:
    snapshot = make_snapshot(retrieved_at=None)

    assert freshness_origin(snapshot) is None
    assert evaluate_freshness(snapshot, NOW) is FreshnessStatus.UNKNOWN


def test_negative_age_is_rejected_instead_of_becoming_live() -> None:
    snapshot = make_snapshot(retrieved_at=NOW + timedelta(seconds=1))

    with pytest.raises(ValueError, match="later than evaluation time"):
        evaluate_freshness(snapshot, NOW)
