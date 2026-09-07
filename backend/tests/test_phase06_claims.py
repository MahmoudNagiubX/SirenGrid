from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.ai import (
    CLAIMABLE_FACT_FIELDS,
    FactState,
    ProviderCallError,
    StructuredExtractionStatus,
    build_evidence_claims,
    disabled_structured_extraction,
    parse_provider_claims,
    run_structured_schema_retry,
)


def test_claim_schema_preserves_unknown_and_is_immutable() -> None:
    claims = build_evidence_claims(
        [
            {
                "field_name": "casualty_count",
                "value": None,
                "fact_state": "UNKNOWN",
                "support_level": "LOW",
                "uncertainty": "not stated",
            }
        ],
        evidence_id="evidence-1",
        report_id="report-1",
        provider="manual",
        model=None,
        observed_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
        provenance={"source": "operator"},
    )

    assert claims[0].fact_state is FactState.UNKNOWN
    assert claims[0].value is None
    with pytest.raises(ValidationError):
        claims[0].value = 0  # type: ignore[misc]


def test_provider_claims_reject_coordinates_and_unknown_fields() -> None:
    assert "location_text" in CLAIMABLE_FACT_FIELDS
    with pytest.raises(ValidationError):
        parse_provider_claims(
            {
                "claims": [
                    {
                        "field_name": "latitude",
                        "value": 30.05,
                        "fact_state": "ASSERTED",
                        "support_level": "HIGH",
                    }
                ]
            }
        )

    with pytest.raises(ValidationError):
        parse_provider_claims(
            {
                "claims": [
                    {
                        "field_name": "casualty_count",
                        "value": 2,
                        "fact_state": "ASSERTED",
                        "support_level": "HIGH",
                        "unsupported": True,
                    }
                ]
            }
        )


def test_schema_retry_is_exactly_one_repair_attempt() -> None:
    calls: list[int] = []

    def request(attempt: int) -> dict[str, object]:
        calls.append(attempt)
        if attempt == 0:
            return {"claims": [{"field_name": "casualty_count"}]}
        return {
            "claims": [
                {
                    "field_name": "casualty_count",
                    "value": None,
                    "fact_state": "UNKNOWN",
                    "support_level": "LOW",
                }
            ]
        }

    parsed, retry_count = run_structured_schema_retry(request)

    assert parsed.claims[0].fact_state is FactState.UNKNOWN
    assert retry_count == 1
    assert calls == [0, 1]


def test_schema_retry_does_not_retry_provider_rate_limit() -> None:
    calls: list[int] = []

    def request(attempt: int) -> dict[str, object]:
        calls.append(attempt)
        raise ProviderCallError("rate_limited", retryable_schema=False)

    with pytest.raises(ProviderCallError):
        run_structured_schema_retry(request)

    assert calls == [0]


def test_structured_extraction_is_disabled_and_manual_fallback_is_explicit() -> None:
    result = disabled_structured_extraction()

    assert result.status is StructuredExtractionStatus.DISABLED
    assert result.manual_fallback_required is True
    assert result.provider is None
    assert result.claims == []
