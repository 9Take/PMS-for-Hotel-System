-- ============================================
-- OMS System - Pricing Model (schema only)
-- Day-of-week rates + festival overrides + per-room policy.
-- NOTE: real prices live in seed_rooms.local.sql (gitignored).
-- ============================================

CREATE TYPE rate_day_type AS ENUM ('mon_thu', 'fri_sun', 'sat');

-- Per-room policy (extra bed + child)
ALTER TABLE rooms
    ADD COLUMN extra_bed_price  NUMERIC(10, 2),            -- NULL = case-by-case (ask admin)
    ADD COLUMN max_extra_beds   INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN child_free_count INTEGER NOT NULL DEFAULT 0;

-- Day-of-week base rates. A room may have >1 row per day_type (e.g. promo vs standard).
CREATE TABLE room_rates (
    id SERIAL PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    day_type rate_day_type NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    base_guests INTEGER NOT NULL,
    label VARCHAR(50),                                     -- e.g. 'standard', 'promo'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_room_rates_room ON room_rates (room_id, day_type);

-- Recurring yearly festival flat rates (month/day based). NewYear wrap stored as two rows.
CREATE TABLE rate_overrides (
    id SERIAL PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    start_month INTEGER NOT NULL,
    start_day INTEGER NOT NULL,
    end_month INTEGER NOT NULL,
    end_day INTEGER NOT NULL,
    flat_price NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_rate_overrides_room ON rate_overrides (room_id);
