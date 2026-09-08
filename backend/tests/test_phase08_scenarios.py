from __future__ import annotations

from datetime import datetime, timezone
import json

import networkx as nx
import pytest

from app.benchmark_scenarios import (
    BenchmarkScenario,
    TrafficFixture,
    build_candidate_resources,
    build_fixed_traffic_snapshot,
    load_scenario_manifest,
)
from app.candidate_generation import CandidateResource
from app.coverage import CoverageZone
from app import coverage
from app.models import Incident
from app.planning import evaluate_phase04_candidate_set
from app.benchmark_runner import Phase08ScenarioRunner
from app.schemas import Coordinate, ConfidenceLevel, DataReality, IncidentStatus, ResourceStatus, ResourceType, Severity
from app.traffic.matching import graph_fingerprint
from app.traffic.models import TrafficProviderState


def _manifest_payload() -> dict[str, object]:
    incident = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "coordinate": {"lat": 30.0561, "lon": 31.3452},
        "requirements": [
            {"resource_type": "AMBULANCE", "minimum_count": 1},
        ],
    }
    scenarios = [
        {
            "id": f"T{index:02d}",
            "title": f"T{index:02d} fixture",
            "seed": index,
            "master_plan_case": f"T{index:02d}",
            "tags": ["test"],
            "incident": incident,
            "traffic_fixture": {
                "fixture_id": f"fixture-{index}",
                "mode": "FALLBACK",
                "source_reference": "phase08-test-fixture",
            },
            "expected": {"baseline": "PLAN_GENERATED", "sirengrid": "PLAN_GENERATED"},
        }
        for index in range(1, 16)
    ]
    scenarios.extend(
        {
            "id": f"X{index:02d}",
            "title": f"Cross-cutting fixture {index}",
            "seed": 100 + index,
            "master_plan_case": None,
            "tags": ["cross-cutting"],
            "incident": incident,
            "traffic_fixture": {
                "fixture_id": f"fixture-x-{index}",
                "mode": "FALLBACK",
                "source_reference": "phase08-test-fixture",
            },
            "expected": {"baseline": "PLAN_GENERATED", "sirengrid": "PLAN_GENERATED"},
        }
        for index in range(1, 22)
    )
    return {
        "dataset_version": "PHASE08_SCENARIO_DATASET_V1",
        "policy_version": "SIRENGRID_PHASE08_BENCHMARK_V1",
        "scenarios": scenarios,
    }


def test_manifest_requires_all_fifteen_master_plan_cases(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")

    manifest = load_scenario_manifest(path)

    assert len(manifest.scenarios) == 36
    assert {scenario.master_plan_case for scenario in manifest.scenarios[:15]} == {
        f"T{index:02d}" for index in range(1, 16)
    }


def test_resource_overrides_are_isolated_and_preserve_provenance() -> None:
    scenario = BenchmarkScenario.model_validate(
        {
            "id": "fixture",
            "title": "resource override",
            "seed": 1,
            "master_plan_case": None,
            "tags": ["resource"],
            "incident": _manifest_payload()["scenarios"][0]["incident"],
            "resource_overrides": [
                {
                    "resource_id": "10000000-0000-0000-0000-000000000001",
                    "status": "OUT_OF_SERVICE",
                }
            ],
            "traffic_fixture": {
                "fixture_id": "fixture",
                "mode": "FALLBACK",
                "source_reference": "phase08-test-fixture",
            },
            "expected": {"baseline": "PLAN_GENERATED", "sirengrid": "PLAN_GENERATED"},
        }
    )

    resources = build_candidate_resources(scenario)

    changed = next(resource for resource in resources if resource.resource_id.endswith("001"))
    unchanged = next(resource for resource in resources if resource.resource_id.endswith("002"))
    assert changed.status.value == "OUT_OF_SERVICE"
    assert unchanged.status.value == "AVAILABLE"
    assert changed.data_reality.value == "SIMULATED"
    assert changed.source == "scenario_phase01_seed"


def test_fixed_traffic_fixture_is_deterministic_and_never_refreshes_provider() -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=31.3, y=30.0)
    graph.add_node("b", x=31.31, y=30.0)
    graph.add_edge("a", "b", key="0", length=100.0, travel_time=10.0)
    fixture = TrafficFixture(
        fixture_id="fixed-closure",
        mode="CLOSURE",
        source_reference="phase08-test-fixture",
        closure_edge_index=0,
    )

    first = build_fixed_traffic_snapshot(graph, fixture)
    second = build_fixed_traffic_snapshot(graph, fixture)

    assert first is not None
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.provider_state is TrafficProviderState.AVAILABLE
    assert first.graph_fingerprint == graph_fingerprint(graph)
    assert first.overlay is not None
    assert first.overlay.entries[0].road_closure is True
    assert first.data_reality is None
    assert first.refresh_attempted_at == datetime(2026, 9, 8, tzinfo=timezone.utc)


def test_phase04_evaluator_accepts_fixed_replay_inputs_without_refreshing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("resource", x=31.3, y=30.0)
    graph.add_node("incident", x=31.31, y=30.0)
    graph.add_node("zone", x=31.31, y=30.0)
    graph.add_edge("resource", "incident", key="0", length=1000.0, travel_time=120.0)
    graph.add_edge("resource", "zone", key="0", length=1000.0, travel_time=120.0)
    resource = CandidateResource(
        resource_id="amb-1",
        resource_type=ResourceType.AMBULANCE,
        capability_tags=(),
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id=None,
        coordinate=Coordinate(lat=30.0, lon=31.3),
        data_reality=DataReality.SIMULATED,
        source="phase08_test_fixture",
    )
    incident = Incident(
        id="incident-fixed-replay",
        version=1,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=30.0,
        longitude=31.31,
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    zones = (
        CoverageZone(
            zone_id="zone",
            centroid=Coordinate(lat=30.0, lon=31.31),
            population=100.0,
        ),
    )
    capture_called = False

    def fail_capture(*_args, **_kwargs):
        nonlocal capture_called
        capture_called = True
        raise AssertionError("fixed replay must not capture provider traffic")

    monkeypatch.setattr("app.planning.traffic_runtime.capture_snapshot", fail_capture)

    _resolution, ranked, _proposals, _timestamp = evaluate_phase04_candidate_set(
        None,
        incident,
        graph_override=graph,
        zones_override=zones,
        traffic_snapshot_override=None,
        use_traffic_runtime=False,
        resources_override=(resource,),
    )

    assert not capture_called
    assert len(ranked) == 1
    assert ranked[0].combination.resource_ids == ("amb-1",)


def test_phase08_runner_replays_a_real_asset_scenario_deterministically() -> None:
    from app.benchmark_scenarios import load_scenario_manifest

    scenario = load_scenario_manifest().scenarios[0]
    runner = Phase08ScenarioRunner()

    first = runner.run_scenario(scenario)
    second = runner.run_scenario(scenario)

    assert first == second
    assert first["baseline"]["outcome"] == "PLAN_GENERATED"
    assert first["sirengrid"]["outcome"] == "PLAN_GENERATED"
    assert first["traffic_fixture"]["benchmark_reality"] == "SYNTHETIC"


def test_coverage_reuses_immutable_travel_trees_for_repeated_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("resource", x=31.3, y=30.0)
    graph.add_node("zone", x=31.31, y=30.0)
    graph.add_edge("resource", "zone", key="0", length=1000.0, travel_time=120.0)
    resource = coverage.CoverageResource(
        resource_id="amb-cache",
        resource_type=ResourceType.AMBULANCE,
        capability_tags=(),
        status=ResourceStatus.AVAILABLE,
        coordinate=Coordinate(lat=30.0, lon=31.3),
        data_reality=DataReality.SIMULATED,
        source="phase08_test_fixture",
    )
    zone = CoverageZone(
        zone_id="zone",
        centroid=Coordinate(lat=30.0, lon=31.31),
        population=100.0,
    )
    original = coverage.compute_single_source_travel_times
    call_count = 0

    def counted(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(coverage, "compute_single_source_travel_times", counted)
    cache: dict[tuple[object, ...], object] = {}
    kwargs = {
        "graph": graph,
        "zones": (zone,),
        "resources": (resource,),
        "cohort": coverage.CoverageCohort(ResourceType.AMBULANCE),
        "traffic_snapshot": None,
        "modeled_at": datetime(2026, 9, 8, tzinfo=timezone.utc),
        "travel_times_cache": cache,
    }

    first = coverage.compute_coverage_snapshot(**kwargs)
    second = coverage.compute_coverage_snapshot(**kwargs)

    assert first == second
    assert call_count == 1
