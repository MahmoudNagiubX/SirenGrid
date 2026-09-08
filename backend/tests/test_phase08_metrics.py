from __future__ import annotations

import pytest

from app.benchmark_metrics import aggregate_engine_results, percentile
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
