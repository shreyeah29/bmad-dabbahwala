-- Migration 003: Agent pipeline tables
-- Idempotent: all use CREATE TABLE IF NOT EXISTS

-- ── customer_goals ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.customer_goals (
    id          SERIAL PRIMARY KEY,
    contact_id  INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    goal_type   VARCHAR(100) NOT NULL,
    goal_data   JSONB NOT NULL DEFAULT '{}',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS customer_goals_contact_idx ON dabbahwala.customer_goals(contact_id);

-- ── contact_observations ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.contact_observations (
    id              SERIAL PRIMARY KEY,
    contact_id      INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    cycle_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    menu_signal     TEXT,
    sentiment       VARCHAR(50),
    intent          VARCHAR(100),
    engagement_lvl  VARCHAR(50),
    raw_outputs     JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS observations_contact_idx ON dabbahwala.contact_observations(contact_id);
CREATE INDEX IF NOT EXISTS observations_cycle_idx ON dabbahwala.contact_observations(cycle_at);

-- ── action_plans ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.action_plans (
    id              SERIAL PRIMARY KEY,
    contact_id      INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    cycle_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stage_signal    VARCHAR(100),
    channel         VARCHAR(50),
    offer           TEXT,
    escalation_flag BOOLEAN NOT NULL DEFAULT FALSE,
    raw_outputs     JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS action_plans_contact_idx ON dabbahwala.action_plans(contact_id);

-- ── orchestrator_log ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.orchestrator_log (
    id          SERIAL PRIMARY KEY,
    contact_id  INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    cycle_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decision    TEXT,
    reasoning   TEXT,
    actions     JSONB NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS orchestrator_log_contact_idx ON dabbahwala.orchestrator_log(contact_id);

-- ── action_queue ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.action_queue (
    id              SERIAL PRIMARY KEY,
    contact_id      INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    action_type     dabbahwala.opportunity_action NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'executing', 'done', 'failed')),
    scheduled_for   TIMESTAMPTZ,
    executed_at     TIMESTAMPTZ,
    error_msg       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS action_queue_status_idx ON dabbahwala.action_queue(status);
CREATE INDEX IF NOT EXISTS action_queue_contact_idx ON dabbahwala.action_queue(contact_id);

-- ── rules ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.rules (
    id          SERIAL PRIMARY KEY,
    rule_name   VARCHAR(255) UNIQUE NOT NULL,
    rule_type   VARCHAR(100) NOT NULL,
    conditions  JSONB NOT NULL DEFAULT '{}',
    actions     JSONB NOT NULL DEFAULT '[]',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    priority    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── campaign_routing ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.campaign_routing (
    id                      SERIAL PRIMARY KEY,
    lifecycle_segment       dabbahwala.lifecycle_segment NOT NULL UNIQUE,
    campaign_name           dabbahwala.campaign_name,
    instantly_campaign_id   VARCHAR(100),
    instantly_campaign_name VARCHAR(255),
    template_id             VARCHAR(100),
    daily_limit             INTEGER NOT NULL DEFAULT 50,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── campaign_push_log ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.campaign_push_log (
    id                  SERIAL PRIMARY KEY,
    contact_id          INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    lifecycle_segment   dabbahwala.lifecycle_segment,
    campaign_name       dabbahwala.campaign_name,
    instantly_lead_id   VARCHAR(100),
    pushed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status              VARCHAR(50),
    error_msg           TEXT
);

CREATE INDEX IF NOT EXISTS push_log_contact_idx ON dabbahwala.campaign_push_log(contact_id);

-- ── agent_playbook ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.agent_playbook (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(255) NOT NULL,
    segment     dabbahwala.lifecycle_segment,
    content     TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── sms_templates ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.sms_templates (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) UNIQUE NOT NULL,
    segment     dabbahwala.lifecycle_segment,
    body        TEXT NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── team_content ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.team_content (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(255) NOT NULL,
    content_type    VARCHAR(100),
    content         TEXT NOT NULL,
    content_vector  vector(1536),
    source_doc_id   VARCHAR(100),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── opportunities ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.opportunities (
    id              SERIAL PRIMARY KEY,
    contact_id      INTEGER NOT NULL REFERENCES dabbahwala.contacts(id) ON DELETE CASCADE,
    signal_type     VARCHAR(100) NOT NULL,
    confidence      NUMERIC(4,3) CHECK (confidence >= 0 AND confidence <= 1),
    recommended_action  dabbahwala.opportunity_action,
    status          dabbahwala.opportunity_status NOT NULL DEFAULT 'pending',
    notes           TEXT,
    actioned_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS opportunities_contact_idx ON dabbahwala.opportunities(contact_id);
CREATE INDEX IF NOT EXISTS opportunities_status_idx ON dabbahwala.opportunities(status);

-- ── decision_log ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.decision_log (
    id              SERIAL PRIMARY KEY,
    contact_id      INTEGER REFERENCES dabbahwala.contacts(id) ON DELETE SET NULL,
    decision_type   VARCHAR(100) NOT NULL,
    input_data      JSONB NOT NULL DEFAULT '{}',
    output_data     JSONB NOT NULL DEFAULT '{}',
    model_used      VARCHAR(100),
    tokens_used     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS decision_log_contact_idx ON dabbahwala.decision_log(contact_id);
CREATE INDEX IF NOT EXISTS decision_log_type_idx ON dabbahwala.decision_log(decision_type);

-- ── daily_reports ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.daily_reports (
    id          SERIAL PRIMARY KEY,
    report_date DATE NOT NULL UNIQUE,
    report_data JSONB NOT NULL DEFAULT '{}',
    summary     TEXT,
    sent_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── test_runs ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dabbahwala.test_runs (
    id          SERIAL PRIMARY KEY,
    run_name    VARCHAR(255) NOT NULL,
    status      VARCHAR(50) NOT NULL DEFAULT 'running',
    results     JSONB NOT NULL DEFAULT '{}',
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ
);
