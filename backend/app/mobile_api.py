"""SirenGrid Citizen (mobile) API gateway.

Frozen routes under ``/api/v1/mobile``:

- ``POST /mobile/auth/login``   — phone + PIN -> opaque bearer session + profile
- ``GET  /mobile/me``           — authenticated citizen profile (masked ID)
- ``POST /mobile/auth/logout``  — revoke the current session
- ``POST /mobile/emergency-requests``          — authenticated one-tap intake
- ``GET  /mobile/emergency-requests/{id}``     — citizen-safe tracking projection

The emergency request reuses the existing ``Incident`` / ``Report`` /
``TimelineEvent`` pipeline and the existing operations event. It never creates
a parallel dispatch state machine, never approves a plan, and never adds a
Police resource type. The live device GPS is the operational location; the
registered address is account context only and is never a GPS fallback.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.incidents import serialize_incident
from app.mobile_auth import (
    CitizenAuthContext,
    authenticate_citizen,
    issue_session,
    mask_national_id,
    verify_pin,
)
from app.models import (
    CitizenIdempotencyRecord,
    CitizenProfile,
    EmergencyResource,
    Incident,
    Report,
    ResponsePlan,
    TimelineEvent,
    new_timeline_event_id,
)
from app.schemas import (
    CitizenRequestStatus,
    ConfidenceLevel,
    Coordinate,
    DataReality,
    FreshnessStatus,
    IncidentStatus,
    MobileCitizenProfileRead,
    MobileEmergencyRequestCreate,
    MobileEmergencyRequestCreated,
    MobileEmergencyTrackingRead,
    MobileLoginRequest,
    MobileLoginResponse,
    MobileResponderRead,
    MobileService,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)
from app.websocket import publish_operations_event

__all__ = ["router"]

router = APIRouter(prefix="/mobile", tags=["mobile"])

MOBILE_SOURCE_TYPE = "MOBILE_APP"
MOBILE_SOURCE = "SIRENGRID_CITIZEN_APP"
SEVERITY_AUTHORITY_PLACEHOLDER = "UNCONFIRMED_MOBILE_PLACEHOLDER"

# Locked citizen-facing status projection (mission section 24).
_STATUS_PROJECTION: dict[IncidentStatus, CitizenRequestStatus] = {
    IncidentStatus.RECEIVED: CitizenRequestStatus.RECEIVED,
    IncidentStatus.INTERPRETING: CitizenRequestStatus.UNDER_REVIEW,
    IncidentStatus.ACTIVE_UNCONFIRMED: CitizenRequestStatus.UNDER_REVIEW,
    IncidentStatus.RESPONSE_PROPOSED: CitizenRequestStatus.UNDER_REVIEW,
    IncidentStatus.AWAITING_APPROVAL: CitizenRequestStatus.UNDER_REVIEW,
    IncidentStatus.RESPONSE_ACTIVE: CitizenRequestStatus.RESPONSE_ASSIGNED,
    IncidentStatus.EN_ROUTE: CitizenRequestStatus.EN_ROUTE,
    IncidentStatus.ON_SCENE: CitizenRequestStatus.ARRIVED,
    IncidentStatus.TRANSPORT_ACTIVE: CitizenRequestStatus.ARRIVED,
    IncidentStatus.HANDOVER: CitizenRequestStatus.ARRIVED,
    IncidentStatus.CLOSED: CitizenRequestStatus.COMPLETED,
    IncidentStatus.CANCELLED_FALSE_REPORT: CitizenRequestStatus.CANCELLED,
    IncidentStatus.REQUIRES_REVIEW: CitizenRequestStatus.UNDER_REVIEW,
    IncidentStatus.DUPLICATE_MERGED: CitizenRequestStatus.UNDER_REVIEW,
}

# Explicit operational requirement per requested service. Police/General
# deliberately carry no resource requirement (operator review only).
_SERVICE_REQUIREMENTS: dict[MobileService, list[dict[str, Any]]] = {
    MobileService.AMBULANCE: [{"resource_type": "AMBULANCE", "count": 1}],
    MobileService.FIRE: [{"resource_type": "FIRE_RESCUE", "count": 1}],
    MobileService.POLICE: [],
    MobileService.GENERAL: [],
}
_SERVICE_RESPONDER_TYPE: dict[MobileService, ResourceType] = {
    MobileService.AMBULANCE: ResourceType.AMBULANCE,
    MobileService.FIRE: ResourceType.FIRE_RESCUE,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _idempotency_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "IDEMPOTENCY_CONFLICT",
            "message": (
                "This Idempotency-Key was already used for a different "
                "emergency request."
            ),
        },
    )


def _find_idempotency_record(
    db: Session,
    citizen_reference: str,
    key: str,
) -> CitizenIdempotencyRecord | None:
    return db.scalars(
        select(CitizenIdempotencyRecord).where(
            CitizenIdempotencyRecord.citizen_reference == citizen_reference,
            CitizenIdempotencyRecord.idempotency_key == key,
        )
    ).first()


def _replay_created(
    db: Session,
    record: CitizenIdempotencyRecord,
    service: MobileService,
) -> MobileEmergencyRequestCreated:
    """Return the original creation result for a retried idempotent request."""
    original = db.get(Report, record.report_id)
    return MobileEmergencyRequestCreated(
        request_id=record.report_id,
        incident_id=record.incident_id,
        service=service,
        received_at=(
            original.received_at.isoformat()
            if original is not None and original.received_at is not None
            else _utcnow().isoformat()
        ),
        tracking_available=False,
    )


def _profile_payload(citizen: CitizenProfile) -> MobileCitizenProfileRead:
    return MobileCitizenProfileRead(
        citizen_reference=citizen.citizen_reference,
        display_name=citizen.display_name,
        phone=citizen.phone,
        registered_address=citizen.registered_address_text,
        national_id_masked=mask_national_id(citizen.national_id_last4),
        identity_status=citizen.identity_status,
    )


def _citizen_context(citizen: CitizenProfile) -> dict[str, Any]:
    """The authorized-operator context block embedded in mobile provenance.

    Contains no PIN, token, hash, salt, or full National ID.
    """
    return {
        "citizen_reference": citizen.citizen_reference,
        "display_name": citizen.display_name,
        "phone": citizen.phone,
        "registered_address": citizen.registered_address_text,
        "national_id_masked": mask_national_id(citizen.national_id_last4),
        "identity_status": citizen.identity_status,
    }


def _request_fingerprint(
    citizen_reference: str,
    service: MobileService,
    lat: float,
    lon: float,
) -> str:
    material = json.dumps(
        {
            "citizen_reference": citizen_reference,
            "service": service.value,
            "lat": round(float(lat), 6),
            "lon": round(float(lon), 6),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _service_from_incident(incident: Incident) -> MobileService:
    requested = (incident.provenance_json or {}).get("requested_service")
    if isinstance(requested, str):
        try:
            return MobileService(requested)
        except ValueError:
            pass
    # Fallback: incident_type is "mobile_<service>_request".
    parts = (incident.incident_type or "").split("_")
    if len(parts) >= 3:
        try:
            return MobileService(parts[1].upper())
        except ValueError:
            pass
    return MobileService.GENERAL


def _project_status(incident_status: IncidentStatus) -> CitizenRequestStatus:
    return _STATUS_PROJECTION.get(incident_status, CitizenRequestStatus.UNDER_REVIEW)


@router.post(
    "/auth/login",
    status_code=status.HTTP_200_OK,
    response_model=MobileLoginResponse,
)
def mobile_login(
    payload: MobileLoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> MobileLoginResponse:
    """Authenticate a pre-registered synthetic citizen with phone + PIN."""
    phone = payload.phone.strip()
    citizen = db.scalars(
        select(CitizenProfile).where(CitizenProfile.phone == phone)
    ).first()

    # Generic failure: never disclose whether the phone exists.
    if citizen is None or not verify_pin(
        payload.pin,
        salt=citizen.pin_salt,
        expected_hash=citizen.pin_hash,
        iterations=citizen.pin_iterations,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not citizen.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    raw_token, session = issue_session(db, citizen)
    expires_at = session.expires_at  # tz-aware in memory; keep before commit
    db.commit()

    return MobileLoginResponse(
        access_token=raw_token,
        token_type="bearer",
        expires_at=expires_at,
        profile=_profile_payload(citizen),
    )


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=MobileCitizenProfileRead,
)
def mobile_me(
    context: Annotated[CitizenAuthContext, Depends(authenticate_citizen)],
) -> MobileCitizenProfileRead:
    """Return the authenticated citizen profile (masked ID, registered address)."""
    return _profile_payload(context.profile)


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def mobile_logout(
    context: Annotated[CitizenAuthContext, Depends(authenticate_citizen)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Revoke the current session. A revoked token is rejected afterwards."""
    context.session.revoked_at = _utcnow()
    db.add(context.session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _build_mobile_provenance(
    citizen: CitizenProfile,
    service: MobileService,
    payload: MobileEmergencyRequestCreate,
    now: datetime,
    idempotency_key: str | None,
) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "source": MOBILE_SOURCE,
        "source_type": MOBILE_SOURCE_TYPE,
        "source_reference": citizen.citizen_reference,
        "data_reality": DataReality.SYNTHETIC.value,
        "freshness_status": FreshnessStatus.FRESH.value,
        "last_updated": now.isoformat(),
        "citizen_context": _citizen_context(citizen),
        "location_source": "DEVICE_GPS",
        "location_accuracy_m": payload.location_accuracy_m,
        "client_timestamp": (
            payload.client_timestamp.isoformat()
            if payload.client_timestamp is not None
            else None
        ),
        "severity_authority": SEVERITY_AUTHORITY_PLACEHOLDER,
        "requested_service": service.value,
    }
    if service is MobileService.POLICE:
        provenance["service_disposition"] = "OPERATOR_HANDOFF"
        provenance["operator_handoff_required"] = True
    elif service is MobileService.GENERAL:
        provenance["service_disposition"] = "OPERATOR_REVIEW"
        provenance["operator_review_required"] = True
    if idempotency_key:
        provenance["idempotency_key"] = idempotency_key
    return provenance


def _tracking_from_state(
    db: Session,
    report: Report,
    incident: Incident,
) -> MobileEmergencyTrackingRead:
    service = _service_from_incident(incident)
    responder: MobileResponderRead | None = None
    eta_seconds: float | None = None

    responder_type = _SERVICE_RESPONDER_TYPE.get(service)
    if responder_type is not None and incident.current_plan_id:
        plan = db.get(ResponsePlan, incident.current_plan_id)
        if plan is not None and plan.status == ResponsePlanStatus.APPROVED:
            assigned = db.scalars(
                select(EmergencyResource)
                .where(EmergencyResource.assigned_incident_id == incident.id)
                .order_by(EmergencyResource.id.asc())
            ).all()
            match = next(
                (r for r in assigned if r.resource_type == responder_type),
                None,
            )
            if match is not None:
                prov = match.provenance_json or {}
                try:
                    freshness = FreshnessStatus(prov.get("freshness_status"))
                except ValueError:
                    freshness = FreshnessStatus.UNKNOWN
                try:
                    reality = DataReality(prov.get("data_reality"))
                except ValueError:
                    reality = DataReality.SIMULATED
                responder = MobileResponderRead(
                    id=match.id,
                    label=match.name,
                    location=Coordinate(lat=match.latitude, lon=match.longitude),
                    last_updated=(
                        match.last_updated.isoformat()
                        if match.last_updated is not None
                        else None
                    ),
                    freshness_status=freshness,
                    data_reality=reality,
                )
                for route in plan.routes_json or []:
                    if not isinstance(route, dict):
                        continue
                    if route.get("resource_id") != match.id:
                        continue
                    raw_eta = route.get("eta_seconds")
                    if isinstance(raw_eta, (int, float)) and math.isfinite(
                        float(raw_eta)
                    ):
                        eta_seconds = float(raw_eta)
                    break

    last_updated = None
    if responder is not None and responder.last_updated is not None:
        last_updated = responder.last_updated
    elif incident.updated_at is not None:
        last_updated = incident.updated_at.isoformat()

    return MobileEmergencyTrackingRead(
        request_id=report.id,
        incident_id=incident.id,
        service=service,
        status=_project_status(incident.status),
        eta_seconds=eta_seconds,
        responder=responder,
        last_updated=last_updated,
    )


@router.post(
    "/emergency-requests",
    status_code=status.HTTP_201_CREATED,
    response_model=MobileEmergencyRequestCreated,
)
def create_emergency_request(
    payload: MobileEmergencyRequestCreate,
    response: Response,
    context: Annotated[CitizenAuthContext, Depends(authenticate_citizen)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
) -> MobileEmergencyRequestCreated:
    """Authenticated one-tap emergency intake.

    Body carries only service + live GPS + optional technical metadata; citizen
    identity and registered address are derived from the session. Missing GPS
    fails with ``CURRENT_LOCATION_REQUIRED`` — the registered address is never
    used as a fallback dispatch location.
    """
    citizen = context.profile
    service = payload.service

    if payload.location is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "CURRENT_LOCATION_REQUIRED",
                "message": (
                    "Current device location is required to create this "
                    "emergency request."
                ),
            },
        )

    lat = payload.location.lat
    lon = payload.location.lon
    fingerprint = _request_fingerprint(citizen.citizen_reference, service, lat, lon)
    key = idempotency_key.strip() if idempotency_key else None

    # Fast path for a retried request. The UNIQUE (citizen_reference,
    # idempotency_key) constraint below is the authoritative guard against a
    # concurrent duplicate insert.
    if key:
        existing = _find_idempotency_record(db, citizen.citizen_reference, key)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise _idempotency_conflict()
            response.status_code = status.HTTP_200_OK
            return _replay_created(db, existing, service)

    now = _utcnow()
    incident_id = str(uuid.uuid4())
    report_id = str(uuid.uuid4())
    provenance = _build_mobile_provenance(citizen, service, payload, now, key)

    incident_status = (
        IncidentStatus.ACTIVE_UNCONFIRMED
        if service in (MobileService.AMBULANCE, MobileService.FIRE)
        else IncidentStatus.REQUIRES_REVIEW
    )

    incident = Incident(
        id=incident_id,
        version=1,
        incident_type=f"mobile_{service.value.lower()}_request",
        severity=Severity.MODERATE,
        confidence_level=ConfidenceLevel.LOW,
        status=incident_status,
        latitude=lat,
        longitude=lon,
        location_text=None,
        required_hospital_capabilities_json=[],
        required_resources_json=list(_SERVICE_REQUIREMENTS[service]),
        current_plan_id=None,
        created_at=now,
        updated_at=now,
        provenance_json=provenance,
    )
    report = Report(
        id=report_id,
        incident_id=incident_id,
        source_type=MOBILE_SOURCE_TYPE,
        source_reference=citizen.citizen_reference,
        raw_text=(
            f"Authenticated citizen requested {service.value} through "
            "SirenGrid Citizen."
        ),
        location_text=None,
        location_json={"lat": lat, "lon": lon},
        received_at=now,
        data_reality=DataReality.SYNTHETIC,
        provenance_json=provenance,
        processing_status="PROCESSED",
        evidence_items_json=[],
        created_at=now,
    )
    incident_created_event = TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident_id,
        event_type="INCIDENT_CREATED",
        details_json={
            "source": MOBILE_SOURCE,
            "source_type": MOBILE_SOURCE_TYPE,
            "citizen_reference": citizen.citizen_reference,
            "requested_service": service.value,
            "status": incident_status.value,
            "location_source": "DEVICE_GPS",
        },
        created_at=now,
    )
    report_created_event = TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident_id,
        event_type="REPORT_CREATED",
        details_json={
            "report_id": report_id,
            "source_type": MOBILE_SOURCE_TYPE,
            "source_reference": citizen.citizen_reference,
            "data_reality": DataReality.SYNTHETIC.value,
        },
        created_at=now,
    )

    db.add(incident)
    db.add(report)
    db.add(incident_created_event)
    db.add(report_created_event)
    if key:
        db.add(
            CitizenIdempotencyRecord(
                citizen_reference=citizen.citizen_reference,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                report_id=report_id,
                incident_id=incident_id,
                created_at=now,
            )
        )

    try:
        db.commit()
    except IntegrityError as exc:
        # A concurrent identical idempotent request committed first (or the
        # (citizen_reference, idempotency_key) scope is otherwise taken).
        db.rollback()
        existing = (
            _find_idempotency_record(db, citizen.citizen_reference, key)
            if key
            else None
        )
        if existing is None:
            raise _idempotency_conflict() from exc
        if existing.request_fingerprint != fingerprint:
            raise _idempotency_conflict() from exc
        response.status_code = status.HTTP_200_OK
        return _replay_created(db, existing, service)
    except Exception:
        db.rollback()
        raise

    db.refresh(incident)
    db.refresh(report)

    # Notify the institutional Command Center only after a successful commit.
    publish_operations_event(
        event="incident.created",
        incident_id=incident.id,
        payload=serialize_incident(incident),
    )

    return MobileEmergencyRequestCreated(
        request_id=report.id,
        incident_id=incident.id,
        service=service,
        received_at=report.received_at.isoformat(),
        tracking_available=False,
    )


@router.get(
    "/emergency-requests/{request_id}",
    status_code=status.HTTP_200_OK,
    response_model=MobileEmergencyTrackingRead,
)
def get_emergency_request(
    request_id: str,
    context: Annotated[CitizenAuthContext, Depends(authenticate_citizen)],
    db: Annotated[Session, Depends(get_db)],
) -> MobileEmergencyTrackingRead:
    """Citizen-safe read projection of one owned emergency request.

    Unknown and not-owned request IDs return the same ``404`` (anti-enumeration).
    """
    citizen = context.profile
    report = db.get(Report, request_id)
    if (
        report is None
        or report.source_type != MOBILE_SOURCE_TYPE
        or report.source_reference != citizen.citizen_reference
        or not report.incident_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emergency request not found",
        )
    incident = db.get(Incident, report.incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emergency request not found",
        )
    return _tracking_from_state(db, report, incident)
