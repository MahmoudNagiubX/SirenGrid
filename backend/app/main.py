from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.benchmark_api import router as benchmark_router
from app.config import settings
from app.db import init_db
from app.corridor_api import router as corridor_router
from app.driver_alert_api import router as driver_alert_router
from app.incidents import router as incidents_router
from app.hospital_api import router as hospital_router
from app.map import router as map_router
from app.mobile_api import router as mobile_router
from app.operational_api import router as operational_router
from app.phase06_api import router as phase06_router
from app.planning import router as planning_router
from app.resources import router as resources_router
from app.replanning import router as replanning_router
from app.simulation_api import router as simulation_router
from app.traffic.api import router as traffic_router
from app.websocket import router as websocket_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Ensure the operational schema exists before serving.

    ``init_db()`` is an idempotent ``CREATE TABLE IF NOT EXISTS`` pass. Running
    it on startup means ``uvicorn app.main:app`` against a fresh database no
    longer 500s every read endpoint (which previously left the dashboard
    showing "refresh failed" everywhere). Demo data is still seeded separately
    via ``python -m app.seed``.
    """
    try:
        init_db()
    except Exception:  # pragma: no cover - startup must not crash the server
        logger.exception("init_db() failed during startup")
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix=settings.api_prefix)


@api_router.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "SirenGrid API",
        "api_version": "v1",
    }


api_router.include_router(incidents_router)
api_router.include_router(hospital_router)
api_router.include_router(corridor_router)
api_router.include_router(driver_alert_router)
api_router.include_router(operational_router)
api_router.include_router(resources_router)
api_router.include_router(replanning_router)
api_router.include_router(planning_router)
api_router.include_router(map_router)
api_router.include_router(traffic_router)
api_router.include_router(benchmark_router)
api_router.include_router(phase06_router)
api_router.include_router(simulation_router)
api_router.include_router(mobile_router)
api_router.include_router(websocket_router)

app.include_router(api_router)
