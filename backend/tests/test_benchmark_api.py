from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_phase08_benchmark_endpoint_exposes_committed_artifact() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/benchmark/phase08")

    assert response.status_code == 200
    payload = response.json()
    assert payload["aggregate"]["baseline"]["count"] == 36
    assert payload["aggregate"]["sirengrid"]["count"] == 36
    assert len(payload["validation"]) == 15
    assert payload["provenance"]["data_reality"] == "SYNTHETIC"
