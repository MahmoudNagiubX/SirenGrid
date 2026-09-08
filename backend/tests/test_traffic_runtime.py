from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Lock

import networkx as nx

from app.schemas import DataReality, FreshnessStatus
from app.traffic.client import CorridorSamplePoint, TomTomRefreshResult
from app.traffic.matching import graph_fingerprint
from app.traffic.models import TrafficObservation, TrafficProviderState
from app.traffic.runtime import TrafficRuntime


T0 = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
SAMPLES = (
    CorridorSamplePoint(
        sample_id="tayaran",
        corridor_name="Tayaran",
        osm_name="Tayaran",
        lat=30.06005,
        lon=31.3305,
    ),
)


def make_graph(x_offset: float = 0) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node("a", x=31.3300 + x_offset, y=30.0600)
    graph.add_node("b", x=31.3310 + x_offset, y=30.0600)
    graph.add_edge(
        "a",
        "b",
        key="0",
        name="Tayaran",
        geometry=(
            f"LINESTRING ({31.3300 + x_offset} 30.0600, "
            f"{31.3310 + x_offset} 30.0600)"
        ),
        length=100.0,
        travel_time=10.0,
        oneway=True,
    )
    return graph


def make_observation(retrieved_at: datetime = T0) -> TrafficObservation:
    return TrafficObservation(
        observation_id="obs-1",
        sample_id="tayaran",
        frc="FRC2",
        current_speed_kph=35,
        free_flow_speed_kph=70,
        current_travel_time_s=20,
        free_flow_travel_time_s=10,
        confidence=0.90,
        road_closure=False,
        coordinates=((31.3300, 30.06005), (31.3310, 30.06005)),
        retrieved_at=retrieved_at,
    )


def make_result(
    state: TrafficProviderState,
    *,
    observations: tuple[TrafficObservation, ...] = (),
    failure_reason: str | None = None,
) -> TomTomRefreshResult:
    return TomTomRefreshResult(
        state=state,
        refresh_attempted_at=T0,
        requested_observation_count=1,
        completed_observation_count=len(observations),
        malformed_observation_count=0,
        observations=observations,
        flow_style="absolute",
        flow_zoom=22,
        units="kmph",
        failure_reason=failure_reason,
    )


class FakeTomTomClient:
    def __init__(self, results: list[TomTomRefreshResult]) -> None:
        self._results = results
        self.refresh_count = 0

    def refresh(self, *args, **kwargs) -> TomTomRefreshResult:
        result = self._results[self.refresh_count]
        self.refresh_count += 1
        retrieved_at = kwargs["wall_clock"]()
        return result.model_copy(
            update={
                "refresh_attempted_at": kwargs["refresh_attempted_at"],
                "observations": tuple(
                    observation.model_copy(update={"retrieved_at": retrieved_at})
                    for observation in result.observations
                ),
            }
        )


def make_runtime(client: FakeTomTomClient) -> TrafficRuntime:
    return TrafficRuntime(
        client=client,
        sample_points_loader=lambda: SAMPLES,
    )


def test_failed_refresh_is_not_retried_inside_sixty_seconds() -> None:
    client = FakeTomTomClient(
        [make_result(TrafficProviderState.RATE_LIMITED, failure_reason="TOMTOM_RATE_LIMITED")]
    )
    runtime = make_runtime(client)
    graph = make_graph()

    first = runtime.capture_snapshot(
        graph,
        now=T0,
        wall_clock=lambda: T0,
        monotonic=lambda: 1.0,
    )
    second = runtime.capture_snapshot(
        graph,
        now=T0 + timedelta(seconds=59),
        wall_clock=lambda: T0,
        monotonic=lambda: 2.0,
    )

    assert first.provider_state is TrafficProviderState.RATE_LIMITED
    assert second.snapshot_id == first.snapshot_id
    assert client.refresh_count == 1


def test_refresh_is_allowed_at_sixty_seconds() -> None:
    unavailable = make_result(
        TrafficProviderState.UNAVAILABLE,
        failure_reason="TOMTOM_PROVIDER_UNAVAILABLE",
    )
    client = FakeTomTomClient([unavailable, unavailable])
    runtime = make_runtime(client)
    graph = make_graph()

    first = runtime.capture_snapshot(
        graph, now=T0, wall_clock=lambda: T0, monotonic=lambda: 1.0
    )
    second = runtime.capture_snapshot(
        graph,
        now=T0 + timedelta(seconds=60),
        wall_clock=lambda: T0 + timedelta(seconds=60),
        monotonic=lambda: 2.0,
    )

    assert first.snapshot_id != second.snapshot_id
    assert second.version == first.version + 1
    assert client.refresh_count == 2


def test_graph_fingerprint_change_forces_a_new_snapshot() -> None:
    available = make_result(
        TrafficProviderState.AVAILABLE,
        observations=(make_observation(),),
    )
    client = FakeTomTomClient([available, available])
    runtime = make_runtime(client)

    first = runtime.capture_snapshot(
        make_graph(), now=T0, wall_clock=lambda: T0, monotonic=lambda: 1.0
    )
    second = runtime.capture_snapshot(
        make_graph(x_offset=0.01),
        now=T0 + timedelta(seconds=1),
        wall_clock=lambda: T0 + timedelta(seconds=1),
        monotonic=lambda: 2.0,
    )

    assert first.graph_fingerprint != second.graph_fingerprint
    assert client.refresh_count == 2


def test_partial_result_keeps_only_independently_valid_overlay_entries() -> None:
    client = FakeTomTomClient(
        [
            make_result(
                TrafficProviderState.TIMED_OUT,
                observations=(make_observation(),),
                failure_reason="TOMTOM_REFRESH_BUDGET_EXHAUSTED",
            )
        ]
    )
    runtime = make_runtime(client)
    graph = make_graph()

    snapshot = runtime.capture_snapshot(
        graph, now=T0, wall_clock=lambda: T0, monotonic=lambda: 1.0
    )

    assert snapshot.provider_state is TrafficProviderState.TIMED_OUT
    assert snapshot.data_reality is DataReality.REAL_LIVE
    assert snapshot.freshness_status is FreshnessStatus.LIVE
    assert snapshot.retrieved_at == T0
    assert snapshot.overlay is not None
    assert len(snapshot.overlay.entries) == 1
    assert snapshot.matches[0].reason == "ALL_SAFETY_GATES_PASSED"


def test_failed_attempt_has_no_fabricated_retrieval_timestamp() -> None:
    client = FakeTomTomClient(
        [make_result(TrafficProviderState.TIMED_OUT, failure_reason="TOMTOM_REFRESH_TIMEOUT")]
    )
    runtime = make_runtime(client)

    snapshot = runtime.capture_snapshot(
        make_graph(), now=T0, wall_clock=lambda: T0, monotonic=lambda: 1.0
    )

    assert snapshot.refresh_attempted_at == T0
    assert snapshot.retrieved_at is None
    assert snapshot.provider_last_updated is None
    assert snapshot.data_reality is None
    assert snapshot.freshness_status is FreshnessStatus.UNKNOWN


def test_current_snapshot_recomputes_stale_status_without_refreshing() -> None:
    client = FakeTomTomClient(
        [make_result(TrafficProviderState.AVAILABLE, observations=(make_observation(),))]
    )
    runtime = make_runtime(client)
    runtime.capture_snapshot(
        make_graph(), now=T0, wall_clock=lambda: T0, monotonic=lambda: 1.0
    )

    current = runtime.current_snapshot(now=T0 + timedelta(seconds=121))

    assert current is not None
    assert current.freshness_status is FreshnessStatus.STALE
    assert client.refresh_count == 1


def test_cached_refresh_clock_rollback_degrades_without_refreshing() -> None:
    client = FakeTomTomClient(
        [make_result(TrafficProviderState.AVAILABLE, observations=(make_observation(),))]
    )
    runtime = make_runtime(client)
    first = runtime.capture_snapshot(
        make_graph(), now=T0, wall_clock=lambda: T0, monotonic=lambda: 1.0
    )

    current = runtime.capture_snapshot(
        make_graph(),
        now=T0 - timedelta(seconds=1),
        wall_clock=lambda: T0 - timedelta(seconds=1),
        monotonic=lambda: 2.0,
    )

    assert current.snapshot_id == first.snapshot_id
    assert current.freshness_status is FreshnessStatus.UNKNOWN
    assert current.failure_reason == "TOMTOM_SNAPSHOT_TIMESTAMP_IN_FUTURE"
    assert client.refresh_count == 1


def test_future_retrieval_degrades_successful_snapshot() -> None:
    future = T0 + timedelta(seconds=1)
    client = FakeTomTomClient(
        [make_result(TrafficProviderState.AVAILABLE, observations=(make_observation(),))]
    )
    runtime = make_runtime(client)

    snapshot = runtime.capture_snapshot(
        make_graph(), now=T0, wall_clock=lambda: future, monotonic=lambda: 1.0
    )

    assert snapshot.retrieved_at == future
    assert snapshot.freshness_status is FreshnessStatus.UNKNOWN
    assert snapshot.failure_reason == "TOMTOM_SNAPSHOT_TIMESTAMP_IN_FUTURE"

    caught_up = runtime.current_snapshot(now=future)

    assert caught_up is not None
    assert caught_up.freshness_status is FreshnessStatus.LIVE
    assert caught_up.failure_reason is None


def test_sample_loader_failure_is_visible_and_does_not_call_provider() -> None:
    client = FakeTomTomClient([])
    runtime = TrafficRuntime(
        client=client,
        sample_points_loader=lambda: (_ for _ in ()).throw(ValueError("bad asset")),
    )

    snapshot = runtime.capture_snapshot(
        make_graph(), now=T0, wall_clock=lambda: T0, monotonic=lambda: 1.0
    )

    assert client.refresh_count == 0
    assert snapshot.provider_state is TrafficProviderState.UNAVAILABLE
    assert snapshot.failure_reason == "TRAFFIC_SAMPLE_POINTS_UNAVAILABLE"
    assert snapshot.observations == ()
    assert snapshot.overlay is None


class BlockingFakeTomTomClient(FakeTomTomClient):
    def __init__(self, result: TomTomRefreshResult) -> None:
        super().__init__([result])
        self.entered = Barrier(2)
        self.release = Barrier(2)
        self._count_lock = Lock()

    def refresh(self, *args, **kwargs) -> TomTomRefreshResult:
        with self._count_lock:
            self.refresh_count += 1
        self.entered.wait(timeout=2)
        self.release.wait(timeout=2)
        retrieved_at = kwargs["wall_clock"]()
        return self._results[0].model_copy(
            update={
                "refresh_attempted_at": kwargs["refresh_attempted_at"],
                "observations": tuple(
                    observation.model_copy(update={"retrieved_at": retrieved_at})
                    for observation in self._results[0].observations
                ),
            }
        )


def test_simultaneous_capture_launches_exactly_one_provider_refresh() -> None:
    client = BlockingFakeTomTomClient(
        make_result(TrafficProviderState.AVAILABLE, observations=(make_observation(),))
    )
    runtime = make_runtime(client)
    graph = make_graph()

    def capture():
        return runtime.capture_snapshot(
            graph, now=T0, wall_clock=lambda: T0, monotonic=lambda: 1.0
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(capture)
        client.entered.wait(timeout=2)
        second_future = executor.submit(capture)
        client.release.wait(timeout=2)
        first = first_future.result(timeout=2)
        second = second_future.result(timeout=2)

    assert client.refresh_count == 1
    assert first.snapshot_id == second.snapshot_id
    assert first is second


def test_snapshot_is_bound_to_graph_and_sample_set_fingerprints() -> None:
    client = FakeTomTomClient(
        [make_result(TrafficProviderState.AVAILABLE, observations=(make_observation(),))]
    )
    runtime = make_runtime(client)
    graph = make_graph()

    snapshot = runtime.capture_snapshot(
        graph, now=T0, wall_clock=lambda: T0, monotonic=lambda: 1.0
    )

    assert snapshot.graph_fingerprint == graph_fingerprint(graph)
    assert len(snapshot.sample_points_fingerprint) == 64
    assert snapshot.flow_style == "absolute"
    assert snapshot.flow_zoom == 22
    assert snapshot.units == "kmph"
