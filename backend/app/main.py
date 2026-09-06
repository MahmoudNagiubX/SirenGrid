from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.incidents import router as incidents_router
from app.resources import router as resources_router

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
api_router.include_router(resources_router)

app.include_router(api_router)
