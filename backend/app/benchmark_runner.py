"""Deterministic Phase 08 baseline/SirenGrid comparison runner."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Iterable

import networkx as nx

from app.benchmark_baseline import (
    BaselineInsufficientResourcesError,
    BaselineSelection,
    choose_greedy_baseline_resources,
    choose_nearest_baseline_hospital,
)
from app.benchmark_scenarios import (
    BenchmarkManifest,
    BenchmarkScenario,
    DEFAULT_SCENARIO_MANIFEST,
    build_candidate_resources,
    build_fixed_traffic_snapshot,
    build_hospital_operational_states,
    load_scenario_manifest,
)
from app.candidate_evaluation import evaluate_candidate_combination
from app.candidate_generation import (
    CandidateCombination,
    CandidateResponder,
    CandidateResource,
    NoFeasibleCandidateError,
)
from app.config import REPO_ROOT, settings
from app.coverage import CoverageZone, JointCoverageSnapshot, CoverageSnapshot, load_population_zones
from app.hospitals import (
    HospitalOperationalSnapshot,
    HospitalRouteCandidate,
    load_static_hospitals,
    rank_hospital_candidates,
)
from app.models import Incident
from app.planning import evaluate_phase04_candidate_set
from app.materiality import evaluate_replan_materiality
from app.schemas import ConfidenceLevel, DataReality, IncidentStatus, ResourceStatus
from app.routing import (
    RouteNotFoundError,
    RoutingPointOutsideGraphError,
    compute_traffic_aware_route,
    load_routing_graph,
)


DEFAULT_PHASE08_POPULATION_ZONES = (
    settings.NASR_CITY_DATA_DIR / "nasr_city_zone_population_worldpop_2025.geojson"
)
DEFAULT_PHASE08_OUTPUT_DIR = REPO_ROOT / "data" / "evaluation" / "phase08"
PHASE08_FIXED_MODEL_TIME = datetime(2026, 9, 8, tzinfo=timezone.utc)


@dataclass(frozen=True)
class EngineRunResult:
    engine: str
    outcome: str
    resource_ids: tuple[str, ...] = ()
    incident_eta_seconds: float | None = None
    routes: tuple[dict[str, Any], ...] = ()
    baseline_joint: JointCoverageSnapshot | None = None
    post_dispatch_joint: JointCoverageSnapshot | None = None
    score: dict[str, Any] | None = None
    reposition_proposal: dict[str, Any] | None = None
    hospital: dict[str, Any] | None = None
    replan: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "outcome": self.outcome,
            "resource_ids": list(self.resource_ids),
            "incident_eta_seconds": self.incident_eta_seconds,
            "routes": list(self.routes),
            "baseline_joint": _joint_snapshot_to_dict(self.baseline_joint),
            "post_dispatch_joint": _joint_snapshot_to_dict(self.post_dispatch_joint),
            "score": self.score,
            "reposition_proposal": self.reposition_proposal,
            "hospital": self.hospital,
            "replan": self.replan,
            "error": self.error,
        }


def _zone_to_dict(zone: Any) -> dict[str, Any]:
    return {
        "zone_id": zone.zone_id,
        "population": zone.population,
        "eta_seconds": zone.eta_seconds,
        "covered": zone.covered,
        "routing_source": getattr(zone, "routing_source", None),
        "failing_cohort_ids": list(getattr(zone, "failing_cohort_ids", ())),
    }


def _coverage_snapshot_to_dict(snapshot: CoverageSnapshot) -> dict[str, Any]:
    return {
        "cohort_id": snapshot.cohort.cohort_id,
        "resource_type": snapshot.cohort.resource_type.value,
        "required_capability_tags": list(snapshot.cohort.required_capability_tags),
        "data_reality": snapshot.data_reality.value,
        "population_data_reality": snapshot.population_data_reality.value,
        "population_source_reference": snapshot.population_source_reference,
        "graph_fingerprint": snapshot.graph_fingerprint,
        "target_response_time_seconds": snapshot.prototype_target_response_time_seconds,
        "zones": [_zone_to_dict(zone) for zone in snapshot.zones],
        "eligible_resource_ids": list(snapshot.eligible_resource_ids),
        "excluded_resource_ids": list(snapshot.excluded_resource_ids),
        "total_modeled_population": snapshot.total_modeled_population,
        "covered_population": snapshot.covered_population,
        "population_weighted_coverage": snapshot.population_weighted_coverage,
        "worst_zone_eta": snapshot.worst_zone_eta,
        "worst_finite_zone_eta": snapshot.worst_finite_zone_eta,
        "undercovered_zone_count": snapshot.undercovered_zone_count,
        "unreachable_zone_count": snapshot.unreachable_zone_count,
        "unreachable_zone_ids": list(snapshot.unreachable_zone_ids),
        "routing_source": snapshot.routing_source,
        "traffic_snapshot_id": snapshot.traffic_snapshot_id,
        "traffic_snapshot_version": snapshot.traffic_snapshot_version,
        "traffic_freshness_status": (
            snapshot.traffic_freshness_status.value
            if snapshot.traffic_freshness_status
            else None
        ),
        "traffic_source_reference": snapshot.traffic_source_reference,
        "traffic_fallback_reason": snapshot.traffic_fallback_reason,
    }


def _joint_snapshot_to_dict(snapshot: JointCoverageSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "aggregation_policy": snapshot.aggregation_policy,
        "data_reality": snapshot.data_reality.value,
        "population_data_reality": snapshot.population_data_reality.value,
        "population_source_reference": snapshot.population_source_reference,
        "graph_fingerprint": snapshot.graph_fingerprint,
        "target_response_time_seconds": snapshot.prototype_target_response_time_seconds,
        "zones": [_zone_to_dict(zone) for zone in snapshot.zones],
        "total_modeled_population": snapshot.total_modeled_population,
        "covered_population": snapshot.covered_population,
        "population_weighted_coverage": snapshot.population_weighted_coverage,
        "worst_zone_eta": snapshot.worst_zone_eta,
        "worst_finite_zone_eta": snapshot.worst_finite_zone_eta,
        "undercovered_zone_count": snapshot.undercovered_zone_count,
        "unreachable_zone_count": snapshot.unreachable_zone_count,
        "unreachable_zone_ids": list(snapshot.unreachable_zone_ids),
        "traffic_snapshot_id": snapshot.traffic_snapshot_id,
        "traffic_snapshot_version": snapshot.traffic_snapshot_version,
        "traffic_freshness_status": (
            snapshot.traffic_freshness_status.value
            if snapshot.traffic_freshness_status
            else None
        ),
        "per_cohort": [
            _coverage_snapshot_to_dict(cohort) for cohort in snapshot.cohort_snapshots
        ],
    }


def _score_to_dict(score: Any) -> dict[str, Any]:
    return {
        "policy_version": score.policy_version,
        "convention": score.convention,
        "max_incident_eta_seconds": score.max_incident_eta_seconds,
        "post_dispatch_joint_population_weighted_coverage": (
            score.post_dispatch_joint_population_weighted_coverage
        ),
        "remaining_reserve_exhausted": score.remaining_reserve_exhausted,
        "proposed_reposition_eta_seconds": score.proposed_reposition_eta_seconds,
        "normalized_eta_term": score.normalized_eta_term,
        "coverage_penalty": score.coverage_penalty,
        "reserve_penalty": score.reserve_penalty,
        "reposition_penalty": score.reposition_penalty,
        "hospital_penalty": score.hospital_penalty,
        "weights": dict(score.weights),
        "weighted_terms": dict(score.weighted_terms),
        "final_score": score.final_score,
    }


def _reposition_to_dict(proposal: Any | None) -> dict[str, Any] | None:
    if proposal is None:
        return None
    return {
        "target_zone_id": proposal.target_zone_id,
        "staging_zone_id": proposal.staging_zone_id,
        "staging_centroid": proposal.staging_centroid.model_dump(mode="json"),
        "staging_data_reality": proposal.staging_data_reality.value,
        "staging_source": proposal.staging_source,
        "staging_policy": proposal.staging_policy,
        "repositioned_resource_id": proposal.repositioned_resource_id,
        "failing_cohort_ids": list(proposal.failing_cohort_ids),
        "reposition_route": proposal.reposition_route.model_dump(mode="json"),
        "reposition_eta_seconds": proposal.reposition_eta_seconds,
        "reposition_distance_m": proposal.reposition_distance_m,
        "target_failing_cohort_ids_before": list(
            proposal.target_failing_cohort_ids_before
        ),
        "target_failing_cohort_ids_after": list(proposal.target_failing_cohort_ids_after),
        "target_improved": proposal.target_improved,
        "pre_reposition_cohort_snapshots": [
            _coverage_snapshot_to_dict(snapshot)
            for snapshot in proposal.pre_reposition_cohort_snapshots
        ],
        "post_reposition_cohort_snapshots": [
            _coverage_snapshot_to_dict(snapshot)
            for snapshot in proposal.post_reposition_cohort_snapshots
        ],
        "pre_reposition_joint": _joint_snapshot_to_dict(proposal.pre_reposition_joint),
        "post_reposition_joint": _joint_snapshot_to_dict(proposal.post_reposition_joint),
    }


def _error_result(engine: str, error: Exception) -> EngineRunResult:
    return EngineRunResult(
        engine=engine,
        outcome="INSUFFICIENT_RESOURCES",
        error=str(error),
    )


def _hospital_state_to_dict(state: HospitalOperationalSnapshot) -> dict[str, Any]:
    return {
        "hospital_id": state.hospital_id,
        "accepting_state": state.accepting_state,
        "simulated_load_ratio": state.simulated_load_ratio,
        "simulated_free_capacity": state.simulated_free_capacity,
        "incoming_cases": state.incoming_cases,
        "freshness_status": state.freshness_status,
        "data_reality": state.data_reality,
        "last_updated": state.last_updated,
        "source": state.source,
    }


def _hospital_result(
    *,
    graph: nx.Graph,
    resources: tuple[CandidateResource, ...],
    scenario: BenchmarkScenario,
    primary: EngineRunResult,
    traffic_snapshot: Any,
    engine: str,
) -> dict[str, Any] | None:
    """Measure hospital choice using the same static and routing inputs.

    Hospital operational state is deliberately unknown unless a scenario later
    supplies an explicit fixture.  This keeps the benchmark from turning
    missing public facts into fabricated live capacity or acceptance state.
    """
    if scenario.incident.transport_required is False:
        return {"status": "NOT_APPLICABLE", "data_reality": "SIMULATED"}
    if scenario.incident.transport_required is None:
        return {
            "status": "REQUIRES_REVIEW",
            "reason": "TRANSPORT_REQUIREMENT_UNKNOWN",
            "data_reality": "SIMULATED",
        }
    if primary.outcome != "PLAN_GENERATED" or not primary.resource_ids:
        return {"status": "NOT_AVAILABLE", "reason": "NO_TRANSPORT_ORIGIN"}

    resources_by_id = {resource.resource_id: resource for resource in resources}
    origin_resource = resources_by_id.get(primary.resource_ids[0])
    if origin_resource is None:
        return {"status": "NOT_AVAILABLE", "reason": "ORIGIN_RESOURCE_NOT_FOUND"}
    hospitals = load_static_hospitals()
    states = {
        hospital.id: build_hospital_operational_states(scenario).get(
            hospital.id, HospitalOperationalSnapshot.unknown(hospital.id)
        )
        for hospital in hospitals
    }
    origin = origin_resource.coordinate
    if engine == "BASELINE":
        selected = choose_nearest_baseline_hospital(
            graph=graph,
            origin=origin,
            required_capabilities=tuple(
                scenario.incident.required_hospital_capabilities
            ),
            traffic_snapshot=traffic_snapshot,
            hospitals=hospitals,
            operational_states=states,
            include_route_alternatives=False,
        )
        if selected is None:
            return {"status": "NOT_AVAILABLE", "reason": "NO_REACHABLE_HOSPITAL"}
        return {
            "status": "SELECTED",
            "hospital_id": selected.hospital.id,
            "route": selected.route,
            "score": None,
            "score_breakdown": {},
            "operational_state": _hospital_state_to_dict(selected.operational_state),
            "selection_policy": "BASELINE_NEAREST_FEASIBLE_HOSPITAL_V1",
            "data_reality": "REAL_DERIVED",
        }

    candidates: list[HospitalRouteCandidate] = []
    for hospital in hospitals:
        try:
            route = compute_traffic_aware_route(
                graph,
                origin,
                type(origin)(lat=hospital.latitude, lon=hospital.longitude),
                traffic_snapshot,
                include_alternatives=False,
            )
        except (RouteNotFoundError, RoutingPointOutsideGraphError, ValueError):
            continue
        candidates.append(
            HospitalRouteCandidate(
                hospital=hospital,
                operational_state=states[hospital.id],
                route=route.model_dump(mode="json"),
            )
        )
    ranked = rank_hospital_candidates(
        candidates,
        required_capabilities=tuple(scenario.incident.required_hospital_capabilities),
    )
    if not ranked:
        return {"status": "NOT_AVAILABLE", "reason": "NO_REACHABLE_HOSPITAL"}
    selected = ranked[0]
    return {
        "status": "SELECTED",
        "hospital_id": selected.hospital.id,
        "route": selected.route,
        "score": selected.score,
        "score_breakdown": selected.score_breakdown,
        "operational_state": _hospital_state_to_dict(selected.operational_state),
        "selection_policy": "SIRENGRID_PROTOTYPE_HOSPITAL_SCORE_V1",
        "data_reality": "REAL_DERIVED",
    }


def _replan_result(
    *,
    graph: nx.Graph,
    resources: tuple[CandidateResource, ...],
    scenario: BenchmarkScenario,
    primary: EngineRunResult,
    traffic_snapshot: Any,
) -> dict[str, Any] | None:
    """Compare a fixed current traffic state with the approved base route.

    This is a measurement-only replan check.  It does not persist a
    replacement plan or mutate an operational resource; the production
    ``evaluate_replan_materiality`` policy remains the authority for the
    material/no-material result.
    """
    if primary.outcome != "PLAN_GENERATED" or not primary.resource_ids:
        return None
    resource = next(
        (item for item in resources if item.resource_id == primary.resource_ids[0]),
        None,
    )
    if resource is None:
        return None
    try:
        old_route = compute_traffic_aware_route(
            graph,
            resource.coordinate,
            scenario.incident.coordinate,
            None,
            include_alternatives=False,
        )
    except (RouteNotFoundError, RoutingPointOutsideGraphError, ValueError) as exc:
        return {
            "status": "NO_MATERIAL_CHANGE",
            "reason": "BASE_ROUTE_UNAVAILABLE",
            "error": str(exc),
        }
    new_eta = primary.incident_eta_seconds
    old_keys = {tuple(edge) for edge in old_route.edge_keys}
    new_keys = {
        tuple(edge)
        for route in primary.routes
        for edge in route.get("edge_keys", [])
    }
    overlap = len(old_keys.intersection(new_keys)) / len(old_keys) if old_keys else None
    closure_keys = {
        tuple(entry.edge_key)
        for entry in (traffic_snapshot.overlay.entries if traffic_snapshot and traffic_snapshot.overlay else ())
        if entry.road_closure
    }
    materiality = evaluate_replan_materiality(
        old_eta_seconds=old_route.effective_eta,
        new_eta_seconds=new_eta,
        route_edge_overlap_ratio=overlap,
        active_route_closure=bool(old_keys.intersection(closure_keys)),
    )
    delta = new_eta - old_route.effective_eta if new_eta is not None else None
    return {
        "status": "MATERIAL" if materiality.material else "NO_MATERIAL_CHANGE",
        "materiality_policy_version": "SIRENGRID_REPLAN_MATERIALITY_V1",
        "reasons": list(materiality.reasons),
        "previous_eta_seconds": old_route.effective_eta,
        "proposed_eta_seconds": new_eta,
        "eta_delta_seconds": delta,
        "route_edge_overlap_ratio": overlap,
        "traffic_snapshot_id": traffic_snapshot.snapshot_id if traffic_snapshot else None,
        "traffic_freshness_status": (
            traffic_snapshot.freshness_status.value
            if traffic_snapshot is not None
            else "UNKNOWN"
        ),
        "data_reality": "DERIVED_FROM_FIXED_BENCHMARK_INPUTS",
    }


def _baseline_result(
    *,
    graph: nx.Graph,
    zones: tuple[CoverageZone, ...],
    resources: tuple[CandidateResource, ...],
    scenario: BenchmarkScenario,
    traffic_snapshot: Any,
    travel_times_cache: dict[tuple[Any, ...], Any] | None = None,
    zone_nodes_cache: dict[tuple[Any, ...], Any] | None = None,
) -> EngineRunResult:
    try:
        selection: BaselineSelection = choose_greedy_baseline_resources(
            graph=graph,
            incident_coordinate=scenario.incident.coordinate,
            resources=resources,
            requirements=scenario.incident.response_requirements(),
            traffic_snapshot=traffic_snapshot,
            include_route_alternatives=False,
        )
    except BaselineInsufficientResourcesError as exc:
        return _error_result("BASELINE", exc)
    combination = CandidateCombination(
        responders=tuple(
            CandidateResponder(choice.requirement, choice.resource, choice.route)
            for choice in selection.choices
        )
    )
    evaluated = evaluate_candidate_combination(
        graph=graph,
        zones=zones,
        resources=resources,
        requirements=scenario.incident.response_requirements(),
        combination=combination,
        traffic_snapshot=traffic_snapshot,
        modeled_at=PHASE08_FIXED_MODEL_TIME,
        travel_times_cache=travel_times_cache,
        zone_nodes_cache=zone_nodes_cache,
    )
    result = EngineRunResult(
        engine="BASELINE",
        outcome="PLAN_GENERATED",
        resource_ids=selection.resource_ids,
        incident_eta_seconds=selection.max_incident_eta_seconds,
        routes=tuple(choice.route.model_dump(mode="json") for choice in selection.choices),
        baseline_joint=evaluated.metrics.baseline_joint,
        post_dispatch_joint=evaluated.metrics.post_dispatch_joint,
    )
    return replace(
        result,
        hospital=_hospital_result(
            graph=graph,
            resources=resources,
            scenario=scenario,
            primary=result,
            traffic_snapshot=traffic_snapshot,
            engine="BASELINE",
        ),
        replan=_replan_result(
            graph=graph,
            resources=resources,
            scenario=scenario,
            primary=result,
            traffic_snapshot=traffic_snapshot,
        ),
    )


def _benchmark_incident(scenario: BenchmarkScenario) -> Incident:
    return Incident(
        id=f"phase08-{scenario.id}",
        version=1,
        incident_type=scenario.incident.incident_type,
        severity=scenario.incident.severity,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=scenario.incident.coordinate.lat,
        longitude=scenario.incident.coordinate.lon,
        transport_required=scenario.incident.transport_required,
        required_resources_json=[
            {
                "resource_type": requirement.resource_type.value,
                "count": requirement.minimum_count,
                "required_capability_tags": list(requirement.required_capability_tags),
            }
            for requirement in scenario.incident.requirements
        ],
    )


def _sirengrid_result(
    *,
    graph: nx.Graph,
    zones: tuple[CoverageZone, ...],
    resources: tuple[CandidateResource, ...],
    scenario: BenchmarkScenario,
    traffic_snapshot: Any,
    travel_times_cache: dict[tuple[Any, ...], Any] | None = None,
    zone_nodes_cache: dict[tuple[Any, ...], Any] | None = None,
) -> EngineRunResult:
    try:
        _resolution, ranked, reposition_proposals, _timestamp = (
            evaluate_phase04_candidate_set(
                None,
                _benchmark_incident(scenario),
                now_utc=PHASE08_FIXED_MODEL_TIME,
                graph_override=graph,
                zones_override=zones,
                traffic_snapshot_override=traffic_snapshot,
                use_traffic_runtime=False,
                resources_override=resources,
                travel_times_cache=travel_times_cache,
                zone_nodes_cache=zone_nodes_cache,
                include_route_alternatives=False,
            )
        )
    except (NoFeasibleCandidateError, ValueError) as exc:
        return _error_result("SIRENGRID", exc)
    selected = ranked[0]
    proposal = reposition_proposals.get(selected.combination.resource_ids)
    result = EngineRunResult(
        engine="SIRENGRID",
        outcome="PLAN_GENERATED",
        resource_ids=selected.combination.resource_ids,
        incident_eta_seconds=selected.metrics.max_incident_eta_seconds,
        routes=tuple(
            responder.route.model_dump(mode="json")
            for responder in selected.combination.responders
        ),
        baseline_joint=selected.metrics.baseline_joint,
        post_dispatch_joint=selected.metrics.post_dispatch_joint,
        score=_score_to_dict(selected.score),
        reposition_proposal=_reposition_to_dict(proposal),
    )
    return replace(
        result,
        hospital=_hospital_result(
            graph=graph,
            resources=resources,
            scenario=scenario,
            primary=result,
            traffic_snapshot=traffic_snapshot,
            engine="SIRENGRID",
        ),
        replan=_replan_result(
            graph=graph,
            resources=resources,
            scenario=scenario,
            primary=result,
            traffic_snapshot=traffic_snapshot,
        ),
    )


def _apply_overrides(
    resources: tuple[CandidateResource, ...],
    overrides: Iterable[Any],
) -> tuple[CandidateResource, ...]:
    by_id = {resource.resource_id: resource for resource in resources}
    for override in overrides:
        current = by_id.get(override.resource_id)
        if current is None:
            raise ValueError(f"Scenario event references unknown resource {override.resource_id}")
        by_id[override.resource_id] = replace(
            current,
            status=override.status if override.status is not None else current.status,
            assigned_incident_id=(
                override.assigned_incident_id
                if "assigned_incident_id" in override.model_fields_set
                else current.assigned_incident_id
            ),
            coordinate=replace(
                current.coordinate,
                lat=override.latitude
                if override.latitude is not None
                else current.coordinate.lat,
                lon=override.longitude
                if override.longitude is not None
                else current.coordinate.lon,
            ),
            capability_tags=(
                tuple(override.capability_tags)
                if override.capability_tags is not None
                else current.capability_tags
            ),
        )
    return tuple(sorted(by_id.values(), key=lambda resource: resource.resource_id))


def _commit_primary_resources(
    resources: tuple[CandidateResource, ...],
    primary: EngineRunResult,
    scenario_id: str,
) -> tuple[CandidateResource, ...]:
    committed = set(primary.resource_ids)
    if primary.outcome != "PLAN_GENERATED":
        return resources
    updated = [
        (
            replace(
                resource,
                status=ResourceStatus.ASSIGNED,
                assigned_incident_id=f"phase08-{scenario_id}-primary",
            )
            if resource.resource_id in committed
            else resource
        )
        for resource in resources
    ]
    return tuple(sorted(updated, key=lambda resource: resource.resource_id))


class Phase08ScenarioRunner:
    """Run scenarios from immutable shared assets and isolated inputs."""

    def __init__(
        self,
        *,
        graph: nx.Graph | None = None,
        zones: tuple[CoverageZone, ...] | None = None,
        manifest: BenchmarkManifest | None = None,
        manifest_path: Path | str = DEFAULT_SCENARIO_MANIFEST,
        resource_seed_path: Path | str | None = None,
    ) -> None:
        self.graph = graph if graph is not None else load_routing_graph()
        self.zones = zones if zones is not None else load_population_zones(DEFAULT_PHASE08_POPULATION_ZONES)
        self.manifest = manifest if manifest is not None else load_scenario_manifest(manifest_path)
        self.resource_seed_path = resource_seed_path
        self._travel_times_cache: dict[tuple[Any, ...], Any] = {}
        self._zone_nodes_cache: dict[tuple[Any, ...], Any] = {}

    def run_scenario(self, scenario: BenchmarkScenario) -> dict[str, Any]:
        resources = build_candidate_resources(
            scenario,
            seed_path=self.resource_seed_path
            if self.resource_seed_path is not None
            else REPO_ROOT / "data" / "scenarios" / "phase01_resources.json",
        )
        traffic_snapshot = build_fixed_traffic_snapshot(
            self.graph,
            scenario.traffic_fixture,
        )
        baseline_started = time.perf_counter()
        baseline = _baseline_result(
            graph=self.graph,
            zones=self.zones,
            resources=resources,
            scenario=scenario,
            traffic_snapshot=traffic_snapshot,
            travel_times_cache=self._travel_times_cache,
            zone_nodes_cache=self._zone_nodes_cache,
        )
        baseline_wall_clock = time.perf_counter() - baseline_started
        sirengrid_started = time.perf_counter()
        sirengrid = _sirengrid_result(
            graph=self.graph,
            zones=self.zones,
            resources=resources,
            scenario=scenario,
            traffic_snapshot=traffic_snapshot,
            travel_times_cache=self._travel_times_cache,
            zone_nodes_cache=self._zone_nodes_cache,
        )
        sirengrid_wall_clock = time.perf_counter() - sirengrid_started
        secondary: list[dict[str, Any]] = []
        for event in sorted(scenario.events, key=lambda item: (item.at_seconds, item.event_index)):
            if event.event_type == "RESOURCE_STATE":
                resources = _apply_overrides(resources, event.resource_overrides)
                continue
            if event.event_type != "SECOND_INCIDENT" or event.incident is None:
                continue
            primary_by_engine = {baseline.engine: baseline, sirengrid.engine: sirengrid}
            event_resources_by_engine = {
                engine: _commit_primary_resources(resources, result, scenario.id)
                for engine, result in primary_by_engine.items()
            }
            event_scenario = scenario.model_copy(update={"incident": event.incident, "events": []})
            secondary.append(
                {
                    "event_index": event.event_index,
                    "at_seconds": event.at_seconds,
                    "baseline": _baseline_result(
                        graph=self.graph,
                        zones=self.zones,
                        resources=event_resources_by_engine["BASELINE"],
                        scenario=event_scenario,
                        traffic_snapshot=traffic_snapshot,
                        travel_times_cache=self._travel_times_cache,
                        zone_nodes_cache=self._zone_nodes_cache,
                    ).to_dict(),
                    "sirengrid": _sirengrid_result(
                        graph=self.graph,
                        zones=self.zones,
                        resources=event_resources_by_engine["SIRENGRID"],
                        scenario=event_scenario,
                        traffic_snapshot=traffic_snapshot,
                        travel_times_cache=self._travel_times_cache,
                        zone_nodes_cache=self._zone_nodes_cache,
                    ).to_dict(),
                }
            )
        return {
            "scenario_id": scenario.id,
            "seed": scenario.seed,
            "master_plan_case": scenario.master_plan_case,
            "expected": scenario.expected.model_dump(mode="json"),
            "traffic_fixture": {
                **scenario.traffic_fixture.model_dump(mode="json"),
                "benchmark_reality": DataReality.SYNTHETIC.value,
                "snapshot_id": traffic_snapshot.snapshot_id if traffic_snapshot else None,
            },
            "baseline": baseline.to_dict(),
            "sirengrid": sirengrid.to_dict(),
            "wall_clock_seconds": {
                "baseline": baseline_wall_clock,
                "sirengrid": sirengrid_wall_clock,
            },
            "secondary_incidents": secondary,
            "model_timestamp": PHASE08_FIXED_MODEL_TIME.isoformat(),
        }

    def run_all(self) -> list[dict[str, Any]]:
        return [self.run_scenario(scenario) for scenario in self.manifest.scenarios]


def write_json(path: Path | str, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
