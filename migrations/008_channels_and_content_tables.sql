-- Migration 008: Channels, content, and extended tables
-- broadcasts, team_content, field_calls, competitor_notes, broadcasts table

-- Broadcasts
CREATE TABLE IF NOT EXISTS dabbahwala.broadcasts (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    message_body TEXT NOT NULL,
    segment      TEXT,
    scheduled_at TIMESTAMPTZ,
    status       TEXT NOT NULL DEFAULT 'draft',  -- draft, scheduled, sending, sent, cancelled
    sent_count   INT  NOT NULL DEFAULT 0,
    failed_count INT  NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Team content (tips, recipes, promotions)
CREATE TABLE IF NOT EXISTS dabbahwala.team_content (
    id           SERIAL PRIMARY KEY,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'general',
    author       TEXT,
    segment      TEXT,
    tags         TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending, approved, rejected, archived
    airtable_id  TEXT UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Field agent call log
CREATE TABLE IF NOT EXISTS dabbahwala.field_calls (
    id           SERIAL PRIMARY KEY,
    contact_id   INT REFERENCES dabbahwala.contacts(id) ON DELETE SET NULL,
    agent_name   TEXT NOT NULL,
    outcome      TEXT NOT NULL,  -- order_placed, not_interested, callback, left_voicemail, no_answer
    notes        TEXT,
    order_ref    TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_field_calls_contact ON dabbahwala.field_calls(contact_id);
CREATE INDEX IF NOT EXISTS idx_field_calls_agent ON dabbahwala.field_calls(agent_name);
CREATE INDEX IF NOT EXISTS idx_field_calls_created ON dabbahwala.field_calls(created_at);

-- Competitor intelligence notes
CREATE TABLE IF NOT EXISTS dabbahwala.competitor_notes (
    id               SERIAL PRIMARY KEY,
    competitor_name  TEXT NOT NULL DEFAULT 'Unknown',
    notes            TEXT NOT NULL,
    source           TEXT DEFAULT 'field',  -- field, social, customer, research
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_competitor_notes_created ON dabbahwala.competitor_notes(created_at);

-- Growth goals
CREATE TABLE IF NOT EXISTS dabbahwala.growth_goals (
    id           SERIAL PRIMARY KEY,
    goal_type    TEXT NOT NULL,
    target_value NUMERIC NOT NULL,
    period       DATE NOT NULL DEFAULT DATE_TRUNC('month', NOW()),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (goal_type, period)
);

-- Add tags/notes columns to contacts if not present
ALTER TABLE dabbahwala.contacts ADD COLUMN IF NOT EXISTS tags  TEXT;
ALTER TABLE dabbahwala.contacts ADD COLUMN IF NOT EXISTS notes TEXT;

-- Add airtable_id to menu_catalog if not present
ALTER TABLE dabbahwala.menu_catalog ADD COLUMN IF NOT EXISTS airtable_id TEXT UNIQUE;
ALTER TABLE dabbahwala.menu_catalog ADD COLUMN IF NOT EXISTS tags TEXT;

-- Add conflict target for menu_catalog upsert (name)
DO $$ BEGIN
    ALTER TABLE dabbahwala.menu_catalog ADD CONSTRAINT menu_catalog_name_unique UNIQUE (name);
EXCEPTION WHEN duplicate_table THEN NULL;
         WHEN duplicate_object THEN NULL;
END $$;
