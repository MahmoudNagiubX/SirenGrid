from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.config import settings
from app.db import init_db
from app.main import app
from app.models import Incident, Report, TimelineEvent
from app.phase06_api import _structured_processing_text
from app.schemas import IncidentStatus

PNG_BYTES = b"\x89PNG\r\n\x1a\n"
WAV_BYTES = b"RIFF\x04\x00\x00\x00WAVE"


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _incident_payload() -> dict[str, Any]:
    return {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Tayaran Street",
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "phase06-test",
    }


def test_structured_processing_prefers_manual_then_asr_then_raw_text() -> None:
    report = Report(
        id="transcript-precedence-report",
        source_type="audio",
        source_reference="call-transcript-precedence",
        raw_text="raw report text",
        evidence_items_json=[
            {"type": "ASR_TRANSCRIPT", "extracted_facts": {"transcript": "asr transcript"}},
            {"type": "MANUAL_TRANSCRIPT", "extracted_facts": {"transcript": "manual transcript"}},
        ],
    )

    assert _structured_processing_text(report) == "manual transcript"
    report.evidence_items_json = report.evidence_items_json[:1]
    assert _structured_processing_text(report) == "asr transcript"
    report.evidence_items_json = []
    assert _structured_processing_text(report) == "raw report text"


def test_operator_can_explicitly_create_one_incident_from_standalone_report(client: TestClient) -> None:
    report = client.post(
        "/api/v1/reports",
        json={"source_type": "control_room_text", "source_reference": "activation-test", "raw_text": "collision"},
    ).json()
    payload = {**_incident_payload(), "operator_reference": "activation-operator"}
    created = client.post(f"/api/v1/reports/{report['id']}/create-incident", json=payload)

    assert created.status_code == 201, created.text
    assert created.json()["provenance"]["source"] == "operator_report_activation"
    assert client.post(f"/api/v1/reports/{report['id']}/create-incident", json=payload).status_code == 409


def test_audio_upload_persists_opaque_media_and_requires_manual_transcript(
    client: TestClient,
    db_session: Session,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "phase06_media_dir", tmp_path)

    response = client.post(
        "/api/v1/reports/intake/audio",
        files={"file": ("caller.wav", WAV_BYTES, "audio/wav")},
        data={"source_reference": "call-001"},
    )

    assert response.status_code == 201, response.text
    report = response.json()
    assert report["raw_text"] == ""
    assert report["processing_status"] == "ASR_MANUAL_REQUIRED"
    evidence = report["evidence_items"][0]
    assert evidence["uri_or_reference"].startswith("media:")
    assert "storage_path" not in report
    assert "Windows" not in response.text
    persisted = db_session.get(Report, report["id"])
    assert persisted is not None
    assert persisted.incident_id is None
    assert list(tmp_path.iterdir())


def test_image_upload_is_retained_and_spoofed_image_and_video_are_rejected(
    client: TestClient,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "phase06_media_dir", tmp_path)

    image = client.post(
        "/api/v1/reports/intake/image",
        files={"file": ("evidence.png", PNG_BYTES, "image/png")},
        data={"source_reference": "image-001"},
    )
    spoofed_image = client.post(
        "/api/v1/reports/intake/image",
        files={"file": ("evidence.png", b"PNG synthetic", "image/png")},
        data={"source_reference": "image-spoofed"},
    )
    video = client.post(
        "/api/v1/reports/intake/image",
        files={"file": ("evidence.mp4", b"video", "video/mp4")},
        data={"source_reference": "image-002"},
    )

    assert image.status_code == 201, image.text
    assert image.json()["processing_status"] == "VISION_MANUAL_REVIEW"
    assert spoofed_image.status_code == 422
    assert video.status_code == 422
    assert len(list(tmp_path.glob("*.png"))) == 1


def test_default_structured_processing_is_visible_and_does_not_mutate_incident(
    client: TestClient,
    db_session: Session,
) -> None:
    created = client.post("/api/v1/intake/manual", json=_incident_payload())
    incident = created.json()
    report = client.post(
        "/api/v1/reports",
        json={
            "incident_id": incident["id"],
            "source_type": "control_room_text",
            "source_reference": "text-001",
            "raw_text": "Two people may be injured.",
        },
    )
    assert report.status_code == 201, report.text

    processed = client.post(f"/api/v1/reports/{report.json()['id']}/process")

    assert processed.status_code == 200, processed.text
    assert processed.json()["status"] == "DISABLED"
    current = db_session.get(Incident, incident["id"])
    assert current is not None
    assert current.version == 1
    assert current.status == IncidentStatus.ACTIVE_UNCONFIRMED


def test_operator_resolves_claim_with_one_version_increment_and_history_retained(
    client: TestClient,
    db_session: Session,
) -> None:
    created = client.post("/api/v1/intake/manual", json=_incident_payload())
    incident = created.json()
    observed = datetime(2026, 9, 8, tzinfo=timezone.utc).isoformat()
    report = Report(
        id="claim-report-1",
        incident_id=incident["id"],
        source_type="control_room_text",
        source_reference="caller-a",
        raw_text="Caller says two people are injured.",
        received_at=datetime.now(timezone.utc),
        data_reality="SIMULATED",
        provenance_json={"source": "test"},
        processing_status="PROCESSED",
        evidence_items_json=[
            {
                "type": "EVIDENCE_CLAIMS",
                "claims": [
                    {
                        "field_name": "casualty_count",
                        "value": 2,
                        "fact_state": "ASSERTED",
                        "evidence_id": "evidence-a",
                        "report_id": "claim-report-1",
                        "support_level": "HIGH",
                        "provider": "manual",
                        "model": None,
                        "observed_at": observed,
                        "provenance": {"source": "test"},
                        "uncertainty": None,
                        "provider_confidence": None,
                    }
                ],
            }
        ],
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(report)
    db_session.commit()

    resolved = client.post(
        f"/api/v1/incidents/{incident['id']}/fact-claims/resolve",
        json={
            "expected_incident_version": 1,
            "operator_reference": "operator-claim-review",
            "field_name": "casualty_count",
            "value": 2,
            "selected_evidence_id": "evidence-a",
        },
    )

    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["incident"]["version"] == 2
    assert resolved.json()["incident"]["casualty_count"] == 2
    events = db_session.query(TimelineEvent).filter_by(incident_id=incident["id"]).all()
    assert any(event.event_type == "FACT_CLAIM_RESOLVED" for event in events)
    retained = db_session.get(Report, "claim-report-1")
    assert retained is not None
    assert retained.evidence_items_json[0]["claims"][0]["value"] == 2


def test_related_standalone_report_is_auto_associated_once_with_audit_event(
    client: TestClient,
    db_session: Session,
) -> None:
    created = client.post("/api/v1/intake/manual", json=_incident_payload())
    incident = created.json()
    standalone = client.post(
        "/api/v1/reports",
        json={
            "source_type": "control_room_text",
            "source_reference": "caller-b",
            "raw_text": "A second report at Tayaran.",
            "location_text": "Tayaran Street",
            "location": {"lat": 30.0562, "lon": 31.3453},
            "provenance": {
                "source": "caller-b",
                "canonical_category": "traffic_collision",
                "coordinates_trusted": True,
            },
        },
    )
    assert standalone.status_code == 201, standalone.text

    associated = client.post(
        f"/api/v1/reports/{standalone.json()['id']}/associate",
        json={
            "target_incident_id": incident["id"],
            "expected_incident_version": 1,
            "operator_reference": "fusion-operator",
        },
    )

    assert associated.status_code == 200, associated.text
    assert associated.json()["decision"] == "AUTO_ASSOCIATE"
    assert associated.json()["incident_version"] == 2
    persisted = db_session.get(Report, standalone.json()["id"])
    assert persisted is not None
    assert persisted.incident_id == incident["id"]
    events = db_session.query(TimelineEvent).filter_by(incident_id=incident["id"]).all()
    assert any(event.event_type == "REPORT_ASSOCIATED" for event in events)


def test_fusion_review_does_not_mutate_incident_or_force_merge(
    client: TestClient,
    db_session: Session,
) -> None:
    created = client.post("/api/v1/intake/manual", json=_incident_payload())
    incident = created.json()
    standalone = client.post(
        "/api/v1/reports",
        json={
            "source_type": "control_room_text",
            "source_reference": "caller-c",
            "raw_text": "A report with no trusted location.",
            "location_text": "Somewhere in Nasr City",
            "provenance": {"canonical_category": "traffic_collision"},
        },
    )
    assert standalone.status_code == 201

    reviewed = client.post(
        f"/api/v1/reports/{standalone.json()['id']}/associate",
        json={
            "target_incident_id": incident["id"],
            "expected_incident_version": 1,
            "operator_reference": "fusion-operator",
        },
    )

    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["decision"] == "REQUIRES_REVIEW"
    current = db_session.get(Incident, incident["id"])
    assert current is not None
    assert current.version == 1
    assert db_session.get(Report, standalone.json()["id"]).incident_id is None


def test_manual_transcript_fallback_appends_transcript_without_overwriting_media(
    client: TestClient,
    db_session: Session,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "phase06_media_dir", tmp_path)
    uploaded = client.post(
        "/api/v1/reports/intake/audio",
        files={"file": ("caller.wav", WAV_BYTES, "audio/wav")},
        data={"source_reference": "call-manual"},
    )
    report_id = uploaded.json()["id"]

    transcript = client.post(
        f"/api/v1/reports/{report_id}/manual-transcript",
        json={
            "operator_reference": "transcript-operator",
            "transcript": "Caller reports a collision near Tayaran; casualty count unknown.",
        },
    )

    assert transcript.status_code == 200, transcript.text
    data = transcript.json()
    assert data["processing_status"] == "MANUAL_TRANSCRIPT_PROVIDED"
    assert data["raw_text"] == ""
    assert data["evidence_items"][0]["type"] == "AUDIO"
    assert data["evidence_items"][1]["type"] == "MANUAL_TRANSCRIPT"
    assert data["evidence_items"][1]["extracted_facts"]["transcript"].startswith("Caller")
    persisted = db_session.get(Report, report_id)
    assert persisted is not None
    assert len(persisted.evidence_items_json) == 2


def test_explicit_asr_action_appends_transcript_without_mutating_incident(
    client: TestClient,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    monkeypatch.setattr(settings, "phase06_media_dir", tmp_path)
    monkeypatch.setattr(
        "app.phase06_api.configured_groq_transcriber",
        lambda path, model, timeout: "نسخة تفريغ تجريبية",
    )
    created = client.post("/api/v1/intake/manual", json=_incident_payload()).json()
    uploaded = client.post(
        "/api/v1/reports/intake/audio",
        files={"file": ("caller.wav", WAV_BYTES, "audio/wav")},
        data={"source_reference": "call-asr", "incident_id": created["id"]},
    )
    assert uploaded.status_code == 201

    transcribed = client.post(f"/api/v1/reports/{uploaded.json()['id']}/transcribe")

    assert transcribed.status_code == 200, transcribed.text
    assert transcribed.json()["status"] == "SUCCEEDED"
    assert transcribed.json()["report"]["evidence_items"][-1]["type"] == "ASR_TRANSCRIPT"
    assert transcribed.json()["report"]["evidence_items"][-1]["provenance"]["model"] == "whisper-large-v3"
    current = db_session.get(Incident, created["id"])
    assert current is not None
    assert current.version == 1


def test_claim_ingress_preserves_conflict_and_requires_review_without_version_increment(
    client: TestClient,
    db_session: Session,
) -> None:
    incident = client.post("/api/v1/intake/manual", json=_incident_payload()).json()
    report = client.post(
        "/api/v1/reports",
        json={
            "incident_id": incident["id"],
            "source_type": "control_room_text",
            "source_reference": "conflict-report",
            "raw_text": "Two callers disagree about casualties.",
        },
    ).json()

    first = client.post(
        f"/api/v1/reports/{report['id']}/claims",
        json={
            "provider": "test-provider",
            "model": "test-model",
            "evidence_id": "evidence-a",
            "claims": [
                {
                    "field_name": "casualty_count",
                    "value": 2,
                    "fact_state": "ASSERTED",
                    "support_level": "HIGH",
                }
            ],
        },
    )
    second = client.post(
        f"/api/v1/reports/{report['id']}/claims",
        json={
            "provider": "test-provider",
            "model": "test-model",
            "evidence_id": "evidence-b",
            "claims": [
                {
                    "field_name": "casualty_count",
                    "value": 5,
                    "fact_state": "ASSERTED",
                    "support_level": "MEDIUM",
                }
            ],
        },
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["processing_status"] == "REQUIRES_REVIEW"
    assert len(second.json()["claims"]) == 2
    assert second.json()["resolved_facts"]["casualty_count"]["claim_count"] == 2
    current = db_session.get(Incident, incident["id"])
    assert current is not None
    assert current.version == 1


def test_explicit_duplicate_merge_preserves_reports_and_marks_redundant_incident(
    client: TestClient,
    db_session: Session,
) -> None:
    canonical = client.post("/api/v1/intake/manual", json=_incident_payload()).json()
    redundant = client.post(
        "/api/v1/intake/manual",
        json={**_incident_payload(), "location_text": "Tayaran Street report B"},
    ).json()
    source_report = client.post(
        "/api/v1/incidents/{}/reports".format(redundant["id"]),
        json={
            "source_type": "operator_manual_entry",
            "source_reference": "redundant-report",
            "raw_text": "Report attached to redundant incident.",
        },
    )
    assert source_report.status_code == 201

    merged = client.post(
        f"/api/v1/incidents/{redundant['id']}/duplicate-merge",
        json={
            "canonical_incident_id": canonical["id"],
            "expected_incident_version": 1,
            "expected_canonical_incident_version": 1,
            "operator_reference": "duplicate-reviewer",
        },
    )

    assert merged.status_code == 200, merged.text
    assert merged.json()["redundant_incident"]["status"] == "DUPLICATE_MERGED"
    assert merged.json()["redundant_incident"]["version"] == 2
    assert merged.json()["canonical_incident"]["version"] == 2
    retained = db_session.get(Report, source_report.json()["id"])
    assert retained is not None
    assert retained.incident_id == canonical["id"]
    redundant_events = db_session.query(TimelineEvent).filter_by(incident_id=redundant["id"]).all()
    canonical_events = db_session.query(TimelineEvent).filter_by(incident_id=canonical["id"]).all()
    assert any(event.event_type == "DUPLICATE_MERGED" for event in redundant_events)
    assert any(event.event_type == "DUPLICATE_INCIDENT_MERGED" for event in canonical_events)


def test_duplicate_merge_refuses_redundant_incident_with_committed_state(
    client: TestClient,
    db_session: Session,
) -> None:
    canonical = client.post("/api/v1/intake/manual", json=_incident_payload()).json()
    redundant = client.post("/api/v1/intake/manual", json=_incident_payload()).json()
    db_redundant = db_session.get(Incident, redundant["id"])
    assert db_redundant is not None
    db_redundant.current_plan_id = "committed-plan"
    db_session.commit()

    response = client.post(
        f"/api/v1/incidents/{redundant['id']}/duplicate-merge",
        json={
            "canonical_incident_id": canonical["id"],
            "expected_incident_version": 1,
            "expected_canonical_incident_version": 1,
            "operator_reference": "duplicate-reviewer",
        },
    )

    assert response.status_code == 409
    unchanged = db_session.get(Incident, redundant["id"])
    assert unchanged is not None
    assert unchanged.status == IncidentStatus.ACTIVE_UNCONFIRMED
    assert unchanged.version == 1
