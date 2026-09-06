from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Event
import time
from typing import Any

import httpx
import pytest

from app.traffic.client import (
    CorridorSamplePoint,
    TomTomFlowClient,
    TomTomPayloadError,
    parse_flow_segment,
)
from app.config import settings
from app.traffic.models import TrafficProviderState


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
SECRET = "test-secret-must-not-escape"


def flow_payload(**overrides: Any) -> dict[str, Any]:
    segment: dict[str, Any] = {
        "frc": "FRC2",
        "currentSpeed": 41,
        "freeFlowSpeed": 70,
        "currentTravelTime": 153,
        "freeFlowTravelTime": 90,
        "confidence": 0.80,
        "roadClosure": False,
        "coordinates": {
            "coordinate": [
                {"latitude": 30.07, "longitude": 31.33},
                {"latitude": 30.06, "longitude": 31.34},
            ]
        },
        "openlr": "audit-only",
    }
    segment.update(overrides)
    return {"flowSegmentData": segment}


SAMPLES = (
    CorridorSamplePoint(sample_id="rabaa", corridor_name="Rabaa", lat=30.07, lon=31.33),
    CorridorSamplePoint(sample_id="tayaran", corridor_name="Tayaran", lat=30.06, lon=31.34),
    CorridorSamplePoint(sample_id="abbas", corridor_name="Abbas El Akkad", lat=30.05, lon=31.35),
)


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: dict[str, Any] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload or flow_payload()
        self._json_error = json_error

    def json(self) -> dict[str, Any]:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeHttpClient:
    def __init__(self, outcomes: list[FakeResponse | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        outcome = self.outcomes[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class SequenceClock:
    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class BlockingHttpClient:
    def __init__(self) -> None:
        self.release = Event()
        self.request_count = 0

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.request_count += 1
        self.release.wait(timeout=1)
        return FakeResponse()


def utc_clock_factory() -> Callable[[], datetime]:
    calls = iter(NOW + timedelta(milliseconds=i) for i in range(20))
    return lambda: next(calls)


def make_client(fake_http: FakeHttpClient, api_key: str | None = SECRET) -> TomTomFlowClient:
    return TomTomFlowClient(api_key=api_key, http_client=fake_http)


def test_parse_flow_segment_accepts_documented_payload() -> None:
    observation = parse_flow_segment(
        payload=flow_payload(),
        sample=SAMPLES[0],
        retrieved_at=NOW,
    )

    assert observation.confidence == 0.80
    assert observation.coordinates[0] == (31.33, 30.07)
    assert observation.openlr == "audit-only"
    assert observation.provider_last_updated is None


def test_parse_flow_segment_accepts_zero_speed_for_reported_closure() -> None:
    observation = parse_flow_segment(
        payload=flow_payload(currentSpeed=0, roadClosure=True),
        sample=SAMPLES[0],
        retrieved_at=NOW,
    )

    assert observation.current_speed_kph == 0
    assert observation.road_closure is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("currentSpeed", -1),
        ("freeFlowSpeed", 0),
        ("currentTravelTime", 0),
        ("freeFlowTravelTime", -1),
        ("confidence", 1.1),
        ("coordinates", {"coordinate": []}),
    ],
)
def test_parse_flow_segment_rejects_invalid_operational_values(
    field: str,
    value: Any,
) -> None:
    with pytest.raises(TomTomPayloadError):
        parse_flow_segment(
            payload=flow_payload(**{field: value}),
            sample=SAMPLES[0],
            retrieved_at=NOW,
        )


def test_refresh_uses_fixed_configuration_and_one_total_deadline() -> None:
    fake_http = FakeHttpClient([FakeResponse(), FakeResponse(), FakeResponse()])
    monotonic = SequenceClock([100.0, 101.0, 106.0, 110.0])

    result = make_client(fake_http).refresh(
        SAMPLES,
        refresh_attempted_at=NOW,
        wall_clock=utc_clock_factory(),
        monotonic=monotonic,
    )

    assert len(fake_http.calls) == 2
    assert fake_http.calls[0]["url"].endswith("/absolute/22/json")
    assert fake_http.calls[0]["params"]["unit"] == "kmph"
    assert fake_http.calls[0]["params"]["openLr"] == "true"
    assert fake_http.calls[0]["timeout"] == pytest.approx(9.0)
    assert fake_http.calls[1]["timeout"] == pytest.approx(4.0)
    assert result.state is TrafficProviderState.TIMED_OUT
    assert result.completed_observation_count == 2
    assert len(result.observations) == 2
    assert result.requested_observation_count == 3


def test_timeout_stops_without_retry_and_sanitizes_failure() -> None:
    request = httpx.Request("GET", "https://api.tomtom.com")
    fake_http = FakeHttpClient([httpx.ReadTimeout("contains provider detail", request=request)])

    result = make_client(fake_http).refresh(
        SAMPLES,
        refresh_attempted_at=NOW,
        wall_clock=utc_clock_factory(),
        monotonic=SequenceClock([10.0, 10.1]),
    )

    assert len(fake_http.calls) == 1
    assert result.state is TrafficProviderState.TIMED_OUT
    assert result.observations == ()
    assert result.failure_reason == "TOMTOM_REFRESH_TIMEOUT"
    assert SECRET not in result.failure_reason


def test_total_budget_stops_awaiting_a_blocked_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_http = BlockingHttpClient()
    monkeypatch.setattr(settings, "tomtom_refresh_timeout_seconds", 0.01)
    started = time.monotonic()

    result = make_client(fake_http).refresh(
        SAMPLES,
        refresh_attempted_at=NOW,
        wall_clock=utc_clock_factory(),
        monotonic=time.monotonic,
    )

    elapsed = time.monotonic() - started
    assert elapsed < 0.2
    assert fake_http.request_count == 1
    assert result.state is TrafficProviderState.TIMED_OUT
    assert result.failure_reason == "TOMTOM_REFRESH_TIMEOUT"


def test_rate_limit_stops_without_retry_or_secret_leakage() -> None:
    fake_http = FakeHttpClient([FakeResponse(status_code=429)])

    result = make_client(fake_http).refresh(
        SAMPLES,
        refresh_attempted_at=NOW,
        wall_clock=utc_clock_factory(),
        monotonic=SequenceClock([10.0, 10.1]),
    )

    assert len(fake_http.calls) == 1
    assert result.state is TrafficProviderState.RATE_LIMITED
    assert result.failure_reason == "TOMTOM_RATE_LIMITED"
    assert SECRET not in str(result.model_dump())


def test_missing_key_does_not_issue_a_request() -> None:
    fake_http = FakeHttpClient([])

    result = make_client(fake_http, api_key=None).refresh(
        SAMPLES,
        refresh_attempted_at=NOW,
        wall_clock=utc_clock_factory(),
        monotonic=SequenceClock([10.0]),
    )

    assert fake_http.calls == []
    assert result.state is TrafficProviderState.MISSING_KEY
    assert result.failure_reason == "TOMTOM_API_KEY_MISSING"


def test_malformed_observation_does_not_fabricate_and_later_valid_result_survives() -> None:
    fake_http = FakeHttpClient(
        [
            FakeResponse(payload=flow_payload(confidence="not-a-number")),
            FakeResponse(),
        ]
    )

    result = make_client(fake_http).refresh(
        SAMPLES[:2],
        refresh_attempted_at=NOW,
        wall_clock=utc_clock_factory(),
        monotonic=SequenceClock([10.0, 10.1, 10.2]),
    )

    assert len(fake_http.calls) == 2
    assert result.state is TrafficProviderState.PARTIAL
    assert result.completed_observation_count == 1
    assert len(result.observations) == 1
    assert result.observations[0].sample_id == "tayaran"
    assert result.failure_reason == "TOMTOM_PARTIAL_MALFORMED_PAYLOAD"
