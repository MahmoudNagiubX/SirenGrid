"""Provider-neutral public social intelligence contracts and normalization."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai import FactState, ProviderClaimDraft, SupportLevel
from app.schemas import DataReality

BLUESKY_PUBLIC_API_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
SOCIAL_SOURCE_TYPE = "social_media"
SOCIAL_PROVIDER_VERSION = "SIRENGRID_SOCIAL_PROVIDER_V1"
SOCIAL_NORMALIZATION_VERSION = "SIRENGRID_SOCIAL_NORMALIZATION_V1"
MAX_SOCIAL_TEXT_LENGTH = 5_000

EMERGENCY_KEYWORDS: tuple[str, ...] = (
    "حادث",
    "تصادم",
    "حريق",
    "دخان",
    "إسعاف",
    "اسعاف",
    "مطافي",
    "طريق مقفول",
    "الطريق واقف",
    "accident",
    "collision",
    "fire",
    "smoke",
    "ambulance",
    "road closed",
)

LOCATION_CLUE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Nasr City",
        ("مدينة نصر", "nasr city", "nasr-city"),
    ),
    (
        "Abbas El Akkad",
        ("عباس العقاد", "abbas el akkad", "abbas el-akkad"),
    ),
    (
        "Makram Ebeid",
        ("مكرم عبيد", "makram ebeid", "makram obeid"),
    ),
    (
        "El Nasr Road",
        ("طريق النصر", "el nasr road", "nasr road"),
    ),
    (
        "Tayaran",
        ("الطيران", "طيران", "tayaran"),
    ),
    (
        "Rabaa",
        ("رابعة", "rabaa", "rabaah"),
    ),
)

_COLLISION_TERMS = ("حادث", "تصادم", "accident", "collision")
_FIRE_TERMS = ("حريق", "دخان", "مطافي", "fire", "smoke")
_ROAD_BLOCKAGE_TERMS = (
    "طريق مقفول",
    "الطريق واقف",
    "road closed",
    "road is closed",
    "blocked road",
)


class ProviderState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    DISABLED = "DISABLED"


class SocialPost(BaseModel):
    """A validated provider post; no operational meaning is implied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=80)
    post_id: str = Field(min_length=1, max_length=500)
    source_url: str | None = Field(default=None, max_length=1_000)
    text: str = Field(min_length=1, max_length=MAX_SOCIAL_TEXT_LENGTH)
    posted_at: datetime
    retrieved_at: datetime
    author_reference: str | None = Field(default=None, max_length=300)
    location_text: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    coordinates_trusted: bool = False
    media_references: tuple[str, ...] = ()
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    data_reality: DataReality

    @model_validator(mode="after")
    def validate_coordinates(self) -> SocialPost:
        has_lat = self.latitude is not None
        has_lon = self.longitude is not None
        if has_lat != has_lon:
            raise ValueError("latitude and longitude must be supplied together")
        if self.coordinates_trusted and not (has_lat and has_lon):
            raise ValueError("trusted coordinates must include latitude and longitude")
        return self


class SocialProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=80)
    status: ProviderState
    query: str
    requested_limit: int = Field(ge=1, le=50)
    retrieved_at: datetime
    posts: tuple[SocialPost, ...] = ()
    failure_code: str | None = None


class NormalizedSocialSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=80)
    provider_post_id: str = Field(min_length=1, max_length=500)
    source_url: str | None = Field(default=None, max_length=1_000)
    text: str = Field(min_length=1, max_length=MAX_SOCIAL_TEXT_LENGTH)
    posted_at: datetime
    retrieved_at: datetime
    location_text: str | None = Field(default=None, max_length=500)
    location_json: dict[str, float] | None = None
    coordinates_trusted: bool = False
    media_references: tuple[str, ...] = ()
    normalized_keywords: tuple[str, ...] = ()
    location_clues: tuple[str, ...] = ()
    canonical_category: str | None = None
    filter_state: str
    unknown_fields: tuple[str, ...] = ()
    claims: tuple[ProviderClaimDraft, ...] = ()
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    data_reality: DataReality
    provenance: dict[str, Any] = Field(default_factory=dict)


class SocialProvider:
    """Small provider boundary used by live and deterministic providers."""

    name = "social_provider"

    def search(
        self,
        *,
        query: str,
        limit: int,
        retrieved_at: datetime,
    ) -> SocialProviderResult:
        raise NotImplementedError


HttpGet = Callable[..., Any]


class BlueskyPublicProvider(SocialProvider):
    name = "bluesky_public"

    def __init__(
        self,
        *,
        http_get: HttpGet | None = None,
        endpoint: str = BLUESKY_PUBLIC_API_URL,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._http_get = http_get or httpx.get
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def search(
        self,
        *,
        query: str,
        limit: int,
        retrieved_at: datetime,
    ) -> SocialProviderResult:
        try:
            response = self._http_get(
                self._endpoint,
                params={"q": query, "limit": str(limit)},
                timeout=self._timeout_seconds,
            )
        except Exception:  # provider boundary: never leak network details
            return SocialProviderResult(
                provider=self.name,
                status=ProviderState.UNAVAILABLE,
                query=query,
                requested_limit=limit,
                retrieved_at=retrieved_at,
                failure_code="PROVIDER_UNAVAILABLE",
            )

        if response.status_code == 429:
            return SocialProviderResult(
                provider=self.name,
                status=ProviderState.RATE_LIMITED,
                query=query,
                requested_limit=limit,
                retrieved_at=retrieved_at,
                failure_code="RATE_LIMITED",
            )
        if response.status_code < 200 or response.status_code >= 300:
            return SocialProviderResult(
                provider=self.name,
                status=ProviderState.UNAVAILABLE,
                query=query,
                requested_limit=limit,
                retrieved_at=retrieved_at,
                failure_code="PROVIDER_HTTP_ERROR",
            )

        try:
            payload = response.json()
            posts = _parse_bluesky_posts(payload, retrieved_at=retrieved_at, limit=limit)
        except (TypeError, ValueError, KeyError):
            return SocialProviderResult(
                provider=self.name,
                status=ProviderState.INVALID_RESPONSE,
                query=query,
                requested_limit=limit,
                retrieved_at=retrieved_at,
                failure_code="INVALID_PROVIDER_RESPONSE",
            )
        return SocialProviderResult(
            provider=self.name,
            status=ProviderState.AVAILABLE,
            query=query,
            requested_limit=limit,
            retrieved_at=retrieved_at,
            posts=tuple(posts),
        )


def _parse_bluesky_posts(
    payload: Any,
    *,
    retrieved_at: datetime,
    limit: int,
) -> list[SocialPost]:
    if not isinstance(payload, dict) or not isinstance(payload.get("posts"), list):
        raise ValueError("posts must be a list")
    if len(payload["posts"]) > limit:
        raise ValueError("provider returned more posts than requested")
    parsed: list[SocialPost] = []
    for raw in payload["posts"]:
        if not isinstance(raw, dict):
            raise TypeError("post must be an object")
        uri = raw.get("uri")
        record = raw.get("record")
        if not isinstance(uri, str) or not uri or not isinstance(record, dict):
            raise ValueError("post uri and record are required")
        text = record.get("text")
        created_at = record.get("createdAt")
        if not isinstance(text, str) or not text.strip() or not isinstance(created_at, str):
            raise ValueError("post text and createdAt are required")
        posted_at = _parse_timestamp(created_at)
        author = raw.get("author")
        handle = author.get("handle") if isinstance(author, dict) else None
        rkey = uri.rsplit("/", 1)[-1]
        source_url = (
            f"https://bsky.app/profile/{handle}/post/{rkey}"
            if isinstance(handle, str) and handle
            else None
        )
        media_references = _media_references(raw.get("embed"))
        cid = raw.get("cid")
        metadata = {"cid": cid} if isinstance(cid, str) and cid else {}
        parsed.append(
            SocialPost(
                provider="bluesky_public",
                post_id=uri,
                source_url=source_url,
                text=text.strip(),
                posted_at=posted_at,
                retrieved_at=retrieved_at,
                author_reference=handle if isinstance(handle, str) else None,
                media_references=tuple(media_references),
                provider_metadata=metadata,
                data_reality=DataReality.REAL_PUBLIC,
            )
        )
    return parsed


def _media_references(embed: Any) -> list[str]:
    if not isinstance(embed, dict) or not isinstance(embed.get("images"), list):
        return []
    references: list[str] = []
    for image in embed["images"]:
        if not isinstance(image, dict):
            continue
        fullsize = image.get("fullsize")
        if isinstance(fullsize, str) and fullsize.startswith(("https://", "http://")):
            references.append(fullsize[:1_000])
    return references


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class DeterministicSyntheticSocialProvider(SocialProvider):
    name = "synthetic_social"

    def __init__(self, fixtures: Sequence[SocialPost] | None = None) -> None:
        self._fixtures = tuple(fixtures or _default_synthetic_posts())

    def search(
        self,
        *,
        query: str,
        limit: int,
        retrieved_at: datetime,
    ) -> SocialProviderResult:
        query_tokens = _tokens(query)
        posts: list[SocialPost] = []
        for fixture in self._fixtures:
            fixture_tokens = _tokens(f"{fixture.text} {fixture.location_text or ''}")
            if query_tokens and not query_tokens.intersection(fixture_tokens):
                continue
            posts.append(
                fixture.model_copy(
                    update={"posted_at": retrieved_at, "retrieved_at": retrieved_at}
                )
            )
            if len(posts) >= limit:
                break
        return SocialProviderResult(
            provider=self.name,
            status=ProviderState.AVAILABLE,
            query=query,
            requested_limit=limit,
            retrieved_at=retrieved_at,
            posts=tuple(posts),
        )


def _default_synthetic_posts() -> tuple[SocialPost, ...]:
    posted_at = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)

    def post(
        post_id: str,
        text: str,
        *,
        location_text: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        coordinates_trusted: bool = False,
    ) -> SocialPost:
        return SocialPost(
            provider="synthetic_social",
            post_id=post_id,
            source_url=f"synthetic://demo/{post_id}",
            text=text,
            posted_at=posted_at,
            retrieved_at=posted_at,
            location_text=location_text,
            latitude=latitude,
            longitude=longitude,
            coordinates_trusted=coordinates_trusted,
            data_reality=DataReality.SYNTHETIC,
            provider_metadata={"fixture": "PHASE09_SOCIAL_DEMO_V1"},
        )

    return (
        post(
            "synthetic-near-collision",
            "حادث على شارع الطيران في مدينة نصر. 2 injured. الطريق مقفول.",
            location_text="Tayaran Street, Nasr City",
            latitude=30.0561,
            longitude=31.3452,
            coordinates_trusted=True,
        ),
        post(
            "synthetic-vague-location",
            "حادث عاجل، possible accident report with vague location.",
        ),
        post(
            "synthetic-contradictory",
            "Accident near Tayaran, 5 injured.",
            location_text="Tayaran Street, Nasr City",
            latitude=30.0561,
            longitude=31.3452,
            coordinates_trusted=True,
        ),
        post(
            "synthetic-second-fire",
            "حريق ودخان قرب عباس العقاد في مدينة نصر.",
            location_text="Abbas El Akkad, Nasr City",
        ),
        post(
            "synthetic-irrelevant",
            "A weekend film club discussion with no emergency event.",
        ),
    )


def normalize_social_post(post: SocialPost) -> NormalizedSocialSignal:
    text = post.text.casefold()
    normalized_keywords = tuple(
        keyword for keyword in EMERGENCY_KEYWORDS if keyword.casefold() in text
    )
    location_clues = tuple(
        label
        for label, terms in LOCATION_CLUE_GROUPS
        if any(term.casefold() in text or term.casefold() in (post.location_text or "").casefold() for term in terms)
    )
    canonical_category = _canonical_category(text)
    filter_state = (
        "IRRELEVANT"
        if not normalized_keywords
        else "POTENTIALLY_RELEVANT"
        if location_clues
        else "INSUFFICIENT_CONTEXT"
    )
    claims = _explicit_claims(post, canonical_category, text)
    location_json = None
    if post.coordinates_trusted and post.latitude is not None and post.longitude is not None:
        location_json = {"lat": post.latitude, "lon": post.longitude}
    unknown_fields = tuple(
        field_name
        for field_name, is_known in (
            ("casualty_count", any(claim.field_name == "casualty_count" for claim in claims)),
            ("severity", False),
            ("required_resources", False),
            ("transport_required", False),
            ("coordinates", location_json is not None),
        )
        if not is_known
    )
    return NormalizedSocialSignal(
        provider=post.provider,
        provider_post_id=post.post_id,
        source_url=post.source_url,
        text=post.text,
        posted_at=post.posted_at,
        retrieved_at=post.retrieved_at,
        location_text=post.location_text,
        location_json=location_json,
        coordinates_trusted=post.coordinates_trusted,
        media_references=post.media_references,
        normalized_keywords=normalized_keywords,
        location_clues=location_clues,
        canonical_category=canonical_category,
        filter_state=filter_state,
        unknown_fields=unknown_fields,
        claims=tuple(claims),
        provider_metadata=post.provider_metadata,
        data_reality=post.data_reality,
        provenance={
            "source": post.provider,
            "provider_post_id": post.post_id,
            "data_reality": post.data_reality.value,
            "provider_policy": SOCIAL_PROVIDER_VERSION,
            "normalization_policy": SOCIAL_NORMALIZATION_VERSION,
            "coordinates_trusted": post.coordinates_trusted,
        },
    )


def _canonical_category(text: str) -> str | None:
    if any(term.casefold() in text for term in _COLLISION_TERMS):
        return "traffic_collision"
    if any(term.casefold() in text for term in _FIRE_TERMS):
        return "fire"
    return None


def _explicit_claims(
    post: SocialPost,
    canonical_category: str | None,
    text: str,
) -> list[ProviderClaimDraft]:
    claims: list[ProviderClaimDraft] = []
    uncertainty = "UNVERIFIED_PUBLIC_SOCIAL_TEXT"
    if canonical_category:
        claims.append(
            ProviderClaimDraft(
                field_name="incident_type",
                value=canonical_category,
                fact_state=FactState.ASSERTED,
                support_level=SupportLevel.LOW,
                uncertainty=uncertainty,
            )
        )
    if post.location_text:
        claims.append(
            ProviderClaimDraft(
                field_name="location_text",
                value=post.location_text,
                fact_state=FactState.ASSERTED,
                support_level=SupportLevel.LOW,
                uncertainty=uncertainty,
            )
        )
    casualty_match = re.search(
        r"\b(\d{1,2})\s+(?:casualties|injured|people injured)\b",
        text,
        flags=re.IGNORECASE,
    )
    if casualty_match:
        claims.append(
            ProviderClaimDraft(
                field_name="casualty_count",
                value=int(casualty_match.group(1)),
                fact_state=FactState.ASSERTED,
                support_level=SupportLevel.LOW,
                uncertainty=uncertainty,
            )
        )
    if any(term.casefold() in text for term in _ROAD_BLOCKAGE_TERMS):
        claims.append(
            ProviderClaimDraft(
                field_name="road_blockage",
                value=True,
                fact_state=FactState.ASSERTED,
                support_level=SupportLevel.LOW,
                uncertainty=uncertainty,
            )
        )
    return claims


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


__all__ = [
    "BLUESKY_PUBLIC_API_URL",
    "SOCIAL_NORMALIZATION_VERSION",
    "SOCIAL_PROVIDER_VERSION",
    "SOCIAL_SOURCE_TYPE",
    "BlueskyPublicProvider",
    "DeterministicSyntheticSocialProvider",
    "NormalizedSocialSignal",
    "ProviderState",
    "SocialPost",
    "SocialProvider",
    "SocialProviderResult",
    "normalize_social_post",
]
