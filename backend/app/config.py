from __future__ import annotations

import json
import os
from pathlib import Path
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
    )


settings = get_settings()
