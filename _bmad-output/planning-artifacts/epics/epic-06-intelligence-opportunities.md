# Epic 6: Intelligence & Opportunities

**Layer:** 2 — Lifecycle & Intelligence
**FRs:** FR-INTEL-01 to FR-INTEL-06, FR-OPP-01 to FR-OPP-07
**Depends on:** E04, E05
**Status:** backlog

## Goal
The Contact Sweep — 5-phase SQL signal scanner that finds contacts ready for action and creates opportunities. No Claude involved. Runs hourly.

---

## Stories

### Story 6.1: Intelligence Router & Run-Cycle Endpoint
Create `app/routers/intelligence.py` with `POST /api/intelligence/run-cycle`. Runs all 5 phases in sequence and returns phase results.

**Acceptance Criteria:**
- `POST /api/intelligence/run-cycle` executes 5 phases: COLLECT → PROFILE → SIGNAL → ROUTE → DISPATCH
- Returns summary: `{"phases": {...}, "opportunities_created": N, "duration_ms": N}`
- Each phase result logged individually
- Phase failure logged but does not abort subsequent phases

---

### Story 6.2: COLLECT & PROFILE Phases
COLLECT: query contacts eligible for signal detection (not opted-out, not cooling, last_contact_at threshold).
PROFILE: call `refresh_engagement_rollups()` to update 7d/30d metrics.

**Acceptance Criteria:**
- COLLECT returns list of eligible contact IDs
- PROFILE updates `engagement_rollups` for each collected contact
- `refresh_engagement_rollups()` counts email_open, sms_received, order_placed in 7d and 30d windows

---

### Story 6.3: SIGNAL Phase — 7 Signal Detectors
Implement all 7 SQL signal detectors as part of the SIGNAL phase. Each detector queries contacts and calls `create_opportunity()` for hits.

**Acceptance Criteria:**
- `engaged_no_order`: engaged segment, no order in 14d → opportunity: `send_sms`
- `new_customer_no_repeat`: new_customer, 1 order, no repeat in 7d → opportunity: `send_sms`
- `lapsed_reengaged`: lapsed, recent email open/click → opportunity: `send_sms`
- `reorder_intent`: active_customer, high engagement, order > 7d ago → opportunity: `send_sms`
- `app_customers_for_conversion`: contacts tagged as app customers, no direct order → opportunity: `field_sales_call`
- `subscription_candidates`: 5+ orders, regular cadence → opportunity: `send_email`
- `high_value_at_risk`: top 20% by order value, declining engagement → opportunity: `field_sales_call`
- Each fires `create_opportunity()` with dedup (no duplicate pending per contact+signal_type)

---

### Story 6.4: ROUTE & DISPATCH Phases
ROUTE: assign priority and channel to each new opportunity.
DISPATCH: queue any immediate automated responses for pending opportunities.

**Acceptance Criteria:**
- ROUTE sets priority based on signal type and contact value
- DISPATCH adds eligible opportunities to execution queue
- Returns count of routed and dispatched items

---

### Story 6.5: Opportunities API
Implement all opportunity endpoints: `GET /detect`, `POST /`, `GET /pending`, `POST /{id}/dispatched`, `POST /{id}/outcome`.

**Acceptance Criteria:**
- `GET /detect` runs signal detection and returns new opportunities
- `POST /` creates opportunity manually with dedup
- `GET /pending` returns pending opportunities with contact info
- `POST /{id}/dispatched` moves to `dispatched` status
- `POST /{id}/outcome` records outcome (converted/declined/expired)

---

### Story 6.6: Instantly Events Ingestion
`POST /api/intelligence/ingest-instantly-events` — pull email engagement events from Instantly API and persist as `events` records.

**Acceptance Criteria:**
- Fetches open, click, reply events from Instantly
- Each event persisted via `ingest_event()` with contact lookup by email
- Returns `{"ingested": N, "skipped": N}`
- `GET /api/intelligence/pending-actions` lists pending opportunities

---
