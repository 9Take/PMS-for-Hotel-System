"""Room management API endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Room
from app.schemas import (
    NightBreakdownResponse, QuoteResponse, RoomCreate, RoomResponse, RoomUpdate,
)
from app.services.pricing import PricingError, quote_booking

router = APIRouter(prefix="/rooms", tags=["Rooms"])


@router.get("/", response_model=list[RoomResponse])
async def list_rooms(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Room).order_by(Room.room_number))
    return result.scalars().all()


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(room_id: int, db: AsyncSession = Depends(get_db)):
    room = await db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.post("/", response_model=RoomResponse, status_code=201)
async def create_room(data: RoomCreate, db: AsyncSession = Depends(get_db)):
    room = Room(**data.model_dump())
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


@router.patch("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: int, data: RoomUpdate, db: AsyncSession = Depends(get_db)
):
    room = await db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(room, key, value)
    await db.commit()
    await db.refresh(room)
    return room


@router.get("/{room_id}/quote", response_model=QuoteResponse)
async def quote_room(
    room_id: int,
    check_in: date = Query(...),
    check_out: date = Query(...),
    adults: int = Query(1, ge=1),
    children_0_5: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Price a stay without creating a hold. Returns full per-night breakdown."""
    try:
        quote = await quote_booking(
            db, room_id, check_in, check_out, adults, children_0_5
        )
    except PricingError as e:
        raise HTTPException(422, f"Pricing error: {e}")
    return QuoteResponse(
        room_id=quote.room_id,
        nights=[NightBreakdownResponse(**n.__dict__) for n in quote.nights],
        room_subtotal=quote.room_subtotal,
        extra_bed_subtotal=quote.extra_bed_subtotal,
        total=quote.total,
        peak_extras_needed=quote.peak_extras_needed,
        requires_admin=quote.requires_admin,
        notes=quote.notes,
    )


@router.delete("/{room_id}", status_code=204)
async def delete_room(room_id: int, db: AsyncSession = Depends(get_db)):
    room = await db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    await db.delete(room)
    await db.commit()
