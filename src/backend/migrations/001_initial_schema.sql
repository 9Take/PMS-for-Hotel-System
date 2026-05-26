-- ============================================
-- OMS System - Initial Database Schema
-- Compatible with PostgreSQL 15+ / Supabase
-- ============================================

-- Enums
CREATE TYPE room_status AS ENUM ('available', 'maintenance', 'unavailable');
CREATE TYPE booking_status AS ENUM ('hold', 'confirmed', 'cancelled', 'completed');
CREATE TYPE document_type AS ENUM ('receipt', 'confirmation', 'invoice');
CREATE TYPE discount_type AS ENUM ('percentage', 'fixed');

-- Rooms
CREATE TABLE rooms (
    id SERIAL PRIMARY KEY,
    room_number VARCHAR(20) UNIQUE NOT NULL,
    type VARCHAR(50) NOT NULL,
    price_per_night NUMERIC(10, 2) NOT NULL,
    max_guests INTEGER NOT NULL DEFAULT 2,
    amenities TEXT,
    status room_status NOT NULL DEFAULT 'available',
    images JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Guests
CREATE TABLE guests (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    line_id VARCHAR(100),
    phone VARCHAR(20),
    email VARCHAR(200),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_guests_line_id ON guests (line_id);

-- Bookings
CREATE TABLE bookings (
    id SERIAL PRIMARY KEY,
    guest_id INTEGER NOT NULL REFERENCES guests(id),
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    num_guests INTEGER NOT NULL DEFAULT 1,
    total_price NUMERIC(10, 2) NOT NULL,
    status booking_status NOT NULL DEFAULT 'hold',
    hold_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_dates CHECK (check_out > check_in)
);
CREATE INDEX idx_bookings_status ON bookings (status);
CREATE INDEX idx_bookings_dates ON bookings (check_in, check_out);

-- Transactions (Payments)
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    booking_id INTEGER NOT NULL REFERENCES bookings(id),
    amount NUMERIC(10, 2) NOT NULL,
    slip_url TEXT,
    slipok_result JSONB,
    verified_by_admin BOOLEAN NOT NULL DEFAULT FALSE,
    admin_notes TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Documents (Generated PDFs)
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    booking_id INTEGER NOT NULL REFERENCES bookings(id),
    file_path TEXT NOT NULL,
    type document_type NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Promotions
CREATE TABLE promotions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    discount_type discount_type NOT NULL,
    discount_value NUMERIC(10, 2) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_promo_dates CHECK (end_date >= start_date)
);

-- Seed data: Example rooms (adjust for your villa)
INSERT INTO rooms (room_number, type, price_per_night, max_guests, amenities) VALUES
    ('V01', 'pool_villa', 3500.00, 4, 'สระว่ายน้ำส่วนตัว, WiFi, แอร์, ทีวี, ตู้เย็น'),
    ('V02', 'pool_villa', 3500.00, 4, 'สระว่ายน้ำส่วนตัว, WiFi, แอร์, ทีวี, ตู้เย็น'),
    ('V03', 'pool_villa_deluxe', 5000.00, 6, 'สระว่ายน้ำส่วนตัว, จากุซซี่, WiFi, แอร์, ทีวี, ตู้เย็น, ห้องครัว');
