from __future__ import annotations

from pathlib import Path

from app.ai import FactState, ProviderCallError, StructuredExtractionStatus
from app.ai_processing import (
    ASRStatus,
    process_structured_extraction,
    transcribe_with_fallback,
)


def test_asr_uses_approved_fallback_inside_one_total_budget(tmp_path: Path) -> None:
    audio_path = tmp_path / "call.wav"
    audio_path.write_bytes(b"synthetic")
    now = iter([100.0, 100.0, 101.0, 101.0])
    calls: list[tuple[str, float]] = []

    def transcriber(path: Path, model: str, timeout: float) -> str:
        calls.append((model, timeout))
        if model == "whisper-large-v3":
            raise ProviderCallError("provider_server_error")
        return "manual-looking transcript from approved fallback"

    result = transcribe_with_fallback(
        audio_path,
        transcriber=transcriber,
        clock=lambda: next(now),
    )

    assert result.status is ASRStatus.SUCCEEDED
    assert result.provider == "groq"
    assert result.model == "whisper-large-v3-turbo"
    assert result.transcript is not None
    assert result.confidence is None
    assert [model for model, _ in calls] == [
        "whisper-large-v3",
        "whisper-large-v3-turbo",
    ]
    assert calls[0][1] == 30.0
    assert calls[1][1] == 29.0


def test_asr_budget_expiry_does_not_call_second_model(tmp_path: Path) -> None:
    audio_path = tmp_path / "call.wav"
    audio_path.write_bytes(b"synthetic")
    now = iter([100.0, 100.0, 131.0])
    calls: list[str] = []

    def transcriber(path: Path, model: str, timeout: float) -> str:
        calls.append(model)
        raise TimeoutError("provider timeout")

    result = transcribe_with_fallback(
        audio_path,
        transcriber=transcriber,
        clock=lambda: next(now),
    )

    assert result.status is ASRStatus.MANUAL_REQUIRED
    assert result.transcript is None
    assert calls == ["whisper-large-v3"]


def test_structured_provider_is_disabled_without_manual_fallback_loss() -> None:
    result = process_structured_extraction(
        "There are two casualties.",
        evidence_id="evidence-1",
        report_id="report-1",
    )

    assert result.status is StructuredExtractionStatus.DISABLED
    assert result.manual_fallback_required is True
    assert result.claims == []


def test_structured_provider_failure_is_visible_and_not_retried() -> None:
    calls: list[int] = []

    def request(attempt: int, timeout: float) -> dict[str, object]:
        calls.append(attempt)
        raise ProviderCallError("rate_limited")

    result = process_structured_extraction(
        "There are two casualties.",
        evidence_id="evidence-1",
        report_id="report-1",
        enabled=True,
        provider="groq",
        model="gpt-oss",
        request=request,
    )

    assert result.status is StructuredExtractionStatus.FAILED
    assert result.error_code == "rate_limited"
    assert result.manual_fallback_required is True
    assert calls == [0]


def test_structured_success_builds_evidence_claims_without_coordinates() -> None:
    result = process_structured_extraction(
        "Two people are injured at Tayaran.",
        evidence_id="evidence-1",
        report_id="report-1",
        enabled=True,
        provider="test-provider",
        model="test-model",
        request=lambda attempt, timeout: {
            "claims": [
                {
                    "field_name": "casualty_count",
                    "value": 2,
                    "fact_state": "ASSERTED",
                    "support_level": "HIGH",
                },
                {
                    "field_name": "location_text",
                    "value": "Tayaran",
                    "fact_state": "ASSERTED",
                    "support_level": "MEDIUM",
                },
                {
                    "field_name": "trapped_person",
                    "value": None,
                    "fact_state": "UNKNOWN",
                    "support_level": "LOW",
                },
            ]
        },
    )

    assert result.status is StructuredExtractionStatus.SUCCEEDED
    assert result.retry_count == 0
    assert [claim.fact_state for claim in result.claims] == [
        FactState.ASSERTED,
        FactState.ASSERTED,
        FactState.UNKNOWN,
    ]
