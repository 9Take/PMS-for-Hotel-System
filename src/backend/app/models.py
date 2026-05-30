"""SQLAlchemy ORM models for all database tables."""

import enum
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String, Text, Integer, Numeric, Boolean, Date, DateTime,
    ForeignKey, Enum, JSON, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# --- Enums ---

class RoomStatus(str, enum.Enum):
    available = "available"
    maintenance = "maintenance"
    unavailable = "unavailable"


class BookingStatus(str, enum.Enum):
    hold = "hold"
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"


class DocumentType(str, enum.Enum):
    receipt = "receipt"
    confirmation = "confirmation"
    invoice = "invoice"


class DiscountType(str, enum.Enum):
    percentage = "percentage"
    fixed = "fixed"


class DayType(str, enum.Enum):
    mon_thu = "mon_thu"
    fri_sun = "fri_sun"
    sat = "sat"


# --- Models ---

class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_number: Mapped[str] = mapped_column(String(20), unique=True)
    type: Mapped[str] = mapped_column(String(50))  # e.g. "pool_villa", "deluxe"
    price_per_night: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_guests: Mapped[int] = mapped_column(Integer, default=2)
    amenities: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RoomStatus] = mapped_column(
        Enum(RoomStatus, name="room_status"), default=RoomStatus.available
    )
    images: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_bed_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_extra_beds: Mapped[int] = mapped_column(Integer, default=0)
    child_free_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    bookings: Mapped[list["Booking"]] = relationship(back_populates="room")
    rates: Mapped[list["RoomRate"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
    rate_overrides: Mapped[list["RateOverride"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    line_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    bookings: Mapped[list["Booking"]] = relationship(back_populates="guest")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    num_guests: Mapped[int] = mapped_column(Integer, default=1)
    adults: Mapped[int] = mapped_column(Integer, default=1)
    children_0_5: Mapped[int] = mapped_column(Integer, default=0)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"), default=BookingStatus.hold
    )
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    guest: Mapped["Guest"] = relationship(back_populates="bookings")
    room: Mapped["Room"] = relationship(back_populates="bookings")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="booking")
    documents: Mapped[list["Document"]] = relationship(back_populates="booking")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    slip_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    slipok_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verified_by_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    booking: Mapped["Booking"] = relationship(back_populates="transactions")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"))
    file_path: Mapped[str] = mapped_column(Text)
    type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="document_type"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    booking: Mapped["Booking"] = relationship(back_populates="documents")


class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_type: Mapped[DiscountType] = mapped_column(Enum(DiscountType, name="discount_type"))
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    surcharge: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1000"))
    source: Mapped[str] = mapped_column(String(50), default="google_calendar")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RoomRate(Base):
    __tablename__ = "room_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    day_type: Mapped[DayType] = mapped_column(Enum(DayType, name="rate_day_type"))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    base_guests: Mapped[int] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    room: Mapped["Room"] = relationship(back_populates="rates")


class RateOverride(Base):
    __tablename__ = "rate_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    start_month: Mapped[int] = mapped_column(Integer)
    start_day: Mapped[int] = mapped_column(Integer)
    end_month: Mapped[int] = mapped_column(Integer)
    end_day: Mapped[int] = mapped_column(Integer)
    flat_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    room: Mapped["Room"] = relationship(back_populates="rate_overrides")
