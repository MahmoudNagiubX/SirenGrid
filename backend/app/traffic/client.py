from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
import math
from queue import Empty, Queue
from threading import Thread
from typing import Any, Protocol
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.traffic.models import TrafficObservation, TrafficProviderState

TOMTOM_FLOW_BASE_URL = (
    "https://api.tomtom.com/traffic/services/4/flowSegmentData"
)


class TomTomPayloadError(ValueError):
    """Raised when provider data cannot become an operational observation."""


class CorridorSamplePoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_id: str = Field(min_length=1)
    corridor_name: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class TomTomRefreshResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: TrafficProviderState
    refresh_attempted_at: datetime
    requested_observation_count: int = Field(ge=0)
    completed_observation_count: int = Field(ge=0)
    malformed_observation_count: int = Field(ge=0)
    observations: tuple[TrafficObservation, ...] = ()
    flow_style: str
    flow_zoom: int
    units: str
    failure_reason: str | None = None


class HttpResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> HttpResponse: ...


class _TotalBudgetExpired(TimeoutError):
    pass


def _request_with_total_budget(
    http_client: HttpClient,
    url: str,
    params: dict[str, str],
    remaining: float,
) -> HttpResponse:
    """Stop awaiting a request at the shared deadline, not per HTTPX phase."""
    outcomes: Queue[HttpResponse | Exception] = Queue(maxsize=1)

    def request() -> None:
        try:
            outcomes.put(
                http_client.get(
                    url,
                    params=params,
                    timeout=remaining,
                )
            )
        except Exception as exc:  # provider/client boundary
            outcomes.put(exc)

    Thread(target=request, daemon=True).start()
    try:
        outcome = outcomes.get(timeout=remaining)
    except Empty as exc:
        raise _TotalBudgetExpired from exc
    if isinstance(outcome, Exception):
        raise outcome
    return outcome


def _number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TomTomPayloadError(f"{field_name} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise TomTomPayloadError(f"{field_name} must be finite")
    return parsed


def parse_flow_segment(
    payload: Any,
    sample: CorridorSamplePoint,
    retrieved_at: datetime,
) -> TrafficObservation:
    """Validate a documented Flow Segment response without filling missing facts."""
    if not isinstance(payload, dict):
        raise TomTomPayloadError("payload must be an object")
    segment = payload.get("flowSegmentData")
    if not isinstance(segment, dict):
        raise TomTomPayloadError("flowSegmentData must be an object")

    frc = segment.get("frc")
    if not isinstance(frc, str) or not frc.strip():
        raise TomTomPayloadError("frc must be a non-empty string")

    current_speed = _number(segment.get("currentSpeed"), "currentSpeed")
    free_flow_speed = _number(segment.get("freeFlowSpeed"), "freeFlowSpeed")
    current_travel_time = _number(
        segment.get("currentTravelTime"), "currentTravelTime"
    )
    free_flow_travel_time = _number(
        segment.get("freeFlowTravelTime"), "freeFlowTravelTime"
    )
    confidence = _number(segment.get("confidence"), "confidence")
    if current_speed < 0:
        raise TomTomPayloadError("currentSpeed must be non-negative")
    if free_flow_speed <= 0:
        raise TomTomPayloadError("freeFlowSpeed must be positive")
    if current_travel_time <= 0:
        raise TomTomPayloadError("currentTravelTime must be positive")
    if free_flow_travel_time <= 0:
        raise TomTomPayloadError("freeFlowTravelTime must be positive")
    if not 0 <= confidence <= 1:
        raise TomTomPayloadError("confidence must be between zero and one")

    road_closure = segment.get("roadClosure")
    if not isinstance(road_closure, bool):
        raise TomTomPayloadError("roadClosure must be boolean")

    coordinates_container = segment.get("coordinates")
    if not isinstance(coordinates_container, dict):
        raise TomTomPayloadError("coordinates must be an object")
    raw_coordinates = coordinates_container.get("coordinate")
    if not isinstance(raw_coordinates, list) or len(raw_coordinates) < 2:
        raise TomTomPayloadError("coordinates must contain at least two points")

    coordinates: list[tuple[float, float]] = []
    for raw_coordinate in raw_coordinates:
        if not isinstance(raw_coordinate, dict):
            raise TomTomPayloadError("coordinate must be an object")
        lat = _number(raw_coordinate.get("latitude"), "coordinate.latitude")
        lon = _number(raw_coordinate.get("longitude"), "coordinate.longitude")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise TomTomPayloadError("coordinate is outside WGS84 bounds")
        coordinates.append((lon, lat))

    openlr = segment.get("openlr")
    if openlr is not None and (not isinstance(openlr, str) or not openlr.strip()):
        raise TomTomPayloadError("openlr must be a non-empty string when present")

    try:
        return TrafficObservation(
            observation_id=f"traffic-observation-{uuid4()}",
            sample_id=sample.sample_id,
            frc=frc,
            current_speed_kph=current_speed,
            free_flow_speed_kph=free_flow_speed,
            current_travel_time_s=current_travel_time,
            free_flow_travel_time_s=free_flow_travel_time,
            confidence=confidence,
            road_closure=road_closure,
            coordinates=tuple(coordinates),
            openlr=openlr,
            retrieved_at=retrieved_at,
            provider_last_updated=None,
        )
    except ValueError as exc:
        raise TomTomPayloadError("flow segment failed schema validation") from exc


class TomTomFlowClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        http_client: HttpClient,
    ) -> None:
        self._api_key = api_key
        self._http_client = http_client

    def _result(
        self,
        *,
        state: TrafficProviderState,
        refresh_attempted_at: datetime,
        requested_count: int,
        observations: list[TrafficObservation],
        malformed_count: int = 0,
        failure_reason: str | None = None,
    ) -> TomTomRefreshResult:
        return TomTomRefreshResult(
            state=state,
            refresh_attempted_at=refresh_attempted_at,
            requested_observation_count=requested_count,
            completed_observation_count=len(observations),
            malformed_observation_count=malformed_count,
            observations=tuple(observations),
            flow_style=settings.TOMTOM_FLOW_STYLE,
            flow_zoom=settings.TOMTOM_FLOW_ZOOM,
            units=settings.TOMTOM_FLOW_UNITS,
            failure_reason=failure_reason,
        )

    def refresh(
        self,
        points: Sequence[CorridorSamplePoint],
        *,
        refresh_attempted_at: datetime,
        wall_clock: Callable[[], datetime],
        monotonic: Callable[[], float],
    ) -> TomTomRefreshResult:
        requested_count = len(points)
        if not self._api_key:
            return self._result(
                state=TrafficProviderState.MISSING_KEY,
                refresh_attempted_at=refresh_attempted_at,
                requested_count=requested_count,
                observations=[],
                failure_reason="TOMTOM_API_KEY_MISSING",
            )

        deadline = monotonic() + settings.TOMTOM_REFRESH_TIMEOUT_SECONDS
        observations: list[TrafficObservation] = []
        malformed_count = 0
        url = (
            f"{TOMTOM_FLOW_BASE_URL}/{settings.TOMTOM_FLOW_STYLE}/"
            f"{settings.TOMTOM_FLOW_ZOOM}/json"
        )

        for sample in points:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return self._result(
                    state=TrafficProviderState.TIMED_OUT,
                    refresh_attempted_at=refresh_attempted_at,
                    requested_count=requested_count,
                    observations=observations,
                    malformed_count=malformed_count,
                    failure_reason="TOMTOM_REFRESH_BUDGET_EXHAUSTED",
                )

            try:
                response = _request_with_total_budget(
                    self._http_client,
                    url,
                    {
                        "key": self._api_key,
                        "point": f"{sample.lat},{sample.lon}",
                        "unit": settings.TOMTOM_FLOW_UNITS,
                        "openLr": "true",
                    },
                    remaining,
                )
            except (httpx.TimeoutException, _TotalBudgetExpired):
                return self._result(
                    state=TrafficProviderState.TIMED_OUT,
                    refresh_attempted_at=refresh_attempted_at,
                    requested_count=requested_count,
                    observations=observations,
                    malformed_count=malformed_count,
                    failure_reason="TOMTOM_REFRESH_TIMEOUT",
                )
            except httpx.RequestError:
                return self._result(
                    state=TrafficProviderState.UNAVAILABLE,
                    refresh_attempted_at=refresh_attempted_at,
                    requested_count=requested_count,
                    observations=observations,
                    malformed_count=malformed_count,
                    failure_reason="TOMTOM_PROVIDER_UNAVAILABLE",
                )
            except Exception:
                return self._result(
                    state=TrafficProviderState.UNAVAILABLE,
                    refresh_attempted_at=refresh_attempted_at,
                    requested_count=requested_count,
                    observations=observations,
                    malformed_count=malformed_count,
                    failure_reason="TOMTOM_PROVIDER_UNAVAILABLE",
                )

            if response.status_code == 429:
                return self._result(
                    state=TrafficProviderState.RATE_LIMITED,
                    refresh_attempted_at=refresh_attempted_at,
                    requested_count=requested_count,
                    observations=observations,
                    malformed_count=malformed_count,
                    failure_reason="TOMTOM_RATE_LIMITED",
                )
            if response.status_code < 200 or response.status_code >= 300:
                return self._result(
                    state=TrafficProviderState.UNAVAILABLE,
                    refresh_attempted_at=refresh_attempted_at,
                    requested_count=requested_count,
                    observations=observations,
                    malformed_count=malformed_count,
                    failure_reason=f"TOMTOM_HTTP_{response.status_code}",
                )

            retrieved_at = wall_clock()
            try:
                payload = response.json()
                observation = parse_flow_segment(payload, sample, retrieved_at)
            except (ValueError, TypeError, TomTomPayloadError):
                malformed_count += 1
                continue
            observations.append(observation)

        if malformed_count:
            return self._result(
                state=(
                    TrafficProviderState.PARTIAL
                    if observations
                    else TrafficProviderState.MALFORMED
                ),
                refresh_attempted_at=refresh_attempted_at,
                requested_count=requested_count,
                observations=observations,
                malformed_count=malformed_count,
                failure_reason=(
                    "TOMTOM_PARTIAL_MALFORMED_PAYLOAD"
                    if observations
                    else "TOMTOM_MALFORMED_PAYLOAD"
                ),
            )
        return self._result(
            state=TrafficProviderState.AVAILABLE,
            refresh_attempted_at=refresh_attempted_at,
            requested_count=requested_count,
            observations=observations,
        )
