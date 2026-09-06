from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "processed" / "nasr_city"

ENV_PATH = REPO_ROOT / "backend" / ".env"
if load_dotenv is not None and ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=False)


def _parse_cors_origins(raw: str | None) -> list[str]:
    if not raw:
        return ["*"]
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseModel):
    app_name: str = Field(default="SirenGrid API")
    api_prefix: str = Field(default="/api/v1")
    database_url: str = Field(default="sqlite:///./sirengrid.db")
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    max_route_snap_distance_m: float = Field(default=1500.0)
    nasr_city_data_dir: Path = Field(default_factory=lambda: DEFAULT_DATA_DIR)
    tomtom_api_key: str | None = Field(default=None, exclude=True)
    tomtom_refresh_interval_seconds: Literal[60] = 60
    tomtom_fresh_max_age_seconds: Literal[120] = 120
    tomtom_refresh_timeout_seconds: Literal[10] = 10
    tomtom_flow_style: Literal["absolute"] = "absolute"
    tomtom_flow_zoom: Literal[22] = 22
    tomtom_flow_units: Literal["kmph"] = "kmph"
    tomtom_min_provider_confidence: Literal[0.8] = 0.8
    tomtom_max_geometry_separation_m: Literal[30] = 30
    tomtom_max_direction_difference_degrees: Literal[30] = 30

    @property
    def APP_NAME(self) -> str:
        return self.app_name

    @property
    def API_PREFIX(self) -> str:
        return self.api_prefix

    @property
    def DATABASE_URL(self) -> str:
        return self.database_url

    @property
    def CORS_ORIGINS(self) -> list[str]:
        return self.cors_origins

    @property
    def MAX_ROUTE_SNAP_DISTANCE_M(self) -> float:
        return self.max_route_snap_distance_m

    @property
    def NASR_CITY_DATA_DIR(self) -> Path:
        return self.nasr_city_data_dir

    @property
    def TOMTOM_API_KEY(self) -> str | None:
        return self.tomtom_api_key

    @property
    def TOMTOM_REFRESH_INTERVAL_SECONDS(self) -> int:
        return self.tomtom_refresh_interval_seconds

    @property
    def TOMTOM_FRESH_MAX_AGE_SECONDS(self) -> int:
        return self.tomtom_fresh_max_age_seconds

    @property
    def TOMTOM_REFRESH_TIMEOUT_SECONDS(self) -> int:
        return self.tomtom_refresh_timeout_seconds

    @property
    def TOMTOM_FLOW_STYLE(self) -> str:
        return self.tomtom_flow_style

    @property
    def TOMTOM_FLOW_ZOOM(self) -> int:
        return self.tomtom_flow_zoom

    @property
    def TOMTOM_FLOW_UNITS(self) -> str:
        return self.tomtom_flow_units

    @property
    def TOMTOM_MIN_PROVIDER_CONFIDENCE(self) -> float:
        return self.tomtom_min_provider_confidence

    @property
    def TOMTOM_MAX_GEOMETRY_SEPARATION_M(self) -> int:
        return self.tomtom_max_geometry_separation_m

    @property
    def TOMTOM_MAX_DIRECTION_DIFFERENCE_DEGREES(self) -> int:
        return self.tomtom_max_direction_difference_degrees


def get_settings() -> Settings:
    cors_raw = os.getenv("CORS_ORIGINS")
    cors_origins = _parse_cors_origins(cors_raw) if cors_raw else ["*"]

    data_dir_env = os.getenv("NASR_CITY_DATA_DIR")
    nasr_city_data_dir = (
        Path(data_dir_env).resolve() if data_dir_env else DEFAULT_DATA_DIR
    )

    return Settings(
        app_name=os.getenv("APP_NAME", "SirenGrid API"),
        api_prefix=os.getenv("API_PREFIX", "/api/v1"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./sirengrid.db"),
        cors_origins=cors_origins,
        max_route_snap_distance_m=float(
            os.getenv("MAX_ROUTE_SNAP_DISTANCE_M", "1500.0")
        ),
        nasr_city_data_dir=nasr_city_data_dir,
        tomtom_api_key=os.getenv("TOMTOM_API_KEY") or None,
        tomtom_refresh_interval_seconds=int(
            os.getenv("TOMTOM_REFRESH_INTERVAL_SECONDS", "60")
        ),
        tomtom_fresh_max_age_seconds=int(
            os.getenv("TOMTOM_FRESH_MAX_AGE_SECONDS", "120")
        ),
        tomtom_refresh_timeout_seconds=int(
            os.getenv("TOMTOM_REFRESH_TIMEOUT_SECONDS", "10")
        ),
        tomtom_flow_style=os.getenv("TOMTOM_FLOW_STYLE", "absolute"),
        tomtom_flow_zoom=int(os.getenv("TOMTOM_FLOW_ZOOM", "22")),
        tomtom_flow_units=os.getenv("TOMTOM_FLOW_UNITS", "kmph"),
        tomtom_min_provider_confidence=float(
            os.getenv("TOMTOM_MIN_PROVIDER_CONFIDENCE", "0.80")
        ),
        tomtom_max_geometry_separation_m=int(
            os.getenv("TOMTOM_MAX_GEOMETRY_SEPARATION_M", "30")
        ),
        tomtom_max_direction_difference_degrees=int(
            os.getenv("TOMTOM_MAX_DIRECTION_DIFFERENCE_DEGREES", "30")
        ),
    )


settings = get_settings()
