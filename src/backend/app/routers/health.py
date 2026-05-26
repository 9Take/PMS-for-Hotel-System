"""Health check endpoint."""

from fastapi import APIRouter
from app.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "OMS Backend",
        "villa": settings.villa_name,
    }
