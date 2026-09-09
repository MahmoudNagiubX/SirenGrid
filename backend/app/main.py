from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.corridor_api import router as corridor_router
from app.benchmark_api import router as benchmark_router
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
from app.social_api import router as social_router
from app.traffic.api import router as traffic_router
from app.websocket import router as websocket_router

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
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
api_router.include_router(benchmark_router)
api_router.include_router(driver_alert_router)
api_router.include_router(operational_router)
api_router.include_router(resources_router)
api_router.include_router(replanning_router)
api_router.include_router(simulation_router)
api_router.include_router(planning_router)
api_router.include_router(map_router)
api_router.include_router(traffic_router)
api_router.include_router(phase06_router)
api_router.include_router(social_router)
api_router.include_router(mobile_router)
api_router.include_router(websocket_router)

app.include_router(api_router)
