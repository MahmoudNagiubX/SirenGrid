from __future__ import annotations

import pytest

from app.benchmark_metrics import (
    aggregate_engine_results,
    aggregate_raw_engine_results,
    performance_aggregate,
    percentile,
)
from app.benchmark_runner import EngineRunResult


def test_aggregate_reports_only_present_metrics_and_separates_outcomes() -> None:
    results = [
        EngineRunResult(
            engine="BASELINE",
            outcome="PLAN_GENERATED",
            incident_eta_seconds=10.0,
        ),
        EngineRunResult(
            engine="BASELINE",
            outcome="INSUFFICIENT_RESOURCES",
            error="visible expected failure",
        ),
        EngineRunResult(
            engine="BASELINE",
            outcome="REQUIRES_REVIEW",
        ),
    ]

    aggregate = aggregate_engine_results(results)

    assert aggregate["count"] == 3
    assert aggregate["outcome_counts"] == {
        "INSUFFICIENT_RESOURCES": 1,
        "PLAN_GENERATED": 1,
        "REQUIRES_REVIEW": 1,
    }
    assert aggregate["incident_eta_seconds"] == {
        "available_count": 1,
        "mean": 10.0,
        "median": 10.0,
        "min": 10.0,
        "max": 10.0,
    }
    assert "population_weighted_coverage" not in aggregate


def test_percentile_rejects_empty_values_and_is_deterministic() -> None:
    with pytest.raises(ValueError, match="at least one"):
        percentile((), 0.95)

    assert percentile((10.0, 20.0, 30.0, 40.0), 0.95) == pytest.approx(38.5)


def test_raw_aggregation_omits_unavailable_metrics_and_counts_outcomes() -> None:
    raw = [
        {
            "baseline": {
                "outcome": "PLAN_GENERATED",
                "incident_eta_seconds": 10,
                "post_dispatch_joint": {"population_weighted_coverage": 0.5},
            }
        },
        {"baseline": {"outcome": "INSUFFICIENT_RESOURCES", "incident_eta_seconds": None}},
    ]

    aggregate = aggregate_raw_engine_results(raw, "BASELINE")

    assert aggregate["count"] == 2
    assert aggregate["outcome_counts"] == {"INSUFFICIENT_RESOURCES": 1, "PLAN_GENERATED": 1}
    assert aggregate["incident_eta_seconds"]["available_count"] == 1
    assert aggregate["post_dispatch_population_weighted_coverage"]["median"] == 0.5


def test_performance_aggregation_retains_three_repetition_samples() -> None:
    raw = [
        {"scenario_id": "A", "wall_clock_seconds": {"baseline": 1.0, "sirengrid": 2.0}},
        {"scenario_id": "B", "wall_clock_seconds": {"baseline": 3.0, "sirengrid": 4.0}},
        {"scenario_id": "C", "wall_clock_seconds": {"baseline": 5.0, "sirengrid": 6.0}},
    ]

    aggregate = performance_aggregate(raw, "BASELINE")

    assert aggregate == {
        "available_count": 3,
        "mean": 3.0,
        "median": 3.0,
        "min": 1.0,
        "max": 5.0,
    }
