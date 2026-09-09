"""Read-only access to the committed Phase 08 benchmark artifact."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.config import REPO_ROOT

__all__ = ["router"]

router = APIRouter(tags=["benchmark"])

_ARTIFACT_DIR = REPO_ROOT / "data" / "evaluation" / "phase08"


def _read_artifact(filename: str) -> Any:
    path = _ARTIFACT_DIR / filename
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Phase 08 benchmark artifact unavailable: {filename}",
        ) from exc


@router.get("/benchmark/phase08")
def get_phase08_benchmark() -> dict[str, Any]:
    """Expose committed benchmark evidence without recalculating or mutating it."""
    return {
        "aggregate": _read_artifact("aggregate_results.json"),
        "performance": _read_artifact("performance_subset_results.json"),
        "validation": _read_artifact("t01_t15_validation.json"),
        "metadata": _read_artifact("benchmark_metadata.json"),
        "provenance": {
            "source": "committed_phase08_benchmark_artifact",
            "data_reality": "SYNTHETIC",
            "source_reference": "data/evaluation/phase08",
        },
    }
