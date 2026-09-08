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


def _stats(values: Iterable[float]) -> dict[str, float | int]:
    cleaned = [float(value) for value in values]
    if not cleaned:
        return {"available_count": 0}
    result: dict[str, float | int] = {
        "available_count": len(cleaned),
        "mean": mean(cleaned),
        "median": median(cleaned),
        "min": min(cleaned),
        "max": max(cleaned),
    }
    if len(cleaned) >= 20:
        result["p95"] = percentile(cleaned, 0.95)
    return result


def aggregate_engine_results(results: Iterable[EngineRunResult]) -> dict[str, object]:
    """Aggregate one engine's raw scenario results without inventing values."""
    materialized = tuple(results)
    outcome_counts = Counter(result.outcome for result in materialized)
    aggregate: dict[str, object] = {
        "count": len(materialized),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "incident_eta_seconds": _stats(
            result.incident_eta_seconds
            for result in materialized
            if result.incident_eta_seconds is not None
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
            value
            for result in materialized
            if (value := value_getter(result)) is not None
        )
    return aggregate


def compare_metric_change(
    baseline_values: Sequence[float],
    sirengrid_values: Sequence[float],
) -> dict[str, object]:
    """Return absolute medians and a percentage only with a valid denominator."""
    baseline = _stats(baseline_values)
    sirengrid = _stats(sirengrid_values)
    result: dict[str, object] = {
        "baseline": baseline,
        "sirengrid": sirengrid,
    }
    denominator = baseline.get("median")
    numerator = sirengrid.get("median")
    if isinstance(denominator, (int, float)) and denominator != 0 and isinstance(
        numerator, (int, float)
    ):
        result["median_percent_change"] = (numerator - denominator) / denominator * 100
    else:
        result["median_percent_change"] = None
    return result


def aggregate_raw_engine_results(
    raw_results: Iterable[dict[str, object]],
    engine: str,
) -> dict[str, object]:
    """Aggregate serialized scenario results without filling missing values."""
    key = engine.casefold()
    entries = [
        result[key]
        for result in raw_results
        if isinstance(result.get(key), dict)
    ]
    outcomes = Counter(
        str(entry.get("outcome")) for entry in entries if entry.get("outcome")
    )

    def values(path: tuple[str, ...]) -> list[float]:
        found: list[float] = []
        for entry in entries:
            current: object = entry
            for part in path:
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(part)
            if isinstance(current, (int, float)) and not isinstance(current, bool):
                found.append(float(current))
        return found

    aggregate: dict[str, object] = {
        "count": len(entries),
        "outcome_counts": dict(sorted(outcomes.items())),
    }
    for field_name, path in (
        ("incident_eta_seconds", ("incident_eta_seconds",)),
        (
            "baseline_population_weighted_coverage",
            ("baseline_joint", "population_weighted_coverage"),
        ),
        (
            "post_dispatch_population_weighted_coverage",
            ("post_dispatch_joint", "population_weighted_coverage"),
        ),
        (
            "post_dispatch_undercovered_zone_count",
            ("post_dispatch_joint", "undercovered_zone_count"),
        ),
        (
            "post_dispatch_unreachable_zone_count",
            ("post_dispatch_joint", "unreachable_zone_count"),
        ),
    ):
        aggregate[field_name] = _stats(values(path))
    hospital_statuses = Counter(
        str(hospital.get("status"))
        for entry in entries
        if isinstance(hospital := entry.get("hospital"), dict)
        and hospital.get("status")
    )
    aggregate["hospital_status_counts"] = dict(sorted(hospital_statuses.items()))
    aggregate["hospital_eta_seconds"] = _stats(
        value
        for entry in entries
        if isinstance(hospital := entry.get("hospital"), dict)
        and isinstance(route := hospital.get("route"), dict)
        and isinstance(value := route.get("eta_seconds"), (int, float))
        and not isinstance(value, bool)
    )
    replan_statuses = Counter(
        str(replan.get("status"))
        for entry in entries
        if isinstance(replan := entry.get("replan"), dict)
        and replan.get("status")
    )
    aggregate["replan_status_counts"] = dict(sorted(replan_statuses.items()))
    aggregate["replan_eta_delta_seconds"] = _stats(
        value
        for entry in entries
        if isinstance(replan := entry.get("replan"), dict)
        and isinstance(value := replan.get("eta_delta_seconds"), (int, float))
        and not isinstance(value, bool)
    )
    return aggregate


def performance_aggregate(
    raw_results: Iterable[dict[str, object]],
    engine: str,
) -> dict[str, object]:
    """Aggregate retained wall-clock samples for one performance engine."""
    key = engine.casefold()
    values: list[float] = []
    for result in raw_results:
        timing = result.get("wall_clock_seconds")
        if isinstance(timing, dict):
            value = timing.get(key)
            if isinstance(value, (int, float)):
                values.append(float(value))
    return _stats(values)
