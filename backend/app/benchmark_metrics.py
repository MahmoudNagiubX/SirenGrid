"""Pure aggregation helpers for reproducible Phase 08 benchmark outputs."""

from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Iterable, Sequence

from app.benchmark_runner import EngineRunResult


def percentile(values: Sequence[float], quantile: float) -> float:
    """Return a deterministic linearly interpolated percentile."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("percentile quantile must be between zero and one")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _stats(values: Iterable[float | None]) -> dict[str, float | int]:
    materialized = tuple(values)
    cleaned = [float(value) for value in materialized if value is not None]
    total_count = len(materialized)
    result: dict[str, float | int] = {
        "total_count": total_count,
        "available_count": len(cleaned),
        "missing_count": total_count - len(cleaned),
        "availability_rate": len(cleaned) / total_count if total_count else 0.0,
    }
    if not cleaned:
        return result
    result.update(
        {
            "mean": mean(cleaned),
            "median": median(cleaned),
            "min": min(cleaned),
            "max": max(cleaned),
        }
    )
    if len(cleaned) >= 20:
        result["p95"] = percentile(cleaned, 0.95)
    return result


def aggregate_engine_results(results: Iterable[EngineRunResult]) -> dict[str, object]:
    """Aggregate one engine's raw scenario results without inventing values."""
    materialized = tuple(results)
    outcome_counts = Counter(result.outcome for result in materialized)
    expected_outcome_pass_count = sum(
        result.outcome == result.expected_outcome for result in materialized
    )
    aggregate: dict[str, object] = {
        "count": len(materialized),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "workflow": {
            "scenario_count": len(materialized),
            "outcome_counts": dict(sorted(outcome_counts.items())),
            "expected_outcome_pass_count": expected_outcome_pass_count,
            "unexpected_failure_count": len(materialized)
            - expected_outcome_pass_count,
            "workflow_success_rate": (
                expected_outcome_pass_count / len(materialized) if materialized else 0.0
            ),
        },
        "incident_eta_seconds": _stats(
            result.incident_eta_seconds for result in materialized
        ),
    }
    for field_name, value_getter in (
        (
            "baseline_population_weighted_coverage",
            lambda result: (
                result.baseline_joint.population_weighted_coverage
                if result.baseline_joint is not None
                else None
            ),
        ),
        (
            "post_dispatch_population_weighted_coverage",
            lambda result: (
                result.post_dispatch_joint.population_weighted_coverage
                if result.post_dispatch_joint is not None
                else None
            ),
        ),
        (
            "post_dispatch_undercovered_zone_count",
            lambda result: (
                float(result.post_dispatch_joint.undercovered_zone_count)
                if result.post_dispatch_joint is not None
                else None
            ),
        ),
        (
            "post_dispatch_unreachable_zone_count",
            lambda result: (
                float(result.post_dispatch_joint.unreachable_zone_count)
                if result.post_dispatch_joint is not None
                else None
            ),
        ),
    ):
        aggregate[field_name] = _stats(
            value_getter(result) for result in materialized
        )
    return aggregate


def compare_metric_change(
    baseline_values: Sequence[float | None],
    sirengrid_values: Sequence[float | None],
) -> dict[str, object]:
    """Compare only paired values while reporting each engine's availability."""
    if len(baseline_values) != len(sirengrid_values):
        raise ValueError("paired metric sequences must have the same scenario count")
    paired = [
        (baseline, sirengrid)
        for baseline, sirengrid in zip(baseline_values, sirengrid_values, strict=True)
        if baseline is not None and sirengrid is not None
    ]
    baseline = _stats(baseline_values)
    sirengrid = _stats(sirengrid_values)
    paired_baseline = _stats(value for value, _ in paired)
    paired_sirengrid = _stats(value for _, value in paired)
    result: dict[str, object] = {
        "baseline": baseline,
        "sirengrid": sirengrid,
        "paired_baseline": paired_baseline,
        "paired_sirengrid": paired_sirengrid,
        "paired_count": len(paired),
        "unpaired_baseline_only_count": sum(
            baseline_value is not None and sirengrid_value is None
            for baseline_value, sirengrid_value in zip(
                baseline_values, sirengrid_values, strict=True
            )
        ),
        "unpaired_sirengrid_only_count": sum(
            baseline_value is None and sirengrid_value is not None
            for baseline_value, sirengrid_value in zip(
                baseline_values, sirengrid_values, strict=True
            )
        ),
        "both_missing_count": sum(
            baseline_value is None and sirengrid_value is None
            for baseline_value, sirengrid_value in zip(
                baseline_values, sirengrid_values, strict=True
            )
        ),
    }
    denominator = paired_baseline.get("median")
    numerator = paired_sirengrid.get("median")
    if isinstance(denominator, (int, float)) and denominator != 0 and isinstance(
        numerator, (int, float)
    ):
        result["median_percent_change"] = (numerator - denominator) / denominator * 100
    else:
        result["median_percent_change"] = None
    return result
