"""Pricing engine — converts room_detail.md rules into a Quote.

Per-night precedence:
  1. Sp2 festival override (rate_overrides flat_price, beats everything)
  2. Day-of-week base rate (cheapest room_rates row covering `adults`;
     if none covers, the highest-base rate is used and the shortfall is
     billed as extra beds)
  3. Sp1 holiday surcharge (+holiday.surcharge when the night falls in a
     bridged weekend+holiday block; does NOT stack on top of Sp2)

Children 0-5 are free and do NOT consume occupancy. They are validated
against `room.child_free_count`; exceeding flips `requires_admin`.

Missing rate config raises PricingError — no silent fallback to the
deprecated `rooms.price_per_night` column.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import DayType, Holiday, RateOverride, Room, RoomRate
from app.services.holidays import get_surcharge_dates


class PricingError(Exception):
    """Raised when pricing cannot be computed (missing rate, bad input)."""


@dataclass
class NightBreakdown:
    date: date
    day_type: str               # "mon_thu" | "fri_sun" | "sat" | "festival"
    base: Decimal               # base/flat price for the night
    surcharge: Decimal          # Sp1 holiday surcharge (0 if none)
    extras_needed: int          # raw shortfall (may exceed what can be priced)
    extras_priced: int          # actually billed (0 if blocked by policy)
    extra_bed_cost: Decimal     # extras_priced × extra_bed_price
    source: str                 # rate label or override name


@dataclass
class Quote:
    room_id: int
    nights: list[NightBreakdown]
    room_subtotal: Decimal      # sum of base + surcharge
    extra_bed_subtotal: Decimal # sum of extra_bed_cost
    total: Decimal
    peak_extras_needed: int     # max extras on any night (capacity signal)
    requires_admin: bool        # any policy needs human review
    notes: list[str] = field(default_factory=list)


def _day_type(d: date) -> DayType:
    """Mon-Thu → mon_thu, Fri & Sun → fri_sun, Sat → sat."""
    wd = d.weekday()  # Mon=0 ... Sun=6
    if wd <= 3:
        return DayType.mon_thu
    if wd == 5:
        return DayType.sat
    return DayType.fri_sun  # Fri(4) or Sun(6)


def _daterange(start: date, end: date):
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


def _match_override(overrides: list[RateOverride], d: date) -> RateOverride | None:
    """Return the override covering `d`. NewYear's wrap is stored as two rows
    (Dec 30-31 and Jan 1), so a simple per-row month/day compare suffices."""
    m, day = d.month, d.day
    for o in overrides:
        if (o.start_month, o.start_day) <= (m, day) <= (o.end_month, o.end_day):
            return o
    return None


def _pick_rate(rates_for_day: list[RoomRate], adults: int) -> tuple[RoomRate, int]:
    """Pick the cheapest rate covering `adults`. If none covers, fall back
    to the highest-base rate and return the shortfall as extras."""
    for r in rates_for_day:  # pre-sorted ascending by base_guests
        if adults <= r.base_guests:
            return r, 0
    fallback = rates_for_day[-1]
    return fallback, adults - fallback.base_guests


async def _load_room(db: AsyncSession, room_id: int) -> Room:
    result = await db.execute(
        select(Room)
        .where(Room.id == room_id)
        .options(selectinload(Room.rates), selectinload(Room.rate_overrides))
    )
    room = result.scalars().first()
    if room is None:
        raise PricingError(f"Room {room_id} not found")
    return room


async def _holiday_surcharge_amount(
    db: AsyncSession, check_in: date, check_out: date
) -> Decimal:
    """Look up the surcharge amount used in this booking's window. We pick
    the max surcharge across holidays in the window — the table allows
    per-holiday overrides but in practice all rows share the same value."""
    result = await db.execute(
        select(Holiday.surcharge).where(
            Holiday.date >= check_in - timedelta(days=10),
            Holiday.date < check_out + timedelta(days=10),
        )
    )
    amounts = list(result.scalars().all())
    return max(amounts) if amounts else Decimal("0")


async def quote_booking(
    db: AsyncSession,
    room_id: int,
    check_in: date,
    check_out: date,
    adults: int,
    children_0_5: int = 0,
) -> Quote:
    """Compute a full quote. Pure read against DB state — does not write."""

    if check_in >= check_out:
        raise PricingError("check_in must be before check_out")
    if adults < 1:
        raise PricingError("adults must be >= 1")
    if children_0_5 < 0:
        raise PricingError("children_0_5 must be >= 0")

    room = await _load_room(db, room_id)
    notes: list[str] = []
    requires_admin = False

    if children_0_5 > room.child_free_count:
        requires_admin = True
        notes.append(
            f"{children_0_5} children exceeds free-child cap "
            f"({room.child_free_count}) — admin review required"
        )

    # Index rates by day_type, ascending by base_guests.
    rates_by_day: dict[DayType, list[RoomRate]] = {}
    for r in room.rates:
        rates_by_day.setdefault(r.day_type, []).append(r)
    for k in rates_by_day:
        rates_by_day[k].sort(key=lambda r: r.base_guests)

    surcharge_dates = await get_surcharge_dates(db, check_in, check_out)
    surcharge_amount = await _holiday_surcharge_amount(db, check_in, check_out)

    nights: list[NightBreakdown] = []
    peak_extras_needed = 0
    extra_bed_subtotal = Decimal("0")
    flagged_no_price = False
    flagged_overcap = False

    for d in _daterange(check_in, check_out):
        override = _match_override(room.rate_overrides, d)

        if override is not None:
            # Sp2: flat festival price, no day-type, no Sp1 stacking.
            # For extras we have no tier — use room.max_guests as the implicit base.
            base_capacity = room.max_guests
            extras_needed = max(0, adults - base_capacity)
            day_type_label = "festival"
            source = override.name
            night_base = override.flat_price
            night_surcharge = Decimal("0")
        else:
            dt = _day_type(d)
            rates_for_day = rates_by_day.get(dt, [])
            if not rates_for_day:
                raise PricingError(
                    f"No rate configured for room {room.room_number} on {d} "
                    f"(day_type={dt.value})"
                )
            chosen, extras_needed = _pick_rate(rates_for_day, adults)
            day_type_label = dt.value
            source = chosen.label or "standard"
            night_base = chosen.price
            night_surcharge = surcharge_amount if d in surcharge_dates else Decimal("0")

        # Extras pricing (per-night so a peak day flags the whole booking).
        extras_priced = 0
        extra_bed_cost = Decimal("0")
        if extras_needed > 0:
            if room.extra_bed_price is None:
                requires_admin = True
                if not flagged_no_price:
                    flagged_no_price = True
                    notes.append(
                        f"Room {room.room_number}: extras needed but no "
                        f"extra_bed_price set — admin must price manually"
                    )
            elif extras_needed > room.max_extra_beds:
                requires_admin = True
                if not flagged_overcap:
                    flagged_overcap = True
                    notes.append(
                        f"Room {room.room_number}: {extras_needed} extras "
                        f"needed, max allowed is {room.max_extra_beds} — admin review"
                    )
            else:
                extras_priced = extras_needed
                extra_bed_cost = Decimal(extras_priced) * room.extra_bed_price

        peak_extras_needed = max(peak_extras_needed, extras_needed)
        extra_bed_subtotal += extra_bed_cost

        nights.append(NightBreakdown(
            date=d,
            day_type=day_type_label,
            base=night_base,
            surcharge=night_surcharge,
            extras_needed=extras_needed,
            extras_priced=extras_priced,
            extra_bed_cost=extra_bed_cost,
            source=source,
        ))

    room_subtotal = sum((n.base + n.surcharge for n in nights), Decimal("0"))
    total = room_subtotal + extra_bed_subtotal

    return Quote(
        room_id=room_id,
        nights=nights,
        room_subtotal=room_subtotal,
        extra_bed_subtotal=extra_bed_subtotal,
        total=total,
        peak_extras_needed=peak_extras_needed,
        requires_admin=requires_admin,
        notes=notes,
    )
