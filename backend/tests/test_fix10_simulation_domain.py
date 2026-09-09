from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.benchmark_scenarios import (
    BenchmarkScenario,
    ScenarioEvent,
    ScenarioExpected,
    ScenarioIncident,
    ScenarioRequirement,
    ScenarioResourceOverride,
    TrafficFixture,
)
from app.config import settings
from app.coverage import load_population_zones
from app.db import init_db
from app.main import app
from app.models import EmergencyResource, Incident, ReplanEvaluation, ResponsePlan, TimelineEvent
from app.schemas import IncidentStatus, ResourceStatus, ResponsePlanStatus, ResourceType, Severity


RESOURCE_ID = "10000000-0000-0000-0000-000000000001"
SCENARIO_ID = "FIX10_resource_outage"


@pytest.fixture(autouse=True)
def setup_simulation_database(
    isolated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db(isolated_engine)
    monkeypatch.setattr(settings, "simulation_controls_enabled", True)
    import app.simulation_api as simulation_api

    monkeypatch.setattr(simulation_api, "_loaded_scenario_id", None)
    monkeypatch.setattr(simulation_api, "_next_event_index", 0)


def _scenario(*, event_status: ResourceStatus = ResourceStatus.OUT_OF_SERVICE) -> BenchmarkScenario:
    incident_id = f"simulation-{SCENARIO_ID}"
    return BenchmarkScenario(
        id=SCENARIO_ID,
        title="FIX-10 resource outage integration",
        seed=90110,
        tags=["fix10", "simulation", "resource-outage"],
        incident=ScenarioIncident(
            incident_type="traffic_collision",
            severity=Severity.HIGH,
            coordinate={"lat": 30.0561, "lon": 31.3452},
            requirements=[
                ScenarioRequirement(resource_type=ResourceType.AMBULANCE, minimum_count=1),
            ],
        ),
        resource_overrides=[
            ScenarioResourceOverride(
                resource_id=RESOURCE_ID,
                status=ResourceStatus.ASSIGNED,
                assigned_incident_id=incident_id,
            )
        ],
        traffic_fixture=TrafficFixture(
            fixture_id="fix10-fallback",
            mode="FALLBACK",
            source_reference="fix10-test-fixture",
        ),
        events=[
            ScenarioEvent(
                event_index=0,
                at_seconds=10,
                event_type="RESOURCE_STATE",
                resource_overrides=[
                    ScenarioResourceOverride(
                        resource_id=RESOURCE_ID,
                        status=event_status,
                    )
                ],
            )
        ],
        expected=ScenarioExpected(
            baseline="PLAN_GENERATED",
            sirengrid="PLAN_GENERATED",
        ),
    )


def _load_and_approve_primary_plan(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Incident, EmergencyResource, ResponsePlan]:
    scenario = _scenario()
    monkeypatch.setattr("app.simulation_api._find_scenario", lambda scenario_id: scenario)
    loaded = client.post(f"/api/v1/simulation/load/{SCENARIO_ID}")
    assert loaded.status_code == 200, loaded.text

    db.expire_all()
    incident = db.get(Incident, f"simulation-{SCENARIO_ID}")
    resource = db.get(EmergencyResource, RESOURCE_ID)
    assert incident is not None
    assert resource is not None
    plan = ResponsePlan(
        id="fix10-approved-plan",
        incident_id=incident.id,
        incident_version=incident.version,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=[resource.id],
        routes_json=[],
        metrics_json={},
        score_breakdown_json={},
    )
    incident.status = IncidentStatus.RESPONSE_ACTIVE
    incident.current_plan_id = plan.id
    db.add(plan)
    db.commit()
    db.refresh(incident)
    db.refresh(resource)
    return incident, resource, plan


def test_resource_outage_event_uses_domain_side_effects_and_replan_pipeline(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    incident, resource, plan = _load_and_approve_primary_plan(client, db_session, monkeypatch)
    published: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.simulation_api.publish_operations_event",
        lambda **event: published.append(event),
        raising=False,
    )

    applied = client.post("/api/v1/simulation/events", json={"next": True})

    assert applied.status_code == 200, applied.text
    db_session.expire_all()
    saved_resource = db_session.get(EmergencyResource, resource.id)
    saved_incident = db_session.get(Incident, incident.id)
    assert saved_resource is not None
    assert saved_incident is not None
    assert saved_resource.status == ResourceStatus.OUT_OF_SERVICE
    assert saved_resource.version == 2
    assert saved_resource.provenance_json["data_reality"] == "SIMULATED"
    assert saved_resource.provenance_json["freshness_status"] == "FRESH"
    assert saved_incident.current_plan_id == plan.id
    assert db_session.scalar(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident.id)
    ) is not None
    event_types = db_session.scalars(
        select(TimelineEvent.event_type).where(TimelineEvent.incident_id == incident.id)
    ).all()
    assert "RESOURCE_STATUS_CHANGED" in event_types
    assert "SIMULATION_EVENT_TRIGGERED" in event_types
    assert {event["event"] for event in published} >= {
        "resource.updated",
        "replan.required",
        "simulation.event",
    }

    modeled_zones = load_population_zones(
        settings.NASR_CITY_DATA_DIR / "nasr_city_zone_population_worldpop_2025.geojson"
    )[:1]
    with (
        patch("app.planning.traffic_runtime.capture_snapshot", return_value=None),
        patch("app.planning.load_population_zones", return_value=modeled_zones),
    ):
        evaluated = client.post(
            f"/api/v1/incidents/{incident.id}/replan/evaluate",
            json={"expected_incident_version": incident.version},
        )
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["status"] == "REPLACEMENT_RECOMMENDED"
    assert evaluated.json()["pending_plan_id"] is not None

    active = client.get(f"/api/v1/incidents/{incident.id}")
    assert active.status_code == 200
    assert active.json()["current_plan_id"] == plan.id


def test_resource_outage_event_rolls_back_on_replan_failure(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    incident, resource, _ = _load_and_approve_primary_plan(client, db_session, monkeypatch)
    published: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.simulation_api.publish_operations_event",
        lambda **event: published.append(event),
        raising=False,
    )

    def fail_trigger(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("injected simulation replan failure")

    monkeypatch.setattr("app.replanning.apply_replan_trigger", fail_trigger)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/simulation/events",
        json={"next": True},
    )

    assert response.status_code == 500
    db_session.expire_all()
    saved_resource = db_session.get(EmergencyResource, resource.id)
    assert saved_resource is not None
    assert saved_resource.status == ResourceStatus.ASSIGNED
    assert saved_resource.version == 1
    assert db_session.scalar(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident.id)
    ) is None
    assert db_session.scalar(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "RESOURCE_STATUS_CHANGED",
        )
    ) is None
    assert published == []
