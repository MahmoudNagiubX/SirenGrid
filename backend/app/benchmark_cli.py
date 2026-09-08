"""Command-line Phase 08 benchmark artifact generator."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import platform
from pathlib import Path
import subprocess
from typing import Any

from app.benchmark_metrics import aggregate_raw_engine_results, performance_aggregate
from app.benchmark_runner import DEFAULT_PHASE08_OUTPUT_DIR, Phase08ScenarioRunner, write_json
from app.benchmark_scenarios import PHASE08_BENCHMARK_POLICY_VERSION, PHASE08_DATASET_VERSION
from app.config import REPO_ROOT
from app.benchmark_validation import (
    PHASE08_VALIDATION_VERSION,
    validate_scenario_manifest_mapping,
)


PERFORMANCE_SCENARIO_IDS = (
    "T01_urgent_activation",
    "X02_multi_resource",
    "X04_reposition_useful",
    "X07_valid_closure",
    "X08_no_path",
    "X10_insufficient_resources",
    "X11_hospital_unknown",
    "X15_material_eta_replan",
    "X19_two_incidents_available",
    "T11_hospital_prealert",
)


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _commit_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _run_performance_subset(runner: Phase08ScenarioRunner) -> dict[str, Any]:
    selected = [
        scenario
        for scenario in runner.manifest.scenarios
        if scenario.id in PERFORMANCE_SCENARIO_IDS
    ]
    if len(selected) != len(PERFORMANCE_SCENARIO_IDS):
        raise ValueError("Performance subset must contain exactly ten scenarios")

    # Warm-up is intentionally discarded.  Each measured repetition gets a
    # fresh runner instance, while the scenario/asset inputs remain identical.
    for scenario in selected:
        Phase08ScenarioRunner().run_scenario(scenario)

    repetitions: list[dict[str, Any]] = []
    for repetition in range(1, 4):
        measured_runner = Phase08ScenarioRunner()
        for scenario in selected:
            result = measured_runner.run_scenario(scenario)
            repetitions.append(
                {
                    "repetition": repetition,
                    "scenario_id": scenario.id,
                    "wall_clock_seconds": result["wall_clock_seconds"],
                }
            )
    return {
        "scenario_ids": list(PERFORMANCE_SCENARIO_IDS),
        "warmup_excluded": True,
        "measured_repetitions": repetitions,
        "aggregate": {
            "baseline": performance_aggregate(repetitions, "BASELINE"),
            "sirengrid": performance_aggregate(repetitions, "SIRENGRID"),
        },
    }


def build_benchmark_artifacts(output_dir: Path = DEFAULT_PHASE08_OUTPUT_DIR) -> dict[str, Any]:
    runner = Phase08ScenarioRunner()
    raw_results = runner.run_all()
    mappings = [result.to_dict() for result in validate_scenario_manifest_mapping()]
    if not all(result["passed"] for result in mappings):
        raise RuntimeError("One or more Master Plan T01-T15 validations failed")

    expected_checks: list[dict[str, Any]] = []
    for result in raw_results:
        expected = result["expected"]
        actual = {
            "baseline": result["baseline"]["outcome"],
            "sirengrid": result["sirengrid"]["outcome"],
        }
        expected_checks.append(
            {
                "scenario_id": result["scenario_id"],
                "expected": expected,
                "actual": actual,
                "passed": all(actual[key] == expected[key] for key in actual),
            }
        )

    aggregate = {
        "baseline": aggregate_raw_engine_results(raw_results, "BASELINE"),
        "sirengrid": aggregate_raw_engine_results(raw_results, "SIRENGRID"),
    }
    metadata = {
        "benchmark_policy_version": PHASE08_BENCHMARK_POLICY_VERSION,
        "scenario_dataset_version": PHASE08_DATASET_VERSION,
        "validation_version": PHASE08_VALIDATION_VERSION,
        "scenario_count": len(raw_results),
        "code_commit": _commit_sha(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "assets": {
            "scenario_manifest": _sha256(runner.manifest.source_path)
            if hasattr(runner.manifest, "source_path")
            else _sha256(REPO_ROOT / "data/evaluation/phase08/scenarios.json"),
            "routing_graph": _sha256(REPO_ROOT / "data/processed/nasr_city/nasr_city_graph.graphml"),
            "population_zones": _sha256(REPO_ROOT / "data/processed/nasr_city/nasr_city_zone_population_worldpop_2025.geojson"),
            "hospitals": _sha256(REPO_ROOT / "data/processed/nasr_city/nasr_city_emergency_facilities.geojson"),
            "traffic_signals": _sha256(REPO_ROOT / "data/processed/nasr_city/nasr_city_traffic_signals.geojson"),
        },
        "reality": "SIMULATED benchmark scenarios grounded in REAL_PUBLIC/REAL_DERIVED static assets",
    }
    performance = _run_performance_subset(runner)
    write_json(output_dir / "raw_scenario_results.json", raw_results)
    write_json(output_dir / "aggregate_results.json", aggregate)
    write_json(output_dir / "performance_subset_results.json", performance)
    write_json(output_dir / "t01_t15_validation.json", mappings)
    write_json(output_dir / "benchmark_metadata.json", metadata)
    write_json(output_dir / "expected_outcome_checks.json", expected_checks)
    return {
        "raw_results": raw_results,
        "aggregate": aggregate,
        "performance": performance,
        "t01_t15": mappings,
        "expected_checks": expected_checks,
        "metadata": metadata,
    }


def main() -> None:
    result = build_benchmark_artifacts()
    print(
        f"Phase 08 benchmark generated: {result['metadata']['scenario_count']} scenarios; "
        f"T01-T15={'PASS' if all(item['passed'] for item in result['t01_t15']) else 'FAIL'}"
    )


if __name__ == "__main__":
    main()
