-- Migration 005: Growth and experiment tables
-- Idempotent: all use CREATE TABLE IF NOT EXISTS

-- ── experiments ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.experiments (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) UNIQUE NOT NULL,
    description     TEXT,
    hypothesis      TEXT,
    status          VARCHAR(50) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'running', 'paused', 'completed', 'cancelled')),
    started_at      TIMESTAMPTZ,
    ended_at        TIMESTAMPTZ,
    results         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── experiment_contacts ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.experiment_contacts (
    id              SERIAL PRIMARY KEY,
    experiment_id   INTEGER NOT NULL REFERENCES dabbahwala.experiments(id) ON DELETE CASCADE,
    contact_id      INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    variant         VARCHAR(50) NOT NULL DEFAULT 'control',
    enrolled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (experiment_id, contact_id)
);

CREATE INDEX IF NOT EXISTS exp_contacts_exp_idx ON dabbahwala.experiment_contacts(experiment_id);

-- ── growth_baseline ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.growth_baseline (
    id              SERIAL PRIMARY KEY,
    metric_name     VARCHAR(255) NOT NULL,
    metric_date     DATE NOT NULL,
    metric_value    NUMERIC(12,4) NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (metric_name, metric_date)
);

-- ── goal_experiments ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.goal_experiments (
    id                  SERIAL PRIMARY KEY,
    hypothesis          TEXT NOT NULL,
    hypothesis_hash     VARCHAR(64) UNIQUE NOT NULL,
    goal_type           VARCHAR(100) NOT NULL,
    target_segment      dabbahwala.lifecycle_segment,
    status              VARCHAR(50) NOT NULL DEFAULT 'pending',
    confidence_score    NUMERIC(4,3),
    started_at          TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ,
    results             JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── goal_experiment_contacts ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.goal_experiment_contacts (
    id              SERIAL PRIMARY KEY,
    experiment_id   INTEGER NOT NULL REFERENCES dabbahwala.goal_experiments(id) ON DELETE CASCADE,
    contact_id      INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    variant         VARCHAR(50) NOT NULL DEFAULT 'test',
    enrolled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcome         JSONB NOT NULL DEFAULT '{}',
    UNIQUE (experiment_id, contact_id)
);

-- ── goal_agent_runs ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.goal_agent_runs (
    id              SERIAL PRIMARY KEY,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    goals_evaluated INTEGER NOT NULL DEFAULT 0,
    experiments_created INTEGER NOT NULL DEFAULT 0,
    contacts_enrolled   INTEGER NOT NULL DEFAULT 0,
    raw_output      JSONB NOT NULL DEFAULT '{}'
);

-- ── discovered_signals ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.discovered_signals (
    id              SERIAL PRIMARY KEY,
    signal_type     VARCHAR(100) NOT NULL,
    contact_id      INTEGER REFERENCES dabbahwala.contacts(id) ON DELETE SET NULL,
    signal_data     JSONB NOT NULL DEFAULT '{}',
    confidence      NUMERIC(4,3),
    actioned        BOOLEAN NOT NULL DEFAULT FALSE,
    discovered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS discovered_signals_type_idx ON dabbahwala.discovered_signals(signal_type);

-- ── competitor_agent_runs ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.competitor_agent_runs (
    id              SERIAL PRIMARY KEY,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    competitors     JSONB NOT NULL DEFAULT '[]',
    insights        TEXT,
    raw_output      JSONB NOT NULL DEFAULT '{}'
);

-- ── schema_migrations (tracker) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
