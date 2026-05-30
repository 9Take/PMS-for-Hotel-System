"""Admin endpoints — internal operations (holiday sync, etc).

These should sit behind VPN / internal-network auth in production. For now
no auth middleware is wired up; tighten before exposing past LXC.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import and_, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Holiday
from app.schemas import HolidaySyncRequest, HolidaySyncResult

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/holidays/sync", response_model=HolidaySyncResult)
async def sync_holidays(
    payload: HolidaySyncRequest, db: AsyncSession = Depends(get_db)
):
    """Replace holidays in [window_start, window_end) with the supplied list.

    Called by the n8n Google Calendar sync workflow. Window-replacement (not
    a plain upsert) so deletions in Google Calendar propagate. Uses ON CONFLICT
    to be idempotent if two syncs race.
    """
    # Delete existing rows in the window first so removed Calendar entries vanish.
    del_result = await db.execute(
        delete(Holiday).where(
            and_(
                Holiday.date >= payload.window_start,
                Holiday.date < payload.window_end,
            )
        )
    )
    deleted = del_result.rowcount or 0

    inserted = 0
    if payload.holidays:
        rows = [
            {
                "date": h.date,
                "name": h.name,
                "surcharge": h.surcharge,
                "source": payload.source,
            }
            for h in payload.holidays
            if payload.window_start <= h.date < payload.window_end
        ]
        if rows:
            stmt = pg_insert(Holiday).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["date"],
                set_={
                    "name": stmt.excluded.name,
                    "surcharge": stmt.excluded.surcharge,
                    "source": stmt.excluded.source,
                },
            )
            result = await db.execute(stmt)
            inserted = result.rowcount or len(rows)

    await db.commit()
    return HolidaySyncResult(
        deleted=deleted,
        inserted=inserted,
        window_start=payload.window_start,
        window_end=payload.window_end,
    )
