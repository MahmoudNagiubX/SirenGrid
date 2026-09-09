"""Pure-function tests for the deterministic responder tracking projection.

Every case injects ``now`` (and a fixed approval time) so there are no sleeps
and no wall-clock flakiness. Scenarios are built from minimal ORM rows rather
than the full planning pipeline.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.db import init_db
from app.models import Approval, EmergencyResource, Incident, ResponsePlan
from app.responder_tracking import (
    TRACKING_SOURCE_REAL,
    TRACKING_SOURCE_SIMULATED,
    resolve_responder_tracking_snapshot,
)
from app.schemas import (
    CitizenRequestStatus,
    ConfidenceLevel,
    DataReality,
    FreshnessStatus,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)

START = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)

# Sentinel: use the default even-spacing geometry (distinct from ``None``, which
# means "the route record carries no geometry key at all").
_DEFAULT_GEOMETRY = object()

# Even spacing: three collinear points ~1.93 km apart each.
EVEN_GEOMETRY = {
    "type": "LineString",
    "coordinates": [[31.30, 30.05], [31.32, 30.05], [31.34, 30.05]],
}
# Uneven spacing: first segment ~96 m, second segment ~9.5 km.
UNEVEN_GEOMETRY = {
    "type": "LineString",
    "coordinates": [[31.300, 30.05], [31.301, 30.05], [31.400, 30.05]],
}


@pytest.fixture(autouse=True)
def _tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


def _build(
    db: Session,
    *,
    incident_status: IncidentStatus = IncidentStatus.RESPONSE_ACTIVE,
    plan_status: ResponsePlanStatus = ResponsePlanStatus.APPROVED,
    geometry: object = _DEFAULT_GEOMETRY,
    geometry_key: str = "geometry",
    eta_seconds: float | None = 100.0,
    route_resource_id: str | None = None,
    resource_id: str = "res-amb-1",
    provenance: dict | None = None,
    with_approval: bool = True,
    approval_at: datetime | None = None,
    plan_created_at: datetime | None = None,
    current_plan_id: str | None = None,
    resource_lat: float = 30.06,
    resource_lon: float = 31.29,
) -> tuple[Incident, ResponsePlan, EmergencyResource]:
    if geometry is _DEFAULT_GEOMETRY:
        geometry = EVEN_GEOMETRY
    route: dict = {
        "resource_id": route_resource_id or resource_id,
        "eta_seconds": eta_seconds,
    }
    if geometry is not None:
        route[geometry_key] = geometry

    incident = Incident(
        id="inc-1",
        version=3,
        incident_type="mobile_ambulance_request",
        severity=Severity.MODERATE,
        confidence_level=ConfidenceLevel.LOW,
        status=incident_status,
        latitude=30.05,
        longitude=31.34,
    )
    plan = ResponsePlan(
        id="plan-1",
        incident_id="inc-1",
        incident_version=2,
        plan_version=1,
        status=plan_status,
        resource_ids_json=[resource_id],
        routes_json=[route],
        created_at=plan_created_at or (START - timedelta(hours=6)),
    )
    incident.current_plan_id = current_plan_id if current_plan_id is not None else plan.id
    resource = EmergencyResource(
        id=resource_id,
        name="Ambulance 1",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.ASSIGNED,
        latitude=resource_lat,
        longitude=resource_lon,
        assigned_incident_id="inc-1",
        provenance_json=provenance
        or {
            "data_reality": DataReality.SIMULATED.value,
            "freshness_status": FreshnessStatus.STATIC.value,
        },
    )
    db.add_all([incident, plan, resource])
    if with_approval:
        db.add(
            Approval(
                id="appr-1",
                plan_id="plan-1",
                incident_id="inc-1",
                operator_reference="dispatcher-op-01",
                action="APPROVE_PLAN",
                expected_incident_version=2,
                expected_plan_version=1,
                created_at=approval_at or START,
            )
        )
    db.commit()
    return incident, plan, resource


# --------------------------------------------------------------------------- #


def test_pre_approval_request_has_no_tracking(db_session: Session) -> None:
    incident, plan, resource = _build(
        db_session,
        plan_status=ResponsePlanStatus.RECOMMENDED,
        incident_status=IncidentStatus.AWAITING_APPROVAL,
    )
    assert (
        resolve_responder_tracking_snapshot(
            db_session, incident=incident, plan=plan, resource=resource, now=START
        )
        is None
    )


def test_approved_ambulance_returns_snapshot_for_assigned_resource(
    db_session: Session,
) -> None:
    incident, plan, resource = _build(db_session)
    snap = resolve_responder_tracking_snapshot(
        db_session, incident=incident, plan=plan, resource=resource, now=START
    )
    assert snap is not None
    assert snap.resource_id == "res-amb-1"
    assert snap.tracking_source == TRACKING_SOURCE_SIMULATED
    assert snap.data_reality is DataReality.SIMULATED


def test_at_start_time_responder_is_at_route_start(db_session: Session) -> None:
    incident, plan, resource = _build(db_session)
    snap = resolve_responder_tracking_snapshot(
        db_session, incident=incident, plan=plan, resource=resource, now=START
    )
    assert snap is not None
    assert snap.progress_fraction == 0.0
    assert snap.effective_location.lon == pytest.approx(31.30)
    assert snap.effective_location.lat == pytest.approx(30.05)
    assert snap.tracking_state is CitizenRequestStatus.EN_ROUTE


def test_no_movement_before_start_time(db_session: Session) -> None:
    incident, plan, resource = _build(db_session)
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=plan,
        resource=resource,
        now=START - timedelta(seconds=30),
    )
    assert snap is not None
    assert snap.progress_fraction == 0.0
    assert snap.effective_location.lon == pytest.approx(31.30)
    assert snap.remaining_eta_seconds == pytest.approx(100.0)


def test_halfway_uses_distance_not_array_index(db_session: Session) -> None:
    incident, plan, resource = _build(db_session, geometry=UNEVEN_GEOMETRY)
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=plan,
        resource=resource,
        now=START + timedelta(seconds=50),
    )
    assert snap is not None
    assert snap.progress_fraction == pytest.approx(0.5)
    # Index-based interpolation would sit at (or near) the dense middle vertex
    # 31.301; distance-based interpolation is deep inside the long second leg.
    assert snap.effective_location.lon > 31.34
    assert snap.effective_location.lon < 31.40


def test_near_arrival_returns_point_close_to_destination(db_session: Session) -> None:
    incident, plan, resource = _build(db_session)
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=plan,
        resource=resource,
        now=START + timedelta(seconds=95),
    )
    assert snap is not None
    assert snap.progress_fraction == pytest.approx(0.95)
    assert snap.effective_location.lon == pytest.approx(31.30 + 0.95 * 0.04)
    assert snap.tracking_state is CitizenRequestStatus.EN_ROUTE


def test_after_eta_returns_destination_arrived_zero_eta(db_session: Session) -> None:
    incident, plan, resource = _build(db_session)
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=plan,
        resource=resource,
        now=START + timedelta(seconds=250),
    )
    assert snap is not None
    assert snap.progress_fraction == 1.0
    assert snap.effective_location.lon == pytest.approx(31.34)
    assert snap.effective_location.lat == pytest.approx(30.05)
    assert snap.remaining_eta_seconds == 0.0
    assert snap.tracking_state is CitizenRequestStatus.ARRIVED


def test_eta_is_never_negative(db_session: Session) -> None:
    incident, plan, resource = _build(db_session)
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=plan,
        resource=resource,
        now=START + timedelta(days=1),
    )
    assert snap is not None
    assert snap.remaining_eta_seconds == 0.0
    assert snap.progress_fraction == 1.0


@pytest.mark.parametrize(
    "terminal",
    [IncidentStatus.CLOSED, IncidentStatus.CANCELLED_FALSE_REPORT],
)
def test_terminal_incident_stops_projection(
    db_session: Session, terminal: IncidentStatus
) -> None:
    incident, plan, resource = _build(db_session, incident_status=terminal)
    assert (
        resolve_responder_tracking_snapshot(
            db_session,
            incident=incident,
            plan=plan,
            resource=resource,
            now=START + timedelta(seconds=50),
        )
        is None
    )


@pytest.mark.parametrize(
    "geometry",
    [
        None,
        {"type": "Polygon", "coordinates": [[[31.3, 30.0], [31.4, 30.1]]]},
        {"type": "LineString", "coordinates": [[31.3, 30.0]]},
        {"type": "LineString", "coordinates": [[31.3, 30.0], [float("nan"), 30.1]]},
        {"type": "LineString", "coordinates": [[31.3, 30.0], [999.0, 30.1]]},
        {"type": "LineString", "coordinates": [[31.3, 30.0], [31.4]]},
    ],
)
def test_malformed_route_geometry_falls_back(
    db_session: Session, geometry: dict | None
) -> None:
    incident, plan, resource = _build(db_session, geometry=geometry)
    assert (
        resolve_responder_tracking_snapshot(
            db_session,
            incident=incident,
            plan=plan,
            resource=resource,
            now=START + timedelta(seconds=10),
        )
        is None
    )


def test_route_for_a_different_resource_is_ignored(db_session: Session) -> None:
    incident, plan, resource = _build(
        db_session, route_resource_id="some-other-resource"
    )
    assert (
        resolve_responder_tracking_snapshot(
            db_session, incident=incident, plan=plan, resource=resource, now=START
        )
        is None
    )


def test_missing_eta_yields_no_time_projection(db_session: Session) -> None:
    incident, plan, resource = _build(db_session, eta_seconds=None)
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=plan,
        resource=resource,
        now=START + timedelta(seconds=90),
    )
    assert snap is not None
    assert snap.progress_fraction == 0.0
    assert snap.original_route_eta_seconds is None
    assert snap.remaining_eta_seconds is None
    assert snap.effective_location.lon == pytest.approx(31.30)


def test_zero_eta_falls_back_safely(db_session: Session) -> None:
    incident, plan, resource = _build(db_session, eta_seconds=0.0)
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=plan,
        resource=resource,
        now=START + timedelta(seconds=90),
    )
    assert snap is not None
    assert snap.progress_fraction == 0.0
    assert snap.remaining_eta_seconds is None


def test_real_live_resource_is_not_overwritten_by_route_projection(
    db_session: Session,
) -> None:
    incident, plan, resource = _build(
        db_session,
        provenance={
            "data_reality": DataReality.REAL_LIVE.value,
            "freshness_status": FreshnessStatus.LIVE.value,
        },
        resource_lat=30.061,
        resource_lon=31.291,
    )
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=plan,
        resource=resource,
        now=START + timedelta(seconds=50),
    )
    assert snap is not None
    assert snap.tracking_source == TRACKING_SOURCE_REAL
    assert snap.data_reality is DataReality.REAL_LIVE
    assert snap.freshness_status is FreshnessStatus.LIVE
    # The real coordinate wins; the route simulation never moves it.
    assert snap.effective_location.lat == pytest.approx(30.061)
    assert snap.effective_location.lon == pytest.approx(31.291)


def test_stale_plan_pointer_is_not_tracked(db_session: Session) -> None:
    incident, plan, resource = _build(
        db_session, current_plan_id="a-different-current-plan"
    )
    assert (
        resolve_responder_tracking_snapshot(
            db_session, incident=incident, plan=plan, resource=resource, now=START
        )
        is None
    )


def test_replan_switches_tracking_to_new_current_plan(db_session: Session) -> None:
    incident, old_plan, resource = _build(db_session)
    # A replacement plan becomes the incident's current plan and is approved.
    new_plan = ResponsePlan(
        id="plan-2",
        incident_id="inc-1",
        incident_version=3,
        plan_version=2,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=["res-amb-1"],
        routes_json=[
            {
                "resource_id": "res-amb-1",
                "eta_seconds": 60.0,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[31.35, 30.07], [31.34, 30.05]],
                },
            }
        ],
        created_at=START,
    )
    old_plan.status = ResponsePlanStatus.SUPERSEDED
    incident.current_plan_id = "plan-2"
    db_session.add(new_plan)
    db_session.add(
        Approval(
            id="appr-2",
            plan_id="plan-2",
            incident_id="inc-1",
            operator_reference="dispatcher-op-01",
            action="APPROVE_PLAN",
            expected_incident_version=3,
            expected_plan_version=2,
            created_at=START + timedelta(seconds=5),
        )
    )
    db_session.commit()

    # The superseded plan is refused outright.
    assert (
        resolve_responder_tracking_snapshot(
            db_session,
            incident=incident,
            plan=old_plan,
            resource=resource,
            now=START + timedelta(seconds=10),
        )
        is None
    )
    # The new current plan tracks, from its own approval time and route.
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=new_plan,
        resource=resource,
        now=START + timedelta(seconds=5),
    )
    assert snap is not None
    assert snap.started_at == START + timedelta(seconds=5)
    assert snap.progress_fraction == 0.0
    assert snap.effective_location.lon == pytest.approx(31.35)


def test_approval_time_is_preferred_over_plan_created_at(db_session: Session) -> None:
    # plan.created_at is 6h before START; if it were used, the responder would
    # have "arrived" long ago. The approval timestamp is the real start.
    incident, plan, resource = _build(
        db_session,
        approval_at=START,
        plan_created_at=START - timedelta(hours=6),
    )
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=plan,
        resource=resource,
        now=START + timedelta(seconds=10),
    )
    assert snap is not None
    assert snap.started_at == START
    assert snap.progress_fraction == pytest.approx(0.1)


def test_plan_created_at_used_when_no_approval_row(db_session: Session) -> None:
    incident, plan, resource = _build(
        db_session,
        with_approval=False,
        plan_created_at=START,
    )
    snap = resolve_responder_tracking_snapshot(
        db_session,
        incident=incident,
        plan=plan,
        resource=resource,
        now=START + timedelta(seconds=25),
    )
    assert snap is not None
    assert snap.started_at == START
    assert snap.progress_fraction == pytest.approx(0.25)


def test_missing_plan_or_resource_returns_none(db_session: Session) -> None:
    incident, plan, resource = _build(db_session)
    assert (
        resolve_responder_tracking_snapshot(
            db_session, incident=incident, plan=None, resource=resource, now=START
        )
        is None
    )
    assert (
        resolve_responder_tracking_snapshot(
            db_session, incident=incident, plan=plan, resource=None, now=START
        )
        is None
    )
