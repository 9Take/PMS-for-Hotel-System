"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine, Base
from app.routers import health, rooms, guests, bookings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup (dev only — use migrations in production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="HospitAI - Pool Villa Management API",
    description="Self-hosted booking & operations management for pool villas",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(rooms.router, prefix="/api/v1")
app.include_router(guests.router, prefix="/api/v1")
app.include_router(bookings.router, prefix="/api/v1")
