"""Holiday surcharge bridging — Sp1 logic.

A night gets the holiday surcharge if it falls in a contiguous run of
"non-working" days (weekend Sat/Sun ∪ public holidays) that contains at
least one public holiday. A plain weekend with no holiday does NOT
trigger the surcharge.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Holiday

# Look outside the booking window when growing a block — Thai long
# weekends never span more than a handful of days, but be generous.
_WINDOW_PAD_DAYS = 10


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # Sat=5, Sun=6


async def get_surcharge_dates(
    db: AsyncSession, check_in: date, check_out: date
) -> set[date]:
    """Return the subset of nights in [check_in, check_out) that get the Sp1 surcharge.

    Algorithm: load holidays in a padded window, then for each holiday walk
    backward/forward across non-working days to find the maximal block, and
    mark every date in that block that lies in the booking window.
    """
    window_start = check_in - timedelta(days=_WINDOW_PAD_DAYS)
    window_end = check_out + timedelta(days=_WINDOW_PAD_DAYS)

    result = await db.execute(
        select(Holiday.date).where(
            Holiday.date >= window_start, Holiday.date < window_end
        )
    )
    holidays: set[date] = set(result.scalars().all())
    if not holidays:
        return set()

    def is_off(d: date) -> bool:
        return _is_weekend(d) or d in holidays

    surcharge: set[date] = set()
    visited_block_starts: set[date] = set()

    for h in holidays:
        # Walk backward to the start of the contiguous off-day block
        block_start = h
        while is_off(block_start - timedelta(days=1)):
            block_start -= timedelta(days=1)
        if block_start in visited_block_starts:
            continue
        visited_block_starts.add(block_start)

        # Walk forward, collecting nights that fall in the booking window
        d = block_start
        while is_off(d):
            if check_in <= d < check_out:
                surcharge.add(d)
            d += timedelta(days=1)

    return surcharge
