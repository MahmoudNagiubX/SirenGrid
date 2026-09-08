from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import _parse_cors_origins, get_settings
from app.main import app

LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def test_default_cors_origins_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    assert get_settings().cors_origins == LOCAL_ORIGINS


def test_cors_origins_accept_json_list() -> None:
    assert _parse_cors_origins('["https://one.example", "https://two.example"]') == [
        "https://one.example",
        "https://two.example",
    ]


def test_cors_origins_accept_comma_separated_list() -> None:
    assert _parse_cors_origins("https://one.example, https://two.example") == [
        "https://one.example",
        "https://two.example",
    ]


def test_cors_origins_reject_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "*")

    with pytest.raises(ValueError, match="wildcard"):
        get_settings()


def test_allowed_local_origin_receives_cors_header() -> None:
    response = TestClient(app).get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_disallowed_origin_does_not_receive_cors_header() -> None:
    response = TestClient(app).get(
        "/api/v1/health",
        headers={"Origin": "https://evil.example"},
    )

    assert "access-control-allow-origin" not in response.headers
