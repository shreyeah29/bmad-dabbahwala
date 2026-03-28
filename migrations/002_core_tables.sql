-- Migration 002: Core tables
-- Idempotent: all use CREATE TABLE IF NOT EXISTS

-- ── contacts ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.contacts (
    id                  SERIAL PRIMARY KEY,
    email               VARCHAR(255) UNIQUE NOT NULL,
    phone               VARCHAR(20),
    name                VARCHAR(255),
    lifecycle_segment   dabbahwala.lifecycle_segment NOT NULL DEFAULT 'cold',
    priority_override   BOOLEAN NOT NULL DEFAULT FALSE,
    sales_notes         TEXT,
    source              VARCHAR(100),
    opted_out           BOOLEAN NOT NULL DEFAULT FALSE,
    cooling_until       TIMESTAMPTZ,
    order_count         INTEGER NOT NULL DEFAULT 0,
    last_order_at       TIMESTAMPTZ,
    first_order_at      TIMESTAMPTZ,
    total_spent         NUMERIC(10,2) NOT NULL DEFAULT 0,
    city                VARCHAR(100),
    zip_code            VARCHAR(20),
    company             VARCHAR(255),
    instantly_lead_id   VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS contacts_lifecycle_idx ON dabbahwala.contacts(lifecycle_segment);
CREATE INDEX IF NOT EXISTS contacts_email_idx ON dabbahwala.contacts(email);
CREATE INDEX IF NOT EXISTS contacts_phone_idx ON dabbahwala.contacts(phone);

-- ── events ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.events (
    id          SERIAL PRIMARY KEY,
    contact_id  INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    event_type  dabbahwala.event_type NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS events_contact_idx ON dabbahwala.events(contact_id);
CREATE INDEX IF NOT EXISTS events_type_idx ON dabbahwala.events(event_type);
CREATE INDEX IF NOT EXISTS events_created_idx ON dabbahwala.events(created_at);

-- ── orders ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.orders (
    id              SERIAL PRIMARY KEY,
    contact_id      INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    order_ref       VARCHAR(100) UNIQUE,
    total_amount    NUMERIC(10,2),
    delivery_date   DATE,
    order_type      VARCHAR(50),
    notes           TEXT,
    shipday_order_id VARCHAR(100),
    status          dabbahwala.delivery_status_type NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS orders_contact_idx ON dabbahwala.orders(contact_id);
CREATE INDEX IF NOT EXISTS orders_delivery_date_idx ON dabbahwala.orders(delivery_date);

-- ── order_items ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES dabbahwala.orders(id) ON DELETE CASCADE,
    item_name   VARCHAR(255) NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1,
    unit_price  NUMERIC(10,2),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── menu_catalog ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.menu_catalog (
    id                  SERIAL PRIMARY KEY,
    airtable_record_id  VARCHAR(100) UNIQUE NOT NULL,
    name                VARCHAR(255) NOT NULL,
    category            VARCHAR(100),
    description         TEXT,
    price               NUMERIC(10,2),
    is_available        BOOLEAN NOT NULL DEFAULT TRUE,
    discarded_date      DATE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── menu_catalog_history ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.menu_catalog_history (
    id          SERIAL PRIMARY KEY,
    catalog_id  INTEGER NOT NULL REFERENCES dabbahwala.menu_catalog(id) ON DELETE CASCADE,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    old_data    JSONB,
    new_data    JSONB
);

-- ── telnyx_messages ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.telnyx_messages (
    id              SERIAL PRIMARY KEY,
    contact_id      INTEGER REFERENCES dabbahwala.contacts(id) ON DELETE SET NULL,
    direction       VARCHAR(10) NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    from_number     VARCHAR(20),
    to_number       VARCHAR(20),
    body            TEXT,
    telnyx_msg_id   VARCHAR(100) UNIQUE,
    status          VARCHAR(50),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS telnyx_messages_contact_idx ON dabbahwala.telnyx_messages(contact_id);

-- ── telnyx_calls ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.telnyx_calls (
    id              SERIAL PRIMARY KEY,
    contact_id      INTEGER REFERENCES dabbahwala.contacts(id) ON DELETE SET NULL,
    direction       VARCHAR(10) NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    from_number     VARCHAR(20),
    to_number       VARCHAR(20),
    duration_sec    INTEGER,
    telnyx_call_id  VARCHAR(100) UNIQUE,
    status          VARCHAR(50),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── delivery_status ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.delivery_status (
    id              SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES dabbahwala.orders(id) ON DELETE CASCADE,
    status          dabbahwala.delivery_status_type NOT NULL,
    driver_name     VARCHAR(255),
    driver_phone    VARCHAR(20),
    shipday_data    JSONB,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── engagement_rollups ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.engagement_rollups (
    id              SERIAL PRIMARY KEY,
    contact_id      INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    orders_7d       INTEGER NOT NULL DEFAULT 0,
    orders_30d      INTEGER NOT NULL DEFAULT 0,
    spend_7d        NUMERIC(10,2) NOT NULL DEFAULT 0,
    spend_30d       NUMERIC(10,2) NOT NULL DEFAULT 0,
    sms_sent_7d     INTEGER NOT NULL DEFAULT 0,
    sms_recv_7d     INTEGER NOT NULL DEFAULT 0,
    email_opens_7d  INTEGER NOT NULL DEFAULT 0,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (contact_id)
);
