# Epics 8–26: Remaining Epics

**BMAD Phase 3 | Version 1.0 | 2026-03-28**

---

## Epic 8: Single-Agent Tooling

**Layer:** 3 | **FRs:** FR-SA-01 | **Depends on:** E07

### Story 8.1: Single-Agent Router
`app/routers/agent.py` — specialized endpoints for single-contact analysis, direct agent calls, and tooling experiments.

**AC:** Functional parity with test group G6 agent tests; endpoints callable independently of batch pipeline.

---

## Epic 9: Telnyx SMS

**Layer:** 4 | **FRs:** FR-SMS-01 to FR-SMS-04 | **Depends on:** E04, E07

### Story 9.1: Inbound/Outbound Message Storage
`POST /api/telnyx/message` (alias `/api/sms/message`) — store SMS in `telnyx_messages`; auto-create contact for unknown inbound numbers; trigger agent cycle for inbound.

**AC:** Unknown inbound number → contact auto-created with `source='telnyx'`; `run-for-contact` triggered after storing; direction (inbound/outbound) stored correctly.

### Story 9.2: Call Tracking
`POST /api/telnyx/call` — store call metadata and transcript in `telnyx_calls`.

**AC:** Stores duration, transcript, summary; linked to contact by phone number.

### Story 9.3: Field Agent SMS & Templates
`POST /api/telnyx/field-agent-message` — field-initiated SMS with separate tracking.
SMS template CRUD: `GET/POST /api/telnyx/templates`.

**AC:** Field messages tagged with agent name; templates stored in `sms_templates`; A/B variant selection supported.

---

## Epic 10: Webhooks & Delivery

**Layer:** 4 | **FRs:** FR-WH-01 to FR-WH-06 | **Depends on:** E04, E07, E09

### Story 10.1: Instantly Webhook
`POST /api/webhooks/instantly` — receive email events (open, click, reply, bounce); persist via `ingest_event()`.

**AC:** All event types handled; contact looked up by email; unknown contacts logged and skipped.

### Story 10.2: Telnyx Inbound Webhook
`POST /api/webhooks/telnyx` — Telnyx push webhook for inbound SMS; stores message and triggers agent cycle.

**AC:** Signature validated if `TELNYX_WEBHOOK_SECRET` set; calls `POST /api/telnyx/message` internally.

### Story 10.3: Shipday Webhooks & Delivery Status
`POST /api/webhooks/shipday`, `GET /api/webhooks/shipday` — delivery status webhooks.
`POST /api/delivery/status` — maps Shipday statuses to internal events; triggers delivery-aware agent delay.

**AC:** `delivered` → 4h threading.Timer before agent cycle; `delivery_failed` → immediate escalation; `out_for_delivery` → suppress outreach.

### Story 10.4: Campaign Sync Webhooks
`POST /api/webhooks/sync-campaigns`, `GET /api/webhooks/campaigns`, `POST /api/webhooks/campaign-stats` — sync Instantly campaign list and performance stats into `campaign_routing`.

**AC:** `campaign_routing` updated with latest Instantly campaign IDs and stats; idempotent upsert.

---

## Epic 11: Orders & Shipday

**Layer:** 5 | **FRs:** FR-ORD-01 to FR-ORD-06 | **Depends on:** E04

### Story 11.1: Shipday Order Ingestion
`POST /api/shipday/ingest-orders` — fetch orders from Shipday API; upsert into `orders` + `order_items`; create/update contacts.

**AC:** Deduplicates by order_ref; creates contact if not exists; updates order_count on contact.

### Story 11.2: Sync Status & Top Calls
`GET /api/shipday/sync-status` — last sync metadata.
`GET /api/shipday/top-calls` — contacts by order count.

**AC:** Returns last sync timestamp, count ingested; top-calls returns ordered list with order counts.

### Story 11.3: Historical Import Pipeline
`POST /api/shipday/import-all-and-run-agents` — full historical import + agent cycle trigger.
`GET /api/shipday/import-pipeline-status` — progress of import.

**AC:** Paginated Shipday import; progress trackable via status endpoint; agent cycles queued after import.

### Story 11.4: Delivery Feedback
`POST /api/shipday/sync-feedback` — pull delivery feedback from Shipday; store as events.
`GET /api/shipday/feedback-stats` — feedback summary stats.

**AC:** Feedback types (positive/negative/neutral) stored; tied to contact and order.

---

## Epic 12: Daily CSV Orders

**Layer:** 5 | **FRs:** FR-DAILY-01 | **Depends on:** E04

### Story 12.1: CSV Order Processing
`POST /api/daily-orders/` — accept daily CSV upload; parse rows; create/update contacts; create orders; normalize phone numbers; resolve menu item names; return summary.

**AC:** Phone normalization (strip non-digits, handle Indian/US formats); menu item matched by name (fuzzy); missing contacts created; existing contacts updated; returns `{created, updated, errors}`.

---

## Epic 13: Instantly Campaigns

**Layer:** 6 | **FRs:** FR-CAMP-01 to FR-CAMP-08 | **Depends on:** E05, E10

### Story 13.1: Push Lead & Pending Queue
`POST /api/campaigns/push-lead` — enqueue `push_instantly_lead` into `action_queue`.
`GET /api/campaigns/pending` — list pending push items.

**AC:** Action queued with contact email + target campaign; n8n picks up and executes.

### Story 13.2: Active Contacts & Stats
`GET /api/campaigns/active-contacts` — contacts with active campaigns (for Instantly seed).
`GET /api/campaigns/active-contacts-stats` — diagnostic with filter counts and campaign distribution.

**AC:** Excludes opted-out, cooling, do-not-contact; campaign derived from lifecycle_segment JOIN.

### Story 13.3: Push Log & Audit
`POST /api/campaigns/log-push` — record Instantly push result in `campaign_push_log`.
`GET /api/campaigns/push-log` — read audit trail; filter by success/failure.

**AC:** Each push attempt logged with status_code and response_body; filterable.

### Story 13.4: Analytics & Templates
`GET /api/campaigns/analytics` — campaign performance from `campaign_routing`.
SMS template CRUD + AI rewrite: `GET/PUT /templates/{name}`, `POST /templates/{name}/rewrite`.
`POST /api/campaigns/setup-instantly` — bootstrap Instantly configuration.

**AC:** AI rewrite uses Sonnet with playbook messaging rules; analytics returns opens/clicks/replies per campaign.

---

## Epic 14: Prospects & Contacts

**Layer:** 6 | **FRs:** FR-PROS-01 to FR-PROS-05, FR-CONT-01 to FR-CONT-02 | **Depends on:** E04

### Story 14.1: New Contact CSV Import
`GET /api/prospects/template` — download CSV template.
`POST /api/prospects/upload-csv` — bulk add new contacts.

**AC:** Template has all required columns; upload validates, deduplicates by email/phone; returns summary.

### Story 14.2: Bulk Contact Update
`GET /api/prospects/update-template`, `POST /api/prospects/update-csv` — bulk update existing contacts (name, address, priority_override, sales_notes).

**AC:** Matches existing contact by email or phone; only updates provided fields; returns updated count.

### Story 14.3: Single Contact Operations
`POST /api/prospects/add` — add single contact.
`PATCH /api/contacts/{id}/priority` — override priority.
`PATCH /api/contacts/{id}/notes` — update sales notes.

**AC:** Single add validates required fields; priority values: `normal`, `high`, `do_not_contact`; notes stored as free text.

---

## Epic 15: Broadcasts

**Layer:** 6 | **FRs:** FR-BC-01 to FR-BC-06 | **Depends on:** E04, E09

### Story 15.1: Broadcast Job Management
Create, list, and check status of broadcast jobs. Target by lifecycle segment, channel (sms/email), message body, and schedule.

**AC:** `POST /api/broadcasts/` creates job; `GET /api/broadcasts/` lists all; status: pending/running/complete/failed.

### Story 15.2: Recipient Preview & Dispatch
`GET /api/broadcasts/{id}/recipients` — preview who will receive.
`POST /api/broadcasts/{id}/dispatch` — queue for n8n execution.

**AC:** Preview excludes opted-out, cooling, do-not-contact contacts; dispatch enqueues into action_queue; delay alert if pending > threshold.

---

## Epic 16: Menu & History

**Layer:** 7 | **FRs:** FR-MENU-01 to FR-MENU-06 | **Depends on:** E04

### Story 16.1: Menu Catalog API
`GET /api/menu/items` — active items.
`GET /api/menu/items/inactive` — discarded items.
`GET /api/menu/items/{id}/history` — change history.

**AC:** Active = `discarded_date IS NULL AND active = true`; history ordered by changed_at DESC.

### Story 16.2: Airtable Menu Sync
`POST /api/menu/sync` — two-phase sync: Phase 1 upsert active items; Phase 2 detect discards.

**AC:** Upsert by airtable_record_id; price change → `menu_catalog_history` row with `change_type='price_change'`; item removed from Airtable → `discarded_date` set, history row with `change_type='discarded'`; never hard-delete.

---

## Epic 17: Playbook Rules

**Layer:** 7 | **FRs:** FR-PB-01 to FR-PB-05 | **Depends on:** E04, E07

### Story 17.1: Playbook Rules API
`GET /api/playbook/rules`, `POST /api/playbook/rules`, `GET /api/playbook/for-prompt`.

**AC:** Rules have: category (exclusion/priority/observer/advisor/messaging), priority int, active bool, rule_text; `for-prompt` returns formatted string filtered by category.

### Story 17.2: Airtable Playbook Sync
`POST /api/playbook/sync-from-airtable` — pull rules from Airtable; upsert into `agent_playbook`.

**AC:** Existing rules updated; new rules inserted; deactivated rules (removed from Airtable) marked inactive; triggers LLM service cache invalidation.

---

## Epic 18: Team Content

**Layer:** 7 | **FRs:** FR-TC-01 to FR-TC-04 | **Depends on:** E04

### Story 18.1: Content Sync & Submit
`POST /api/team-content/sync` — pull from Google Docs into `team_content`.
`POST /api/team-content/submit` — manually submit ground note or ad copy.

**AC:** Google Doc text chunked and stored; each chunk gets pgvector embedding; submit stores with content_type tag.

### Story 18.2: Browse & Search
`GET /api/team-content/browse` — list all entries.
`POST /api/team-content/search` — keyword + semantic search.

**AC:** Browse returns entries with type and created_at; search uses pgvector similarity for semantic results; returns ranked list.

---

## Epic 19: Reports

**Layer:** 8 | **FRs:** FR-REP-01 to FR-REP-03 | **Depends on:** E04, E07

### Story 19.1: Daily Reports API
`GET /api/reports/daily/{date}`, `POST /api/reports/daily/{date}`.

**AC:** POST calls `generate_daily_report()` and stores in `daily_reports`; GET retrieves stored report; date format YYYY-MM-DD; returns JSONB metrics.

---

## Epic 20: Field Agent

**Layer:** 8 | **FRs:** FR-FA-01 to FR-FA-07 | **Depends on:** E04, E07, E16

### Story 20.1: Daily Brief Generation
`GET /api/field-agent/brief` — top-10 priority contacts with name, phone, segment, last interaction, AI talking points.

**AC:** Sorted by priority_override + engagement score; talking points generated by Claude using contact history + menu; delivered by n8n at 7:30 AM.

### Story 20.2: Outcome Logging & Hot Leads
`POST /api/field-agent/log-outcome` — log call outcome; mark hot lead; add notes.
`GET /api/field-agent/pending-calls` — contacts assigned to field.

**AC:** Outcomes: connected/not-answered/interested/not-interested; hot lead → immediate Airtable task + agent cycle; notes appended to `contacts.sales_notes`.

### Story 20.3: Scorecard & Call Analysis
`GET /api/field-agent/scorecard` — field performance metrics.
`POST /api/field-agent/analyze-call` — Claude analysis of completed call.

**AC:** Scorecard: calls made, outcomes by type, conversion rate; analyze-call returns sentiment, key points, next action recommendation.

---

## Epic 21: Chatbot

**Layer:** 8 | **FRs:** FR-CHAT-01 to FR-CHAT-05 | **Depends on:** E04, E18

### Story 21.1: Chatbot Ask & Suggest
`POST /api/chatbot/ask` — RAG Q&A over indexed content.
`GET /api/chatbot/suggest` — suggested questions.

**AC:** Uses pgvector similarity search on `team_content`; context injected into Claude prompt; answer is grounded in retrieved content; `GET /history` returns recent Q&A.

### Story 21.2: Reindex
`POST /api/chatbot/reindex` — trigger full doc reindex from Google Docs + team_content.

**AC:** Clears old vectors; re-ingests all Google Docs; re-embeds; returns `{"indexed": N, "duration_ms": N}`; startup hook runs this non-blocking.

---

## Epic 22: Marketing Query

**Layer:** 8 | **FRs:** FR-QRY-01 to FR-QRY-05 | **Depends on:** E04, E05, E07

### Story 22.1: Named Query Categories (Tier 1)
`POST /api/query/` for all 19 Tier-1 categories; `GET /api/query/categories`.

**AC:** All 19 categories return correct SQL-backed data; date-range categories accept `start_date`/`end_date`; `GET /categories` returns full list with descriptions.

### Story 22.2: Free-Form Claude Query (Tier 2)
`free_form` category — passes question to Claude with DB schema context; returns natural-language analytics answer.

**AC:** Claude receives schema summary + question; returns coherent answer with supporting data; guardrailed to read-only queries.

---

## Epic 23: Growth / Goal / Competitor Agents

**Layer:** 9 | **FRs:** FR-GROW-01 to FR-GROW-04, FR-GOAL-01 to FR-GOAL-05, FR-COMP-01 to FR-COMP-03 | **Depends on:** E07

### Story 23.1: Growth Agent
`POST /api/growth/run-cycle` — Claude designs experiment (timing/offer/message_angle/channel_sequence); assigns cohort; sets measure_at.
`POST /api/growth/measure` — evaluate results.
`POST /api/growth/baseline/update`, `GET /api/growth/experiments`, `GET /api/growth/insights`.

**AC:** Experiment stored in `experiments`; contacts enrolled in `experiment_contacts`; measure compares conversion vs `growth_baseline`; insights summarize learnings.

### Story 23.2: Goal Agent
`POST /api/goal-agent/run` — full 4-phase cycle: hypothesize → experiment → measure → harvest.
Individual phase endpoints + read endpoints.

**AC:** `hypothesis_hash` prevents duplicate hypotheses; harvest phase writes proven experiments to `discovered_signals` as SQL rules; `goal_agent_runs` audit log.

### Story 23.3: Competitor Agent
`POST /api/competitor-agent/run` — parse competitor emails + scrape sites + generate hypotheses + inject into goal experiments.
`GET /runs`, `GET /experiments`.

**AC:** Competitor emails parsed for offers/positioning; hypotheses generated and inserted into `goal_experiments` with `source='competitor_agent'`; `competitor_agent_runs` audit log.

---

## Epic 24: Test Harness & Admin Schedules

**Layer:** 10 | **FRs:** FR-TEST-01 to FR-TEST-05, FR-SCH-01 to FR-SCH-02 | **Depends on:** All prior epics

### Story 24.1: E2E Test Harness
`POST /api/test/run`, `GET /api/test/results`, `GET /api/test/results/{run_id}`, `GET /api/test/run/{group_id}`.

**AC:** All 16 groups (G1–G16) runnable; results persisted as JSONB in `test_runs`; per-test pass/fail in result; G14 (cleanup) restores test data.

### Story 24.2: n8n Schedule Management
`GET /api/admin/schedules` — list all workflow schedules.
`POST /api/admin/schedules/{workflow_id}` — update schedule trigger.

**AC:** Returns human-readable cron strings sorted by workflow name; update pushes to n8n API; requires active Google OAuth session.

---

## Epic 25: MCP Server

**Layer:** 10 | **FRs:** FR-MCP-01 to FR-MCP-04 | **Depends on:** E04, E05, E06, E07

### Story 25.1: FastMCP Server Setup
`mcp_server/server.py` — FastMCP server with DB connection; tool registration.

**AC:** Server starts and connects to Postgres; Claude Desktop can connect via MCP protocol.

### Story 25.2: Contact & Analytics Tools
Tools: contact lookup, update, list by segment, pipeline snapshot, lifecycle summary, campaign performance.

**AC:** All tools query DB directly (not FastAPI); return structured data; tested via MCP client.

### Story 25.3: Communication & Action Tools
Tools: SMS history, call log, communication history, next actions, opportunities, run agent cycle, queue status, Shipday order lookup, Instantly campaign stats, lead push.

**AC:** 35+ tools total registered; each tool documented with input schema and return type.

---

## Epic 26: n8n Workflow Suite

**Layer:** 10 | **FRs:** FR-N8N-01 to FR-N8N-27 | **Depends on:** All prior epics

### Story 26.1: Core Automation Workflows
Implement workflows: Action Queue Executor, Agent Orchestration Cron, Contact Sweep, Stage Runner, SMS Dispatch, Telnyx Inbound Collector.

**AC:** Each workflow calls `/api/credentials/` at startup; no hardcoded secrets; correct cron schedules; tested via G8/G10 harness groups.

### Story 26.2: Data Sync Workflows
Implement: Airtable Menu Sync, Playbook Sync, Outcome Sync, Shipday Collector, Shipday Feedback, Instantly Campaign Sync, Chatbot Docs Reindex, Daily Order Upload.

**AC:** Each sync is idempotent; errors logged to n8n execution log; schedules per SYSTEM.md.

### Story 26.3: Reporting & Field Workflows
Implement: Daily Activity Report, Daily Outcome Report, Daily Field Brief, Broadcast Dispatch.

**AC:** Reports emailed to `REPORT_EMAIL_TO`; field brief to field team inbox at 7:30 AM; broadcast dispatch reads from action_queue.

### Story 26.4: Growth & System Workflows
Implement: Goal Agent Cycle, Growth Cycle, Competitor Agent Cycle (weekly), System Feature Tests (5 AM daily), System Connectivity Check (manual).

**AC:** Feature tests email on any failure; connectivity check pings all external services; competitor agent runs weekly.

### Story 26.5: CI/CD n8n Sync
`.github/workflows/sync_n8n.yml` — on push to `main`, sync all workflow JSON files to n8n instance via API.

**AC:** Workflow JSON synced to `digitalworker.dataskate.io`; uses `N8N_API_KEY` from GitHub secrets; failed syncs fail the CI job.

---
