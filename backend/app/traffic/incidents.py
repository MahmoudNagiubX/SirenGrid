from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from email.utils import parsedate_to_datetime
import math
from typing import Any

import httpx
import networkx as nx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import settings
from app.schemas import DataReality, FreshnessStatus
from app.traffic.client import (
    HttpClient,
    _TotalBudgetExpired,
    _request_with_total_budget,
)
from app.traffic.freshness import evaluate_freshness_origin
from app.traffic.matching import match_polyline_geometry
from app.traffic.models import EdgeKey, TrafficEdgeMatch, TrafficMatchStatus, TrafficProviderState

TOMTOM_INCIDENT_DETAILS_BASE_URL = (
    "https://api.tomtom.com/traffic/services/5/incidentDetails"
)
TOMTOM_INCIDENT_DETAILS_SOURCE = "TomTom Traffic Incident Details v5"
TOMTOM_INCIDENT_DETAILS_SOURCE_REFERENCE = TOMTOM_INCIDENT_DETAILS_BASE_URL

# Derived from the committed Nasr City boundary artifact; order is the TomTom
# API's required minLon,minLat,maxLon,maxLat EPSG:4326 order.
NASR_CITY_BBOX = (31.3132729, 29.9905089, 31.4345304, 30.0864727)

INCIDENT_DETAILS_FIELDS = (
    "{incidents{type,geometry{type,coordinates},properties{"
    "id,iconCategory,magnitudeOfDelay,events{description,code,iconCategory},"
    "startTime,endTime,from,to,length,delay,roadNumbers,timeValidity,"
    "probabilityOfOccurrence,numberOfReports,lastReportTime}}}"
)


class TomTomIncidentPayloadError(ValueError):
    """Raised when Incident Details data cannot become a trusted record."""


class TomTomIncidentEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str | None = None
    code: int | None = Field(default=None, ge=0)
    icon_category: int | None = Field(default=None, ge=0)


class TomTomIncident(BaseModel):
    model_config = ConfigDict(frozen=True)

    incident_id: str = Field(min_length=1)
    feature_type: str = Field(min_length=1)
    geometry_type: str = Field(min_length=1)
    coordinates: tuple[tuple[float, float], ...] = Field(min_length=1)
    icon_category: int = Field(ge=0)
    magnitude_of_delay: int = Field(ge=0, le=4)
    road_closed: bool | None = None
    events: tuple[TomTomIncidentEvent, ...] = ()
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    from_location: str | None = None
    to_location: str | None = None
    length_m: float | None = Field(default=None, ge=0)
    delay_seconds: int | None = Field(default=None, ge=0)
    road_numbers: tuple[str, ...] = ()
    time_validity: str | None = None
    probability_of_occurrence: str | None = None
    number_of_reports: int | None = Field(default=None, ge=0)
    last_report_time: datetime | None = None

    @model_validator(mode="after")
    def validate_geometry(self) -> TomTomIncident:
        if self.feature_type != "Feature":
            raise ValueError("incident type must be Feature")
        if self.geometry_type not in {"Point", "LineString"}:
            raise ValueError("incident geometry type is unsupported")
        expected_points = 1 if self.geometry_type == "Point" else 2
        if len(self.coordinates) < expected_points:
            raise ValueError("incident geometry has too few coordinates")
        if not all(
            math.isfinite(value)
            and (-180 <= value <= 180 if index == 0 else -90 <= value <= 90)
            for coordinate in self.coordinates
            for index, value in enumerate(coordinate)
        ):
            raise ValueError("incident coordinates are outside WGS84 bounds")
        return self


class TomTomIncidentDetailsResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: TrafficProviderState
    requested_at: datetime
    retrieved_at: datetime | None = None
    provider_timestamp: datetime | None = None
    traffic_model_id: str | None = None
    bbox: tuple[float, float, float, float]
    incidents: tuple[TomTomIncident, ...] = ()
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    source: str = TOMTOM_INCIDENT_DETAILS_SOURCE
    source_reference: str = TOMTOM_INCIDENT_DETAILS_SOURCE_REFERENCE
    data_reality: DataReality | None = None
    failure_reason: str | None = None

    @model_validator(mode="after")
    def validate_timestamps(self) -> TomTomIncidentDetailsResult:
        timestamps = (
            ("requested_at", self.requested_at),
            ("retrieved_at", self.retrieved_at),
            ("provider_timestamp", self.provider_timestamp),
        )
        for name, value in timestamps:
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        if self.data_reality is not None and self.data_reality is not DataReality.REAL_LIVE:
            raise ValueError("TomTom incident data must be labeled REAL_LIVE")
        if self.data_reality is not None and self.retrieved_at is None:
            raise ValueError("data_reality requires successfully retrieved data")
        return self


def _number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TomTomIncidentPayloadError(f"{field_name} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise TomTomIncidentPayloadError(f"{field_name} must be finite")
    return parsed


def _optional_text(properties: Mapping[str, Any], field_name: str) -> str | None:
    value = properties.get(field_name)
    if value is not None and not isinstance(value, str):
        raise TomTomIncidentPayloadError(f"{field_name} must be a string")
    return value


def _optional_datetime(properties: Mapping[str, Any], field_name: str) -> datetime | None:
    value = properties.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TomTomIncidentPayloadError(f"{field_name} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TomTomIncidentPayloadError(f"{field_name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TomTomIncidentPayloadError(f"{field_name} must include a timezone")
    return parsed


def _optional_integer(properties: Mapping[str, Any], field_name: str) -> int | None:
    value = properties.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TomTomIncidentPayloadError(f"{field_name} must be a non-negative integer")
    return value


def _parse_coordinate(raw_coordinate: Any) -> tuple[float, float]:
    if (
        not isinstance(raw_coordinate, list)
        or len(raw_coordinate) != 2
    ):
        raise TomTomIncidentPayloadError(
            "geometry coordinate must be [longitude, latitude]"
        )
    lon = _number(raw_coordinate[0], "geometry.coordinates.longitude")
    lat = _number(raw_coordinate[1], "geometry.coordinates.latitude")
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise TomTomIncidentPayloadError("geometry coordinate is outside WGS84 bounds")
    return lon, lat


def _parse_coordinates(
    geometry: Mapping[str, Any],
    geometry_type: str,
) -> tuple[tuple[float, float], ...]:
    raw_coordinates = geometry.get("coordinates")
    if geometry_type == "Point":
        return (_parse_coordinate(raw_coordinates),)
    if not isinstance(raw_coordinates, list):
        raise TomTomIncidentPayloadError("geometry.coordinates must be a list")
    coordinates: list[tuple[float, float]] = []
    for raw_coordinate in raw_coordinates:
        coordinates.append(_parse_coordinate(raw_coordinate))
    return tuple(coordinates)


def _parse_events(properties: Mapping[str, Any]) -> tuple[TomTomIncidentEvent, ...]:
    raw_events = properties.get("events", [])
    if raw_events is None:
        return ()
    if not isinstance(raw_events, list):
        raise TomTomIncidentPayloadError("events must be a list")
    events: list[TomTomIncidentEvent] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            raise TomTomIncidentPayloadError("incident event must be an object")
        description = raw_event.get("description")
        code = raw_event.get("code")
        icon_category = raw_event.get("iconCategory")
        if not isinstance(description, str) or not description.strip():
            raise TomTomIncidentPayloadError("event description must be a non-empty string")
        if isinstance(code, bool) or not isinstance(code, int) or code < 0:
            raise TomTomIncidentPayloadError("event code must be a non-negative integer")
        if (
            isinstance(icon_category, bool)
            or not isinstance(icon_category, int)
            or icon_category < 0
        ):
            raise TomTomIncidentPayloadError("event iconCategory must be a non-negative integer")
        events.append(
            TomTomIncidentEvent(
                description=description,
                code=code,
                icon_category=icon_category,
            )
        )
    return tuple(events)


def _parse_road_numbers(properties: Mapping[str, Any]) -> tuple[str, ...]:
    raw_numbers = properties.get("roadNumbers", [])
    if raw_numbers is None:
        return ()
    if not isinstance(raw_numbers, list) or not all(
        isinstance(value, str) for value in raw_numbers
    ):
        raise TomTomIncidentPayloadError("roadNumbers must be a list of strings")
    return tuple(raw_numbers)


def parse_incident_details(
    payload: Any,
) -> tuple[TomTomIncident, ...]:
    """Strictly validate the documented Incident Details feature collection."""
    if not isinstance(payload, dict):
        raise TomTomIncidentPayloadError("payload must be an object")
    raw_incidents = payload.get("incidents")
    if not isinstance(raw_incidents, list):
        raise TomTomIncidentPayloadError("incidents must be a list")

    parsed_incidents: list[TomTomIncident] = []
    for raw_incident in raw_incidents:
        if not isinstance(raw_incident, dict):
            raise TomTomIncidentPayloadError("incident must be an object")
        if raw_incident.get("type") != "Feature":
            raise TomTomIncidentPayloadError("incident type must be Feature")
        geometry = raw_incident.get("geometry")
        properties = raw_incident.get("properties")
        if not isinstance(geometry, dict) or not isinstance(properties, dict):
            raise TomTomIncidentPayloadError("incident geometry and properties are required")

        incident_id = properties.get("id")
        geometry_type = geometry.get("type")
        icon_category = properties.get("iconCategory")
        magnitude_of_delay = properties.get("magnitudeOfDelay")
        if not isinstance(incident_id, str) or not incident_id.strip():
            raise TomTomIncidentPayloadError("properties.id must be a non-empty string")
        if (
            isinstance(icon_category, bool)
            or not isinstance(icon_category, int)
            or icon_category < 0
        ):
            raise TomTomIncidentPayloadError("iconCategory must be a non-negative integer")
        if (
            isinstance(magnitude_of_delay, bool)
            or not isinstance(magnitude_of_delay, int)
            or not 0 <= magnitude_of_delay <= 4
        ):
            raise TomTomIncidentPayloadError("magnitudeOfDelay must be between zero and four")
        if geometry_type not in {"Point", "LineString"}:
            raise TomTomIncidentPayloadError("geometry.type is unsupported")

        road_closed = properties.get("roadClosed")
        if road_closed is not None and not isinstance(road_closed, bool):
            raise TomTomIncidentPayloadError("roadClosed must be boolean when present")
        if road_closed is None and icon_category == 8:
            road_closed = True

        coordinates = _parse_coordinates(geometry, geometry_type)
        events = _parse_events(properties)
        description = next(
            (
                event.description
                for event in events
                if event.description is not None
            ),
            None,
        )
        length = properties.get("length")
        length_m = None if length is None else _number(length, "length")
        delay_seconds = _optional_integer(properties, "delay")
        number_of_reports = _optional_integer(properties, "numberOfReports")
        try:
            parsed_incidents.append(
                TomTomIncident(
                    incident_id=incident_id,
                    feature_type="Feature",
                    geometry_type=geometry_type,
                    coordinates=coordinates,
                    icon_category=icon_category,
                    magnitude_of_delay=magnitude_of_delay,
                    road_closed=road_closed,
                    events=events,
                    description=description,
                    start_time=_optional_datetime(properties, "startTime"),
                    end_time=_optional_datetime(properties, "endTime"),
                    from_location=_optional_text(properties, "from"),
                    to_location=_optional_text(properties, "to"),
                    length_m=length_m,
                    delay_seconds=delay_seconds,
                    road_numbers=_parse_road_numbers(properties),
                    time_validity=_optional_text(properties, "timeValidity"),
                    probability_of_occurrence=_optional_text(
                        properties, "probabilityOfOccurrence"
                    ),
                    number_of_reports=number_of_reports,
                    last_report_time=_optional_datetime(properties, "lastReportTime"),
                )
            )
        except ValueError as exc:
            if isinstance(exc, TomTomIncidentPayloadError):
                raise
            raise TomTomIncidentPayloadError("incident failed schema validation") from exc
    return tuple(parsed_incidents)


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.casefold()
    return next(
        (value for key, value in headers.items() if str(key).casefold() == wanted),
        None,
    )


def _provider_timestamp(headers: Mapping[str, str]) -> datetime | None:
    value = _header(headers, "Date")
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


class TomTomIncidentDetailsClient:
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
        requested_at: datetime,
        bbox: tuple[float, float, float, float],
        retrieved_at: datetime | None = None,
        provider_timestamp: datetime | None = None,
        traffic_model_id: str | None = None,
        incidents: tuple[TomTomIncident, ...] = (),
        freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN,
        data_reality: DataReality | None = None,
        failure_reason: str | None = None,
    ) -> TomTomIncidentDetailsResult:
        return TomTomIncidentDetailsResult(
            state=state,
            requested_at=requested_at,
            retrieved_at=retrieved_at,
            provider_timestamp=provider_timestamp,
            traffic_model_id=traffic_model_id,
            bbox=bbox,
            incidents=incidents,
            freshness_status=freshness_status,
            data_reality=data_reality,
            failure_reason=failure_reason,
        )

    def fetch(
        self,
        *,
        bbox: tuple[float, float, float, float] = NASR_CITY_BBOX,
        requested_at: datetime,
        wall_clock: Callable[[], datetime],
        monotonic: Callable[[], float],
    ) -> TomTomIncidentDetailsResult:
        if not self._api_key:
            return self._result(
                state=TrafficProviderState.MISSING_KEY,
                requested_at=requested_at,
                bbox=bbox,
                failure_reason="TOMTOM_API_KEY_MISSING",
            )

        remaining = settings.TOMTOM_REFRESH_TIMEOUT_SECONDS
        try:
            deadline = monotonic() + remaining
            response = _request_with_total_budget(
                self._http_client,
                TOMTOM_INCIDENT_DETAILS_BASE_URL,
                {
                    "key": self._api_key,
                    "bbox": ",".join(str(value) for value in bbox),
                    "fields": INCIDENT_DETAILS_FIELDS,
                    "language": "en-GB",
                    "timeValidityFilter": "present",
                },
                deadline - monotonic(),
            )
        except (httpx.TimeoutException, _TotalBudgetExpired):
            return self._result(
                state=TrafficProviderState.TIMED_OUT,
                requested_at=requested_at,
                bbox=bbox,
                failure_reason="TOMTOM_INCIDENT_DETAILS_TIMEOUT",
            )
        except httpx.RequestError:
            return self._result(
                state=TrafficProviderState.UNAVAILABLE,
                requested_at=requested_at,
                bbox=bbox,
                failure_reason="TOMTOM_INCIDENT_DETAILS_PROVIDER_UNAVAILABLE",
            )
        except Exception:
            return self._result(
                state=TrafficProviderState.UNAVAILABLE,
                requested_at=requested_at,
                bbox=bbox,
                failure_reason="TOMTOM_INCIDENT_DETAILS_PROVIDER_UNAVAILABLE",
            )

        if response.status_code in {401, 403}:
            return self._result(
                state=TrafficProviderState.AUTH_FAILED,
                requested_at=requested_at,
                bbox=bbox,
                failure_reason="TOMTOM_AUTH_FAILED",
            )
        if response.status_code == 429:
            return self._result(
                state=TrafficProviderState.RATE_LIMITED,
                requested_at=requested_at,
                bbox=bbox,
                failure_reason="TOMTOM_INCIDENT_DETAILS_RATE_LIMITED",
            )
        if response.status_code < 200 or response.status_code >= 300:
            return self._result(
                state=TrafficProviderState.UNAVAILABLE,
                requested_at=requested_at,
                bbox=bbox,
                failure_reason=f"TOMTOM_INCIDENT_DETAILS_HTTP_{response.status_code}",
            )

        retrieved_at = wall_clock()
        headers = getattr(response, "headers", {}) or {}
        provider_timestamp = _provider_timestamp(headers)
        traffic_model_id = _header(headers, "TrafficModelID")
        try:
            incidents = parse_incident_details(
                response.json(),
            )
        except (TomTomIncidentPayloadError, TypeError, ValueError):
            return self._result(
                state=TrafficProviderState.MALFORMED,
                requested_at=requested_at,
                bbox=bbox,
                retrieved_at=retrieved_at,
                provider_timestamp=provider_timestamp,
                traffic_model_id=traffic_model_id,
                failure_reason="TOMTOM_INCIDENT_DETAILS_MALFORMED_PAYLOAD",
            )

        freshness_origin = provider_timestamp or retrieved_at
        try:
            freshness_status = evaluate_freshness_origin(
                freshness_origin,
                retrieved_at,
            )
        except ValueError:
            # Preserve a provider clock that is ahead of the local clock;
            # claiming an age would be less truthful than UNKNOWN.
            freshness_status = FreshnessStatus.UNKNOWN
        return self._result(
            state=TrafficProviderState.AVAILABLE,
            requested_at=requested_at,
            bbox=bbox,
            retrieved_at=retrieved_at,
            provider_timestamp=provider_timestamp,
            traffic_model_id=traffic_model_id,
            incidents=incidents,
            freshness_status=freshness_status,
            data_reality=DataReality.REAL_LIVE,
        )


def graph_edge_keys(graph: nx.Graph) -> frozenset[EdgeKey]:
    if graph.is_multigraph():
        return frozenset(
            (str(u), str(v), str(key)) for u, v, key in graph.edges(keys=True)
        )
    return frozenset((str(u), str(v), "0") for u, v in graph.edges())


def map_incident_to_graph(
    graph: nx.Graph,
    incident: TomTomIncident,
    allowed_edges: frozenset[EdgeKey],
) -> TrafficEdgeMatch:
    """Map incident geometry to existing edges without mutating graph closures."""
    if incident.geometry_type != "LineString":
        return TrafficEdgeMatch(
            observation_id=incident.incident_id,
            status=TrafficMatchStatus.UNMATCHED,
            reason="POINT_GEOMETRY_NOT_MAPPABLE",
        )
    return match_polyline_geometry(
        graph,
        incident.coordinates,
        subject_id=incident.incident_id,
        allowed_edges=allowed_edges,
    )


def map_incidents_to_graph(
    graph: nx.Graph,
    incidents: tuple[TomTomIncident, ...],
    allowed_edges: frozenset[EdgeKey],
) -> tuple[TrafficEdgeMatch, ...]:
    return tuple(
        map_incident_to_graph(graph, incident, allowed_edges)
        for incident in incidents
    )
