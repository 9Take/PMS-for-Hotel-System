"""Pydantic schemas for API request/response validation."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# --- Room Schemas ---

class RoomBase(BaseModel):
    room_number: str
    type: str
    price_per_night: Decimal
    max_guests: int = 2
    amenities: str | None = None
    status: str = "available"
    images: dict | None = None


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    room_number: str | None = None
    type: str | None = None
    price_per_night: Decimal | None = None
    max_guests: int | None = None
    amenities: str | None = None
    status: str | None = None
    images: dict | None = None


class RoomResponse(RoomBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Guest Schemas ---

class GuestBase(BaseModel):
    name: str
    line_id: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class GuestCreate(GuestBase):
    pass


class GuestUpdate(BaseModel):
    name: str | None = None
    line_id: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class GuestResponse(GuestBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Booking Schemas ---

class BookingCreate(BaseModel):
    """Client-supplied. total_price is intentionally NOT accepted — the server
    always computes it via the pricing engine."""
    guest_id: int
    room_id: int
    check_in: date
    check_out: date
    adults: int = 1
    children_0_5: int = 0


class BookingUpdate(BaseModel):
    check_in: date | None = None
    check_out: date | None = None
    adults: int | None = None
    children_0_5: int | None = None
    status: str | None = None


class BookingResponse(BaseModel):
    id: int
    guest_id: int
    room_id: int
    check_in: date
    check_out: date
    num_guests: int
    adults: int
    children_0_5: int
    total_price: Decimal
    status: str
    hold_expires_at: datetime | None
    created_at: datetime
    guest: GuestResponse | None = None
    room: RoomResponse | None = None
    model_config = ConfigDict(from_attributes=True)


# --- Quote Schemas (pricing engine output) ---

class NightBreakdownResponse(BaseModel):
    date: date
    day_type: str
    base: Decimal
    surcharge: Decimal
    extras_needed: int
    extras_priced: int
    extra_bed_cost: Decimal
    source: str


class QuoteResponse(BaseModel):
    room_id: int
    nights: list[NightBreakdownResponse]
    room_subtotal: Decimal
    extra_bed_subtotal: Decimal
    total: Decimal
    peak_extras_needed: int
    requires_admin: bool
    notes: list[str]


class BookingWithQuoteResponse(BaseModel):
    booking: BookingResponse
    quote: QuoteResponse


# --- Transaction Schemas ---

class TransactionCreate(BaseModel):
    booking_id: int
    amount: Decimal
    slip_url: str | None = None


class TransactionResponse(BaseModel):
    id: int
    booking_id: int
    amount: Decimal
    slip_url: str | None
    slipok_result: dict | None
    verified_by_admin: bool
    admin_notes: str | None
    verified_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TransactionApprove(BaseModel):
    admin_notes: str | None = None


# --- Promotion Schemas ---

class PromotionBase(BaseModel):
    name: str
    description: str | None = None
    discount_type: str  # "percentage" or "fixed"
    discount_value: Decimal
    start_date: date
    end_date: date
    is_active: bool = True


class PromotionCreate(PromotionBase):
    pass


class PromotionResponse(PromotionBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Availability ---

class AvailabilityQuery(BaseModel):
    check_in: date
    check_out: date
    num_guests: int = 1


class AvailabilityResponse(BaseModel):
    room: RoomResponse
    is_available: bool
    nights: int
    total_price: Decimal
    requires_admin: bool = False
    notes: list[str] = []


# --- Holiday Sync (called by n8n Google Calendar workflow) ---

class HolidayItem(BaseModel):
    date: date
    name: str
    surcharge: Decimal = Decimal("1000")


class HolidaySyncRequest(BaseModel):
    """A full window replacement: rows in [window_start, window_end) are
    replaced by `holidays`. Keeps the table in sync with Google Calendar
    even when entries get deleted upstream."""
    window_start: date
    window_end: date
    holidays: list[HolidayItem]
    source: str = "google_calendar"


class HolidaySyncResult(BaseModel):
    deleted: int
    inserted: int
    window_start: date
    window_end: date
