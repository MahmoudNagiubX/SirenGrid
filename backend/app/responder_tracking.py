"""Deterministic, read-only responder tracking projection.

The citizen tracking screen needs the assigned responder to *appear* to move
toward the emergency along the already-approved route while the citizen polls
``GET /api/v1/mobile/emergency-requests/{id}``. There is no real responder GPS
feed in the hackathon environment, so this module derives an **effective**
position from data that already exists:

    approved plan route  +  approval start time  +  server clock  +  route ETA
        -> distance-interpolated point along the approved route

Hard rules encoded here:

* It never mutates the canonical resource, incident, or plan. A citizen GET has
  no side effects.
* It only ever follows ``Incident.current_plan_id`` so a replan automatically
  switches tracking to the newly approved plan.
* It only uses the assigned responder's own route geometry.
* Unless the resource carries genuine live-location provenance
  (``data_reality == REAL_LIVE`` and a LIVE/FRESH freshness), the projection is
  labelled ``SIMULATED`` / ``SIMULATED_ROUTE_PROJECTION`` and is never described
  as live GPS.
* Terminal incidents (closed / cancelled) produce no movement.

Interpolation reuses :func:`app.resources.interpolate_route_progress`, which
walks cumulative Haversine segment distance (uneven vertex spacing is handled)
rather than raw array index.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Approval, EmergencyResource, Incident, ResponsePlan
from app.resources import interpolate_route_progress, remaining_route_coordinates
from app.schemas import (
    CitizenRequestStatus,
    Coordinate,
    DataReality,
    FreshnessStatus,
    IncidentStatus,
    ResponsePlanStatus,
)

__all__ = [
    "ResponderTrackingSnapshot",
    "resolve_responder_tracking_snapshot",
    "TRACKING_SOURCE_SIMULATED",
    "TRACKING_SOURCE_REAL",
]

TRACKING_SOURCE_SIMULATED = "SIMULATED_ROUTE_PROJECTION"
TRACKING_SOURCE_REAL = "REAL_RESOURCE_LOCATION"

# Written by ``planning.approve_plan`` for both first approval and replan
# replacement approval (see ``app/planning.py``).
_APPROVE_ACTION = "APPROVE_PLAN"

_TERMINAL_INCIDENT_STATUSES = frozenset(
    {IncidentStatus.CLOSED, IncidentStatus.CANCELLED_FALSE_REPORT}
)
_LIVE_FRESHNESS = frozenset({FreshnessStatus.LIVE, FreshnessStatus.FRESH})


@dataclass(frozen=True)
class ResponderTrackingSnapshot:
    """One deterministic tracking read for the assigned responder.

    ``original_route_eta_seconds`` / ``remaining_eta_seconds`` are ``None`` when
    the approved route carries no usable ETA (no time-derived projection is
    performed in that case and ``progress_fraction`` stays ``0.0``).
    """

    resource_id: str
    effective_location: Coordinate
    original_route_eta_seconds: float | None
    remaining_eta_seconds: float | None
    progress_fraction: float
    tracking_state: CitizenRequestStatus
    route_geometry: dict[str, Any]
    started_at: datetime
    last_updated: datetime
    data_reality: DataReality
    freshness_status: FreshnessStatus
    tracking_source: str


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _validate_line_string(geometry: Any) -> list[list[float]] | None:
    """Return cleaned ``[[lon, lat], ...]`` for a valid GeoJSON LineString.

    Rejects (returns ``None``) missing geometry, wrong type, fewer than two
    vertices, non-numeric / NaN / infinite ordinates, and out-of-range
    longitude or latitude. It never fabricates a straight line.
    """
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    cleaned: list[list[float]] = []
    for pair in coordinates:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            return None
        try:
            lon = float(pair[0])
            lat = float(pair[1])
        except (TypeError, ValueError):
            return None
        if not math.isfinite(lon) or not math.isfinite(lat):
            return None
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return None
        cleaned.append([lon, lat])
    return cleaned


def _route_for_resource(
    plan: ResponsePlan, resource_id: str
) -> dict[str, Any] | None:
    """The assigned responder's own route record, matched only by resource id."""
    routes = plan.routes_json if isinstance(plan.routes_json, list) else []
    for route in routes:
        if isinstance(route, dict) and route.get("resource_id") == resource_id:
            return route
    return None


def _approval_started_at(
    db: Session, *, incident_id: str, plan_id: str
) -> datetime | None:
    """Latest APPROVE_PLAN approval time for this incident's current plan."""
    rows = db.scalars(
        select(Approval).where(
            Approval.incident_id == incident_id,
            Approval.plan_id == plan_id,
            Approval.action == _APPROVE_ACTION,
        )
    ).all()
    stamps = [
        stamp
        for stamp in (_as_utc(row.created_at) for row in rows)
        if stamp is not None
    ]
    return max(stamps) if stamps else None


def _coerce_eta_seconds(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not math.isfinite(value) or value <= 0.0:
        return None
    return value


def resolve_responder_tracking_snapshot(
    db: Session,
    *,
    incident: Incident,
    plan: ResponsePlan | None,
    resource: EmergencyResource | None,
    now: datetime | None = None,
) -> ResponderTrackingSnapshot | None:
    """Resolve the current tracking snapshot, or ``None`` when tracking is unsafe.

    ``None`` (no simulated movement, no fabricated route) is returned when:

    * the incident is terminal (closed / cancelled),
    * there is no approved plan / assigned responder,
    * the supplied plan is not the incident's current plan (stale / replan),
    * the assigned responder has no route in that plan,
    * the route geometry is missing or malformed.

    ``now`` is injectable for deterministic tests; it defaults to the server
    clock in UTC.
    """
    if incident.status in _TERMINAL_INCIDENT_STATUSES:
        return None
    if plan is None or resource is None:
        return None
    if plan.status != ResponsePlanStatus.APPROVED:
        return None
    # Replan safety: only the incident's *current* plan is ever tracked, never a
    # superseded historical plan.
    if incident.current_plan_id != plan.id:
        return None

    route = _route_for_resource(plan, resource.id)
    if route is None:
        return None
    coordinates = _validate_line_string(
        route.get("geometry") or route.get("route_geometry")
    )
    if coordinates is None:
        return None

    now_utc = _as_utc(now) or datetime.now(timezone.utc)

    provenance = resource.provenance_json or {}
    try:
        resource_reality = DataReality(provenance.get("data_reality"))
    except ValueError:
        resource_reality = DataReality.SIMULATED
    try:
        resource_freshness = FreshnessStatus(provenance.get("freshness_status"))
    except ValueError:
        resource_freshness = FreshnessStatus.UNKNOWN

    started_at = (
        _approval_started_at(db, incident_id=incident.id, plan_id=plan.id)
        or _as_utc(plan.created_at)
        or now_utc
    )

    original_eta = _coerce_eta_seconds(route.get("eta_seconds"))
    elapsed_seconds = max(0.0, (now_utc - started_at).total_seconds())
    if original_eta is not None:
        progress = min(1.0, max(0.0, elapsed_seconds / original_eta))
        remaining_eta: float | None = max(original_eta - elapsed_seconds, 0.0)
    else:
        # ETA missing / invalid: hold the responder at the route start rather
        # than derive movement from time.
        progress = 0.0
        remaining_eta = None

    is_real_live = (
        resource_reality == DataReality.REAL_LIVE
        and resource_freshness in _LIVE_FRESHNESS
    )
    if is_real_live:
        # Genuine live provenance: trust the resource's own coordinate and keep
        # its reality / freshness labels. The route simulation never overrides
        # a real location. `progress` here is time-derived, not matched to the
        # real GPS fix, so trimming the route by it would fabricate a
        # "remaining route" not actually tied to the real position — the full
        # route stays as the only truthful geometry in this branch.
        effective_location = Coordinate(
            lat=resource.latitude, lon=resource.longitude
        )
        tracking_source = TRACKING_SOURCE_REAL
        out_reality = DataReality.REAL_LIVE
        out_freshness = resource_freshness
        route_coordinates = coordinates
    else:
        lon, lat = interpolate_route_progress(coordinates, progress)
        effective_location = Coordinate(lat=lat, lon=lon)
        tracking_source = TRACKING_SOURCE_SIMULATED
        out_reality = DataReality.SIMULATED
        out_freshness = FreshnessStatus.FRESH
        # The displayed route is the remaining path from here to the
        # incident, not the full original route — it visibly shrinks behind
        # the responder as `progress` advances, on both mobile and dashboard
        # (both consume this same field).
        route_coordinates = remaining_route_coordinates(coordinates, progress)

    tracking_state = (
        CitizenRequestStatus.ARRIVED
        if progress >= 1.0
        else CitizenRequestStatus.EN_ROUTE
    )

    return ResponderTrackingSnapshot(
        resource_id=resource.id,
        effective_location=effective_location,
        original_route_eta_seconds=original_eta,
        remaining_eta_seconds=remaining_eta,
        progress_fraction=progress,
        tracking_state=tracking_state,
        route_geometry={"type": "LineString", "coordinates": route_coordinates},
        started_at=started_at,
        last_updated=now_utc,
        data_reality=out_reality,
        freshness_status=out_freshness,
        tracking_source=tracking_source,
    )
