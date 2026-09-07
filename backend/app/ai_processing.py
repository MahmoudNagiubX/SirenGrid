"""Bounded Phase 06 processing flows with manual-safe fallbacks."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from app.ai import (
    ProviderCallError,
    StructuredExtractionResult,
    StructuredExtractionStatus,
    StructuredSchemaFailure,
    build_evidence_claims,
    disabled_structured_extraction,
    run_structured_schema_retry,
)


class ASRStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"


class ASRResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ASRStatus
    transcript: str | None = None
    provider: str | None = None
    model: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    processing_budget_seconds: int = 30
    failures: list[dict[str, str]] = Field(default_factory=list)
    manual_fallback_required: bool = False


def _failure_code(error: Exception) -> str:
    if isinstance(error, ProviderCallError):
        return error.code
    if isinstance(error, TimeoutError):
        return "provider_timeout"
    if isinstance(error, OSError):
        return "audio_read_error"
    return "provider_failure"


def transcribe_with_fallback(
    audio_path: Path,
    *,
    transcriber: Callable[[Path, str, float], str],
    budget_seconds: int = 30,
    clock: Callable[[], float] = time.monotonic,
) -> ASRResult:
    """Run the approved ASR chain against one shared monotonic deadline."""
    started = clock()
    deadline = started + budget_seconds
    failures: list[dict[str, str]] = []
    chain = (
        ("groq", "whisper-large-v3"),
        ("groq", "whisper-large-v3-turbo"),
    )
    for provider, model in chain:
        remaining = deadline - clock()
        if remaining <= 0:
            break
        try:
            transcript = transcriber(audio_path, model, remaining)
            if not isinstance(transcript, str) or not transcript.strip():
                raise ProviderCallError("missing_transcript")
            return ASRResult(
                status=ASRStatus.SUCCEEDED,
                transcript=transcript,
                provider=provider,
                model=model,
                processing_budget_seconds=budget_seconds,
                failures=failures,
            )
        except Exception as exc:  # provider boundary: preserve safe error category only
            failures.append({"provider": provider, "model": model, "code": _failure_code(exc)})

    return ASRResult(
        status=ASRStatus.MANUAL_REQUIRED,
        processing_budget_seconds=budget_seconds,
        failures=failures,
        manual_fallback_required=True,
    )


def process_structured_extraction(
    text: str,
    *,
    evidence_id: str,
    report_id: str | None,
    enabled: bool = False,
    provider: str | None = None,
    model: str | None = None,
    request: Callable[[int, float], str | dict[str, Any]] | None = None,
    budget_seconds: int = 30,
    clock: Callable[[], float] = time.monotonic,
    provenance: dict[str, Any] | None = None,
) -> StructuredExtractionResult:
    """Process provider output only when explicitly enabled/configured."""
    del text
    if not enabled:
        return disabled_structured_extraction()
    if request is None or not provider or not model:
        return StructuredExtractionResult(
            status=StructuredExtractionStatus.FAILED,
            provider=provider,
            model=model,
            error_code="provider_not_configured",
            manual_fallback_required=True,
        )

    deadline = clock() + budget_seconds

    def bounded_request(attempt: int) -> str | dict[str, Any]:
        remaining = deadline - clock()
        if remaining <= 0:
            raise ProviderCallError("processing_budget_exhausted")
        return request(attempt, remaining)

    try:
        payload, retry_count = run_structured_schema_retry(bounded_request)
    except ProviderCallError as exc:
        return StructuredExtractionResult(
            status=StructuredExtractionStatus.FAILED,
            provider=provider,
            model=model,
            error_code=exc.code,
            manual_fallback_required=True,
        )
    except StructuredSchemaFailure:
        return StructuredExtractionResult(
            status=StructuredExtractionStatus.FAILED,
            provider=provider,
            model=model,
            error_code="invalid_after_one_retry",
            retry_count=1,
            manual_fallback_required=True,
        )

    observed_at = datetime.now(timezone.utc)
    claims = build_evidence_claims(
        payload.claims,
        evidence_id=evidence_id,
        report_id=report_id,
        provider=provider,
        model=model,
        observed_at=observed_at,
        provenance=provenance
        or {
            "source": "ai_interpretation",
            "provider": provider,
            "model": model,
            "data_reality": "REAL_DERIVED",
        },
    )
    return StructuredExtractionResult(
        status=StructuredExtractionStatus.SUCCEEDED,
        claims=claims,
        provider=provider,
        model=model,
        retry_count=retry_count,
    )
