import app.main as main_module
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "SirenGrid API",
        "api_version": "v1",
    }


def test_startup_initializes_full_schema_and_database_endpoints(
    isolated_engine: Engine,
) -> None:
    required = {
        "incidents",
        "emergency_resources",
        "hospital_operational_states",
        "citizen_profiles",
        "citizen_sessions",
    }
    assert required.isdisjoint(inspect(isolated_engine).get_table_names())

    with TestClient(app) as startup_client:
        tables_after_first_start = set(inspect(isolated_engine).get_table_names())
        assert required.issubset(tables_after_first_start)
        for route in ("/api/v1/incidents", "/api/v1/resources", "/api/v1/hospitals"):
            assert startup_client.get(route).status_code == 200

    with TestClient(app):
        assert set(inspect(isolated_engine).get_table_names()) == tables_after_first_start


def test_schema_initialization_failure_aborts_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_initialization() -> None:
        raise RuntimeError("schema initialization failed")

    monkeypatch.setattr(main_module, "init_db", fail_initialization, raising=False)

    with pytest.raises(RuntimeError, match="schema initialization failed"):
        with TestClient(app):
            pass
