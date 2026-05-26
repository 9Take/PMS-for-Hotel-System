"""Booking business logic — hold, confirm, cancel, availability check."""

from datetime import datetime, timedelta, date
from decimal import Decimal

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Booking, BookingStatus, Room, RoomStatus


async def check_room_availability(
    db: AsyncSession, room_id: int, check_in: date, check_out: date
) -> bool:
    """Check if a room is available for the given date range."""
    conflict = await db.execute(
        select(Booking).where(
            and_(
                Booking.room_id == room_id,
                Booking.status.in_([BookingStatus.hold, BookingStatus.confirmed]),
                Booking.check_in < check_out,
                Booking.check_out > check_in,
            )
        )
    )
    return conflict.scalars().first() is None


async def get_available_rooms(
    db: AsyncSession, check_in: date, check_out: date, num_guests: int = 1
) -> list[dict]:
    """Return all rooms available for the given date range and guest count."""
    rooms_result = await db.execute(
        select(Room).where(
            and_(
                Room.status == RoomStatus.available,
                Room.max_guests >= num_guests,
            )
        )
    )
    rooms = rooms_result.scalars().all()
    available = []
    nights = (check_out - check_in).days
    for room in rooms:
        is_available = await check_room_availability(db, room.id, check_in, check_out)
        if is_available:
            available.append({
                "room": room,
                "is_available": True,
                "nights": nights,
                "total_price": room.price_per_night * nights,
            })
    return available


async def create_hold_booking(
    db: AsyncSession,
    guest_id: int,
    room_id: int,
    check_in: date,
    check_out: date,
    num_guests: int,
    total_price: Decimal,
    hold_minutes: int = 30,
) -> Booking:
    """Create a booking with HOLD status, expiring after hold_minutes."""
    # Lock the room row so concurrent holds can't both pass the availability check.
    room = await db.execute(
        select(Room).where(Room.id == room_id).with_for_update()
    )
    if room.scalars().first() is None:
        raise ValueError("Room not found.")

    if not await check_room_availability(db, room_id, check_in, check_out):
        raise ValueError("Room is not available for the selected dates.")

    booking = Booking(
        guest_id=guest_id,
        room_id=room_id,
        check_in=check_in,
        check_out=check_out,
        num_guests=num_guests,
        total_price=total_price,
        status=BookingStatus.hold,
        hold_expires_at=datetime.utcnow() + timedelta(minutes=hold_minutes),
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


async def confirm_booking(db: AsyncSession, booking_id: int) -> Booking:
    """Change booking status from HOLD to CONFIRMED."""
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise ValueError("Booking not found.")
    if booking.status != BookingStatus.hold:
        raise ValueError(f"Cannot confirm booking with status '{booking.status}'.")
    booking.status = BookingStatus.confirmed
    booking.hold_expires_at = None
    await db.commit()
    await db.refresh(booking)
    return booking


async def cancel_booking(db: AsyncSession, booking_id: int) -> Booking:
    """Cancel a booking (from hold or confirmed)."""
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise ValueError("Booking not found.")
    if booking.status == BookingStatus.completed:
        raise ValueError("Cannot cancel a completed booking.")
    booking.status = BookingStatus.cancelled
    booking.hold_expires_at = None
    await db.commit()
    await db.refresh(booking)
    return booking


async def expire_stale_holds(db: AsyncSession) -> int:
    """Cancel all HOLD bookings that have expired. Returns count cancelled."""
    now = datetime.utcnow()
    result = await db.execute(
        select(Booking).where(
            and_(
                Booking.status == BookingStatus.hold,
                Booking.hold_expires_at <= now,
            )
        )
    )
    expired = result.scalars().all()
    for booking in expired:
        booking.status = BookingStatus.cancelled
        booking.hold_expires_at = None
    await db.commit()
    return len(expired)
