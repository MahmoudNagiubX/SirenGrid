from __future__ import annotations

import pytest

from app.benchmark_metrics import (
    aggregate_engine_results,
    compare_metric_change,
    percentile,
)
from app.benchmark_runner import EngineRunResult


def _result(
    index: int,
    *,
    eta: float | None,
    outcome: str = "PLAN_GENERATED",
    expected_outcome: str = "PLAN_GENERATED",
) -> EngineRunResult:
    return EngineRunResult(
        scenario_id=f"scenario-{index:02d}",
        engine="BASELINE",
        outcome=outcome,
        expected_outcome=expected_outcome,
        incident_eta_seconds=eta,
    )


def test_aggregate_reports_only_present_metrics_and_separates_outcomes() -> None:
    results = [
        _result(1, eta=10.0),
        _result(
            2,
            eta=None,
            outcome="INSUFFICIENT_RESOURCES",
            expected_outcome="INSUFFICIENT_RESOURCES",
        ),
        _result(3, eta=None, outcome="REQUIRES_REVIEW"),
    ]

    aggregate = aggregate_engine_results(results)

    assert aggregate["count"] == 3
    assert aggregate["workflow"] == {
        "scenario_count": 3,
        "outcome_counts": {
            "INSUFFICIENT_RESOURCES": 1,
            "PLAN_GENERATED": 1,
            "REQUIRES_REVIEW": 1,
        },
        "expected_outcome_pass_count": 2,
        "unexpected_failure_count": 1,
        "workflow_success_rate": pytest.approx(2 / 3),
    }
    assert aggregate["outcome_counts"] == {
        "INSUFFICIENT_RESOURCES": 1,
        "PLAN_GENERATED": 1,
        "REQUIRES_REVIEW": 1,
    }
    assert aggregate["incident_eta_seconds"] == {
        "total_count": 3,
        "available_count": 1,
        "missing_count": 2,
        "availability_rate": pytest.approx(1 / 3),
        "mean": 10.0,
        "median": 10.0,
        "min": 10.0,
        "max": 10.0,
    }
    assert "population_weighted_coverage" not in aggregate


@pytest.mark.parametrize(("available", "missing"), [(36, 0), (30, 6)])
def test_metric_summary_exposes_fixed_denominator(
    available: int,
    missing: int,
) -> None:
    aggregate = aggregate_engine_results(
        _result(index, eta=float(index) if index < available else None)
        for index in range(36)
    )

    summary = aggregate["incident_eta_seconds"]
    assert summary["total_count"] == 36
    assert summary["available_count"] == available
    assert summary["missing_count"] == missing
    assert summary["availability_rate"] == pytest.approx(available / 36)


def test_comparison_uses_only_paired_values_and_reports_unpaired_counts() -> None:
    comparison = compare_metric_change(
        [10.0, 20.0, None, None],
        [5.0, None, 30.0, None],
    )

    assert comparison["paired_count"] == 1
    assert comparison["unpaired_baseline_only_count"] == 1
    assert comparison["unpaired_sirengrid_only_count"] == 1
    assert comparison["both_missing_count"] == 1
    assert comparison["paired_baseline"]["median"] == 10.0
    assert comparison["paired_sirengrid"]["median"] == 5.0
    assert comparison["median_percent_change"] == -50.0


def test_availability_difference_remains_visible_when_subset_mean_looks_better() -> None:
    comparison = compare_metric_change([10.0, 10.0], [5.0, None])

    assert comparison["baseline"]["availability_rate"] == 1.0
    assert comparison["sirengrid"]["availability_rate"] == 0.5
    assert comparison["sirengrid"]["mean"] == 5.0
    assert comparison["paired_count"] == 1


def test_missing_values_do_not_create_numeric_penalties() -> None:
    summary = aggregate_engine_results(
        [_result(index, eta=None, outcome="INSUFFICIENT_RESOURCES") for index in range(36)]
    )["incident_eta_seconds"]

    assert summary == {
        "total_count": 36,
        "available_count": 0,
        "missing_count": 36,
        "availability_rate": 0.0,
    }


def test_zero_paired_baseline_denominator_has_no_percent_change() -> None:
    comparison = compare_metric_change([0.0, None], [5.0, 10.0])

    assert comparison["paired_count"] == 1
    assert comparison["median_percent_change"] is None


def test_percentile_rejects_empty_values_and_is_deterministic() -> None:
    with pytest.raises(ValueError, match="at least one"):
        percentile((), 0.95)

    assert percentile((10.0, 20.0, 30.0, 40.0), 0.95) == pytest.approx(38.5)
