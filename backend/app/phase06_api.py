"""Minimal Phase 06 intake, claim review, and manual-authority endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.ai import (
    EvidenceClaim,
    ProviderClaimDraft,
    StructuredExtractionStatus,
    build_evidence_claims,
)
from app.ai_processing import ASRResult, ASRStatus, process_structured_extraction, transcribe_with_fallback
from app.asr import configured_groq_transcriber
from app.claims import append_claims_to_evidence_items, resolve_claims
from app.db import get_db
from app.fusion import FusionDecision, FusionReport, evaluate_report_association
from app.incidents import (
    FACT_FIELD_NAMES,
    _acquire_write_lock,
    _patch_incident_facts,
    serialize_incident,
    serialize_report,
    serialize_timeline_event,
)
from app.media import MediaValidationError, resolve_media_path, store_media
from app.models import Incident, Report, TimelineEvent, new_timeline_event_id
from app.schemas import (
    ConfidenceLevel,
    DataReality,
    FreshnessStatus,
    IncidentFactsPatchRequest,
    IncidentRead,
    IncidentStatus,
    ManualIncidentCreate,
    ReportRead,
    ResourceRequirement,
    ResourceType,
)
from app.websocket import publish_operations_event

router = APIRouter(tags=["phase06"])


class ClaimResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_incident_version: int = Field(ge=1)
    operator_reference: str = Field(min_length=1, max_length=200)
    field_name: str = Field(min_length=1, max_length=80)
    value: Any
    selected_evidence_id: str | None = None
    required_resources: list[ResourceRequirement] | None = Field(default=None, min_length=1)


class ReportAssociationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_incident_id: str
    expected_incident_version: int = Field(ge=1)
    operator_reference: str = Field(min_length=1, max_length=200)


class ManualTranscriptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_reference: str = Field(min_length=1, max_length=200)
    transcript: str = Field(min_length=1, max_length=20000)


class DuplicateMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_incident_id: str
    expected_incident_version: int = Field(ge=1)
    expected_canonical_incident_version: int = Field(ge=1)
    operator_reference: str = Field(min_length=1, max_length=200)


class ClaimsIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=150)
    evidence_id: str | None = None
    claims: list[ProviderClaimDraft] = Field(default_factory=list, max_length=32)


class ReportIncidentActivationRequest(ManualIncidentCreate):
    """Explicit operator facts required to activate a standalone report."""

    model_config = ConfigDict(extra="forbid")

    confidence_level: ConfidenceLevel
    operator_reference: str = Field(min_length=1)


_CANONICAL_SERVICE_RESOURCE_TYPES: dict[str, ResourceType] = {
    "ambulance": ResourceType.AMBULANCE,
    "fire rescue": ResourceType.FIRE_RESCUE,
    "fire_rescue": ResourceType.FIRE_RESCUE,
}


def _report_claims(report: Report) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    for item in report.evidence_items_json or []:
        if item.get("type") != "EVIDENCE_CLAIMS":
            continue
        for raw_claim in item.get("claims", []):
            try:
                claims.append(EvidenceClaim.model_validate(raw_claim))
            except ValidationError:
                continue
    return claims


def _incident_claims(db: Session, incident_id: str) -> list[EvidenceClaim]:
    reports = db.query(Report).filter(Report.incident_id == incident_id).all()
    claims: list[EvidenceClaim] = []
    for report in reports:
        claims.extend(_report_claims(report))
    return claims


def _validated_required_service_types(
    value: Any,
    required_resources: list[ResourceRequirement] | None,
) -> None:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
        raise HTTPException(
            status_code=422,
            detail="required_services claim must contain one or more service names",
        )
    if required_resources is None:
        raise HTTPException(
            status_code=422,
            detail="explicit required_resources are required to resolve required_services",
        )

    claimed_types: set[ResourceType] = set()
    for service in value:
        normalized = " ".join(
            service.strip().casefold().replace("_", " ").replace("-", " ").split()
        )
        resource_type = _CANONICAL_SERVICE_RESOURCE_TYPES.get(normalized)
        if resource_type is None:
            raise HTTPException(
                status_code=422,
                detail=f"required service '{service}' is unsupported or ambiguous",
            )
        claimed_types.add(resource_type)

    confirmed_types = {requirement.resource_type for requirement in required_resources}
    if not claimed_types.issubset(confirmed_types):
        raise HTTPException(
            status_code=422,
            detail="explicit required_resources must cover every resolved service",
        )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _latest_transcript_text(report: Report, transcript_type: str) -> str | None:
    candidates: list[tuple[str, int, str]] = []
    for index, item in enumerate(report.evidence_items_json or []):
        if item.get("type") != transcript_type:
            continue
        extracted_facts = item.get("extracted_facts")
        if not isinstance(extracted_facts, dict):
            continue
        transcript = extracted_facts.get("transcript")
        if not isinstance(transcript, str) or not transcript.strip():
            continue
        created_at = item.get("created_at")
        if not isinstance(created_at, str):
            provenance = item.get("provenance")
            created_at = provenance.get("created_at", "") if isinstance(provenance, dict) else ""
        candidates.append((created_at, index, transcript))
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]


def _structured_processing_text(report: Report) -> str:
    manual_transcript = _latest_transcript_text(report, "MANUAL_TRANSCRIPT")
    if manual_transcript is not None:
        return manual_transcript
    asr_transcript = _latest_transcript_text(report, "ASR_TRANSCRIPT")
    if asr_transcript is not None:
        return asr_transcript
    return report.raw_text if report.raw_text and report.raw_text.strip() else ""


def _report_fusion_view(report: Report) -> FusionReport:
    provenance = report.provenance_json or {}
    location = report.location_json or {}
    claims = _report_claims(report)
    return FusionReport(
        report_id=report.id,
        category=provenance.get("canonical_category"),
        latitude=location.get("lat"),
        longitude=location.get("lon"),
        coordinates_trusted=provenance.get("coordinates_trusted", False),
        received_at=_utc(report.received_at),
        location_phrase=report.location_text,
        source_reference=report.source_reference,
        facts={claim.field_name: claim.value for claim in claims if claim.value is not None},
        has_committed_operational_state=False,
    )


def _incident_fusion_view(incident: Incident) -> FusionReport:
    status_value = incident.status.value if hasattr(incident.status, "value") else str(incident.status)
    facts = {
        "casualty_count": incident.casualty_count,
        "trapped_person": incident.trapped_person,
        "road_blockage": incident.road_blockage,
    }
    return FusionReport(
        report_id=incident.id,
        category=incident.incident_type,
        latitude=incident.latitude,
        longitude=incident.longitude,
        coordinates_trusted=(
            incident.latitude is not None and incident.longitude is not None
        ),
        received_at=_utc(incident.created_at),
        location_phrase=incident.location_text,
        source_reference=(incident.provenance_json or {}).get("source_reference"),
        facts={key: value for key, value in facts.items() if value is not None},
        has_committed_operational_state=bool(incident.current_plan_id)
        or status_value not in {"ACTIVE_UNCONFIRMED", "RECEIVED", "INTERPRETING"},
    )


def _timeline_event(
    *, incident_id: str, event_type: str, details: dict[str, Any], created_at: datetime
) -> TimelineEvent:
    return TimelineEvent(
        id=new_timeline_event_id(),
        incident_id=incident_id,
        event_type=event_type,
        details_json=details,
        created_at=created_at,
    )


def _create_media_report(
    *,
    db: Session,
    content: bytes,
    media_kind: str,
    content_type: str | None,
    source_reference: str,
    incident_id: str | None,
    data_reality: DataReality,
) -> dict[str, Any]:
    if incident_id and db.get(Incident, incident_id) is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    if not content_type:
        raise HTTPException(status_code=422, detail="upload MIME type is required")
    try:
        stored = store_media(
            content,
            media_kind=media_kind,
            content_type=content_type,
        )
    except MediaValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now_utc = datetime.now(timezone.utc)
    processing_status = (
        "ASR_MANUAL_REQUIRED" if media_kind == "audio" else "VISION_MANUAL_REVIEW"
    )
    evidence_item = {
        "type": media_kind.upper(),
        "uri_or_reference": stored.media_reference,
        "extracted_facts": {},
        "provenance": {
            "source": "control_room_media_upload",
            "source_reference": source_reference,
            "media_id": stored.media_id,
            "mime_type": stored.mime_type,
            "data_reality": data_reality.value,
            "freshness_status": FreshnessStatus.FRESH.value,
            "received_at": now_utc.isoformat(),
        },
        "confidence_support": None,
        "created_at": now_utc.isoformat(),
    }
    report = Report(
        id=str(uuid.uuid4()),
        incident_id=incident_id,
        source_type=f"control_room_{media_kind}",
        source_reference=source_reference,
        raw_text="",
        received_at=now_utc,
        data_reality=data_reality,
        provenance_json=evidence_item["provenance"],
        processing_status=processing_status,
        evidence_items_json=[evidence_item],
        created_at=now_utc,
    )
    db.add(report)
    timeline_event = None
    if incident_id:
        timeline_event = _timeline_event(
            incident_id=incident_id,
            event_type="REPORT_CREATED",
            details={
                "report_id": report.id,
                "source_type": report.source_type,
                "processing_status": processing_status,
                "data_reality": data_reality.value,
            },
            created_at=now_utc,
        )
        db.add(timeline_event)
    db.commit()
    db.refresh(report)
    if timeline_event:
        publish_operations_event(
            event="timeline.appended",
            incident_id=incident_id,
            payload=serialize_timeline_event(timeline_event),
        )
    return serialize_report(report)


def _read_upload(file: UploadFile, *, media_kind: str) -> bytes:
    max_bytes = 15 * 1024 * 1024 if media_kind == "audio" else 10 * 1024 * 1024
    return file.file.read(max_bytes + 1)


@router.post(
    "/reports/intake/audio",
    status_code=status.HTTP_201_CREATED,
    response_model=ReportRead,
)
def intake_audio(
    file: Annotated[UploadFile, File(...)],
    source_reference: Annotated[str, Form(min_length=1, max_length=200)] = "control-room-upload",
    incident_id: Annotated[str | None, Form()] = None,
    data_reality: Annotated[DataReality, Form()] = DataReality.SIMULATED,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _create_media_report(
        db=db,
        content=_read_upload(file, media_kind="audio"),
        media_kind="audio",
        content_type=file.content_type,
        source_reference=source_reference,
        incident_id=incident_id,
        data_reality=data_reality,
    )


@router.post(
    "/reports/intake/image",
    status_code=status.HTTP_201_CREATED,
    response_model=ReportRead,
)
def intake_image(
    file: Annotated[UploadFile, File(...)],
    source_reference: Annotated[str, Form(min_length=1, max_length=200)] = "control-room-upload",
    incident_id: Annotated[str | None, Form()] = None,
    data_reality: Annotated[DataReality, Form()] = DataReality.SIMULATED,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _create_media_report(
        db=db,
        content=_read_upload(file, media_kind="image"),
        media_kind="image",
        content_type=file.content_type,
        source_reference=source_reference,
        incident_id=incident_id,
        data_reality=data_reality,
    )


@router.post("/reports/{report_id}/process")
def process_report(
    report_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    evidence_id = next(
        (
            item.get("provenance", {}).get("media_id") or item.get("uri_or_reference")
            for item in report.evidence_items_json or []
            if item.get("uri_or_reference")
        ),
        report.id,
    )
    result = process_structured_extraction(
        _structured_processing_text(report),
        evidence_id=evidence_id,
        report_id=report.id,
    )
    now_utc = datetime.now(timezone.utc)
    report.processing_status = (
        "AI_DISABLED_MANUAL_REQUIRED"
        if result.status is StructuredExtractionStatus.DISABLED
        else f"AI_{result.status.value}"
    )
    provenance = dict(report.provenance_json or {})
    provenance["ai_processing"] = {
        "status": result.status.value,
        "provider": result.provider,
        "model": result.model,
        "error_code": result.error_code,
        "retry_count": result.retry_count,
        "manual_fallback_required": result.manual_fallback_required,
        "processed_at": now_utc.isoformat(),
    }
    report.provenance_json = provenance
    if result.claims:
        report.evidence_items_json = append_claims_to_evidence_items(
            report.evidence_items_json,
            result.claims,
        )
    event = None
    if report.incident_id:
        event = _timeline_event(
            incident_id=report.incident_id,
            event_type="AI_PROCESSING_COMPLETED",
            details={
                "report_id": report.id,
                "status": result.status.value,
                "manual_fallback_required": result.manual_fallback_required,
                "claims_added": len(result.claims),
            },
            created_at=now_utc,
        )
        db.add(event)
    db.add(report)
    db.commit()
    db.refresh(report)
    if event:
        publish_operations_event(
            event="timeline.appended",
            incident_id=report.incident_id,
            payload=serialize_timeline_event(event),
        )
    return {
        "status": result.status.value,
        "result": result.model_dump(mode="json"),
        "report": serialize_report(report),
    }


@router.post("/reports/{report_id}/associate")
def associate_report(
    report_id: str,
    payload: ReportAssociationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _acquire_write_lock(db)
    report = db.get(Report, report_id)
    incident = db.get(Incident, payload.target_incident_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{payload.target_incident_id}' not found")
    if report.incident_id is not None:
        raise HTTPException(status_code=409, detail="report is already associated with an incident")
    if payload.expected_incident_version != incident.version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Incident version mismatch: expected {payload.expected_incident_version}, "
                f"but current version is {incident.version}"
            ),
        )

    result = evaluate_report_association(
        _report_fusion_view(report),
        _incident_fusion_view(incident),
    )
    now_utc = datetime.now(timezone.utc)
    report_provenance = dict(report.provenance_json or {})
    report_provenance["fusion_evaluation"] = result.model_dump(mode="json")
    report.provenance_json = report_provenance
    event = None
    if result.decision is FusionDecision.AUTO_ASSOCIATE:
        report.incident_id = incident.id
        previous_version = incident.version
        incident.version += 1
        incident.updated_at = now_utc
        event = _timeline_event(
            incident_id=incident.id,
            event_type="REPORT_ASSOCIATED",
            details={
                "report_id": report.id,
                "association_result": result.decision.value,
                "previous_incident_version": previous_version,
                "new_incident_version": incident.version,
                "operator_reference": payload.operator_reference,
                "explanation": result.model_dump(mode="json"),
            },
            created_at=now_utc,
        )
        db.add(event)
        db.add(incident)
    db.add(report)
    db.commit()
    db.refresh(report)
    if event:
        publish_operations_event(
            event="incident.updated",
            incident_id=incident.id,
            payload=serialize_incident(incident),
        )
    return {
        **result.model_dump(mode="json"),
        "incident_id": incident.id if report.incident_id else None,
        "incident_version": incident.version,
        "report": serialize_report(report),
    }


@router.post("/reports/{report_id}/manual-transcript")
def add_manual_transcript(
    report_id: str,
    payload: ManualTranscriptRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    now_utc = datetime.now(timezone.utc)
    evidence_items = list(report.evidence_items_json or [])
    evidence_items.append(
        {
            "type": "MANUAL_TRANSCRIPT",
            "uri_or_reference": report.source_reference,
            "extracted_facts": {"transcript": payload.transcript},
            "provenance": {
                "source": "operator_manual_transcript",
                "operator_reference": payload.operator_reference,
                "data_reality": DataReality.SIMULATED.value,
                "freshness_status": FreshnessStatus.FRESH.value,
                "created_at": now_utc.isoformat(),
            },
            "confidence_support": None,
            "created_at": now_utc.isoformat(),
        }
    )
    report.evidence_items_json = evidence_items
    report.processing_status = "MANUAL_TRANSCRIPT_PROVIDED"
    event = None
    if report.incident_id:
        event = _timeline_event(
            incident_id=report.incident_id,
            event_type="TRANSCRIPT_ADDED",
            details={
                "report_id": report.id,
                "operator_reference": payload.operator_reference,
                "data_reality": DataReality.SIMULATED.value,
            },
            created_at=now_utc,
        )
        db.add(event)
    db.add(report)
    db.commit()
    db.refresh(report)
    if event:
        publish_operations_event(
            event="timeline.appended",
            incident_id=report.incident_id,
            payload=serialize_timeline_event(event),
        )
    return serialize_report(report)


@router.post("/reports/{report_id}/transcribe")
def transcribe_report(
    report_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    media_item = next(
        (item for item in report.evidence_items_json or [] if item.get("type") == "AUDIO"),
        None,
    )
    if media_item is None:
        raise HTTPException(status_code=422, detail="report does not contain audio evidence")
    provenance = media_item.get("provenance", {})
    try:
        audio_path = resolve_media_path(
            str(media_item.get("uri_or_reference", "")),
            mime_type=str(provenance.get("mime_type", "")),
        )
        result = transcribe_with_fallback(
            audio_path,
            transcriber=configured_groq_transcriber,
        )
    except MediaValidationError as exc:
        result = ASRResult(
            status=ASRStatus.MANUAL_REQUIRED,
            failures=[{"provider": "local_media", "model": "", "code": str(exc)}],
            manual_fallback_required=True,
        )

    now_utc = datetime.now(timezone.utc)
    report.processing_status = (
        "ASR_SUCCEEDED" if result.status is ASRStatus.SUCCEEDED else "ASR_MANUAL_REQUIRED"
    )
    report_provenance = dict(report.provenance_json or {})
    report_provenance["asr_processing"] = result.model_dump(mode="json")
    report.provenance_json = report_provenance
    if result.transcript is not None:
        evidence_items = list(report.evidence_items_json or [])
        evidence_items.append(
            {
                "type": "ASR_TRANSCRIPT",
                "uri_or_reference": media_item.get("uri_or_reference"),
                "extracted_facts": {"transcript": result.transcript},
                "provenance": {
                    "source": "groq_asr",
                    "provider": result.provider,
                    "model": result.model,
                    "data_reality": DataReality.REAL_DERIVED.value,
                    "freshness_status": FreshnessStatus.FRESH.value,
                    "created_at": now_utc.isoformat(),
                },
                "confidence_support": None,
                "created_at": now_utc.isoformat(),
            }
        )
        report.evidence_items_json = evidence_items
    event = None
    if report.incident_id:
        event = _timeline_event(
            incident_id=report.incident_id,
            event_type="ASR_PROCESSED",
            details={
                "report_id": report.id,
                "status": result.status.value,
                "manual_fallback_required": result.manual_fallback_required,
            },
            created_at=now_utc,
        )
        db.add(event)
    db.add(report)
    db.commit()
    db.refresh(report)
    if event:
        publish_operations_event(
            event="timeline.appended",
            incident_id=report.incident_id,
            payload=serialize_timeline_event(event),
        )
    return {"status": result.status.value, "result": result.model_dump(mode="json"), "report": serialize_report(report)}


@router.post(
    "/reports/{report_id}/create-incident",
    status_code=status.HTTP_201_CREATED,
    response_model=IncidentRead,
)
def create_incident_from_report(
    report_id: str,
    payload: ReportIncidentActivationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create one incident from a reviewed report using explicit operator facts."""
    _acquire_write_lock(db)
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    if report.incident_id is not None:
        raise HTTPException(status_code=409, detail="report is already associated with an incident")

    now_utc = datetime.now(timezone.utc)
    report_reality = (
        report.data_reality.value
        if hasattr(report.data_reality, "value")
        else str(report.data_reality)
    )
    report_provenance = dict(report.provenance_json or {})
    required_resources = [
        {
            "resource_type": requirement.resource_type.value,
            "count": requirement.count,
            **(
                {"required_capability_tags": list(requirement.required_capability_tags)}
                if requirement.required_capability_tags is not None
                else {}
            ),
        }
        for requirement in payload.required_resources
    ]
    incident_id = str(uuid.uuid4())
    incident_provenance = {
        "source": "operator_report_activation",
        "data_reality": report_reality,
        "freshness_status": report_provenance.get(
            "freshness_status",
            FreshnessStatus.FRESH.value,
        ),
        "last_updated": now_utc.isoformat(),
        "location_resolved": payload.location is not None,
        "source_reference": payload.operator_reference,
        "source_report_id": report.id,
        "report_source_reference": report.source_reference,
    }
    incident = Incident(
        id=incident_id,
        version=1,
        incident_type=payload.incident_type,
        severity=payload.severity,
        confidence_level=payload.confidence_level,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=payload.location.lat if payload.location else None,
        longitude=payload.location.lon if payload.location else None,
        location_text=payload.location_text,
        casualty_count=payload.casualty_count,
        casualty_range=payload.casualty_range,
        trapped_person=payload.trapped_person,
        road_blockage=payload.road_blockage,
        transport_required=payload.transport_required,
        required_hospital_capabilities_json=payload.required_hospital_capabilities,
        required_resources_json=required_resources,
        current_plan_id=None,
        pending_replan_plan_id=None,
        created_at=now_utc,
        updated_at=now_utc,
        provenance_json=incident_provenance,
    )
    try:
        timeline_event = _timeline_event(
            incident_id=incident.id,
            event_type="INCIDENT_CREATED_FROM_REPORT",
            details={
                "report_id": report.id,
                "operator_reference": payload.operator_reference,
                "source": "operator_report_activation",
                "data_reality": report_reality,
                "status": IncidentStatus.ACTIVE_UNCONFIRMED.value,
                "incident_version": incident.version,
                "location_resolved": payload.location is not None,
            },
            created_at=now_utc,
        )
        report.incident_id = incident.id
        db.add_all([incident, report, timeline_event])
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(incident)

    result = serialize_incident(incident)
    publish_operations_event(
        event="incident.created",
        incident_id=incident.id,
        payload=result,
    )
    return result


@router.post("/incidents/{incident_id}/duplicate-merge")
def merge_duplicate_incident(
    incident_id: str,
    payload: DuplicateMergeRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _acquire_write_lock(db)
    redundant = db.get(Incident, incident_id)
    canonical = db.get(Incident, payload.canonical_incident_id)
    if redundant is None or canonical is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if redundant.id == canonical.id:
        raise HTTPException(status_code=409, detail="an incident cannot merge into itself")
    if payload.expected_incident_version != redundant.version:
        raise HTTPException(status_code=409, detail="redundant incident version mismatch")
    if payload.expected_canonical_incident_version != canonical.version:
        raise HTTPException(status_code=409, detail="canonical incident version mismatch")
    if redundant.current_plan_id or _incident_fusion_view(redundant).has_committed_operational_state:
        raise HTTPException(
            status_code=409,
            detail="REQUIRES_REVIEW: redundant incident has committed operational state",
        )

    now_utc = datetime.now(timezone.utc)
    reports = db.query(Report).filter(Report.incident_id == redundant.id).all()
    for report in reports:
        report.incident_id = canonical.id
        db.add(report)

    redundant.status = IncidentStatus.DUPLICATE_MERGED
    redundant.version += 1
    redundant.updated_at = now_utc
    redundant_provenance = dict(redundant.provenance_json or {})
    redundant_provenance["canonical_incident_id"] = canonical.id
    redundant_provenance["fusion_status"] = "DUPLICATE_MERGED"
    redundant.provenance_json = redundant_provenance

    canonical.version += 1
    canonical.updated_at = now_utc
    redundant_event = _timeline_event(
        incident_id=redundant.id,
        event_type="DUPLICATE_MERGED",
        details={
            "canonical_incident_id": canonical.id,
            "operator_reference": payload.operator_reference,
            "new_incident_version": redundant.version,
            "reports_attached": [report.id for report in reports],
        },
        created_at=now_utc,
    )
    canonical_event = _timeline_event(
        incident_id=canonical.id,
        event_type="DUPLICATE_INCIDENT_MERGED",
        details={
            "redundant_incident_id": redundant.id,
            "operator_reference": payload.operator_reference,
            "new_incident_version": canonical.version,
            "reports_attached": [report.id for report in reports],
        },
        created_at=now_utc,
    )
    db.add_all([redundant, canonical, redundant_event, canonical_event])
    db.commit()
    db.refresh(redundant)
    db.refresh(canonical)
    publish_operations_event(
        event="incident.updated",
        incident_id=canonical.id,
        payload=serialize_incident(canonical),
    )
    return {
        "canonical_incident": serialize_incident(canonical),
        "redundant_incident": serialize_incident(redundant),
        "reports_attached": [report.id for report in reports],
    }


@router.get("/reports/{report_id}/claims")
def get_report_claims(report_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    return {
        "report_id": report.id,
        "claims": [claim.model_dump(mode="json") for claim in _report_claims(report)],
        "processing_status": report.processing_status,
    }


@router.post("/reports/{report_id}/claims")
def ingest_report_claims(
    report_id: str,
    payload: ClaimsIngestRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    now_utc = datetime.now(timezone.utc)
    evidence_id = payload.evidence_id or str(uuid.uuid4())
    claims = build_evidence_claims(
        payload.claims,
        evidence_id=evidence_id,
        report_id=report.id,
        provider=payload.provider,
        model=payload.model,
        observed_at=now_utc,
        provenance={
            "source": "provider_claim_ingress",
            "provider": payload.provider,
            "model": payload.model,
            "data_reality": DataReality.REAL_DERIVED.value,
            "observed_at": now_utc.isoformat(),
        },
    )
    report.evidence_items_json = append_claims_to_evidence_items(
        report.evidence_items_json,
        claims,
    )
    all_claims = list(_report_claims(report))
    if report.incident_id:
        all_claims.extend(
            claim
            for claim in _incident_claims(db, report.incident_id)
            if claim.report_id != report.id
        )
    resolved = resolve_claims(all_claims)
    conflict_fields = sorted(
        field_name
        for field_name, fact in resolved.items()
        if fact.state.value == "CONFLICT"
    )
    report.processing_status = "REQUIRES_REVIEW" if conflict_fields else "CLAIMS_PERSISTED"
    event = None
    if report.incident_id:
        incident = db.get(Incident, report.incident_id)
        if incident is not None:
            provenance = dict(incident.provenance_json or {})
            provenance["fact_review_required"] = bool(conflict_fields)
            provenance["fact_review_fields"] = conflict_fields
            incident.provenance_json = provenance
            db.add(incident)
        event = _timeline_event(
            incident_id=report.incident_id,
            event_type="CLAIMS_PERSISTED",
            details={
                "report_id": report.id,
                "claims_added": len(claims),
                "conflict_fields": conflict_fields,
                "incident_review_required": bool(conflict_fields),
            },
            created_at=now_utc,
        )
        db.add(event)
    db.add(report)
    db.commit()
    db.refresh(report)
    if event:
        publish_operations_event(
            event="timeline.appended",
            incident_id=report.incident_id,
            payload=serialize_timeline_event(event),
        )
    return {
        "report_id": report.id,
        "processing_status": report.processing_status,
        "claims": [claim.model_dump(mode="json") for claim in _report_claims(report)],
        "resolved_facts": {field: value.model_dump(mode="json") for field, value in resolved.items()},
    }


@router.post("/incidents/{incident_id}/fact-claims/resolve")
def resolve_incident_claim(
    incident_id: str,
    payload: ClaimResolutionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    is_required_services = payload.field_name == "required_services"
    if payload.required_resources is not None and not is_required_services:
        raise HTTPException(
            status_code=422,
            detail="required_resources are only valid when resolving required_services",
        )
    if payload.field_name not in FACT_FIELD_NAMES and not is_required_services:
        raise HTTPException(status_code=422, detail="field is not an approved incident fact")
    claims = [
        claim
        for claim in _incident_claims(db, incident_id)
        if claim.field_name == payload.field_name
    ]
    if payload.selected_evidence_id and not any(
        claim.evidence_id == payload.selected_evidence_id and claim.value == payload.value
        for claim in claims
    ):
        raise HTTPException(status_code=409, detail="selected evidence claim does not match the value")

    if is_required_services:
        if not payload.selected_evidence_id:
            raise HTTPException(
                status_code=422,
                detail="selected_evidence_id is required when resolving required_services",
            )
        selected_claim = next(
            (
                claim
                for claim in claims
                if claim.evidence_id == payload.selected_evidence_id
                and claim.value == payload.value
            ),
            None,
        )
        if selected_claim is None or selected_claim.fact_state.value != "ASSERTED":
            raise HTTPException(
                status_code=422,
                detail="required_services must be resolved from an asserted selected claim",
            )
        _validated_required_service_types(payload.value, payload.required_resources)

    try:
        patch_field = (
            [requirement.model_dump(mode="json") for requirement in payload.required_resources]
            if is_required_services and payload.required_resources is not None
            else payload.value
        )
        patch_payload = IncidentFactsPatchRequest.model_validate(
            {
                "expected_incident_version": payload.expected_incident_version,
                "operator_reference": payload.operator_reference,
                "required_resources" if is_required_services else payload.field_name: patch_field,
            }
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="resolved value is invalid for the selected fact") from exc

    try:
        correction = _patch_incident_facts(
            incident_id,
            patch_payload,
            db,
            acquire_lock=True,
            commit=False,
            publish=False,
        )
        incident = db.get(Incident, incident_id)
        if incident is None:  # pragma: no cover - correction already validates this
            raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
        now_utc = datetime.now(timezone.utc)
        provenance = dict(incident.provenance_json or {})
        states = dict(provenance.get("resolved_fact_states", {}))
        states[payload.field_name] = "CONSISTENT"
        provenance["resolved_fact_states"] = states
        selected = dict(provenance.get("resolved_claim_evidence_ids", {}))
        selected[payload.field_name] = payload.selected_evidence_id
        provenance["resolved_claim_evidence_ids"] = selected
        incident.provenance_json = provenance
        event = _timeline_event(
            incident_id=incident_id,
            event_type="FACT_CLAIM_RESOLVED",
            details={
                "field_name": payload.field_name,
                "selected_evidence_id": payload.selected_evidence_id,
                "operator_reference": payload.operator_reference,
                "incident_version": incident.version,
                "timestamp": now_utc.isoformat(),
                **(
                    {
                        "confirmed_required_resources": [
                            requirement.model_dump(mode="json")
                            for requirement in payload.required_resources or []
                        ]
                    }
                    if is_required_services
                    else {}
                ),
            },
            created_at=now_utc,
        )
        db.add(incident)
        db.add(event)
        db.commit()
        db.refresh(incident)
    except Exception:
        db.rollback()
        raise

    publish_operations_event(
        event="incident.updated",
        incident_id=incident_id,
        payload=serialize_incident(incident),
    )
    return {**correction, "incident": serialize_incident(incident)}
