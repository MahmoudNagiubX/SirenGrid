"""Provider-neutral Phase 06 evidence contracts and safe AI boundaries."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class FactState(str, Enum):
    ASSERTED = "ASSERTED"
    EXPLICIT_NEGATIVE = "EXPLICIT_NEGATIVE"
    UNKNOWN = "UNKNOWN"


class SupportLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ResolvedFactState(str, Enum):
    CONSISTENT = "CONSISTENT"
    CONFLICT = "CONFLICT"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class StructuredExtractionStatus(str, Enum):
    DISABLED = "DISABLED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"


CLAIMABLE_FACT_FIELDS = frozenset(
    {
        "incident_type",
        "location_text",
        "casualty_count",
        "casualty_range",
        "trapped_person",
        "road_blockage",
        "severity",
        "required_services",
        "transport_required",
        "required_hospital_capabilities",
    }
)


class ProviderCallError(RuntimeError):
    """Provider failure that must not be silently retried."""

    def __init__(self, code: str, *, retryable_schema: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable_schema = retryable_schema


class StructuredSchemaFailure(ValueError):
    def __init__(self, failures: tuple[Exception, ...]) -> None:
        super().__init__("structured output remained invalid after one controlled retry")
        self.failures = failures
        self.retry_count = 1


class ProviderClaimDraft(BaseModel):
    """Strict provider output; coordinates and operational fields are excluded."""

    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(min_length=1, max_length=80)
    value: Any | None = None
    fact_state: FactState
    support_level: SupportLevel
    uncertainty: str | None = Field(default=None, max_length=500)

    @field_validator("field_name")
    @classmethod
    def validate_field_name(cls, value: str) -> str:
        if value not in CLAIMABLE_FACT_FIELDS:
            raise ValueError("field is not approved for AI evidence claims")
        return value

    @model_validator(mode="after")
    def validate_unknown_value(self) -> ProviderClaimDraft:
        if self.fact_state is FactState.UNKNOWN and self.value is not None:
            raise ValueError("UNKNOWN claims must use a null value")
        if self.fact_state is not FactState.UNKNOWN and self.value is None:
            raise ValueError("asserted/negative claims require a value")
        return self


class ProviderClaimsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ProviderClaimDraft] = Field(default_factory=list, max_length=32)


class EvidenceClaim(BaseModel):
    """Immutable historical claim; it is never edited in place."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_name: str
    value: Any | None
    fact_state: FactState
    evidence_id: str
    report_id: str | None = None
    support_level: SupportLevel
    provider: str | None = None
    model: str | None = None
    observed_at: datetime
    provenance: dict[str, Any] = Field(default_factory=dict)
    uncertainty: str | None = None
    provider_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class StructuredExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StructuredExtractionStatus
    claims: list[EvidenceClaim] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    error_code: str | None = None
    retry_count: int = Field(default=0, ge=0, le=1)
    manual_fallback_required: bool = False


def parse_provider_claims(raw: str | dict[str, Any]) -> ProviderClaimsPayload:
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise TypeError("provider output must be a JSON object")
    return ProviderClaimsPayload.model_validate(raw)


def run_structured_schema_retry(
    request: Callable[[int], str | dict[str, Any]],
) -> tuple[ProviderClaimsPayload, int]:
    """Validate once and allow exactly one schema-repair request."""
    failures: list[Exception] = []
    for attempt in (0, 1):
        try:
            return parse_provider_claims(request(attempt)), attempt
        except ProviderCallError:
            raise
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
            failures.append(exc)
    raise StructuredSchemaFailure(tuple(failures)) from failures[-1]


def build_evidence_claims(
    drafts: list[ProviderClaimDraft | dict[str, Any]],
    *,
    evidence_id: str,
    report_id: str | None,
    provider: str | None,
    model: str | None,
    observed_at: datetime,
    provenance: dict[str, Any],
) -> list[EvidenceClaim]:
    parsed = [
        draft if isinstance(draft, ProviderClaimDraft) else ProviderClaimDraft.model_validate(draft)
        for draft in drafts
    ]
    return [
        EvidenceClaim(
            field_name=draft.field_name,
            value=draft.value,
            fact_state=draft.fact_state,
            evidence_id=evidence_id,
            report_id=report_id,
            support_level=draft.support_level,
            provider=provider,
            model=model,
            observed_at=observed_at,
            provenance=provenance,
            uncertainty=draft.uncertainty,
        )
        for draft in parsed
    ]


def disabled_structured_extraction() -> StructuredExtractionResult:
    return StructuredExtractionResult(
        status=StructuredExtractionStatus.DISABLED,
        error_code="provider_not_selected",
        manual_fallback_required=True,
    )
