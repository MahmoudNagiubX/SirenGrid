from __future__ import annotations

from app.config import settings


def test_phase06_policy_constants_are_explicit_and_safe_by_default() -> None:
    assert settings.phase06_ai_total_processing_budget_seconds == 30
    assert settings.phase06_structured_primary == "NOT_SELECTED"
    assert settings.phase06_structured_secondary == "NOT_SELECTED"
    assert settings.phase06_structured_default_enabled is False
    assert settings.phase06_max_audio_upload_bytes == 15 * 1024 * 1024
    assert settings.phase06_max_image_upload_bytes == 10 * 1024 * 1024


def test_phase09_social_provider_is_bounded_and_credential_free_by_default() -> None:
    assert settings.social_bluesky_api_url.startswith("https://public.api.bsky.app/")
    assert 1 <= settings.social_provider_timeout_seconds <= 30
    assert 1 <= settings.social_max_results <= 50
