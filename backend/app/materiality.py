"""Deterministic Phase 07 material-change policy and input identity helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

REPLAN_MATERIALITY_POLICY_VERSION = "SIRENGRID_REPLAN_MATERIALITY_V1"
REPLAN_ETA_ABSOLUTE_INCREASE_SECONDS = 60.0
REPLAN_ETA_PERCENT_INCREASE = 0.15
REPLAN_ROUTE_EDGE_OVERLAP_THRESHOLD = 0.80
REPLAN_COVERAGE_DROP_TRIGGER = 0.05


@dataclass(frozen=True)
class ReplanMaterialityResult:
    material: bool
    reasons: tuple[str, ...]


def _validate_ratio(value: float | None, name: str) -> None:
    if value is None:
        return
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")


def evaluate_replan_materiality(
    *,
    old_eta_seconds: float | None = None,
    new_eta_seconds: float | None = None,
    route_edge_overlap_ratio: float | None = None,
    route_geometry_overlap_ratio: float | None = None,
    active_route_closure: bool = False,
    route_unreachable: bool = False,
    required_resource_unavailable: bool = False,
    resource_assignment_conflict: bool = False,
    requirements_changed: bool = False,
    hospital_not_accepting: bool = False,
    hospital_unreachable: bool = False,
    contention_resource_unavailable: bool = False,
    newly_joint_undercovered: bool = False,
    joint_coverage_drop: float | None = None,
    unknown_state: bool = False,
) -> ReplanMaterialityResult:
    """Evaluate the locked Phase 07 materiality policy.

    Only confirmed deterioration/failure facts should be passed as true. The
    function is deliberately pure so API and future event handlers share one
    auditable policy implementation.
    """
    _validate_ratio(route_edge_overlap_ratio, "route_edge_overlap_ratio")
    _validate_ratio(route_geometry_overlap_ratio, "route_geometry_overlap_ratio")
    if joint_coverage_drop is not None and joint_coverage_drop < 0.0:
        raise ValueError("joint_coverage_drop must be non-negative")

    reasons: list[str] = []
    if active_route_closure:
        reasons.append("ACTIVE_ROUTE_CLOSURE")
    if route_unreachable:
        reasons.append("ACTIVE_ROUTE_UNREACHABLE")
    if required_resource_unavailable:
        reasons.append("REQUIRED_RESOURCE_UNAVAILABLE")
    if resource_assignment_conflict:
        reasons.append("RESOURCE_ASSIGNMENT_CONFLICT")
    if requirements_changed:
        reasons.append("RESPONSE_REQUIREMENTS_CHANGED")
    if hospital_not_accepting:
        reasons.append("SELECTED_HOSPITAL_NOT_ACCEPTING")
    if hospital_unreachable:
        reasons.append("SELECTED_HOSPITAL_UNREACHABLE")
    if contention_resource_unavailable:
        reasons.append("MULTI_INCIDENT_CONTENTION")

    if old_eta_seconds is not None and new_eta_seconds is not None:
        delta = float(new_eta_seconds) - float(old_eta_seconds)
        if delta >= REPLAN_ETA_ABSOLUTE_INCREASE_SECONDS:
            reasons.append("ETA_DETERIORATED_ABSOLUTE")
        if old_eta_seconds > 0 and delta / float(old_eta_seconds) >= REPLAN_ETA_PERCENT_INCREASE:
            reasons.append("ETA_DETERIORATED_PERCENT")

    if route_edge_overlap_ratio is not None:
        if route_edge_overlap_ratio < REPLAN_ROUTE_EDGE_OVERLAP_THRESHOLD:
            reasons.append("ROUTE_EDGE_OVERLAP_DEGRADED")
    elif route_geometry_overlap_ratio is not None:
        if route_geometry_overlap_ratio < REPLAN_ROUTE_EDGE_OVERLAP_THRESHOLD:
            reasons.append("ROUTE_GEOMETRY_OVERLAP_DEGRADED")

    if newly_joint_undercovered:
        reasons.append("NEWLY_JOINT_UNDERCOVERED_ZONE")
    if joint_coverage_drop is not None and joint_coverage_drop >= REPLAN_COVERAGE_DROP_TRIGGER:
        reasons.append("JOINT_COVERAGE_DROP")

    # ``unknown_state`` is intentionally accepted for call-site clarity but
    # never adds a materiality reason under PD-041.
    _ = unknown_state
    return ReplanMaterialityResult(material=bool(reasons), reasons=tuple(reasons))


def _canonicalize(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            str(item_key): _canonicalize(item_value, key=str(item_key))
            for item_key, item_value in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        items = [_canonicalize(item) for item in value]
        if key and (
            key.endswith("_ids")
            or key.endswith("_reasons")
            or key in {"reason", "reasons", "resource_ids"}
        ):
            return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        return items
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def build_replan_input_fingerprint(
    *,
    active_plan_id: str,
    incident_version: int,
    trigger_facts: dict[str, Any],
    input_references: dict[str, Any],
) -> str:
    """Return a stable SHA-256 identity for one evaluated replan state."""
    payload = {
        "policy_version": REPLAN_MATERIALITY_POLICY_VERSION,
        "active_plan_id": active_plan_id,
        "trigger_facts": trigger_facts,
        "input_references": input_references,
    }
    # Incident version is validated separately. It changes when a replacement
    # is persisted, but does not change the underlying evaluated world state;
    # excluding it preserves idempotency for an identical repeat.
    _ = incident_version
    encoded = json.dumps(
        _canonicalize(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
