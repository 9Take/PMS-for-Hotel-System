"""Booking API endpoints — availability, create, confirm, cancel."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Booking, Transaction, BookingStatus
from app.schemas import (
    BookingCreate, BookingResponse, BookingUpdate,
    BookingWithQuoteResponse, NightBreakdownResponse, QuoteResponse,
    TransactionCreate, TransactionResponse, TransactionApprove,
    AvailabilityResponse,
)
from app.services.booking import (
    get_available_rooms, create_hold_booking, confirm_booking,
    cancel_booking, expire_stale_holds,
)
from app.services.pricing import PricingError
from app.services.slipok import verify_slip


def _quote_to_response(quote) -> QuoteResponse:
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

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.get("/availability", response_model=list[AvailabilityResponse])
async def check_availability(
    check_in: date = Query(...),
    check_out: date = Query(...),
    adults: int = Query(1, ge=1),
    children_0_5: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Check which rooms are available + their priced quote for the dates."""
    if check_in >= check_out:
        raise HTTPException(400, "check_in must be before check_out")
    rooms = await get_available_rooms(db, check_in, check_out, adults, children_0_5)
    return rooms


@router.get("/", response_model=list[BookingResponse])
async def list_bookings(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List bookings, optionally filtered by status."""
    query = select(Booking).options(
        selectinload(Booking.guest), selectinload(Booking.room)
    ).order_by(Booking.created_at.desc())
    if status:
        query = query.where(Booking.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Booking).where(Booking.id == booking_id).options(
            selectinload(Booking.guest), selectinload(Booking.room)
        )
    )
    booking = result.scalars().first()
    if not booking:
        raise HTTPException(404, "Booking not found")
    return booking


@router.post("/", response_model=BookingWithQuoteResponse, status_code=201)
async def create_booking(data: BookingCreate, db: AsyncSession = Depends(get_db)):
    """Create a HOLD booking (30-min lock). Total is computed server-side."""
    try:
        booking, quote = await create_hold_booking(
            db,
            guest_id=data.guest_id,
            room_id=data.room_id,
            check_in=data.check_in,
            check_out=data.check_out,
            adults=data.adults,
            children_0_5=data.children_0_5,
        )
    except PricingError as e:
        raise HTTPException(422, f"Pricing error: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Re-load with eager relationships so Pydantic from_attributes doesn't try
    # a lazy fetch on a closed greenlet context.
    result = await db.execute(
        select(Booking).where(Booking.id == booking.id).options(
            selectinload(Booking.guest), selectinload(Booking.room)
        )
    )
    booking = result.scalars().first()
    return BookingWithQuoteResponse(
        booking=BookingResponse.model_validate(booking),
        quote=_quote_to_response(quote),
    )


@router.post("/{booking_id}/confirm", response_model=BookingResponse)
async def confirm_booking_endpoint(
    booking_id: int, db: AsyncSession = Depends(get_db)
):
    """Confirm a HOLD booking (after admin approves payment)."""
    try:
        return await confirm_booking(db, booking_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking_endpoint(
    booking_id: int, db: AsyncSession = Depends(get_db)
):
    """Cancel a booking."""
    try:
        return await cancel_booking(db, booking_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/expire-holds")
async def expire_holds(db: AsyncSession = Depends(get_db)):
    """Manually trigger expiration of stale HOLD bookings."""
    count = await expire_stale_holds(db)
    return {"expired_count": count}


# --- Transactions (Payment) ---

@router.post("/{booking_id}/transactions", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    booking_id: int, data: TransactionCreate, db: AsyncSession = Depends(get_db)
):
    """Record a payment transaction and optionally verify slip via SlipOK."""
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")

    slipok_result = None
    if data.slip_url:
        slipok_result = await verify_slip(data.slip_url)

    txn = Transaction(
        booking_id=booking_id,
        amount=data.amount,
        slip_url=data.slip_url,
        slipok_result=slipok_result,
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return txn


@router.post("/{booking_id}/transactions/{txn_id}/approve", response_model=TransactionResponse)
async def approve_transaction(
    booking_id: int,
    txn_id: int,
    data: TransactionApprove,
    db: AsyncSession = Depends(get_db),
):
    """Admin approves a transaction → booking auto-confirms."""
    from datetime import datetime

    txn = await db.get(Transaction, txn_id)
    if not txn or txn.booking_id != booking_id:
        raise HTTPException(404, "Transaction not found")

    txn.verified_by_admin = True
    txn.admin_notes = data.admin_notes
    txn.verified_at = datetime.utcnow()

    # Auto-confirm the booking if still on hold.
    booking = await db.get(Booking, booking_id)
    if booking.status == BookingStatus.hold:
        booking.status = BookingStatus.confirmed
        booking.hold_expires_at = None

    await db.commit()
    await db.refresh(txn)
    return txn
