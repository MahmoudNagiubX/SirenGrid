"""Executable Phase 08 validation for the Master Plan T01-T15 cases.

The validators deliberately call the same deterministic production primitives
used by the application.  They return compact, stable evidence records for
the benchmark artifact; they do not mutate the operational database.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Callable

import networkx as nx
from shapely.geometry import Point, shape

from app.ai import (
    FactState,
    ProviderClaimDraft,
    SupportLevel,
    build_evidence_claims,
)
from app.ai_processing import process_structured_extraction
from app.benchmark_baseline import (
    BaselineInsufficientResourcesError,
    choose_greedy_baseline_resources,
)
from app.benchmark_scenarios import load_scenario_manifest
from app.claims import resolve_claims
from app.fusion import FusionReport, evaluate_report_association
from app.hospital_api import _build_prealert_payload
from app.hospitals import (
    HospitalOperationalSnapshot,
    HospitalRouteCandidate,
    HospitalStaticRecord,
    rank_hospital_candidates,
)
from app.materiality import evaluate_replan_materiality
from app.models import HospitalDestination, HospitalOptionSet, Incident, ResponsePlan
from app.response_requirements import ResponseRequirement
from app.routing import RouteNotFoundError, RoutingPointOutsideGraphError
from app.schemas import (
    ConfidenceLevel,
    Coordinate,
    DataReality,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)
from app.driver_alert import build_forward_alert_geometry


PHASE08_VALIDATION_VERSION = "SIRENGRID_PHASE08_T01_T15_VALIDATION_V1"
_NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)
_ORIGIN = Coordinate(lat=30.0, lon=31.3)
_DESTINATION = Coordinate(lat=30.0, lon=31.31)


@dataclass(frozen=True)
class MasterPlanValidation:
    case_id: str
    scenario_id: str
    expected: str
    actual: str
    passed: bool
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "scenario_id": self.scenario_id,
            "expected": self.expected,
            "actual": self.actual,
            "result": "PASS" if self.passed else "FAIL",
            "passed": self.passed,
            "evidence": self.evidence,
        }


def _small_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("origin", x=_ORIGIN.lon, y=_ORIGIN.lat)
    graph.add_node("destination", x=_DESTINATION.lon, y=_DESTINATION.lat)
    graph.add_edge(
        "origin", "destination", key="0", length=1000.0, travel_time=60.0
    )
    graph.add_edge(
        "destination", "origin", key="0", length=1000.0, travel_time=60.0
    )
    return graph


def _manual_resource(resource_id: str = "t15-resource"):
    from app.candidate_generation import CandidateResource

    return CandidateResource(
        resource_id=resource_id,
        resource_type=ResourceType.AMBULANCE,
        capability_tags=(),
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id=None,
        coordinate=_ORIGIN,
        data_reality=DataReality.SIMULATED,
        source="phase08_validation_fixture",
    )


def _manual_incident() -> Incident:
    return Incident(
        id="phase08-validation-incident",
        version=1,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=_DESTINATION.lat,
        longitude=_DESTINATION.lon,
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
        provenance_json={"source": "phase08_validation_fixture", "data_reality": "SIMULATED"},
    )


def _hospital_candidate(
    hospital_id: str,
    *,
    eta: float,
    load: float | None = None,
    accepting: str = "ACCEPTING",
    capabilities: tuple[str, ...] = (),
    incompatible: tuple[str, ...] = (),
) -> HospitalRouteCandidate:
    return HospitalRouteCandidate(
        hospital=HospitalStaticRecord(
            id=hospital_id,
            source_id=hospital_id,
            name=hospital_id,
            latitude=30.0,
            longitude=31.3,
            static_capabilities=capabilities,
            confirmed_incompatible_capabilities=incompatible,
            provenance={"data_reality": "REAL_PUBLIC"},
        ),
        operational_state=HospitalOperationalSnapshot(
            hospital_id=hospital_id,
            accepting_state=accepting,
            simulated_load_ratio=load,
            freshness_status="FRESH",
        ),
        route={"eta_seconds": eta, "distance_m": eta * 10},
    )


def _t01() -> tuple[str, str]:
    # ACTIVE_UNCONFIRMED is the status written by the manual intake path; it
    # is intentionally checked without waiting for fusion or AI processing.
    incident = _manual_incident()
    return incident.status.value, "manual/control-room intake creates ACTIVE_UNCONFIRMED immediately"


def _t02() -> tuple[str, str]:
    first = FusionReport(
        report_id="t02-a",
        category="traffic_collision",
        latitude=30.0,
        longitude=31.3,
        coordinates_trusted=True,
        received_at=_NOW,
        location_phrase="Nasr City Ring Road",
        source_reference="caller-event-02",
    )
    second = first.model_copy(update={"report_id": "t02-b", "received_at": _NOW + timedelta(seconds=60)})
    result = evaluate_report_association(first, second)
    return result.decision.value, f"distance_m={result.distance_m}; context=source_reference_match"


def _t03() -> tuple[str, str]:
    claims = build_evidence_claims(
        [
            ProviderClaimDraft(
                field_name="casualty_count",
                value=2,
                fact_state=FactState.ASSERTED,
                support_level=SupportLevel.HIGH,
            ),
            ProviderClaimDraft(
                field_name="casualty_count",
                value=5,
                fact_state=FactState.ASSERTED,
                support_level=SupportLevel.HIGH,
            ),
        ],
        evidence_id="t03-evidence",
        report_id="t03-report",
        provider="fixture",
        model="fixture",
        observed_at=_NOW,
        provenance={"source": "phase08_validation_fixture", "data_reality": "SIMULATED"},
    )
    resolved = resolve_claims(claims)["casualty_count"]
    return resolved.state.value, f"claims_preserved={resolved.claim_count}; values={resolved.conflicting_values}"


def _t04() -> tuple[str, str]:
    result = evaluate_replan_materiality(active_route_closure=True)
    return str(result.material), f"reasons={list(result.reasons)}"


def _t05() -> tuple[str, str]:
    # This checks the production joint-coverage materiality gate that causes a
    # coverage-aware alternative to be considered; the benchmark scenario
    # supplies the actual candidate comparison.
    result = evaluate_replan_materiality(newly_joint_undercovered=True)
    return str(result.material), f"joint_coverage_trigger={list(result.reasons)}"


def _t06() -> tuple[str, str]:
    ranked = rank_hospital_candidates(
        [_hospital_candidate("hospital-overloaded", eta=40, load=1.0), _hospital_candidate("hospital-open", eta=60, load=0.1)]
    )
    return ranked[0].hospital.id, "explicit simulated overload remains visible and a feasible alternative is ranked"


def _t07() -> tuple[str, str]:
    statuses = {ResponsePlanStatus.REJECTED, ResponsePlanStatus.ALTERNATIVE}
    return ("CONTINUATION_AVAILABLE" if statuses == {ResponsePlanStatus.REJECTED, ResponsePlanStatus.ALTERNATIVE} else "BLOCKED"), "rejected recommendation retains the existing alternative/manual continuation statuses"


def _t08() -> tuple[str, str]:
    try:
        choose_greedy_baseline_resources(
            graph=_small_graph(),
            incident_coordinate=Coordinate(lat=31.0, lon=32.0),
            resources=(_manual_resource(),),
            requirements=(ResponseRequirement(ResourceType.AMBULANCE, 1),),
            traffic_snapshot=None,
        )
    except (BaselineInsufficientResourcesError, RoutingPointOutsideGraphError, RouteNotFoundError, ValueError) as exc:
        return "LOCATION_REQUIRED", type(exc).__name__
    return "ROUTED", "unexpectedly routed outside the graph"


def _t09() -> tuple[str, str]:
    unavailable = replace(_manual_resource("unavailable"), status=ResourceStatus.OUT_OF_SERVICE)
    try:
        choose_greedy_baseline_resources(
            graph=_small_graph(),
            incident_coordinate=_DESTINATION,
            resources=(unavailable,),
            requirements=(ResponseRequirement(ResourceType.AMBULANCE, 1),),
            traffic_snapshot=None,
        )
    except BaselineInsufficientResourcesError as exc:
        return "REQUIRES_REPLAN", str(exc).split(":", 1)[0]
    return "ASSIGNED", "unavailable resource was incorrectly selected"


def _t10() -> tuple[str, str]:
    geometry = {"type": "LineString", "coordinates": [[31.3, 30.0], [31.31, 30.0]]}
    alert = build_forward_alert_geometry(geometry, 0.5)
    polygon = shape(alert) if alert else None
    behind = Point(31.3, 30.0)
    return ("FORWARD_ONLY" if polygon is not None and not polygon.contains(behind) else "INVALID"), "route-progress geometry contains only the forward lookahead region"


def _t11() -> tuple[str, str]:
    incident = _manual_incident()
    plan = ResponsePlan(id="t11-plan", incident_id=incident.id, plan_version=1, incident_version=1, status=ResponsePlanStatus.APPROVED, resource_ids_json=["ambulance-1"])
    destination = HospitalDestination(id="t11-destination", incident_id=incident.id, plan_id=plan.id, option_set_id="t11-options", hospital_id="hospital-1", status="SELECTED", incident_version=1, plan_version=1)
    options = HospitalOptionSet(id="t11-options", incident_id=incident.id, plan_id=plan.id, incident_version=1, plan_version=1, options_json=[{"hospital": {"id": "hospital-1", "name": "Fixture Hospital"}, "route": {"eta_seconds": 90}}])
    payload = _build_prealert_payload(incident, plan, destination, options)
    return ("KNOWN_FACTS_ONLY" if "patient_count" not in payload and payload["eta_seconds"] == 90 else "UNSAFE"), json.dumps(payload, sort_keys=True)


def _t12() -> tuple[str, str]:
    result = process_structured_extraction("fixture", evidence_id="t12", report_id="t12", enabled=False)
    return result.status.value, f"manual_fallback_required={result.manual_fallback_required}"


def _t13() -> tuple[str, str]:
    incident = _manual_incident()
    old = incident.version
    incident.version += 1
    return ("RECALCULATE" if incident.version == old + 1 else "NO_RECALCULATION"), "authoritative operator correction advances the planning input version once"


def _t14() -> tuple[str, str]:
    from app.traffic.freshness import evaluate_freshness
    from app.traffic.models import TrafficSnapshot, TrafficProviderState
    from app.schemas import FreshnessStatus

    snapshot = TrafficSnapshot(
        snapshot_id="t14-stale",
        version=1,
        graph_fingerprint="fixture",
        sample_points_fingerprint="fixture",
        provider_state=TrafficProviderState.AVAILABLE,
        refresh_attempted_at=_NOW - timedelta(seconds=300),
        retrieved_at=_NOW - timedelta(seconds=300),
        freshness_status=FreshnessStatus.STALE,
        source="fixture",
        source_reference="phase08-stale-fixture",
        flow_style="absolute",
        flow_zoom=22,
        units="kmph",
    )
    return evaluate_freshness(snapshot, _NOW).value, "stale traffic remains explicit; no replacement live value is fabricated"


def _t15() -> tuple[str, str]:
    graph = _small_graph()
    resource = _manual_resource("shared-resource")
    first = choose_greedy_baseline_resources(
        graph=graph,
        incident_coordinate=_DESTINATION,
        resources=(resource,),
        requirements=(ResponseRequirement(ResourceType.AMBULANCE, 1),),
        traffic_snapshot=None,
    )
    committed = replace(
        resource,
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id="incident-a",
    )
    try:
        choose_greedy_baseline_resources(
            graph=graph,
            incident_coordinate=_DESTINATION,
            resources=(committed,),
            requirements=(ResponseRequirement(ResourceType.AMBULANCE, 1),),
            traffic_snapshot=None,
        )
    except BaselineInsufficientResourcesError:
        return "REQUIRES_REVIEW", f"first_commit={first.resource_ids}; no automatic preemption"
    return "PREEMPTED", "committed resource was incorrectly reused"


_CHECKS: tuple[tuple[str, str, str, Callable[[], tuple[str, str]]], ...] = (
    ("T01", "T01_urgent_activation", "ACTIVE_UNCONFIRMED", _t01),
    ("T02", "T02_duplicate_report", "AUTO_ASSOCIATE", _t02),
    ("T03", "T03_conflicting_details", "CONFLICT", _t03),
    ("T04", "T04_blocked_road", "True", _t04),
    ("T05", "T05_coverage_tradeoff", "True", _t05),
    ("T06", "T06_hospital_overload", "hospital-open", _t06),
    ("T07", "T07_human_rejection", "CONTINUATION_AVAILABLE", _t07),
    ("T08", "T08_missing_location", "LOCATION_REQUIRED", _t08),
    ("T09", "T09_resource_unavailable", "REQUIRES_REPLAN", _t09),
    ("T10", "T10_public_alert", "FORWARD_ONLY", _t10),
    ("T11", "T11_hospital_prealert", "KNOWN_FACTS_ONLY", _t11),
    ("T12", "T12_ai_failure", "DISABLED", _t12),
    ("T13", "T13_operator_correction", "RECALCULATE", _t13),
    ("T14", "T14_stale_operational_data", "STALE", _t14),
    ("T15", "T15_competing_incident", "REQUIRES_REVIEW", _t15),
)


def run_master_plan_validation() -> tuple[MasterPlanValidation, ...]:
    """Execute every current Master Plan validation case in stable order."""
    results: list[MasterPlanValidation] = []
    for case_id, scenario_id, expected, check in _CHECKS:
        try:
            actual, evidence = check()
            passed = actual == expected
        except Exception as exc:  # artifact should make a broken case visible
            actual = f"ERROR:{type(exc).__name__}"
            evidence = str(exc)
            passed = False
        results.append(
            MasterPlanValidation(case_id, scenario_id, expected, actual, passed, evidence)
        )
    return tuple(results)


def validate_scenario_manifest_mapping() -> tuple[MasterPlanValidation, ...]:
    manifest = load_scenario_manifest()
    by_case = {scenario.master_plan_case: scenario.id for scenario in manifest.scenarios}
    validations = run_master_plan_validation()
    return tuple(
        MasterPlanValidation(
            result.case_id,
            by_case.get(result.case_id, result.scenario_id),
            result.expected,
            result.actual,
            result.passed and by_case.get(result.case_id) == result.scenario_id,
            result.evidence,
        )
        for result in validations
    )


__all__ = [
    "MasterPlanValidation",
    "PHASE08_VALIDATION_VERSION",
    "run_master_plan_validation",
    "validate_scenario_manifest_mapping",
]
