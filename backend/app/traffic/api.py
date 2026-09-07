from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.schemas import (
    FreshnessStatus,
    TrafficPrototypePolicyRead,
    TrafficSnapshotRead,
)
from app.traffic.runtime import TRAFFIC_SOURCE, traffic_runtime


router = APIRouter(tags=["traffic"])


def _prototype_policy() -> TrafficPrototypePolicyRead:
    return TrafficPrototypePolicyRead(
        refresh_interval_seconds=settings.TOMTOM_REFRESH_INTERVAL_SECONDS,
        fresh_max_age_seconds=settings.TOMTOM_FRESH_MAX_AGE_SECONDS,
        refresh_timeout_seconds=settings.TOMTOM_REFRESH_TIMEOUT_SECONDS,
        min_provider_confidence=settings.TOMTOM_MIN_PROVIDER_CONFIDENCE,
        max_geometry_separation_m=settings.TOMTOM_MAX_GEOMETRY_SEPARATION_M,
        max_direction_difference_degrees=(
            settings.TOMTOM_MAX_DIRECTION_DIFFERENCE_DEGREES
        ),
    )


@router.get("/traffic/snapshot", response_model=TrafficSnapshotRead)
def get_traffic_snapshot() -> TrafficSnapshotRead:
    """Return sanitized read-only state for the latest captured snapshot."""
    snapshot = traffic_runtime.current_snapshot(now=datetime.now(timezone.utc))
    if snapshot is None:
        return TrafficSnapshotRead(
            snapshot_id=None,
            version=None,
            provider_state=None,
            refresh_attempted_at=None,
            retrieved_at=None,
            provider_last_updated=None,
            freshness_status=FreshnessStatus.UNKNOWN,
            source=TRAFFIC_SOURCE,
            source_reference=None,
            data_reality=None,
            flow_style=settings.TOMTOM_FLOW_STYLE,
            flow_zoom=settings.TOMTOM_FLOW_ZOOM,
            units=settings.TOMTOM_FLOW_UNITS,
            observation_count=0,
            match_count=0,
            matched_edge_count=0,
            failure_reason="TOMTOM_SNAPSHOT_NOT_CAPTURED",
            prototype_policy=_prototype_policy(),
        )
    return TrafficSnapshotRead(
        snapshot_id=snapshot.snapshot_id,
        version=snapshot.version,
        provider_state=snapshot.provider_state.value,
        refresh_attempted_at=snapshot.refresh_attempted_at,
        retrieved_at=snapshot.retrieved_at,
        provider_last_updated=snapshot.provider_last_updated,
        freshness_status=snapshot.freshness_status,
        source=snapshot.source,
        source_reference=snapshot.source_reference,
        data_reality=snapshot.data_reality,
        flow_style=snapshot.flow_style,
        flow_zoom=snapshot.flow_zoom,
        units=snapshot.units,
        observation_count=len(snapshot.observations),
        match_count=len(snapshot.matches),
        matched_edge_count=(
            len(snapshot.overlay.entries) if snapshot.overlay is not None else 0
        ),
        failure_reason=snapshot.failure_reason,
        prototype_policy=_prototype_policy(),
    )

