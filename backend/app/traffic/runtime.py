from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import uuid4

import httpx
import networkx as nx

from app.config import settings
from app.schemas import DataReality, FreshnessStatus
from app.traffic.client import (
    CorridorSamplePoint,
    TomTomFlowClient,
    TomTomRefreshResult,
)
from app.traffic.freshness import evaluate_freshness, freshness_origin
from app.traffic.matching import (
    build_overlay,
    graph_fingerprint,
    select_corridor_edges,
)
from app.traffic.models import TrafficProviderState, TrafficSnapshot

TRAFFIC_SAMPLE_POINTS_FILENAME = "nasr_city_traffic_sample_points.geojson"
TRAFFIC_SOURCE = "TomTom Traffic Flow Segment Data"
TRAFFIC_FUTURE_TIMESTAMP_REASON = "TOMTOM_SNAPSHOT_TIMESTAMP_IN_FUTURE"


class TrafficClient(Protocol):
    def refresh(
        self,
        points: tuple[CorridorSamplePoint, ...],
        *,
        refresh_attempted_at: datetime,
        wall_clock: Callable[[], datetime],
        monotonic: Callable[[], float],
    ) -> TomTomRefreshResult: ...


def load_corridor_sample_points(
    path: Path | None = None,
) -> tuple[CorridorSamplePoint, ...]:
    target = path or settings.NASR_CITY_DATA_DIR / TRAFFIC_SAMPLE_POINTS_FILENAME
    with target.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("traffic sample points must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("traffic sample points must contain features")

    points: list[CorridorSamplePoint] = []
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError("traffic sample feature must be an object")
        geometry = feature.get("geometry")
        properties = feature.get("properties")
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            raise ValueError("traffic sample geometry must be Point")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            raise ValueError("traffic sample Point must contain longitude and latitude")
        if not isinstance(properties, dict):
            raise ValueError("traffic sample properties must be an object")
        points.append(
            CorridorSamplePoint(
                sample_id=properties.get("sample_id"),
                corridor_name=properties.get("corridor_name"),
                osm_name=properties.get("osm_name"),
                lon=coordinates[0],
                lat=coordinates[1],
            )
        )
    return tuple(points)


def _sample_points_fingerprint(points: tuple[CorridorSamplePoint, ...]) -> str:
    serialized = json.dumps(
        [point.model_dump(mode="json") for point in points],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


class TrafficRuntime:
    def __init__(
        self,
        *,
        client: TrafficClient,
        sample_points_loader: Callable[[], tuple[CorridorSamplePoint, ...]],
    ) -> None:
        self._client = client
        self._sample_points_loader = sample_points_loader
        self._lock = Lock()
        self._snapshot: TrafficSnapshot | None = None
        self._version = 0

    def _with_current_freshness(
        self,
        snapshot: TrafficSnapshot,
        now: datetime,
    ) -> TrafficSnapshot:
        current = evaluate_freshness(snapshot, now)
        origin = freshness_origin(snapshot)
        timestamp_in_future = snapshot.refresh_attempted_at > now or (
            origin is not None and origin > now
        )
        updates = {}
        if current is not snapshot.freshness_status:
            updates["freshness_status"] = current
        if timestamp_in_future and snapshot.failure_reason is None:
            updates["failure_reason"] = TRAFFIC_FUTURE_TIMESTAMP_REASON
        elif (
            not timestamp_in_future
            and snapshot.failure_reason == TRAFFIC_FUTURE_TIMESTAMP_REASON
        ):
            updates["failure_reason"] = None
        if not updates:
            return snapshot
        return snapshot.model_copy(update=updates)

    def _publish_failure(
        self,
        *,
        graph_hash: str,
        attempted_at: datetime,
        reason: str,
    ) -> TrafficSnapshot:
        self._version += 1
        snapshot_id = f"traffic-snapshot-{uuid4()}"
        self._snapshot = TrafficSnapshot(
            snapshot_id=snapshot_id,
            version=self._version,
            graph_fingerprint=graph_hash,
            sample_points_fingerprint=hashlib.sha256(b"").hexdigest(),
            provider_state=TrafficProviderState.UNAVAILABLE,
            refresh_attempted_at=attempted_at,
            freshness_status=FreshnessStatus.UNKNOWN,
            source=TRAFFIC_SOURCE,
            source_reference=f"traffic-flow-snapshot:{snapshot_id}",
            flow_style=settings.TOMTOM_FLOW_STYLE,
            flow_zoom=settings.TOMTOM_FLOW_ZOOM,
            units=settings.TOMTOM_FLOW_UNITS,
            failure_reason=reason,
        )
        return self._snapshot

    def capture_snapshot(
        self,
        graph: nx.Graph,
        *,
        now: datetime,
        wall_clock: Callable[[], datetime],
        monotonic: Callable[[], float],
    ) -> TrafficSnapshot:
        graph_hash = graph_fingerprint(graph)
        with self._lock:
            if self._snapshot is not None and self._snapshot.graph_fingerprint == graph_hash:
                age = (now - self._snapshot.refresh_attempted_at).total_seconds()
                if age < settings.TOMTOM_REFRESH_INTERVAL_SECONDS:
                    current = self._with_current_freshness(self._snapshot, now)
                    if current is not self._snapshot:
                        self._snapshot = current
                    return self._snapshot

            try:
                points = self._sample_points_loader()
                if not points:
                    raise ValueError("traffic sample point set is empty")
            except (OSError, TypeError, ValueError):
                return self._publish_failure(
                    graph_hash=graph_hash,
                    attempted_at=now,
                    reason="TRAFFIC_SAMPLE_POINTS_UNAVAILABLE",
                )

            points_hash = _sample_points_fingerprint(points)
            result = self._client.refresh(
                points,
                refresh_attempted_at=now,
                wall_clock=wall_clock,
                monotonic=monotonic,
            )
            self._version += 1
            snapshot_id = f"traffic-snapshot-{uuid4()}"
            observations = result.observations
            retrieved_at = (
                min(item.retrieved_at for item in observations)
                if observations
                else None
            )
            provider_times = [
                item.provider_last_updated
                for item in observations
                if item.provider_last_updated is not None
            ]
            provider_last_updated = (
                min(provider_times)
                if observations and len(provider_times) == len(observations)
                else None
            )

            configuration_matches = (
                result.flow_style == settings.TOMTOM_FLOW_STYLE
                and result.flow_zoom == settings.TOMTOM_FLOW_ZOOM
                and result.units == settings.TOMTOM_FLOW_UNITS
            )
            matches = ()
            overlay = None
            failure_reason = result.failure_reason
            provider_state = result.state
            if observations and configuration_matches:
                corridor_names = tuple(
                    point.osm_name or point.corridor_name for point in points
                )
                allowed_edges = select_corridor_edges(graph, corridor_names)
                matches, overlay = build_overlay(
                    graph,
                    snapshot_id=snapshot_id,
                    observations=observations,
                    allowed_edges=allowed_edges,
                )
            elif observations:
                provider_state = TrafficProviderState.MALFORMED
                failure_reason = "TOMTOM_SNAPSHOT_CONFIGURATION_MISMATCH"

            snapshot = TrafficSnapshot(
                snapshot_id=snapshot_id,
                version=self._version,
                graph_fingerprint=graph_hash,
                sample_points_fingerprint=points_hash,
                provider_state=provider_state,
                refresh_attempted_at=now,
                retrieved_at=retrieved_at,
                provider_last_updated=provider_last_updated,
                freshness_status=(
                    FreshnessStatus.LIVE
                    if retrieved_at is not None
                    else FreshnessStatus.UNKNOWN
                ),
                source=TRAFFIC_SOURCE,
                source_reference=f"traffic-flow-snapshot:{snapshot_id}",
                data_reality=(
                    DataReality.REAL_LIVE if retrieved_at is not None else None
                ),
                flow_style=result.flow_style,
                flow_zoom=result.flow_zoom,
                units=result.units,
                observations=observations,
                matches=matches,
                overlay=overlay,
                failure_reason=failure_reason,
            )
            self._snapshot = self._with_current_freshness(snapshot, now)
            return self._snapshot

    def current_snapshot(self, *, now: datetime) -> TrafficSnapshot | None:
        with self._lock:
            if self._snapshot is None:
                return None
            current = self._with_current_freshness(self._snapshot, now)
            if current is not self._snapshot:
                self._snapshot = current
            return self._snapshot


_http_client = httpx.Client()
traffic_runtime = TrafficRuntime(
    client=TomTomFlowClient(
        api_key=settings.TOMTOM_API_KEY,
        http_client=_http_client,
    ),
    sample_points_loader=load_corridor_sample_points,
)
