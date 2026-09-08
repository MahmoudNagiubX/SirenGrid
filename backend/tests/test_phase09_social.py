from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.db import init_db
from app.main import app
from app.models import Incident, Report, TimelineEvent
from app.social import (
    BlueskyPublicProvider,
    ProviderState,
    SocialPost,
    normalize_social_post,
)


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
        "location_text": "Tayaran Street, Nasr City",
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "phase09-test",
    }


def test_social_post_normalization_generates_only_explicit_claims() -> None:
    post = SocialPost(
        provider="synthetic_social",
        post_id="synthetic-explicit-1",
        source_url="synthetic://demo/synthetic-explicit-1",
        text="حادث على شارع الطيران في مدينة نصر. 2 injured. الطريق مقفول.",
        posted_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 9, 8, 0, 1, tzinfo=timezone.utc),
        location_text="Tayaran Street, Nasr City",
        latitude=None,
        longitude=None,
        coordinates_trusted=False,
        data_reality="SYNTHETIC",
    )

    normalized = normalize_social_post(post)

    assert normalized.filter_state == "POTENTIALLY_RELEVANT"
    assert normalized.canonical_category == "traffic_collision"
    assert normalized.location_clues == ("Nasr City", "Tayaran")
    assert normalized.location_json is None
    claims = {claim.field_name: claim for claim in normalized.claims}
    assert claims["incident_type"].value == "traffic_collision"
    assert claims["casualty_count"].value == 2
    assert claims["road_blockage"].value is True
    assert "severity" not in claims
    assert "required_resources" not in claims


def test_bluesky_public_provider_validates_posts_without_auth() -> None:
    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "posts": [
                    {
                        "uri": "at://did:plc:test/app.bsky.feed.post/abc123",
                        "cid": "bafytest",
                        "author": {"did": "did:plc:test", "handle": "demo.example"},
                        "record": {
                            "text": "Accident near Tayaran, Nasr City",
                            "createdAt": "2026-09-08T10:00:00Z",
                        },
                        "indexedAt": "2026-09-08T10:00:01Z",
                    }
                ]
            }

    captured: dict[str, Any] = {}

    def fake_get(url: str, *, params: dict[str, str], timeout: float) -> FakeResponse:
        captured.update(url=url, params=params, timeout=timeout)
        return FakeResponse()

    provider = BlueskyPublicProvider(http_get=fake_get)
    result = provider.search(
        query="Nasr City accident",
        limit=5,
        retrieved_at=datetime(2026, 9, 8, 10, 1, tzinfo=timezone.utc),
    )

    assert result.status is ProviderState.AVAILABLE
    assert len(result.posts) == 1
    assert result.posts[0].post_id.startswith("at://")
    assert result.posts[0].data_reality.value == "REAL_PUBLIC"
    assert captured["params"] == {"q": "Nasr City accident", "limit": "5"}
    assert captured["timeout"] > 0


def test_bluesky_provider_failure_is_visible_and_does_not_fabricate_posts() -> None:
    def failing_get(url: str, *, params: dict[str, str], timeout: float) -> Any:
        raise TimeoutError("provider timeout")

    provider = BlueskyPublicProvider(http_get=failing_get)
    result = provider.search(
        query="accident",
        limit=5,
        retrieved_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )

    assert result.status is ProviderState.UNAVAILABLE
    assert result.posts == ()
    assert result.failure_code == "PROVIDER_UNAVAILABLE"


@pytest.mark.parametrize(
    ("status_code", "expected_state", "expected_code"),
    [
        (429, ProviderState.RATE_LIMITED, "RATE_LIMITED"),
        (502, ProviderState.UNAVAILABLE, "PROVIDER_HTTP_ERROR"),
    ],
)
def test_bluesky_provider_http_failures_are_typed(
    status_code: int,
    expected_state: ProviderState,
    expected_code: str,
) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.status_code = status_code

        def json(self) -> dict[str, Any]:
            return {}

    provider = BlueskyPublicProvider(
        http_get=lambda url, *, params, timeout: FakeResponse()
    )
    result = provider.search(
        query="accident",
        limit=5,
        retrieved_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )

    assert result.status is expected_state
    assert result.failure_code == expected_code
    assert result.posts == ()


def test_bluesky_provider_malformed_payload_is_not_accepted() -> None:
    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"posts": [{"uri": "not-enough-fields"}]}

    provider = BlueskyPublicProvider(
        http_get=lambda url, *, params, timeout: FakeResponse()
    )
    result = provider.search(
        query="accident",
        limit=5,
        retrieved_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )

    assert result.status is ProviderState.INVALID_RESPONSE
    assert result.failure_code == "INVALID_PROVIDER_RESPONSE"
    assert result.posts == ()


def test_synthetic_refresh_persists_signal_and_is_idempotent(
    client: TestClient,
    db_session: Session,
) -> None:
    first = client.post(
        "/api/v1/social/refresh",
        json={"provider": "synthetic", "query": "accident Nasr City"},
    )
    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["provider_status"] == "AVAILABLE"
    assert first_data["new_signal_count"] >= 1
    signal = first_data["signals"][0]
    assert signal["source_type"] == "social_media"
    assert signal["data_reality"] == "SYNTHETIC"
    assert signal["processing_status"] != "ASSOCIATED"
    assert signal["incident_id"] is None

    second = client.post(
        "/api/v1/social/refresh",
        json={"provider": "synthetic", "query": "accident Nasr City"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["new_signal_count"] == 0
    assert second.json()["duplicate_signal_count"] >= 1
    assert db_session.scalar(select(Report).where(Report.source_type == "social_media")) is not None
    assert db_session.scalar(
        select(Report.id).where(Report.source_type == "social_media")
    ) == signal["id"]


def test_social_refresh_evaluates_but_does_not_attach_to_incident(
    client: TestClient,
    db_session: Session,
) -> None:
    incident = client.post("/api/v1/intake/manual", json=_incident_payload()).json()
    refreshed = client.post(
        "/api/v1/social/refresh",
        json={"provider": "synthetic", "query": "accident Tayaran"},
    )
    assert refreshed.status_code == 200, refreshed.text

    current = db_session.get(Incident, incident["id"])
    assert current is not None
    assert current.version == 1
    signals = client.get("/api/v1/social/signals").json()["signals"]
    matching = next(signal for signal in signals if signal["source_reference"] == "synthetic-near-collision")
    assert matching["incident_id"] is None
    assert matching["provenance"]["association_evaluation"]
    assert matching["provenance"]["association_outcome"] == "POSSIBLE_EXISTING_INCIDENT"
    assert matching["provenance"]["verification_status"] == "UNVERIFIED"


def test_bluesky_provider_failure_does_not_silently_use_synthetic(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_search(self: Any, *, query: str, limit: int, retrieved_at: datetime) -> Any:
        from app.social import SocialProviderResult

        return SocialProviderResult(
            provider="bluesky_public",
            status=ProviderState.UNAVAILABLE,
            query=query,
            requested_limit=limit,
            retrieved_at=retrieved_at,
            failure_code="PROVIDER_UNAVAILABLE",
        )

    monkeypatch.setattr("app.social_api.BlueskyPublicProvider.search", unavailable_search)
    response = client.post(
        "/api/v1/social/refresh",
        json={"provider": "bluesky", "query": "accident"},
    )

    assert response.status_code == 200
    assert response.json()["provider_status"] == "UNAVAILABLE"
    assert response.json()["signals"] == []


def test_operator_can_associate_social_signal_with_insufficient_context(
    client: TestClient,
    db_session: Session,
) -> None:
    incident = client.post("/api/v1/intake/manual", json=_incident_payload()).json()
    refreshed = client.post(
        "/api/v1/social/refresh",
        json={"provider": "synthetic", "query": "vague location"},
    )
    signal = next(
        signal
        for signal in refreshed.json()["signals"]
        if signal["source_reference"] == "synthetic-vague-location"
    )

    associated = client.post(
        f"/api/v1/social/signals/{signal['id']}/associate",
        json={
            "target_incident_id": incident["id"],
            "expected_incident_version": 1,
            "operator_reference": "social-reviewer",
        },
    )

    assert associated.status_code == 200, associated.text
    assert associated.json()["incident_version"] == 2
    persisted = db_session.get(Report, signal["id"])
    assert persisted is not None
    assert persisted.incident_id == incident["id"]
    current = db_session.get(Incident, incident["id"])
    assert current is not None
    assert current.casualty_count is None
    assert any(
        event.event_type == "SOCIAL_SIGNAL_ASSOCIATED"
        for event in db_session.scalars(
            select(TimelineEvent).where(TimelineEvent.incident_id == incident["id"])
        )
    )


def test_social_association_is_version_safe_and_idempotent(
    client: TestClient,
    db_session: Session,
) -> None:
    incident = client.post("/api/v1/intake/manual", json=_incident_payload()).json()
    refreshed = client.post(
        "/api/v1/social/refresh",
        json={"provider": "synthetic", "query": "vague location"},
    )
    signal = next(
        item
        for item in refreshed.json()["signals"]
        if item["source_reference"] == "synthetic-vague-location"
    )
    stale = client.post(
        f"/api/v1/social/signals/{signal['id']}/associate",
        json={
            "target_incident_id": incident["id"],
            "expected_incident_version": 99,
            "operator_reference": "social-reviewer",
        },
    )
    assert stale.status_code == 409
    assert db_session.get(Report, signal["id"]).incident_id is None

    first = client.post(
        f"/api/v1/social/signals/{signal['id']}/associate",
        json={
            "target_incident_id": incident["id"],
            "expected_incident_version": 1,
            "operator_reference": "social-reviewer",
        },
    )
    assert first.status_code == 200
    repeated = client.post(
        f"/api/v1/social/signals/{signal['id']}/associate",
        json={
            "target_incident_id": incident["id"],
            "expected_incident_version": 2,
            "operator_reference": "social-reviewer",
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["action"] == "NO_OP_ALREADY_ASSOCIATED"
    assert db_session.get(Incident, incident["id"]).version == 2


def test_irrelevant_social_keyword_filter_is_explicit(client: TestClient) -> None:
    response = client.post(
        "/api/v1/social/refresh",
        json={"provider": "synthetic", "query": "film club"},
    )
    assert response.status_code == 200
    signal = next(
        item
        for item in response.json()["signals"]
        if item["source_reference"] == "synthetic-irrelevant"
    )
    assert signal["processing_status"] == "IRRELEVANT"


def test_dismissal_and_possible_new_are_review_actions_only(
    client: TestClient,
    db_session: Session,
) -> None:
    refreshed = client.post(
        "/api/v1/social/refresh",
        json={"provider": "synthetic", "query": "vague location"},
    )
    vague = next(
        signal
        for signal in refreshed.json()["signals"]
        if signal["source_reference"] == "synthetic-vague-location"
    )
    marked = client.post(
        f"/api/v1/social/signals/{vague['id']}/possible-new",
        json={"operator_reference": "social-reviewer"},
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["processing_status"] == "POSSIBLE_NEW_INCIDENT"
    assert db_session.query(Incident).count() == 0

    dismissed = client.post(
        f"/api/v1/social/signals/{vague['id']}/dismiss",
        json={"operator_reference": "social-reviewer"},
    )
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json()["processing_status"] == "DISMISSED"
    repeated = client.post(
        f"/api/v1/social/signals/{vague['id']}/dismiss",
        json={"operator_reference": "social-reviewer"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["processing_status"] == "DISMISSED"
