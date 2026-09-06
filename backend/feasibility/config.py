from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is declared for the spike
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / "backend" / ".env"

if load_dotenv is not None:
    load_dotenv(ENV_PATH, override=False)


@dataclass(frozen=True)
class Settings:
    groq_api_key: str | None
    tomtom_api_key: str | None
    gemini_api_key: str | None
    groq_primary_model: str
    groq_secondary_model: str
    gemini_model_candidate: str
    request_timeout_seconds: float
    tomtom_test_point: str
    allow_external_media: bool

    @property
    def key_presence(self) -> dict[str, bool]:
        return {
            "GROQ_API_KEY": bool(self.groq_api_key),
            "TOMTOM_API_KEY": bool(self.tomtom_api_key),
            "GEMINI_API_KEY": bool(self.gemini_api_key),
        }


def get_settings() -> Settings:
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        tomtom_api_key=os.getenv("TOMTOM_API_KEY") or None,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        groq_primary_model=os.getenv(
            "GROQ_STRUCTURED_PRIMARY", "qwen/qwen3.8-27b"
        ),
        groq_secondary_model=os.getenv(
            "GROQ_STRUCTURED_SECONDARY", "openai/gpt-oss-120b"
        ),
        gemini_model_candidate=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        request_timeout_seconds=float(os.getenv("FEASIBILITY_TIMEOUT_SECONDS", "30")),
        # This is the official TomTom documentation sample point, not an incident
        # coordinate and not an operational source of truth.
        tomtom_test_point=os.getenv("TOMTOM_TEST_POINT", "52.41072,4.84239"),
        # Media is never sent to a provider unless the human explicitly opts in
        # for this run. Text-only feasibility remains the safe default.
        allow_external_media=os.getenv("PHASE00_ALLOW_EXTERNAL_MEDIA", "false").casefold()
        in {"1", "true", "yes"},
    )
