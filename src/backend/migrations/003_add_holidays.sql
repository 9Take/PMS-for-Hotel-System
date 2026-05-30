-- ============================================
-- OMS System - Holidays + booking guest split
-- Source of truth for Sp1 holiday surcharge (auto-fetched from
-- Google Calendar by n8n; engine bridges weekend+holiday blocks).
-- ============================================

CREATE TABLE holidays (
    id          SERIAL PRIMARY KEY,
    date        DATE NOT NULL UNIQUE,
    name        VARCHAR(200) NOT NULL,
    surcharge   NUMERIC(10, 2) NOT NULL DEFAULT 1000,
    source      VARCHAR(50) NOT NULL DEFAULT 'google_calendar',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_holidays_date ON holidays (date);

-- Bookings: split guest count into adults + free children so the engine can
-- price correctly without re-deriving from num_guests. num_guests stays as
-- total occupancy (adults + children) for occupancy/availability checks.
ALTER TABLE bookings
    ADD COLUMN adults        INTEGER,
    ADD COLUMN children_0_5  INTEGER NOT NULL DEFAULT 0;

UPDATE bookings SET adults = num_guests WHERE adults IS NULL;
ALTER TABLE bookings ALTER COLUMN adults SET NOT NULL;
