"""Booking business logic — hold, confirm, cancel, availability check.

Pricing is delegated to services/pricing.py — never trust client-supplied totals.
"""

from datetime import datetime, timedelta, date

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, Room, RoomStatus
from app.services.pricing import PricingError, Quote, quote_booking


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
    db: AsyncSession,
    check_in: date,
    check_out: date,
    adults: int = 1,
    children_0_5: int = 0,
) -> list[dict]:
    """Return all rooms available for the dates, with a real pricing quote each.

    Rooms whose pricing config can't quote the dates (missing rates, capacity
    exceeded with no extras) are skipped silently — they're not bookable as-is.
    """
    rooms_result = await db.execute(
        select(Room).where(Room.status == RoomStatus.available)
    )
    rooms = rooms_result.scalars().all()

    available: list[dict] = []
    nights = (check_out - check_in).days
    for room in rooms:
        if not await check_room_availability(db, room.id, check_in, check_out):
            continue
        try:
            quote = await quote_booking(
                db, room.id, check_in, check_out, adults, children_0_5
            )
        except PricingError:
            continue
        available.append({
            "room": room,
            "is_available": True,
            "nights": nights,
            "total_price": quote.total,
            "requires_admin": quote.requires_admin,
            "notes": quote.notes,
        })
    return available


async def create_hold_booking(
    db: AsyncSession,
    guest_id: int,
    room_id: int,
    check_in: date,
    check_out: date,
    adults: int,
    children_0_5: int = 0,
    hold_minutes: int = 30,
) -> tuple[Booking, Quote]:
    """Create a HOLD booking with server-computed total. Returns (booking, quote)."""
    # Lock the room row so concurrent holds can't both pass availability.
    room_result = await db.execute(
        select(Room).where(Room.id == room_id).with_for_update()
    )
    if room_result.scalars().first() is None:
        raise ValueError("Room not found.")

    if not await check_room_availability(db, room_id, check_in, check_out):
        raise ValueError("Room is not available for the selected dates.")

    quote = await quote_booking(
        db, room_id, check_in, check_out, adults, children_0_5
    )

    booking = Booking(
        guest_id=guest_id,
        room_id=room_id,
        check_in=check_in,
        check_out=check_out,
        num_guests=adults + children_0_5,
        adults=adults,
        children_0_5=children_0_5,
        total_price=quote.total,
        status=BookingStatus.hold,
        hold_expires_at=datetime.utcnow() + timedelta(minutes=hold_minutes),
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking, quote


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
    """Cancel all HOLD bookings whose hold_expires_at has passed."""
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
