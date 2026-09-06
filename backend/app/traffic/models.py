from __future__ import annotations

from datetime import datetime
from enum import Enum
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas import DataReality, FreshnessStatus

EdgeKey = tuple[str, str, str]


class TrafficProviderState(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    MISSING_KEY = "MISSING_KEY"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED = "MALFORMED"
    TIMED_OUT = "TIMED_OUT"


class TrafficMatchStatus(str, Enum):
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"
    AMBIGUOUS = "AMBIGUOUS"


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


class TrafficObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation_id: str
    sample_id: str
    frc: str
    current_speed_kph: float = Field(ge=0)
    free_flow_speed_kph: float = Field(gt=0)
    current_travel_time_s: float = Field(gt=0)
    free_flow_travel_time_s: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    road_closure: bool
    coordinates: tuple[tuple[float, float], ...] = Field(min_length=2)
    openlr: str | None = None
    retrieved_at: datetime
    provider_last_updated: datetime | None = None

    @model_validator(mode="after")
    def validate_timestamps_and_numbers(self) -> TrafficObservation:
        if not _is_aware(self.retrieved_at):
            raise ValueError("retrieved_at must be timezone-aware")
        if self.provider_last_updated is not None:
            if not _is_aware(self.provider_last_updated):
                raise ValueError("provider_last_updated must be timezone-aware")
            if self.provider_last_updated > self.retrieved_at:
                raise ValueError("provider_last_updated cannot be after retrieved_at")
        numeric_values = (
            self.current_speed_kph,
            self.free_flow_speed_kph,
            self.current_travel_time_s,
            self.free_flow_travel_time_s,
            self.confidence,
        )
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("traffic observation numbers must be finite")
        return self


class TrafficEdgeMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation_id: str
    status: TrafficMatchStatus
    reason: str
    edge_keys: tuple[EdgeKey, ...] = ()
    max_geometry_separation_m: float | None = None
    max_direction_difference_degrees: float | None = None
    metric_crs: str | None = None


class TrafficOverlayEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    edge_key: EdgeKey
    observation_id: str
    traffic_factor: float | None = Field(default=None, gt=0)
    road_closure: bool = False


class TrafficOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    graph_fingerprint: str
    entries: tuple[TrafficOverlayEntry, ...] = ()

    def entry_for(self, edge_key: EdgeKey) -> TrafficOverlayEntry | None:
        return next((entry for entry in self.entries if entry.edge_key == edge_key), None)


class TrafficSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    version: int = Field(gt=0)
    graph_fingerprint: str
    provider_state: TrafficProviderState
    refresh_attempted_at: datetime
    retrieved_at: datetime | None = None
    provider_last_updated: datetime | None = None
    freshness_status: FreshnessStatus
    source: str
    source_reference: str
    data_reality: DataReality | None = None
    flow_style: str
    flow_zoom: int
    units: str
    observations: tuple[TrafficObservation, ...] = ()
    matches: tuple[TrafficEdgeMatch, ...] = ()
    overlay: TrafficOverlay | None = None
    failure_reason: str | None = None

    @model_validator(mode="after")
    def validate_snapshot_consistency(self) -> TrafficSnapshot:
        if not _is_aware(self.refresh_attempted_at):
            raise ValueError("refresh_attempted_at must be timezone-aware")
        if self.retrieved_at is not None and not _is_aware(self.retrieved_at):
            raise ValueError("retrieved_at must be timezone-aware")
        if (
            self.retrieved_at is not None
            and self.retrieved_at < self.refresh_attempted_at
        ):
            raise ValueError("retrieved_at cannot be before refresh_attempted_at")
        if self.provider_last_updated is not None:
            if self.retrieved_at is None:
                raise ValueError("provider timestamp requires retrieved_at")
            if not _is_aware(self.provider_last_updated):
                raise ValueError("provider_last_updated must be timezone-aware")
            if self.provider_last_updated > self.retrieved_at:
                raise ValueError("provider_last_updated cannot be after retrieved_at")
        if self.retrieved_at is None and self.data_reality is not None:
            raise ValueError("data_reality requires successfully retrieved data")
        if self.data_reality is not None and self.data_reality is not DataReality.REAL_LIVE:
            raise ValueError("TomTom snapshot data must be labeled REAL_LIVE")
        if self.overlay is not None:
            if self.overlay.snapshot_id != self.snapshot_id:
                raise ValueError("overlay snapshot_id mismatch")
            if self.overlay.graph_fingerprint != self.graph_fingerprint:
                raise ValueError("overlay graph_fingerprint mismatch")
        return self
