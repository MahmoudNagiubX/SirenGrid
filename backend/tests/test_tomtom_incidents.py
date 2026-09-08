from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import httpx
import networkx as nx
import pytest

from app.traffic.incidents import (
    NASR_CITY_BBOX,
    TomTomIncidentDetailsClient,
    TomTomIncidentPayloadError,
    map_incident_to_graph,
    parse_incident_details,
)
from app.traffic.models import TrafficMatchStatus, TrafficProviderState


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
PROVIDER_TIME = datetime(2026, 9, 8, 11, 59, 30, tzinfo=timezone.utc)
SECRET = "test-incident-secret-must-not-escape"


def incident_feature(**property_overrides: Any) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "id": "incident-1",
        "iconCategory": 8,
        "magnitudeOfDelay": 4,
        "events": [
            {
                "description": "Road closed near Tayaran Street",
                "code": 401,
                "iconCategory": 8,
            }
        ],
        "startTime": "2026-09-08T11:30:00Z",
        "endTime": "2026-09-08T13:00:00Z",
        "from": "Tayaran Street",
        "to": "Nasr Road",
        "length": 250,
        "delay": 300,
        "roadNumbers": ["101"],
        "timeValidity": "present",
        "probabilityOfOccurrence": "certain",
        "numberOfReports": 2,
        "lastReportTime": "2026-09-08T11:58:00Z",
        "roadClosed": True,
    }
    properties.update(property_overrides)
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[31.3300, 30.0600], [31.3310, 30.0600]],
        },
        "properties": properties,
    }


def incident_payload(*features: dict[str, Any]) -> dict[str, Any]:
    return {"incidents": list(features)}


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: Any = None,
        *,
        headers: dict[str, str] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = incident_payload() if payload is None else payload
        self.headers = headers or {}
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeHttpClient:
    def __init__(self, outcome: FakeResponse | Exception) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def make_client(
    outcome: FakeResponse | Exception,
    api_key: str | None = SECRET,
) -> tuple[TomTomIncidentDetailsClient, FakeHttpClient]:
    fake_http = FakeHttpClient(outcome)
    return (
        TomTomIncidentDetailsClient(api_key=api_key, http_client=fake_http),
        fake_http,
    )


def test_parse_incident_details_accepts_documented_fields() -> None:
    incidents = parse_incident_details(
        incident_payload(incident_feature()),
    )

    incident = incidents[0]
    assert incident.incident_id == "incident-1"
    assert incident.geometry_type == "LineString"
    assert incident.coordinates == ((31.33, 30.06), (31.331, 30.06))
    assert incident.road_closed is True
    assert incident.icon_category == 8
    assert incident.magnitude_of_delay == 4
    assert incident.description == "Road closed near Tayaran Street"
    assert incident.model_dump()["description"] == "Road closed near Tayaran Street"
    assert incident.start_time == datetime(2026, 9, 8, 11, 30, tzinfo=timezone.utc)
    assert incident.end_time == datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)


def test_parse_incident_details_accepts_point_geometry() -> None:
    feature = incident_feature()
    feature["geometry"] = {"type": "Point", "coordinates": [31.33, 30.06]}

    incident = parse_incident_details(
        incident_payload(feature),
    )[0]

    assert incident.geometry_type == "Point"
    assert incident.coordinates == ((31.33, 30.06),)


def test_road_closed_is_derived_only_from_provider_category_when_field_absent() -> None:
    feature = incident_feature()
    feature["properties"].pop("roadClosed")

    incident = parse_incident_details(
        incident_payload(feature),
    )[0]

    assert incident.icon_category == 8
    assert incident.road_closed is True


def test_empty_incident_payload_is_valid_empty_result() -> None:
    client, fake_http = make_client(FakeResponse(payload={"incidents": []}))

    result = client.fetch(
        bbox=NASR_CITY_BBOX,
        requested_at=NOW,
        wall_clock=lambda: NOW,
        monotonic=lambda: 10.0,
    )

    assert result.state is TrafficProviderState.AVAILABLE
    assert result.incidents == ()
    assert result.data_reality.value == "REAL_LIVE"
    assert result.retrieved_at == NOW
    assert len(fake_http.calls) == 1
    assert fake_http.calls[0]["params"]["bbox"] == ",".join(
        str(value) for value in NASR_CITY_BBOX
    )
    assert fake_http.calls[0]["params"]["fields"] == (
        "{incidents{type,geometry{type,coordinates},properties{"
        "id,iconCategory,magnitudeOfDelay,events{description,code,iconCategory},"
        "startTime,endTime,from,to,length,delay,roadNumbers,timeValidity,"
        "probabilityOfOccurrence,numberOfReports,lastReportTime}}}"
    )
    assert SECRET not in str(result.model_dump())


def test_fetch_preserves_provider_date_and_road_closure() -> None:
    response = FakeResponse(
        payload=incident_payload(incident_feature()),
        headers={"Date": "Tue, 08 Sep 2026 11:59:30 GMT", "TrafficModelID": "model-7"},
    )
    client, _ = make_client(response)

    result = client.fetch(
        bbox=NASR_CITY_BBOX,
        requested_at=NOW,
        wall_clock=lambda: NOW,
        monotonic=lambda: 10.0,
    )

    assert result.state is TrafficProviderState.AVAILABLE
    assert result.provider_timestamp == PROVIDER_TIME
    assert result.traffic_model_id == "model-7"
    assert result.incidents[0].road_closed is True
    assert result.freshness_status.value == "LIVE"


def test_future_provider_date_preserves_timestamp_without_fabricating_freshness() -> None:
    future = datetime(2026, 9, 8, 12, 1, tzinfo=timezone.utc)
    response = FakeResponse(
        payload={"incidents": []},
        headers={"Date": "Tue, 08 Sep 2026 12:01:00 GMT"},
    )
    client, _ = make_client(response)

    result = client.fetch(
        bbox=NASR_CITY_BBOX,
        requested_at=NOW,
        wall_clock=lambda: NOW,
        monotonic=lambda: 10.0,
    )

    assert result.provider_timestamp == future
    assert result.freshness_status.value == "UNKNOWN"
    assert result.data_reality.value == "REAL_LIVE"


def test_missing_optional_times_are_not_fabricated() -> None:
    feature = incident_feature(
        startTime=None,
        endTime=None,
        lastReportTime=None,
        events=[],
        roadClosed=None,
        iconCategory=1,
    )
    incidents = parse_incident_details(
        incident_payload(feature),
    )

    incident = incidents[0]
    assert incident.start_time is None
    assert incident.end_time is None
    assert incident.last_report_time is None
    assert incident.description is None
    assert incident.road_closed is None


def test_malformed_incident_payload_is_typed_and_secret_safe() -> None:
    client, _ = make_client(FakeResponse(payload={"incidents": [{"type": "Feature"}]}))

    result = client.fetch(
        bbox=NASR_CITY_BBOX,
        requested_at=NOW,
        wall_clock=lambda: NOW,
        monotonic=lambda: 10.0,
    )

    assert result.state is TrafficProviderState.MALFORMED
    assert result.failure_reason == "TOMTOM_INCIDENT_DETAILS_MALFORMED_PAYLOAD"
    assert SECRET not in str(result.model_dump())

    with pytest.raises(TomTomIncidentPayloadError):
        parse_incident_details({"incidents": "not-a-list"})


def test_timeout_and_auth_failure_are_typed_without_retry_or_secret_leakage() -> None:
    request = httpx.Request("GET", "https://api.tomtom.com")
    timeout_client, timeout_http = make_client(
        httpx.ReadTimeout("provider secret detail", request=request)
    )
    timeout_result = timeout_client.fetch(
        bbox=NASR_CITY_BBOX,
        requested_at=NOW,
        wall_clock=lambda: NOW,
        monotonic=lambda: 10.0,
    )

    auth_client, auth_http = make_client(FakeResponse(status_code=403))
    auth_result = auth_client.fetch(
        bbox=NASR_CITY_BBOX,
        requested_at=NOW,
        wall_clock=lambda: NOW,
        monotonic=lambda: 10.0,
    )

    assert timeout_result.state is TrafficProviderState.TIMED_OUT
    assert timeout_result.failure_reason == "TOMTOM_INCIDENT_DETAILS_TIMEOUT"
    assert auth_result.state is TrafficProviderState.AUTH_FAILED
    assert auth_result.failure_reason == "TOMTOM_AUTH_FAILED"
    assert len(timeout_http.calls) == 1
    assert len(auth_http.calls) == 1
    assert SECRET not in str(timeout_result.model_dump())
    assert SECRET not in str(auth_result.model_dump())


def test_missing_key_does_not_call_provider() -> None:
    client, fake_http = make_client(FakeResponse(), api_key=None)

    result = client.fetch(
        bbox=NASR_CITY_BBOX,
        requested_at=NOW,
        wall_clock=lambda: NOW,
        monotonic=lambda: 10.0,
    )

    assert result.state is TrafficProviderState.MISSING_KEY
    assert result.incidents == ()
    assert fake_http.calls == []


def chain_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node("a", x=31.3300, y=30.0600)
    graph.add_node("b", x=31.3305, y=30.0600)
    graph.add_node("c", x=31.3310, y=30.0600)
    graph.add_edge(
        "a",
        "b",
        key="0",
        geometry="LINESTRING (31.33 30.06, 31.3305 30.06)",
    )
    graph.add_edge(
        "b",
        "c",
        key="0",
        geometry="LINESTRING (31.3305 30.06, 31.331 30.06)",
    )
    return graph


def all_edges(graph: nx.MultiDiGraph) -> frozenset[tuple[str, str, str]]:
    return frozenset((str(u), str(v), str(key)) for u, v, key in graph.edges(keys=True))


def test_incident_mapping_matches_safe_chain_without_mutating_graph() -> None:
    graph = chain_graph()
    graph_before = deepcopy(nx.node_link_data(graph, edges="edges"))
    incident = parse_incident_details(
        incident_payload(incident_feature()),
    )[0]

    match = map_incident_to_graph(graph, incident, all_edges(graph))

    assert match.status is TrafficMatchStatus.MATCHED
    assert match.edge_keys == (("a", "b", "0"), ("b", "c", "0"))
    assert nx.node_link_data(graph, edges="edges") == graph_before


def test_ambiguous_incident_geometry_fails_closed_without_graph_mutation() -> None:
    graph = chain_graph()
    graph.add_node("d", x=31.3300, y=30.06015)
    graph.add_node("e", x=31.3305, y=30.06015)
    graph.add_node("f", x=31.3310, y=30.06015)
    graph.add_edge(
        "d",
        "e",
        key="0",
        geometry="LINESTRING (31.33 30.06015, 31.3305 30.06015)",
    )
    graph.add_edge(
        "e",
        "f",
        key="0",
        geometry="LINESTRING (31.3305 30.06015, 31.331 30.06015)",
    )
    graph_before = deepcopy(nx.node_link_data(graph, edges="edges"))
    incident = parse_incident_details(
        incident_payload(incident_feature()),
    )[0]

    match = map_incident_to_graph(graph, incident, all_edges(graph))

    assert match.status is TrafficMatchStatus.AMBIGUOUS
    assert match.reason == "MULTIPLE_CANDIDATE_CHAINS"
    assert match.edge_keys == ()
    assert nx.node_link_data(graph, edges="edges") == graph_before
