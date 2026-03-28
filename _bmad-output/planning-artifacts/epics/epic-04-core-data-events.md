# Epic 4: Core Data & Events

**Layer:** 1 — Data & Events
**FRs:** FR-EVT-01 to FR-EVT-03
**Depends on:** E01
**Status:** backlog

## Goal
Foundation SQL schema (schema, enums, core tables, stored functions) and event ingestion endpoint. Every other epic writes to or reads from this foundation.

---

## Stories

### Story 4.1: Base Schema & Enums (Migration 001)
Create `dabbahwala` schema, `pgvector` extension, and all enum types: `lifecycle_segment`, `campaign_name`, `event_type`, `delivery_status_type`, `opportunity_action`, `opportunity_status`.

**Acceptance Criteria:**
- `migrations/001_schema_types.sql` runs idempotently
- All enums use `DO $$ BEGIN CREATE TYPE ... EXCEPTION WHEN duplicate_object THEN NULL END $$`
- `ALTER TYPE ... ADD VALUE IF NOT EXISTS` for additive enum changes
- `pgvector` extension created

---

### Story 4.2: Core Tables (Migration 002)
Create all core tables: `contacts`, `events`, `orders`, `order_items`, `menu_catalog`, `menu_catalog_history`, `telnyx_messages`, `telnyx_calls`, `delivery_status`, `engagement_rollups`.

**Acceptance Criteria:**
- All tables use `CREATE TABLE IF NOT EXISTS`
- `contacts`: email UNIQUE, phone, lifecycle_segment enum, priority_override, sales_notes, source, opted_out, cooling_until, order_count, last_order_at
- `events`: contact_id FK, event_type enum, metadata JSONB, created_at
- `orders`: contact_id FK, order_ref, total_amount, delivery_date, order_type, notes
- `menu_catalog`: airtable_record_id UNIQUE, discarded_date nullable

---

### Story 4.3: Agent Pipeline Tables (Migration 003)
Create tables: `customer_goals`, `contact_observations`, `action_plans`, `orchestrator_log`, `action_queue`, `rules`, `campaign_routing`, `campaign_push_log`, `agent_playbook`, `sms_templates`, `team_content`, `opportunities`, `decision_log`, `daily_reports`, `test_runs`.

**Acceptance Criteria:**
- All tables use `CREATE TABLE IF NOT EXISTS`
- `action_queue`: status `pending → executing → done / failed`
- `campaign_routing`: `lifecycle_segment` UNIQUE, Instantly campaign id/name/template/stats columns
- `opportunities`: signal_type, confidence, status enum
- `team_content`: content_vector vector(1536) for pgvector search

---

### Story 4.4: Stored Functions (Migration 004)
Implement core stored functions: `ingest_event()`, `run_lifecycle_cycle()`, `refresh_engagement_rollups()`, `get_contact_detail()`, `get_communication_history()`, `suggest_reactivation_targets()`, `get_lifecycle_summary()`, `get_campaign_performance()`, `generate_daily_report()`, `create_opportunity()`.

**Acceptance Criteria:**
- All functions in `migrations/004_functions.sql`
- `ingest_event()` validates event_type; writes to `events`; returns event id
- `create_opportunity()` deduplicates: no duplicate pending opportunity per contact+signal_type
- `refresh_engagement_rollups()` computes 7d/30d metrics from events table

---

### Story 4.5: Growth & Experiment Tables (Migration 005)
Create: `experiments`, `experiment_contacts`, `growth_baseline`, `goal_experiments`, `goal_experiment_contacts`, `goal_agent_runs`, `discovered_signals`, `competitor_agent_runs`, `schema_migrations`.

**Acceptance Criteria:**
- All tables use `CREATE TABLE IF NOT EXISTS`
- `goal_experiments`: `hypothesis_hash VARCHAR(64) UNIQUE`
- `schema_migrations`: `filename TEXT PRIMARY KEY`

---

### Story 4.6: Event Ingestion Endpoint
`POST /api/events/ingest` — accepts typed event payload; calls `ingest_event()` stored procedure; returns `{"event_id": ..., "status": "ok"}`.

**Acceptance Criteria:**
- Validates `event_type` is one of the 10 supported types
- Returns 422 for invalid event type
- Returns event ID on success
- Logs each ingestion at DEBUG level

---
