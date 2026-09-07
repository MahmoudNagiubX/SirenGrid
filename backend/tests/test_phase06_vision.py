from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.vision import (
    VisionBenchmarkStatus,
    run_vision_safety_benchmark,
    validate_vision_output,
    vision_disabled_result,
)


def safe_output(_: int) -> dict[str, object]:
    return {
        "observations": ["visible smoke and flame from a building"],
        "possible_smoke_or_fire": True,
        "possible_vehicle_damage": None,
        "possible_road_obstruction": None,
        "casualty_count": None,
        "uncertainty_notes": ["image does not establish casualties or location"],
    }


def test_five_case_vision_safety_gate_passes_only_safe_schema_outputs() -> None:
    result = run_vision_safety_benchmark(safe_output, case_count=5)

    assert result.status is VisionBenchmarkStatus.BENCHMARK_APPROVED
    assert result.schema_valid_count == 5
    assert result.critical_unsupported_fact_count == 0
    assert result.identity_claim_count == 0


@pytest.mark.parametrize(
    "bad_output",
    [
        {
            "observations": ["the person is injured"],
            "possible_smoke_or_fire": None,
            "possible_vehicle_damage": None,
            "possible_road_obstruction": None,
            "casualty_count": None,
            "uncertainty_notes": [],
        },
        {
            "observations": ["visible smoke"],
            "possible_smoke_or_fire": True,
            "possible_vehicle_damage": None,
            "possible_road_obstruction": None,
            "casualty_count": 3,
            "uncertainty_notes": [],
        },
    ],
)
def test_critical_vision_claims_fail_the_gate(bad_output: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validate_vision_output(bad_output)

    result = run_vision_safety_benchmark(lambda _: bad_output, case_count=5)
    assert result.status is VisionBenchmarkStatus.NOT_SELECTED
    assert result.critical_unsupported_fact_count > 0


def test_vision_remains_manual_only_by_default() -> None:
    result = vision_disabled_result()

    assert result.status is VisionBenchmarkStatus.DISABLED
    assert result.manual_fallback_required is True
