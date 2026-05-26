"""Guest management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Guest
from app.schemas import GuestCreate, GuestResponse, GuestUpdate

router = APIRouter(prefix="/guests", tags=["Guests"])


@router.get("/", response_model=list[GuestResponse])
async def list_guests(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Guest).order_by(Guest.created_at.desc()))
    return result.scalars().all()


@router.get("/{guest_id}", response_model=GuestResponse)
async def get_guest(guest_id: int, db: AsyncSession = Depends(get_db)):
    guest = await db.get(Guest, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    return guest


@router.get("/line/{line_id}", response_model=GuestResponse)
async def get_guest_by_line_id(line_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Guest).where(Guest.line_id == line_id))
    guest = result.scalars().first()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    return guest


@router.post("/", response_model=GuestResponse, status_code=201)
async def create_guest(data: GuestCreate, db: AsyncSession = Depends(get_db)):
    guest = Guest(**data.model_dump())
    db.add(guest)
    await db.commit()
    await db.refresh(guest)
    return guest


@router.patch("/{guest_id}", response_model=GuestResponse)
async def update_guest(
    guest_id: int, data: GuestUpdate, db: AsyncSession = Depends(get_db)
):
    guest = await db.get(Guest, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(guest, key, value)
    await db.commit()
    await db.refresh(guest)
    return guest
