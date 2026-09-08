from __future__ import annotations

from app.benchmark_validation import run_master_plan_validation, validate_scenario_manifest_mapping


def test_all_master_plan_cases_execute_and_pass() -> None:
    results = run_master_plan_validation()

    assert len(results) == 15
    assert [result.case_id for result in results] == [f"T{index:02d}" for index in range(1, 16)]
    assert all(result.passed for result in results)


def test_master_plan_cases_map_to_the_committed_manifest() -> None:
    results = validate_scenario_manifest_mapping()

    assert len(results) == 15
    assert all(result.passed for result in results)
    assert len({result.scenario_id for result in results}) == 15
