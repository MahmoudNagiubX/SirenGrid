"""Append-only claim persistence helpers and deterministic resolution facts."""

from __future__ import annotations

import copy
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ai import EvidenceClaim, FactState, ResolvedFactState


class ResolvedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ResolvedFactState
    value: Any | None = None
    claim_count: int = Field(ge=1)
    conflicting_values: list[Any] = Field(default_factory=list)


def append_claims_to_evidence_items(
    evidence_items: list[dict[str, Any]] | None,
    claims: list[EvidenceClaim],
) -> list[dict[str, Any]]:
    """Append a new claim record; never rewrite a prior evidence item."""
    updated = copy.deepcopy(evidence_items or [])
    if claims:
        updated.append(
            {
                "type": "EVIDENCE_CLAIMS",
                "claims": [claim.model_dump(mode="json") for claim in claims],
            }
        )
    return updated


def _value_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def resolve_claims(claims: list[EvidenceClaim]) -> dict[str, ResolvedFact]:
    grouped: dict[str, list[EvidenceClaim]] = {}
    for claim in claims:
        grouped.setdefault(claim.field_name, []).append(claim)

    resolved: dict[str, ResolvedFact] = {}
    for field_name, field_claims in grouped.items():
        supported = [
            claim
            for claim in field_claims
            if claim.fact_state is not FactState.UNKNOWN
        ]
        values_by_key = {_value_key(claim.value): claim.value for claim in supported}
        ordered_values = [
            values_by_key[key] for key in sorted(values_by_key)
        ]
        state = (
            ResolvedFactState.CONFLICT
            if len(ordered_values) > 1
            else ResolvedFactState.CONSISTENT
        )
        resolved[field_name] = ResolvedFact(
            state=state,
            value=None if state is ResolvedFactState.CONFLICT or not ordered_values else ordered_values[0],
            claim_count=len(field_claims),
            conflicting_values=ordered_values if state is ResolvedFactState.CONFLICT else [],
        )
    return resolved
