from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import pytest

from app import coverage
from app.routing import (
    ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME,
    ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED,
)
from app.schemas import (
    Coordinate,
    DataReality,
    FreshnessStatus,
    ResourceStatus,
    ResourceType,
)
from app.traffic.matching import graph_fingerprint
from app.traffic.models import (
    TrafficOverlay,
    TrafficOverlayEntry,
    TrafficProviderState,
    TrafficSnapshot,
)


def coverage_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=31.3000, y=30.0000)
    graph.add_node("b", x=31.3100, y=30.0000)
    graph.add_node("c", x=31.3200, y=30.0000)
    graph.add_node("isolated", x=31.3300, y=30.0000)
    graph.add_edge(
        "a",
        "b",
        key="0",
        length=1000.0,
        travel_time=600.0,
        base_travel_time_s=600.0,
    )
    graph.add_edge(
        "b",
        "c",
        key="0",
        length=1000.0,
        travel_time=120.0,
        base_travel_time_s=120.0,
    )
    return graph


def ambulance_resource(resource_id: str = "amb-1") -> coverage.CoverageResource:
    return coverage.CoverageResource(
        resource_id=resource_id,
        resource_type=ResourceType.AMBULANCE,
        capability_tags=(),
        status=ResourceStatus.AVAILABLE,
        coordinate=Coordinate(lat=30.0, lon=31.3),
        data_reality=DataReality.SIMULATED,
        source="phase03_simulated_resource",
    )


def ambulance_cohort() -> coverage.CoverageCohort:
    return coverage.CoverageCohort(resource_type=ResourceType.AMBULANCE)


def zones() -> list[coverage.CoverageZone]:
    return [
        coverage.CoverageZone(
            zone_id="zone-b",
            centroid=Coordinate(lat=30.0, lon=31.31),
            population=100.0,
        ),
        coverage.CoverageZone(
            zone_id="zone-c",
            centroid=Coordinate(lat=30.0, lon=31.32),
            population=20.0,
        ),
        coverage.CoverageZone(
            zone_id="zone-isolated",
            centroid=Coordinate(lat=30.0, lon=31.33),
            population=30.0,
        ),
    ]


def traffic_snapshot(graph: nx.MultiDiGraph, freshness: FreshnessStatus) -> TrafficSnapshot:
    now = datetime.now(timezone.utc)
    fingerprint = graph_fingerprint(graph)
    return TrafficSnapshot(
        snapshot_id="snapshot-coverage-1",
        version=1,
        graph_fingerprint=fingerprint,
        sample_points_fingerprint="sample-points",
        provider_state=TrafficProviderState.AVAILABLE,
        refresh_attempted_at=now,
        retrieved_at=now,
        freshness_status=freshness,
        source="TomTom",
        source_reference="https://developer.tomtom.com/",
        data_reality=DataReality.REAL_LIVE,
        flow_style="absolute",
        flow_zoom=22,
        units="kmph",
        overlay=TrafficOverlay(
            snapshot_id="snapshot-coverage-1",
            graph_fingerprint=fingerprint,
            entries=(
                TrafficOverlayEntry(
                    edge_key=("a", "b", "0"),
                    observation_id="observation-1",
                    traffic_factor=2.0,
                ),
            ),
        ),
    )


def test_coverage_uses_inclusive_600_second_target_and_exposes_unreachable_zones() -> None:
    snapshot = coverage.compute_coverage_snapshot(
        graph=coverage_graph(),
        zones=zones(),
        resources=[ambulance_resource()],
        cohort=ambulance_cohort(),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    by_zone = {zone.zone_id: zone for zone in snapshot.zones}
    assert coverage.PROTOTYPE_TARGET_RESPONSE_TIME_SECONDS == 600
    assert by_zone["zone-b"].eta_seconds == 600.0
    assert by_zone["zone-b"].covered is True
    assert by_zone["zone-c"].covered is False
    assert by_zone["zone-isolated"].eta_seconds is None
    assert by_zone["zone-isolated"].covered is False
    assert snapshot.population_weighted_coverage == pytest.approx(100.0 / 150.0)
    assert snapshot.worst_zone_eta is None
    assert snapshot.worst_finite_zone_eta == 720.0
    assert snapshot.undercovered_zone_count == 2
    assert snapshot.unreachable_zone_ids == ("zone-isolated",)
    assert snapshot.routing_source == ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
    assert snapshot.traffic_fallback_reason == "TOMTOM_SNAPSHOT_UNAVAILABLE"


def test_coverage_applies_a_valid_traffic_overlay_without_mutating_base_graph() -> None:
    graph = coverage_graph()
    before = deepcopy(list(graph.edges(data=True, keys=True)))

    snapshot = coverage.compute_coverage_snapshot(
        graph=graph,
        zones=zones(),
        resources=[ambulance_resource()],
        cohort=ambulance_cohort(),
        traffic_snapshot=traffic_snapshot(graph, FreshnessStatus.LIVE),
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    by_zone = {zone.zone_id: zone for zone in snapshot.zones}
    assert by_zone["zone-b"].eta_seconds == 1200.0
    assert by_zone["zone-b"].routing_source == ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED
    assert by_zone["zone-b"].covered is False
    assert snapshot.routing_source == ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED
    assert snapshot.traffic_snapshot_id == "snapshot-coverage-1"
    assert snapshot.traffic_adjusted_zone_count == 2
    assert list(graph.edges(data=True, keys=True)) == before


def test_stale_traffic_snapshot_visibly_falls_back_to_immutable_osm_base() -> None:
    graph = coverage_graph()
    snapshot = coverage.compute_coverage_snapshot(
        graph=graph,
        zones=zones(),
        resources=[ambulance_resource()],
        cohort=ambulance_cohort(),
        traffic_snapshot=traffic_snapshot(graph, FreshnessStatus.STALE),
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    by_zone = {zone.zone_id: zone for zone in snapshot.zones}
    assert by_zone["zone-b"].eta_seconds == 600.0
    assert snapshot.routing_source == ROUTING_SOURCE_OSM_BASE_TRAVEL_TIME
    assert snapshot.traffic_fallback_reason == "TOMTOM_SNAPSHOT_STALE"
    assert snapshot.traffic_snapshot_id == "snapshot-coverage-1"


def test_coverage_keeps_resource_cohorts_separate_and_requires_known_capabilities() -> None:
    graph = coverage_graph()
    resources = [
        ambulance_resource(),
        coverage.CoverageResource(
            resource_id="fire-1",
            resource_type=ResourceType.FIRE_RESCUE,
            capability_tags=("rescue",),
            status=ResourceStatus.AVAILABLE,
            coordinate=Coordinate(lat=30.0, lon=31.31),
            data_reality=DataReality.SIMULATED,
            source="phase03_simulated_resource",
        ),
        coverage.CoverageResource(
            resource_id="amb-unknown-capability",
            resource_type=ResourceType.AMBULANCE,
            capability_tags=(),
            status=ResourceStatus.AVAILABLE,
            coordinate=Coordinate(lat=30.0, lon=31.31),
            data_reality=DataReality.SIMULATED,
            source="phase03_simulated_resource",
        ),
    ]

    rescue = coverage.compute_coverage_snapshot(
        graph=graph,
        zones=zones(),
        resources=resources,
        cohort=coverage.CoverageCohort(
            resource_type=ResourceType.FIRE_RESCUE,
            required_capability_tags=("rescue",),
        ),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    ambulance_with_capability = coverage.compute_coverage_snapshot(
        graph=graph,
        zones=zones(),
        resources=resources,
        cohort=coverage.CoverageCohort(
            resource_type=ResourceType.AMBULANCE,
            required_capability_tags=("advanced_life_support",),
        ),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert rescue.eligible_resource_ids == ("fire-1",)
    assert ambulance_with_capability.eligible_resource_ids == ()
    assert ambulance_with_capability.unreachable_zone_count == 3


def test_population_zone_loader_retains_real_public_worldpop_provenance() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "processed"
        / "nasr_city"
        / "nasr_city_zone_population_worldpop_2025.geojson"
    )

    zones = coverage.load_population_zones(path)
    graph = nx.MultiDiGraph()
    graph.add_node("zone-node", x=zones[0].centroid.lon, y=zones[0].centroid.lat)
    snapshot = coverage.compute_coverage_snapshot(
        graph=graph,
        zones=zones[:1],
        resources=[
            coverage.CoverageResource(
                resource_id="amb-population-provenance",
                resource_type=ResourceType.AMBULANCE,
                capability_tags=(),
                status=ResourceStatus.AVAILABLE,
                coordinate=zones[0].centroid,
                data_reality=DataReality.SIMULATED,
                source="phase03_simulated_resource",
            )
        ],
        cohort=ambulance_cohort(),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert zones[0].data_reality is DataReality.REAL_DERIVED
    assert zones[0].source_reference == coverage.WORLDPOP_SOURCE_REFERENCE
    assert snapshot.population_data_reality is DataReality.REAL_DERIVED
    assert snapshot.population_source_reference == coverage.WORLDPOP_SOURCE_REFERENCE


def test_coverage_snaps_each_zone_once_per_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = coverage_graph()
    original_snap_zone = coverage._snap_zone
    calls = 0

    def count_zone_snaps(graph_arg: nx.Graph, coordinate: Coordinate):
        nonlocal calls
        calls += 1
        return original_snap_zone(graph_arg, coordinate)

    monkeypatch.setattr(coverage, "_snap_zone", count_zone_snaps)
    second_resource = coverage.CoverageResource(
        resource_id="amb-2",
        resource_type=ResourceType.AMBULANCE,
        capability_tags=(),
        status=ResourceStatus.AVAILABLE,
        coordinate=Coordinate(lat=30.0, lon=31.31),
        data_reality=DataReality.SIMULATED,
        source="phase03_simulated_resource",
    )

    coverage.compute_coverage_snapshot(
        graph=graph,
        zones=zones(),
        resources=[ambulance_resource(), second_resource],
        cohort=ambulance_cohort(),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert calls == len(zones())


def test_coverage_keeps_base_optimal_eta_independent_of_traffic_selected_resource() -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("base-fast", x=31.3000, y=30.0000)
    graph.add_node("traffic-alternative", x=31.3200, y=30.0000)
    graph.add_node("zone", x=31.3100, y=30.0000)
    graph.add_edge(
        "base-fast",
        "zone",
        key="0",
        length=1000.0,
        travel_time=500.0,
        base_travel_time_s=500.0,
    )
    graph.add_edge(
        "traffic-alternative",
        "zone",
        key="0",
        length=1000.0,
        travel_time=600.0,
        base_travel_time_s=600.0,
    )
    resources = [
        coverage.CoverageResource(
            resource_id="base-fast",
            resource_type=ResourceType.AMBULANCE,
            capability_tags=(),
            status=ResourceStatus.AVAILABLE,
            coordinate=Coordinate(lat=30.0, lon=31.3),
            data_reality=DataReality.SIMULATED,
            source="phase03_simulated_resource",
        ),
        coverage.CoverageResource(
            resource_id="traffic-alternative",
            resource_type=ResourceType.AMBULANCE,
            capability_tags=(),
            status=ResourceStatus.AVAILABLE,
            coordinate=Coordinate(lat=30.0, lon=31.32),
            data_reality=DataReality.SIMULATED,
            source="phase03_simulated_resource",
        ),
    ]
    now = datetime.now(timezone.utc)
    fingerprint = graph_fingerprint(graph)
    snapshot = TrafficSnapshot(
        snapshot_id="snapshot-selection-change",
        version=1,
        graph_fingerprint=fingerprint,
        sample_points_fingerprint="sample-points",
        provider_state=TrafficProviderState.AVAILABLE,
        refresh_attempted_at=now,
        retrieved_at=now,
        freshness_status=FreshnessStatus.LIVE,
        source="TomTom",
        source_reference="https://developer.tomtom.com/",
        data_reality=DataReality.REAL_LIVE,
        flow_style="absolute",
        flow_zoom=22,
        units="kmph",
        overlay=TrafficOverlay(
            snapshot_id="snapshot-selection-change",
            graph_fingerprint=fingerprint,
            entries=(
                TrafficOverlayEntry(
                    edge_key=("base-fast", "zone", "0"),
                    observation_id="observation-selection-change",
                    traffic_factor=2.0,
                ),
            ),
        ),
    )

    result = coverage.compute_coverage_snapshot(
        graph=graph,
        zones=[
            coverage.CoverageZone(
                zone_id="zone",
                centroid=Coordinate(lat=30.0, lon=31.31),
                population=10.0,
            )
        ],
        resources=resources,
        cohort=ambulance_cohort(),
        traffic_snapshot=snapshot,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    zone = result.zones[0]
    assert zone.base_eta_seconds == 500.0
    assert zone.eta_seconds == 600.0
    assert zone.routing_source == ROUTING_SOURCE_TOMTOM_TRAFFIC_ADJUSTED


def test_dispatch_impact_is_hypothetical_and_exposes_deterministic_coverage_delta() -> None:
    graph = coverage_graph()
    resources = [
        ambulance_resource(),
        coverage.CoverageResource(
            resource_id="amb-reserve",
            resource_type=ResourceType.AMBULANCE,
            capability_tags=(),
            status=ResourceStatus.AVAILABLE,
            coordinate=Coordinate(lat=30.0, lon=31.32),
            data_reality=DataReality.SIMULATED,
            source="phase03_simulated_resource",
        ),
    ]
    original_resources = deepcopy(resources)
    original_graph = deepcopy(list(graph.edges(data=True, keys=True)))
    captured_traffic = traffic_snapshot(graph, FreshnessStatus.STALE)

    impact = coverage.simulate_dispatch_impact(
        graph=graph,
        zones=zones(),
        resources=resources,
        cohort=ambulance_cohort(),
        dispatched_resource_ids=("amb-1",),
        traffic_snapshot=captured_traffic,
        modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert impact.dispatched_resource_ids == ("amb-1",)
    assert impact.baseline.eligible_resource_ids == ("amb-1", "amb-reserve")
    assert impact.post_dispatch.eligible_resource_ids == ("amb-reserve",)
    assert impact.remaining_reserve_resource_ids == ("amb-reserve",)
    assert impact.coverage_delta <= 0.0
    assert impact.newly_undercovered_zone_ids == ("zone-b",)
    assert impact.affected_zone_ids == ("zone-b",)
    assert impact.baseline.traffic_snapshot_id == captured_traffic.snapshot_id
    assert impact.post_dispatch.traffic_snapshot_id == captured_traffic.snapshot_id
    assert impact.baseline.traffic_snapshot_version == impact.post_dispatch.traffic_snapshot_version
    assert resources == original_resources
    assert list(graph.edges(data=True, keys=True)) == original_graph


def test_joint_coverage_requires_every_cohort_and_keeps_population_single_counted() -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("ambulance", x=31.3000, y=30.0000)
    graph.add_node("fire", x=31.3200, y=30.0000)
    graph.add_node("zone-one", x=31.3100, y=30.0000)
    graph.add_node("zone-two", x=31.3300, y=30.0000)
    for source, destination, travel_time in (
        ("ambulance", "zone-one", 500.0),
        ("ambulance", "zone-two", 600.0),
        ("fire", "zone-one", 700.0),
    ):
        graph.add_edge(
            source,
            destination,
            key="0",
            length=1000.0,
            travel_time=travel_time,
            base_travel_time_s=travel_time,
        )
    modeled_at = datetime(2026, 9, 7, tzinfo=timezone.utc)
    modeled_zones = [
        coverage.CoverageZone(
            zone_id="zone-one",
            centroid=Coordinate(lat=30.0, lon=31.31),
            population=100.0,
        ),
        coverage.CoverageZone(
            zone_id="zone-two",
            centroid=Coordinate(lat=30.0, lon=31.33),
            population=50.0,
        ),
    ]
    resources = [
        coverage.CoverageResource(
            resource_id="amb-1",
            resource_type=ResourceType.AMBULANCE,
            capability_tags=(),
            status=ResourceStatus.AVAILABLE,
            coordinate=Coordinate(lat=30.0, lon=31.3),
            data_reality=DataReality.SIMULATED,
            source="phase03_simulated_resource",
        ),
        coverage.CoverageResource(
            resource_id="fire-1",
            resource_type=ResourceType.FIRE_RESCUE,
            capability_tags=(),
            status=ResourceStatus.AVAILABLE,
            coordinate=Coordinate(lat=30.0, lon=31.32),
            data_reality=DataReality.SIMULATED,
            source="phase03_simulated_resource",
        ),
    ]
    ambulance_snapshot = coverage.compute_coverage_snapshot(
        graph=graph,
        zones=modeled_zones,
        resources=resources,
        cohort=coverage.CoverageCohort(ResourceType.AMBULANCE),
        traffic_snapshot=None,
        modeled_at=modeled_at,
    )
    fire_snapshot = coverage.compute_coverage_snapshot(
        graph=graph,
        zones=modeled_zones,
        resources=resources,
        cohort=coverage.CoverageCohort(ResourceType.FIRE_RESCUE),
        traffic_snapshot=None,
        modeled_at=modeled_at,
    )

    joint = coverage.derive_joint_coverage_snapshot(
        (ambulance_snapshot, fire_snapshot)
    )

    by_zone = {zone.zone_id: zone for zone in joint.zones}
    assert joint.aggregation_policy == "JOINT_ALL_REQUIRED_COHORTS_V1"
    assert joint.total_modeled_population == 150.0
    assert joint.population_weighted_coverage == 0.0
    assert by_zone["zone-one"].eta_seconds == 700.0
    assert by_zone["zone-one"].covered is False
    assert by_zone["zone-one"].failing_cohort_ids == ("FIRE_RESCUE",)
    assert by_zone["zone-two"].eta_seconds is None
    assert by_zone["zone-two"].failing_cohort_ids == ("FIRE_RESCUE",)
    assert joint.worst_zone_eta is None
    assert joint.worst_finite_zone_eta == 700.0
    assert joint.unreachable_zone_ids == ("zone-two",)

    single = coverage.derive_joint_coverage_snapshot((ambulance_snapshot,))
    assert single.population_weighted_coverage == ambulance_snapshot.population_weighted_coverage
    assert single.zones[0].eta_seconds == ambulance_snapshot.zones[0].eta_seconds
