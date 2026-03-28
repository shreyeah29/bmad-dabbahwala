# Epic 7: AI Agent Pipeline

**Layer:** 3 — AI Core
**FRs:** FR-AGENT-01 to FR-AGENT-17
**Depends on:** E04, E05, E06
**Status:** backlog

## Goal
The heart of the system. 8 Claude calls per contact: Layer 1 (Observer) → Layer 2 (Advisor) → Layer 3 (Orchestrator) → one action in `action_queue`. Includes prompt caching, playbook RAG, delivery-aware guardrails, and batch post-processing.

---

## Stories

### Story 7.1: LLM Service Foundation
Create `app/services/llm_service.py` — shared Anthropic client, model constants, prompt caching helper, and playbook hash cache.

**Acceptance Criteria:**
- `HAIKU = "claude-haiku-4-5-20251001"`, `SONNET = "claude-sonnet-4-6"` constants
- All system prompts wrapped in `cache_control: {"type": "ephemeral"}` blocks
- `_fetch_playbook_rules(categories)` — queries DB; caches result by SHA-256 hash; re-queries only on hash change
- `call_claude(model, system, messages, tools)` — single entry point for all Claude calls

---

### Story 7.2: Layer 1 — Menu Agent (Haiku)
Observer agent: given this week's menu and contact order history, output `top_picks[]`, `bridge_item`, `avoid[]`.

**Acceptance Criteria:**
- Tool: `submit_menu_picks` with structured output
- Input: active menu items + contact's past orders
- Output stored in `contact_observations.menu_picks`
- Uses Haiku model

---

### Story 7.3: Layer 1 — Sentiment Agent (Haiku)
Observer agent: given last 30 days of SMS + events, output `sentiment` (positive/neutral/negative), `confidence`, `summary`.

**Acceptance Criteria:**
- Tool: `submit_sentiment`
- Input: communication history + recent events
- Output stored in `contact_observations.sentiment`
- Uses Haiku model

---

### Story 7.4: Layer 1 — Intent Agent (Sonnet)
Observer agent: output `intent` (ready_to_order/needs_info/price_sensitive/not_interested/unknown), `signals[]`, `confidence`. Menu picks from Story 7.2 weight toward `ready_to_order` when favourites are available.

**Acceptance Criteria:**
- Tool: `submit_intent`
- Input: contact profile + events + menu picks from Menu agent
- Output stored in `contact_observations.intent`
- Uses Sonnet model

---

### Story 7.5: Layer 1 — Engagement Agent (Haiku)
Observer agent: output `engagement_score` (0–1), `trend` (rising/flat/falling), `last_touch_hours_ago`.

**Acceptance Criteria:**
- Tool: `submit_engagement`
- Input: `engagement_rollups` + recent events
- Output stored in `contact_observations.engagement`
- Uses Haiku model

---

### Story 7.6: Layer 1 — Parallel Execution & Storage
Run all 4 Layer 1 agents in parallel for a contact. Store combined output in `contact_observations`.

**Acceptance Criteria:**
- All 4 agents run concurrently (asyncio or threading)
- Single `contact_observations` row per cycle run
- Total Layer 1 time < sum of individual times
- Errors in one agent don't abort others

---

### Story 7.7: Layer 2 — Stage Agent (Haiku)
Advisor agent: given Layer 1 bundle, output `recommended_stage`, `confidence`, `reason`.

**Acceptance Criteria:**
- Tool: `submit_stage`
- Input: contact profile + full Layer 1 output
- Output stored in `action_plans.stage`
- Uses Haiku model

---

### Story 7.8: Layer 2 — Channel Agent (Haiku)
Advisor agent: output `recommended_channel` (sms/email/call/none), `channel_timing` (immediate/tomorrow/3days/none), `reason`.

**Acceptance Criteria:**
- Tool: `submit_channel`
- Input: Layer 1 bundle + engagement score
- Output stored in `action_plans.channel`
- Uses Haiku model

---

### Story 7.9: Layer 2 — Offer Agent (Sonnet)
Advisor agent: output `offer_type` (discount/reminder/social_proof/none), `suggested_copy` (references menu picks from Layer 1), `reason`.

**Acceptance Criteria:**
- Tool: `submit_offer`
- Input: Layer 1 bundle + contact value segment
- `suggested_copy` mentions specific menu items from `top_picks[]`
- Output stored in `action_plans.offer`
- Uses Sonnet model

---

### Story 7.10: Layer 2 — Escalation Agent (Sonnet)
Advisor agent: output `should_escalate` (bool), `urgency` (high/medium/none), `reason`.

**Acceptance Criteria:**
- Tool: `submit_escalation`
- Input: Layer 1 bundle + recent delivery events
- High urgency always triggered by delivery_failed/returned
- Output stored in `action_plans.escalation`
- Uses Sonnet model

---

### Story 7.11: Layer 2 — Parallel Execution & Storage
Run all 4 Layer 2 agents in parallel. Store combined output in `action_plans`.

**Acceptance Criteria:**
- All 4 agents run concurrently
- Single `action_plans` row per cycle run
- Playbook RAG injected: Observer categories for L1, Advisor+Messaging for L2

---

### Story 7.12: Layer 3 — Orchestrator Agent (Sonnet)
Final decision-maker. Reads all Layer 2 outputs + latest delivery event + recent action history → outputs one `chosen_action`: `send_sms`, `move_campaign`, `escalate_airtable`, or `none`.

**Acceptance Criteria:**
- Delivery-aware guardrails checked first (FR-AGENT-09)
- General guardrails enforced (FR-AGENT-10)
- Tool: `submit_action` with `chosen_action` + `reasoning`
- Output stored in `orchestrator_log`
- Chosen action inserted into `action_queue` with status `pending`
- Uses Sonnet model

---

### Story 7.13: Playbook RAG Injection
`_fetch_playbook_rules(categories)` queries `agent_playbook`, filters by category, formats for prompt injection. SHA-256 hash cache prevents redundant DB calls.

**Acceptance Criteria:**
- Observer agents receive: exclusion + priority + observer categories
- Advisor agents receive: exclusion + priority + advisor + messaging
- Orchestrator receives: exclusion + priority only
- Cache invalidated only when `agent_playbook` content hash changes

---

### Story 7.14: Agent Cycle Endpoints
Implement all cycle endpoints in `app/routers/agents.py`:
- `POST /api/agents/cycle/run` — single contact
- `POST /api/agents/cycle/run-for-contact` — real-time (post-inbound-SMS)
- `POST /api/agents/cycle/run-all` — batch all eligible
- `POST /api/agents/cycle/run-all-lapsed` — batch lapsed only
- `POST /api/agents/cycle/run-daily-sweep` — daily combined

**Acceptance Criteria:**
- Single contact cycle completes Layer 1→2→3 and returns `chosen_action`
- Batch endpoints cap at configurable max contacts per run
- `run-for-contact` skips batch limits (real-time path)
- All return cycle summary with timing

---

### Story 7.15: Action Queue API & Goals
`GET /api/agents/action-queue/pending`, `POST /api/agents/action-queue/{id}/done`, `POST /api/agents/goals`.

**Acceptance Criteria:**
- `GET /pending` returns action_queue rows with status=pending
- `POST /{id}/done` marks action as done with timestamp
- `POST /goals` creates/updates `customer_goals` row (one per contact)
- Goals: `convert_to_order`, `retain`, `reactivate`

---

### Story 7.16: Batch Post-Processing
After `run-all` completes: push `move_campaign` contacts to Instantly immediately; create Airtable tasks for `escalate_airtable` contacts; queue one digest email to `support@dabbahwala.com` if any campaign moves occurred.

**Acceptance Criteria:**
- `move_campaign` contacts pushed to Instantly via API after batch
- `escalate_airtable` contacts get Airtable field-sales task created
- Digest email queued (not sent per-contact) to support
- Post-processing errors logged but don't roll back completed actions

---

### Story 7.17: Layer 4 — Report Agents
`POST /api/agents/report/activity` and `/report/outcome` — daily Sonnet calls that generate HTML/CSV report summaries from `daily_reports` data.

**Acceptance Criteria:**
- Activity report: new orders, SMS activity, email performance
- Outcome report: AI actions taken, conversion attributions
- Both return HTML string suitable for email body
- Triggered daily by n8n

---
