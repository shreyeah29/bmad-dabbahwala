# Epic 5: Lifecycle & Stage Engine

**Layer:** 2 — Lifecycle & Intelligence
**FRs:** FR-LIFE-01 to FR-LIFE-05
**Depends on:** E04
**Status:** backlog

## Goal
The Stage Engine — SQL rules that classify every contact into a lifecycle segment and route them to the correct Instantly email campaign. Runs hourly via n8n.

---

## Stories

### Story 5.1: Lifecycle Router & Run Endpoint
Create `app/routers/lifecycle.py` with `POST /api/lifecycle/run`. Calls `run_lifecycle_cycle()` and returns segment transition counts and timing.

**Acceptance Criteria:**
- `POST /api/lifecycle/run` executes `run_lifecycle_cycle()`
- Returns `{"transitions": N, "duration_ms": N, "segments": {...counts...}}`
- Errors return 500 with detail
- Logged at INFO with transition count

---

### Story 5.2: Lifecycle Segment Rules (Migration)
Seed `rules` table with the SQL predicate rules for all 8 segment transitions. Rules must cover: cold→engaged, engaged→active_customer, active_customer→lapsed, lapsed→reactivation_candidate, new_customer transitions, cooling logic, optout.

**Acceptance Criteria:**
- `run_lifecycle_cycle()` transitions contacts correctly based on order history and engagement
- Each rule has: name, predicate SQL, target_segment, priority
- Rules applied in priority order
- `decision_log` records each transition with reason

---

### Story 5.3: Campaign Routing Seed (Migration)
Seed `campaign_routing` table with all 7 campaign mappings: NURTURE_SLOW, PROMO_STANDARD, PROMO_AGGRESSIVE, NEW_CUSTOMER_ONBOARDING, REACTIVATION, ACTIVE_CUSTOMER, APP_TO_DIRECT. Each maps a `lifecycle_segment` to an Instantly campaign id/name/template.

**Acceptance Criteria:**
- `campaign_routing` seeded with all 7 entries
- Each row has: lifecycle_segment, instantly_campaign_id, instantly_campaign_name, email_template_file
- `run_lifecycle_cycle()` enqueues `push_instantly_lead` into `action_queue` for contacts whose segment-derived campaign changes
- Contact's active campaign derived via JOIN (not stored on contact row)

---
