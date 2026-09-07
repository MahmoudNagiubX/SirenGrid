from __future__ import annotations

from app.materiality import (
    REPLAN_MATERIALITY_POLICY_VERSION,
    build_replan_input_fingerprint,
    evaluate_replan_materiality,
)
from app.incidents import serialize_incident
from app.models import Incident
from app.schemas import ConfidenceLevel, IncidentStatus, Severity
from app.replanning import materiality_for_trigger


def test_eta_materiality_uses_inclusive_absolute_and_percentage_boundaries() -> None:
    below = evaluate_replan_materiality(
        old_eta_seconds=400,
        new_eta_seconds=459,
    )
    absolute_boundary = evaluate_replan_materiality(
        old_eta_seconds=400,
        new_eta_seconds=460,
    )
    percentage_boundary = evaluate_replan_materiality(
        old_eta_seconds=400,
        new_eta_seconds=460,
    )

    assert below.material is False
    assert absolute_boundary.material is True
    assert "ETA_DETERIORATED_ABSOLUTE" in absolute_boundary.reasons
    assert "ETA_DETERIORATED_PERCENT" in percentage_boundary.reasons


def test_eta_improvement_alone_is_not_material() -> None:
    result = evaluate_replan_materiality(old_eta_seconds=500, new_eta_seconds=400)

    assert result.material is False
    assert result.reasons == ()


def test_route_overlap_boundary_and_closure_policy() -> None:
    exact = evaluate_replan_materiality(route_edge_overlap_ratio=0.80)
    below = evaluate_replan_materiality(route_edge_overlap_ratio=0.7999)
    closed = evaluate_replan_materiality(
        route_edge_overlap_ratio=0.95,
        active_route_closure=True,
    )

    assert exact.material is False
    assert below.material is True
    assert "ROUTE_EDGE_OVERLAP_DEGRADED" in below.reasons
    assert closed.material is True
    assert "ACTIVE_ROUTE_CLOSURE" in closed.reasons


def test_coverage_materiality_uses_joint_rules() -> None:
    exact_drop = evaluate_replan_materiality(joint_coverage_drop=0.05)
    small_drop = evaluate_replan_materiality(joint_coverage_drop=0.049)
    newly_undercovered = evaluate_replan_materiality(
        newly_joint_undercovered=True,
    )

    assert exact_drop.material is True
    assert "JOINT_COVERAGE_DROP" in exact_drop.reasons
    assert small_drop.material is False
    assert newly_undercovered.material is True


def test_confirmed_hard_triggers_are_material_but_unknown_is_not() -> None:
    hard = evaluate_replan_materiality(
        route_unreachable=True,
        required_resource_unavailable=True,
        resource_assignment_conflict=True,
        requirements_changed=True,
        hospital_not_accepting=True,
        hospital_unreachable=True,
        contention_resource_unavailable=True,
    )
    unknown_only = evaluate_replan_materiality(unknown_state=True)

    assert hard.material is True
    assert len(hard.reasons) == 7
    assert unknown_only.material is False
    assert unknown_only.reasons == ()


def test_geometry_overlap_is_used_when_edge_identity_is_unavailable() -> None:
    result = evaluate_replan_materiality(
        route_edge_overlap_ratio=None,
        route_geometry_overlap_ratio=0.79,
    )

    assert result.material is True
    assert "ROUTE_GEOMETRY_OVERLAP_DEGRADED" in result.reasons


def test_replan_fingerprint_is_order_independent_and_policy_bound() -> None:
    first = build_replan_input_fingerprint(
        active_plan_id="plan-a",
        incident_version=4,
        trigger_facts={"resource_ids": ["r-2", "r-1"], "reason": "RESOURCE_UNAVAILABLE"},
        input_references={"traffic_snapshot_id": "traffic-1", "resource_version": 3},
    )
    second = build_replan_input_fingerprint(
        active_plan_id="plan-a",
        incident_version=5,
        trigger_facts={"reason": "RESOURCE_UNAVAILABLE", "resource_ids": ["r-1", "r-2"]},
        input_references={"resource_version": 3, "traffic_snapshot_id": "traffic-1"},
    )

    assert first == second
    assert len(first) == 64
    assert REPLAN_MATERIALITY_POLICY_VERSION == "SIRENGRID_REPLAN_MATERIALITY_V1"


def test_incident_exposes_pending_replan_without_repointing_active_plan() -> None:
    incident = Incident(
        id="incident-1",
        version=7,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.05,
        longitude=31.34,
        current_plan_id="approved-plan",
        pending_replan_plan_id="replacement-plan",
    )

    serialized = serialize_incident(incident)

    assert serialized["current_plan_id"] == "approved-plan"
    assert serialized["pending_replan_plan_id"] == "replacement-plan"


def test_trigger_reason_facts_are_mapped_to_confirmed_materiality() -> None:
    result = materiality_for_trigger(
        reasons=["TRAFFIC_CHANGED"],
        references={
            "old_eta_seconds": 400,
            "new_eta_seconds": 460,
            "route_edge_overlap_ratio": 0.95,
        },
    )

    assert result.material is True
    assert "ETA_DETERIORATED_ABSOLUTE" in result.reasons
