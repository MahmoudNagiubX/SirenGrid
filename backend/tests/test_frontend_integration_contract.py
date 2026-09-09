from fastapi.testclient import TestClient

from app.main import app


def test_phase08_benchmark_artifact_is_available_to_frontend() -> None:
    response = TestClient(app).get("/api/v1/benchmark/phase08")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"aggregate", "performance", "validation", "metadata", "provenance"}
    assert payload["metadata"]["scenario_count"] == 36
    assert payload["provenance"]["data_reality"] == "SYNTHETIC"
