from __future__ import annotations

from datetime import datetime, timezone

from app.ai import EvidenceClaim, FactState, SupportLevel
from app.claims import append_claims_to_evidence_items, resolve_claims


def claim(field: str, value: object, state: FactState, evidence_id: str) -> EvidenceClaim:
    return EvidenceClaim(
        field_name=field,
        value=value,
        fact_state=state,
        evidence_id=evidence_id,
        support_level=SupportLevel.HIGH,
        provider="manual",
        observed_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
        provenance={"source": "operator"},
    )


def test_claim_persistence_appends_without_overwriting_existing_evidence() -> None:
    existing = [{"type": "RAW_TEXT", "extracted_facts": {"casualty_count": 1}}]
    claims = [claim("casualty_count", 2, FactState.ASSERTED, "evidence-2")]

    updated = append_claims_to_evidence_items(existing, claims)

    assert existing == [{"type": "RAW_TEXT", "extracted_facts": {"casualty_count": 1}}]
    assert len(updated) == 2
    assert updated[0] == existing[0]
    assert updated[1]["type"] == "EVIDENCE_CLAIMS"
    assert updated[1]["claims"][0]["value"] == 2


def test_conflicting_claims_are_preserved_and_require_review() -> None:
    result = resolve_claims(
        [
            claim("casualty_count", 2, FactState.ASSERTED, "evidence-a"),
            claim("casualty_count", 5, FactState.ASSERTED, "evidence-b"),
        ]
    )

    assert result["casualty_count"].state == "CONFLICT"
    assert result["casualty_count"].value is None
    assert result["casualty_count"].conflicting_values == [2, 5]
    assert result["casualty_count"].claim_count == 2


def test_unknown_claim_is_not_interpreted_as_zero_or_conflict() -> None:
    result = resolve_claims(
        [claim("casualty_count", None, FactState.UNKNOWN, "evidence-a")]
    )

    assert result["casualty_count"].state == "CONSISTENT"
    assert result["casualty_count"].value is None
    assert result["casualty_count"].conflicting_values == []


def test_explicit_negative_and_assertion_conflict() -> None:
    result = resolve_claims(
        [
            claim("trapped_person", False, FactState.EXPLICIT_NEGATIVE, "evidence-a"),
            claim("trapped_person", True, FactState.ASSERTED, "evidence-b"),
        ]
    )

    assert result["trapped_person"].state == "CONFLICT"
    assert result["trapped_person"].conflicting_values == [False, True]
