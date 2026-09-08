"""Conservative, inspectable report association for Phase 06."""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DUPLICATE_SPATIAL_THRESHOLD_METERS = 500
DUPLICATE_TEMPORAL_WINDOW_SECONDS = 900


class FusionDecision(str, Enum):
    AUTO_ASSOCIATE = "AUTO_ASSOCIATE"
    SEPARATE_INCIDENT = "SEPARATE_INCIDENT"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class FusionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    category: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    coordinates_trusted: bool = False
    received_at: datetime
    location_phrase: str | None = None
    source_reference: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    has_committed_operational_state: bool = False


class FusionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: FusionDecision
    reason_code: str
    distance_m: float | None = None
    time_delta_seconds: int
    category_match: bool | None = None
    location_phrase_match: bool = False
    source_reference_match: bool = False
    token_overlap_match: bool = False
    conflicting_field_names: list[str] = Field(default_factory=list)


def _distance_meters(first: FusionReport, second: FusionReport) -> float | None:
    if (
        not first.coordinates_trusted
        or not second.coordinates_trusted
        or first.latitude is None
        or first.longitude is None
        or second.latitude is None
        or second.longitude is None
    ):
        return None
    radius = 6_371_000
    lat1, lat2 = math.radians(first.latitude), math.radians(second.latitude)
    delta_lat = math.radians(second.latitude - first.latitude)
    delta_lon = math.radians(second.longitude - first.longitude)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Generic road and place words carry no identifying information: two different
# streets in the same district share them routinely. They are excluded from the
# overlap signal so they cannot, on their own, associate distinct incidents.
GENERIC_LOCATION_TOKENS = frozenset(
    {
        # English
        "street",
        "road",
        "avenue",
        "square",
        "district",
        "area",
        "zone",
        "city",
        "region",
        "near",
        "next",
        "opposite",
        "front",
        "behind",
        "beside",
        "main",
        "north",
        "south",
        "east",
        "west",
        "cairo",
        "egypt",
        "nasr",
        # Arabic
        "شارع",
        "طريق",
        "ميدان",
        "منطقة",
        "حي",
        "مدينة",
        "القاهرة",
        "مصر",
        "امام",
        "أمام",
        "بجوار",
        "خلف",
        "قرب",
        "بالقرب",
        "شمال",
        "جنوب",
        "شرق",
        "غرب",
        "نصر",
    }
)
MINIMUM_SIGNIFICANT_TOKEN_LENGTH = 3
MINIMUM_SHARED_SIGNIFICANT_TOKENS = 2


def _tokens(value: str | None) -> set[str]:
    """Return normalized word tokens from a free-text location phrase."""
    if not value:
        return set()
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return set(re.findall(r"\w+", normalized, flags=re.UNICODE))


def _significant_tokens(value: str | None) -> set[str]:
    """Return only tokens that can actually identify a specific place.

    Very short fragments and generic road/place words are dropped, because a
    shared "street" says nothing about whether two reports describe one event.
    """
    return {
        token
        for token in _tokens(value)
        if len(token) >= MINIMUM_SIGNIFICANT_TOKEN_LENGTH
        and token not in GENERIC_LOCATION_TOKENS
    }


def _context_matches(first: FusionReport, second: FusionReport) -> tuple[bool, bool, bool]:
    first_phrase = _significant_tokens(first.location_phrase)
    second_phrase = _significant_tokens(second.location_phrase)
    location_match = bool(first_phrase and first_phrase == second_phrase)
    source_match = bool(
        first.source_reference
        and second.source_reference
        and first.source_reference == second.source_reference
    )
    # A single shared word is not corroboration. Overlap-only association needs
    # at least two shared significant tokens; a false merge is more dangerous
    # than a missed automatic one.
    shared = first_phrase & second_phrase
    token_match = len(shared) >= MINIMUM_SHARED_SIGNIFICANT_TOKENS
    return location_match, source_match, token_match


def _conflicting_fields(first: FusionReport, second: FusionReport) -> list[str]:
    conflicts: list[str] = []
    for field_name in sorted(set(first.facts) & set(second.facts)):
        first_value = first.facts[field_name]
        second_value = second.facts[field_name]
        if first_value is not None and second_value is not None and first_value != second_value:
            conflicts.append(field_name)
    return conflicts


def evaluate_report_association(
    first: FusionReport,
    second: FusionReport,
) -> FusionResult:
    distance_m = _distance_meters(first, second)
    time_delta = int(abs((second.received_at - first.received_at).total_seconds()))
    category_match = (
        None
        if not first.category or not second.category
        else first.category.casefold() == second.category.casefold()
    )
    location_match, source_match, token_match = _context_matches(first, second)
    conflicts = _conflicting_fields(first, second)
    common = dict(
        distance_m=distance_m,
        time_delta_seconds=time_delta,
        category_match=category_match,
        location_phrase_match=location_match,
        source_reference_match=source_match,
        token_overlap_match=token_match,
        conflicting_field_names=conflicts,
    )

    if distance_m is None:
        return FusionResult(
            decision=FusionDecision.REQUIRES_REVIEW,
            reason_code="trusted_coordinates_required",
            **common,
        )
    if distance_m > DUPLICATE_SPATIAL_THRESHOLD_METERS:
        return FusionResult(
            decision=FusionDecision.SEPARATE_INCIDENT,
            reason_code="outside_spatial_window",
            **common,
        )
    if time_delta > DUPLICATE_TEMPORAL_WINDOW_SECONDS:
        return FusionResult(
            decision=FusionDecision.SEPARATE_INCIDENT,
            reason_code="outside_temporal_window",
            **common,
        )
    if category_match is None:
        return FusionResult(
            decision=FusionDecision.REQUIRES_REVIEW,
            reason_code="category_unknown",
            **common,
        )
    if not category_match:
        return FusionResult(
            decision=FusionDecision.SEPARATE_INCIDENT,
            reason_code="category_incompatible",
            **common,
        )
    if conflicts:
        return FusionResult(
            decision=FusionDecision.REQUIRES_REVIEW,
            reason_code="structured_fact_conflict",
            **common,
        )
    if first.has_committed_operational_state or second.has_committed_operational_state:
        return FusionResult(
            decision=FusionDecision.REQUIRES_REVIEW,
            reason_code="committed_operational_state",
            **common,
        )
    if not (location_match or source_match or token_match):
        return FusionResult(
            decision=FusionDecision.REQUIRES_REVIEW,
            reason_code="context_match_required",
            **common,
        )
    return FusionResult(
        decision=FusionDecision.AUTO_ASSOCIATE,
        reason_code="all_deterministic_gates_passed",
        **common,
    )
