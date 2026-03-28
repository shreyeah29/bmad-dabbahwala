# DabbahWala — Product Requirements Document (PRD)
**BMAD Phase 2 | Version 1.0 | 2026-03-28**

> Source: Derived from direct analysis of the production codebase (app/, migrations/, n8n/, mcp_server/, SYSTEM.md, USER_STORIES.md).

---

## Table of Contents

1. [Platform & Health](#1-platform--health)
2. [Authentication & Dashboard](#2-authentication--dashboard)
3. [Credentials & Internal Services](#3-credentials--internal-services)
4. [Event Ingestion](#4-event-ingestion)
5. [Lifecycle — Stage Engine](#5-lifecycle--stage-engine)
6. [Intelligence — Contact Sweep](#6-intelligence--contact-sweep)
7. [Opportunities](#7-opportunities)
8. [AI Agent Pipeline](#8-ai-agent-pipeline)
9. [Single-Agent Router](#9-single-agent-router)
10. [SMS / Telnyx](#10-sms--telnyx)
11. [Webhooks & Delivery](#11-webhooks--delivery)
12. [Orders / Shipday](#12-orders--shipday)
13. [Daily CSV Orders](#13-daily-csv-orders)
14. [Instantly Campaigns](#14-instantly-campaigns)
15. [Prospects & Contacts](#15-prospects--contacts)
16. [Broadcasts](#16-broadcasts)
17. [Menu & History](#17-menu--history)
18. [Playbook Rules](#18-playbook-rules)
19. [Team Content](#19-team-content)
20. [Reports](#20-reports)
21. [Field Agent](#21-field-agent)
22. [Chatbot](#22-chatbot)
23. [Marketing Query](#23-marketing-query)
24. [Growth / Goal / Competitor Agents](#24-growth--goal--competitor-agents)
25. [Test Harness & Admin Schedules](#25-test-harness--admin-schedules)
26. [MCP Server](#26-mcp-server)
27. [n8n Workflows](#27-n8n-workflows)
28. [Non-Functional Requirements](#28-non-functional-requirements)
29. [User Stories](#29-user-stories)

---

## 1. Platform & Health

| ID | Requirement |
|----|-------------|
| FR-PLAT-01 | FastAPI app with structured HTTP request logging: method, path, status code, duration (ms), client IP. |
| FR-PLAT-02 | `GET /health` — verifies DB connectivity; returns `{"status":"ok","db":"connected"}` or 503 degraded. |
| FR-PLAT-03 | On startup: apply critical schema patches (e.g. `orders` column additions) idempotently. |
| FR-PLAT-04 | On startup: run all SQL migrations from `migrations/` tracked in `schema_migrations` table; skip already-applied; log applied/skipped/failed counts. |
| FR-PLAT-05 | On startup: kick off chatbot doc reindex in a background thread (non-blocking). |
| FR-PLAT-06 | Global exception handler: JSON `{"detail": ..., "type": ...}` with 500 status. |
| FR-PLAT-07 | `POST /admin/migrate/{n}` — run a specific migration file; protected by `ADMIN_SECRET`. |
| FR-PLAT-08 | `POST /admin/query` — read-only SQL via query param or JSON body; protected by `ADMIN_SECRET`. |
| FR-PLAT-09 | `POST /admin/exec` — write SQL (DDL/DML); protected by `ADMIN_SECRET`. |

---

## 2. Authentication & Dashboard

| ID | Requirement |
|----|-------------|
| FR-AUTH-01 | Google OAuth2 flow: `GET /login` (HTML form), `GET /auth/google` (redirect), `GET /auth/callback` (token exchange + session), `GET /auth/me`, `GET /auth/logout`. |
| FR-AUTH-02 | Only `@dabbahwala.com` (or configurable domain) Google accounts are permitted. |
| FR-AUTH-03 | `GET /dashboard` — serves HTML dashboard; redirects unauthenticated users to `/login`. |
| FR-AUTH-04 | Session stored server-side (cookie or token); `get_current_user(request)` used as auth guard across protected endpoints. |

---

## 3. Credentials & Internal Services

| ID | Requirement |
|----|-------------|
| FR-CRED-01 | `GET /api/credentials/` — returns all runtime API keys/config for n8n bootstrap; requires `X-Admin-Secret` header. |
| FR-CRED-02 | `POST /api/internal/send-email` — SMTP email proxy; used by n8n for report delivery. |
| FR-CRED-03 | `POST /api/internal/drive/upload`, `GET /api/internal/drive/files` — Google Drive file operations. |
| FR-CRED-04 | `GET /api/internal/docs/{doc_id}` — Read a Google Doc by ID; used by n8n chatbot reindex. |

---

## 4. Event Ingestion

| ID | Requirement |
|----|-------------|
| FR-EVT-01 | `POST /api/events/ingest` — accepts a typed event payload and persists via `ingest_event()` stored procedure. |
| FR-EVT-02 | Supported event types: `email_open`, `email_click`, `sms_sent`, `sms_received`, `sms_click`, `call_completed`, `order_placed`, `unsubscribe`, `sms_stop`, `delivery_update`. |
| FR-EVT-03 | `ingest_event()` writes to the `events` table with full audit trail; validates event type. |

---

## 5. Lifecycle — Stage Engine

| ID | Requirement |
|----|-------------|
| FR-LIFE-01 | `POST /api/lifecycle/run` — executes `run_lifecycle_cycle()` SQL stored function; returns segment transition counts. |
| FR-LIFE-02 | Eight lifecycle segments: `cold`, `engaged`, `active_customer`, `new_customer`, `lapsed_customer`, `reactivation_candidate`, `cooling`, `optout`. |
| FR-LIFE-03 | `campaign_routing` table is the single source of truth for segment → Instantly campaign mapping (id, name, template file, performance stats). |
| FR-LIFE-04 | Contact's active campaign is always derived via JOIN on `lifecycle_segment` to `campaign_routing` — never a denormalized field. |
| FR-LIFE-05 | `run_lifecycle_cycle()` evaluates SQL predicates from `rules` table, transitions segments, and enqueues `push_instantly_lead` rows into `action_queue`. |

---

## 6. Intelligence — Contact Sweep

| ID | Requirement |
|----|-------------|
| FR-INTEL-01 | `POST /api/intelligence/run-cycle` — runs 5-phase sweep: COLLECT → PROFILE → SIGNAL → ROUTE → DISPATCH. No Claude calls. |
| FR-INTEL-02 | PROFILE phase calls `refresh_engagement_rollups()` to recompute 7d/30d rolling metrics into `engagement_rollups`. |
| FR-INTEL-03 | SIGNAL phase runs 7 SQL signal detectors: `engaged_no_order`, `new_customer_no_repeat`, `lapsed_reengaged`, `reorder_intent`, `app_customers_for_conversion`, `subscription_candidates`, `high_value_at_risk`. |
| FR-INTEL-04 | Each signal fires `create_opportunity()` with deduplication (no duplicate pending opportunities per contact per type). |
| FR-INTEL-05 | `GET /api/intelligence/pending-actions` — list pending opportunities. |
| FR-INTEL-06 | `POST /api/intelligence/ingest-instantly-events` — pull and persist email engagement events from Instantly API. |

---

## 7. Opportunities

| ID | Requirement |
|----|-------------|
| FR-OPP-01 | `GET /api/opportunities/detect` — run signal detection and return new opportunities. |
| FR-OPP-02 | `POST /api/opportunities/` — manually create an opportunity. |
| FR-OPP-03 | `GET /api/opportunities/pending` — list pending opportunities. |
| FR-OPP-04 | `POST /api/opportunities/{id}/dispatched` — mark as dispatched. |
| FR-OPP-05 | `POST /api/opportunities/{id}/outcome` — record outcome (converted, declined, expired). |
| FR-OPP-06 | Opportunity statuses: `pending`, `dispatched`, `completed`, `expired`, `declined`. |
| FR-OPP-07 | Opportunity actions: `send_sms`, `field_sales_call`, `send_email`. |

---

## 8. AI Agent Pipeline

| ID | Requirement |
|----|-------------|
| FR-AGENT-01 | `POST /api/agents/cycle/run` — run agent cycle for a specified contact. |
| FR-AGENT-02 | `POST /api/agents/cycle/run-for-contact` — real-time single-contact cycle (triggered by inbound SMS). |
| FR-AGENT-03 | `POST /api/agents/cycle/run-all` — batch cycle for all eligible contacts. |
| FR-AGENT-04 | `POST /api/agents/cycle/run-all-lapsed` — batch cycle for lapsed contacts only. |
| FR-AGENT-05 | `POST /api/agents/cycle/run-daily-sweep` — daily combined sweep + agent cycle. |
| FR-AGENT-06 | **Layer 1 — Observer (4 agents):** run in parallel per contact. |
| | • Menu agent (Haiku): outputs `top_picks[]`, `bridge_item`, `avoid[]` → feeds into Intent and Offer. |
| | • Sentiment agent (Haiku): outputs `sentiment` (positive/neutral/negative), `confidence`, `summary`. |
| | • Intent agent (Sonnet): outputs `intent` (ready_to_order/needs_info/price_sensitive/not_interested/unknown), `signals[]`, `confidence`. |
| | • Engagement agent (Haiku): outputs `engagement_score` (0–1), `trend` (rising/flat/falling), `last_touch_hours_ago`. |
| | Stored in: `contact_observations`. |
| FR-AGENT-07 | **Layer 2 — Advisor (4 agents):** run in parallel; input = contact profile + full Layer 1 bundle. |
| | • Stage agent (Haiku): `recommended_stage`, `confidence`, `reason`. |
| | • Channel agent (Haiku): `recommended_channel` (sms/email/call/none), `channel_timing`, `reason`. |
| | • Offer agent (Sonnet): `offer_type` (discount/reminder/social_proof/none), `suggested_copy` (references menu picks), `reason`. |
| | • Escalation agent (Sonnet): `should_escalate` (bool), `urgency` (high/medium/none), `reason`. |
| | Stored in: `action_plans`. |
| FR-AGENT-08 | **Layer 3 — Orchestrator (1 Sonnet call):** reads all Layer 2 outputs + latest delivery event + recent action history → outputs one `chosen_action`. Stored in: `orchestrator_log` + inserted into `action_queue`. |
| FR-AGENT-09 | Delivery-aware guardrails (Orchestrator checks first): `delivered` → 4h delay before outreach; `delivery_failed`/`delivery_returned` → immediate `escalate_airtable` urgency=high; `out_for_delivery`/`driver_assigned` → force `none`. |
| FR-AGENT-10 | General guardrails: max 1 contact per 24h same channel; max 3 SMS/week; escalation beats automation; `intent=not_interested` → `none` unless high urgency; `priority_override=do_not_contact` → `none` always. |
| FR-AGENT-11 | Playbook RAG: each agent receives relevant `agent_playbook` categories injected into system prompt. Playbook SHA-256 hash cache prevents DB re-reads when unchanged. |
| FR-AGENT-12 | Prompt caching: all static system prompt prefixes sent as Anthropic `cache_control: ephemeral` blocks (90%+ token discount from contact #2 in batch). |
| FR-AGENT-13 | Model routing: Haiku for fast classifiers (Menu, Sentiment, Engagement, Stage, Channel); Sonnet for heavy reasoning (Intent, Offer, Escalation, Orchestrator). |
| FR-AGENT-14 | **Layer 4 — Report agents (2 Sonnet calls, daily):** `POST /api/agents/report/activity` and `/report/outcome` — generate HTML/CSV report summaries. |
| FR-AGENT-15 | Action queue API: `GET /api/agents/action-queue/pending`, `POST /api/agents/action-queue/{id}/done`. |
| FR-AGENT-16 | Goals API: `POST /api/agents/goals` — create/update contact goal (`convert_to_order`, `retain`, `reactivate`) stored in `customer_goals`. |
| FR-AGENT-17 | Batch post-processing (after run-all): `move_campaign` contacts pushed to Instantly immediately; `escalate_airtable` contacts get Airtable field-sales task created; digest email queued to `support@dabbahwala.com`. |

---

## 9. Single-Agent Router

| ID | Requirement |
|----|-------------|
| FR-SA-01 | `/api/agent` — specialized single-contact analysis endpoints used for tooling, experiments, and direct agent calls. Functional parity with `test_agent.py` test group. |

---

## 10. SMS / Telnyx

| ID | Requirement |
|----|-------------|
| FR-SMS-01 | `POST /api/telnyx/message` (alias `/api/sms/message`) — store inbound/outbound message in `telnyx_messages`; auto-create contact record for unknown inbound numbers before triggering agent cycle. |
| FR-SMS-02 | `POST /api/telnyx/call` — store call metadata and transcript in `telnyx_calls`. |
| FR-SMS-03 | `POST /api/telnyx/field-agent-message` — field-initiated SMS (separate tracking). |
| FR-SMS-04 | SMS A/B testing: `sms_templates` table with variants; template CRUD. |

---

## 11. Webhooks & Delivery

| ID | Requirement |
|----|-------------|
| FR-WH-01 | `POST /api/webhooks/instantly` — receive Instantly email events (open, click, reply, bounce); persist and trigger downstream processing. |
| FR-WH-02 | `POST /api/webhooks/telnyx` — Telnyx inbound SMS push webhook; store and trigger agent cycle. |
| FR-WH-03 | `POST /api/webhooks/shipday`, `GET /api/webhooks/shipday` — Shipday delivery status webhooks. |
| FR-WH-04 | `POST /api/webhooks/sync-campaigns`, `GET /api/webhooks/campaigns`, `POST /api/webhooks/campaign-stats` — sync Instantly campaign list and stats into `campaign_routing`. |
| FR-WH-05 | `POST /api/delivery/status` — maps Shipday statuses to internal events; triggers appropriate agent cycle delay per FR-AGENT-09. |
| FR-WH-06 | Delivery of `delivered` event → 4h threading.Timer before AI cycle fires (contact has time to eat). |

---

## 12. Orders / Shipday

| ID | Requirement |
|----|-------------|
| FR-ORD-01 | `POST /api/shipday/ingest-orders` — pull orders from Shipday API and persist to `orders` + `order_items`. |
| FR-ORD-02 | `GET /api/shipday/sync-status` — status of last Shipday sync. |
| FR-ORD-03 | `GET /api/shipday/top-calls` — contacts with most order history. |
| FR-ORD-04 | `POST /api/shipday/import-all-and-run-agents` — full historical import + run agent cycle. |
| FR-ORD-05 | `GET /api/shipday/import-pipeline-status` — status of import pipeline. |
| FR-ORD-06 | `POST /api/shipday/sync-feedback`, `GET /api/shipday/feedback-stats` — delivery feedback ingestion and stats. |

---

## 13. Daily CSV Orders

| ID | Requirement |
|----|-------------|
| FR-DAILY-01 | `POST /api/daily-orders/` — accept daily CSV upload; create/update contacts; create orders; normalize phone numbers; resolve menu items; generate order summaries. |

---

## 14. Instantly Campaigns

| ID | Requirement |
|----|-------------|
| FR-CAMP-01 | `POST /api/campaigns/push-lead` — enqueue `push_instantly_lead` action into `action_queue`. |
| FR-CAMP-02 | `GET /api/campaigns/pending` — list pending push_instantly_lead items. |
| FR-CAMP-03 | `GET /api/campaigns/active-contacts` — contacts with active campaigns (used for Instantly seed). |
| FR-CAMP-04 | `GET /api/campaigns/active-contacts-stats` — diagnostic: filter exclusion counts + campaign distribution. |
| FR-CAMP-05 | `POST /api/campaigns/log-push`, `GET /api/campaigns/push-log` — audit trail of Instantly push attempts in `campaign_push_log`. |
| FR-CAMP-06 | `GET /api/campaigns/analytics` — campaign performance metrics. |
| FR-CAMP-07 | SMS template CRUD: `GET/PUT /api/campaigns/templates/{name}`, `POST /templates/{name}/rewrite` (Claude AI rewrite). |
| FR-CAMP-08 | `POST /api/campaigns/setup-instantly` — bootstrap Instantly campaign configuration. |

---

## 15. Prospects & Contacts

| ID | Requirement |
|----|-------------|
| FR-PROS-01 | `GET /api/prospects/template` — download CSV template for new contact import. |
| FR-PROS-02 | `POST /api/prospects/upload-csv` — bulk add new contacts from CSV. |
| FR-PROS-03 | `GET /api/prospects/update-template` — download update CSV template; enqueue Google Drive upload. |
| FR-PROS-04 | `POST /api/prospects/update-csv` — bulk update existing contacts (name, address, priority_override, sales_notes) matched by email or phone. |
| FR-PROS-05 | `POST /api/prospects/add` — add a single contact manually. |
| FR-CONT-01 | `PATCH /api/contacts/{id}/priority` — override contact priority. |
| FR-CONT-02 | `PATCH /api/contacts/{id}/notes` — update free-text sales notes on contact. |

---

## 16. Broadcasts

| ID | Requirement |
|----|-------------|
| FR-BC-01 | Create broadcast job (target segment, channel: sms/email, message, schedule). |
| FR-BC-02 | List broadcast jobs; status per job. |
| FR-BC-03 | List recipients for a broadcast before sending (preview). |
| FR-BC-04 | SMS broadcasts execute via Telnyx (dispatched through n8n). |
| FR-BC-05 | Email broadcasts execute via Instantly or SMTP (dispatched through n8n). |
| FR-BC-06 | Delay alerts: surface broadcast jobs with pending status older than threshold. |

---

## 17. Menu & History

| ID | Requirement |
|----|-------------|
| FR-MENU-01 | `GET /api/menu/items` — list active menu items. |
| FR-MENU-02 | `GET /api/menu/items/inactive` — list inactive/discarded items. |
| FR-MENU-03 | `GET /api/menu/items/{id}/history` — price/status change history from `menu_catalog_history`. |
| FR-MENU-04 | `POST /api/menu/sync` — two-phase Airtable sync: upsert active items + detect discards; write history records. |
| FR-MENU-05 | Discard = soft delete: set `discarded_date`, write `menu_catalog_history` record with `change_type='discarded'`. Never hard-delete. |
| FR-MENU-06 | Airtable is source of truth for menu; DB is the operational copy. |

---

## 18. Playbook Rules

| ID | Requirement |
|----|-------------|
| FR-PB-01 | `GET /api/playbook/rules` — list all rules from `agent_playbook`. |
| FR-PB-02 | `POST /api/playbook/rules` — create or update a rule. |
| FR-PB-03 | `POST /api/playbook/sync-from-airtable` — pull rules from Airtable into `agent_playbook`; runs daily at 6 AM via n8n. |
| FR-PB-04 | Rules have: priority (higher = checked first), active flag, category (exclusion/priority/observer/advisor/messaging), and rule text. |
| FR-PB-05 | `GET /api/playbook/for-prompt` — return rules formatted for agent prompt injection, filtered by category. |

---

## 19. Team Content

| ID | Requirement |
|----|-------------|
| FR-TC-01 | `POST /api/team-content/sync` — pull content from Google Docs into `team_content` table. |
| FR-TC-02 | `POST /api/team-content/submit` — manually submit a piece of content (ground notes, ad copy). |
| FR-TC-03 | `GET /api/team-content/browse` — list all team content entries. |
| FR-TC-04 | `POST /api/team-content/search` — keyword search over team content. |

---

## 20. Reports

| ID | Requirement |
|----|-------------|
| FR-REP-01 | `GET /api/reports/daily/{date}` — retrieve stored daily report for a date. |
| FR-REP-02 | `POST /api/reports/daily/{date}` — generate and store daily report via `generate_daily_report()`. |
| FR-REP-03 | Reports aggregated into `daily_reports` table with JSONB metrics. |

---

## 21. Field Agent

| ID | Requirement |
|----|-------------|
| FR-FA-01 | `GET /api/field-agent/brief` — daily brief: top-10 priority contacts with name, phone, lifecycle stage, last interaction summary, AI talking points. Delivered by n8n at 7:30 AM. |
| FR-FA-02 | `GET /api/field-agent/pending-calls` — list contacts assigned to field with call scripts. |
| FR-FA-03 | `POST /api/field-agent/log-outcome` — log call outcome: connected/not-answered/interested/not-interested; mark hot lead; free-text notes. |
| FR-FA-04 | `GET /api/field-agent/scorecard` — performance metrics for field team. |
| FR-FA-05 | `POST /api/field-agent/analyze-call` — Claude analysis of a completed call. |
| FR-FA-06 | Hot leads immediately create Airtable escalation task and trigger AI cycle. |
| FR-FA-07 | New AI-assigned field tasks appear in Airtable within 4 hours of agent batch run. |

---

## 22. Chatbot

| ID | Requirement |
|----|-------------|
| FR-CHAT-01 | `POST /api/chatbot/ask` — RAG-based Q&A over team docs, menu, and ground notes; responds in natural language. |
| FR-CHAT-02 | `GET /api/chatbot/suggest` — suggested questions based on current context. |
| FR-CHAT-03 | `GET /api/chatbot/history` — recent chatbot Q&A history. |
| FR-CHAT-04 | `POST /api/chatbot/reindex` — trigger doc reindex (pull from Google Docs + team_content). |
| FR-CHAT-05 | Chatbot uses `pgvector` for semantic search over indexed content. |

---

## 23. Marketing Query

| ID | Requirement |
|----|-------------|
| FR-QRY-01 | `POST /api/query/` — named query interface; accepts `category` + optional date range params. |
| FR-QRY-02 | `GET /api/query/categories` — return list of all supported categories. |
| FR-QRY-03 | **20 query categories:** `customer_lookup`, `pipeline_snapshot`, `campaign_performance`, `who_to_contact`, `daily_summary`, `order_analytics`, `order_summary_by_order_date`, `order_summary_by_delivery_date`, `revenue_trends`, `communication_history`, `team_notes`, `ground_team_notes`, `ad_copies`, `submit_input`, `broadcast_history`, `sms_performance`, `email_performance`, `activity_report`, `outcome_report`, `free_form`. |
| FR-QRY-04 | `free_form` category passes the query to Claude for natural-language analytics response. |
| FR-QRY-05 | Date-range categories (`sms_performance`, `email_performance`, `activity_report`, `outcome_report`) accept `start_date` and `end_date`. |

---

## 24. Growth / Goal / Competitor Agents

| ID | Requirement |
|----|-------------|
| FR-GROW-01 | `POST /api/growth/run-cycle` — Claude designs and dispatches a growth experiment; agent sets `measure_days` (7–56 days). |
| FR-GROW-02 | `POST /api/growth/measure` — adaptive measurement: fires at `measure_at` OR after 30+ conversion events. |
| FR-GROW-03 | `POST /api/growth/baseline/update`, `GET /api/growth/experiments`, `GET /api/growth/insights`. |
| FR-GROW-04 | Growth data: `experiments`, `experiment_contacts`, `growth_baseline` tables. |
| FR-GOAL-01 | `POST /api/goal-agent/run` — full 4-phase goal agent cycle: hypothesize → experiment → measure → harvest. |
| FR-GOAL-02 | `POST /api/goal-agent/hypothesize`, `/experiment`, `/measure`, `/harvest` — individual phase endpoints. |
| FR-GOAL-03 | `GET /api/goal-agent/experiments`, `/signals`, `/runs`. |
| FR-GOAL-04 | Hypothesis dedup: `hypothesis_hash VARCHAR(64) UNIQUE` prevents re-running identical ideas. |
| FR-GOAL-05 | Harvest phase promotes proven experiments into `discovered_signals` as reusable SQL rules. |
| FR-COMP-01 | `POST /api/competitor-agent/run` — full cycle: parse competitor emails + scrape sites + generate hypotheses + inject into goal experiments. |
| FR-COMP-02 | `GET /api/competitor-agent/runs`, `GET /api/competitor-agent/experiments`. |
| FR-COMP-03 | Competitor data: `competitor_agent_runs`, `goal_experiments` (shared with goal agent, `source` column distinguishes). |

---

## 25. Test Harness & Admin Schedules

| ID | Requirement |
|----|-------------|
| FR-TEST-01 | `POST /api/test/run` — run full E2E test suite (all groups); results persisted to `test_runs` table with JSONB. |
| FR-TEST-02 | `GET /api/test/results` — list all test run summaries. |
| FR-TEST-03 | `GET /api/test/results/{run_id}` — full result detail for a run. |
| FR-TEST-04 | `GET /api/test/run/{group_id}` — run a single test group; returns per-test pass/fail. |
| FR-TEST-05 | Test groups: G1 Connectivity · G2 Schema · G3 Contact setup · G4 Events/webhooks · G5 Telnyx · G6 Agent pipeline · G7 Intelligence/lifecycle · G8 Instantly · G9 Airtable · G10 Action queue · G11 Orders · G12 Reports · G13 Query/chatbot · G14 Cleanup · G15 Competitor/goal · G16 Content/reports/playbook. |
| FR-SCH-01 | `GET /api/admin/schedules` — list all n8n workflow schedules as human-readable strings; sorted by name; requires Google OAuth session. |
| FR-SCH-02 | `POST /api/admin/schedules/{workflow_id}` — update a workflow's `scheduleTrigger` node and push to n8n API. |

---

## 26. MCP Server

| ID | Requirement |
|----|-------------|
| FR-MCP-01 | FastMCP server in `mcp_server/` — Claude Desktop integration over PostgreSQL data. |
| FR-MCP-02 | **Tool groups (35+ tools):** contacts (lookup, update, list by segment), analytics (pipeline snapshot, lifecycle summary, campaign performance), communications (SMS history, call log), recommendations (next actions, opportunities), opportunities (list, create, update), agents (run cycle, queue status), Shipday (order lookup, feedback), Instantly (campaign stats, lead push). |
| FR-MCP-03 | MCP tools query Postgres via direct DB connection — they do NOT call FastAPI endpoints. |
| FR-MCP-04 | MCP server exposes marketing data to Claude Desktop for operational queries and ad-hoc analysis. |

---

## 27. n8n Workflows

| ID | Requirement |
|----|-------------|
| FR-N8N-01 | **27 workflows** total: 26 active-scheduled + 1 manual (historical import). |
| FR-N8N-02 | All workflows authenticate to FastAPI via `X-Admin-Secret` or call `/api/credentials/` to get runtime keys. No secrets hardcoded in workflow JSON. |
| FR-N8N-03 | Workflow JSON files live in `n8n/` directory; synced to hosted n8n instance via CI on push to `main`. |
| FR-N8N-04 | **Action Queue Executor** — polls `action_queue` for pending items; executes via Telnyx/Instantly/Airtable/Drive/SMTP. |
| FR-N8N-05 | **Agent Orchestration Cron** — runs agent cycle for all eligible contacts every 3 hours. |
| FR-N8N-06 | **Broadcast Dispatch** — executes queued broadcast jobs via SMS (Telnyx) and email (SMTP). |
| FR-N8N-07 | **Contact Sweep (Intelligence Cron)** — calls `/api/intelligence/run-cycle` hourly. |
| FR-N8N-08 | **Stage Runner** — calls `/api/lifecycle/run` hourly. |
| FR-N8N-09 | **Airtable Menu Sync** — daily sync of menu catalog from Airtable. |
| FR-N8N-10 | **Airtable Playbook Sync** — daily sync of playbook rules from Airtable at 6 AM. |
| FR-N8N-11 | **Airtable Outcome Sync** — sync field agent outcomes from Airtable. |
| FR-N8N-12 | **Daily Order Upload** — process daily CSV order file. |
| FR-N8N-13 | **SMS Dispatch** — execute SMS messages from action queue via Telnyx. |
| FR-N8N-14 | **Telnyx Inbound Collector** — pull inbound SMS from Telnyx and post to `/api/telnyx/message`. |
| FR-N8N-15 | **Shipday Delivery Collector** — poll Shipday for delivery status updates. |
| FR-N8N-16 | **Shipday Feedback Sync** — pull delivery feedback from Shipday. |
| FR-N8N-17 | **Instantly Campaign Sync** — sync Instantly campaign list and stats to `campaign_routing`. |
| FR-N8N-18 | **Chatbot Docs Reindex** — pull Google Docs into `team_content` for chatbot RAG. |
| FR-N8N-19 | **Daily Activity Report** — generate and email daily activity summary (HTML + CSV). |
| FR-N8N-20 | **Daily Outcome Report** — generate and email daily AI actions summary. |
| FR-N8N-21 | **Daily Field Brief** — generate and deliver field agent daily brief at 7:30 AM. |
| FR-N8N-22 | **Hourly Intelligence Cycle** — combined intelligence + lifecycle run. |
| FR-N8N-23 | **Goal Agent Cycle** — runs goal agent phase cycle on schedule. |
| FR-N8N-24 | **Growth Agent Cycle** — runs growth experiment cycle on schedule. |
| FR-N8N-25 | **Competitor Agent Cycle** — runs competitor research weekly. |
| FR-N8N-26 | **System Feature Tests** — automated E2E test suite run at 5 AM; emails on failure. |
| FR-N8N-27 | **System Connectivity Check** — manual workflow; pings all external services. |

---

## 28. Non-Functional Requirements

### 28.1 Security

| ID | Requirement |
|----|-------------|
| NFR-SEC-01 | No API keys committed to code; all secrets via environment variables. |
| NFR-SEC-02 | Admin routes protected by `ADMIN_SECRET`; operator UI by Google OAuth. |
| NFR-SEC-03 | SMS STOP and email unsubscribe flows must hard-stop all outreach for that contact. |
| NFR-SEC-04 | `optout` and `do_not_contact` priority override = absolute exclusion from all automated outreach. |

### 28.2 Reliability

| ID | Requirement |
|----|-------------|
| NFR-OPS-01 | All SQL migrations idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`). |
| NFR-OPS-02 | Structured logging with configurable `LOG_LEVEL` env var (default INFO). |
| NFR-OPS-03 | PostgreSQL connection pool (min 1, max 10); `search_path` scoped to `dabbahwala` schema. |
| NFR-OPS-04 | Render deploy: `scripts/render_build.sh`; start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. |
| NFR-OPS-05 | n8n workflow JSON synced via CI (`.github/workflows/sync_n8n.yml`). |

### 28.3 Performance & Cost

| ID | Requirement |
|----|-------------|
| NFR-PERF-01 | Anthropic prompt caching on all agent system prompts (ephemeral blocks). |
| NFR-PERF-02 | Playbook SHA-256 hash cache — only re-query DB when content changes. |
| NFR-PERF-03 | Model routing: Haiku for fast classifiers, Sonnet for reasoning. |
| NFR-PERF-04 | Batch cycle: cap contacts per run; cooldown periods between sweeps. |

### 28.4 Data Integrity

| ID | Requirement |
|----|-------------|
| NFR-DATA-01 | Menu discard is soft delete only — `discarded_date` + history record; order line items remain valid. |
| NFR-DATA-02 | Full audit trail: `decision_log`, `campaign_push_log`, `orchestrator_log`, `menu_catalog_history`, `goal_agent_runs`, `competitor_agent_runs`. |

### 28.5 Testing

| ID | Requirement |
|----|-------------|
| NFR-QA-01 | Pytest suite with mocked DB (psycopg2 mock) for all routers. |
| NFR-QA-02 | E2E test harness (G1–G16) runnable on-demand via `POST /api/test/run`. |
| NFR-QA-03 | Daily automated test run at 5 AM; email alert on any group failure. |
| NFR-QA-04 | Every new feature requires test harness coverage + pytest tests before merge. |

---

## 29. User Stories (Canonical)

### Marketing Operator
- Bulk CSV upload of new contacts
- View contact lifecycle segment and full history
- Manually override contact priority
- Flag contact as opted-out or in cooling-off
- Add free-text note on a contact for AI context
- Send SMS broadcast to a specific lifecycle segment
- Send email broadcast to engaged contacts
- Preview broadcast audience before sending
- View segment → campaign mapping
- Track email open/click/reply per campaign
- Contacts auto-move between campaigns on segment change
- Create/update SMS templates
- Add playbook rule in Airtable; sync is automatic daily
- Set rule priority; deactivate without deleting
- Add menu item in Airtable; auto-syncs to DB
- View price/status change history per menu item
- Discarded items soft-deleted; order history intact
- Receive daily activity report by email each morning
- Receive daily outcome report showing AI actions taken
- View which contacts converted after AI outreach

### Field Agent
- Receive daily brief at 7:30 AM with top-10 call list
- Each brief entry: name, phone, segment, last interaction, talking points
- Brief delivered to inbox or Airtable
- Log call outcome via Airtable or SMS
- Mark contact as hot lead → immediate escalation
- Add free-text call note for AI context
- See prioritized open field tasks in Airtable
- Completed tasks auto-archived
- New AI tasks appear in Airtable within 4h of batch run

### Admin
- Schema migrations run automatically on deploy
- Idempotent SQL always safe to re-run
- Migration numbering tracked to prevent conflicts
- Run full E2E suite on demand via `POST /api/test/run`
- Daily 5 AM tests email on failure
- Every new feature has test coverage
- View and update n8n schedules via API
- Activate/deactivate workflows via API
- Runtime credentials served from single endpoint
- Secrets only in environment
- Manual connectivity workflow for external dependencies

### Analytics / Growth User
- Plain English query or named category query
- 20 query categories + free_form Claude analytics
- View AI observations, action plans, orchestrator decisions, action queue
- Goal Agent: design and run hypothesis experiments
- View active experiments; harvest proven ones to SQL rules
- Competitor agent: weekly research; seed into goal experiments
- Lifecycle funnel analytics; rule frequency; rollup health

### Customer
- Personalised SMS re-engagement at reasonable hours
- Reply STOP to permanently opt out
- SMS content contextually relevant (references menu/order history)
- Email welcome sequence on first order
- Email re-engagement after lapse
- Unsubscribe from email at any time
- Order confirmation and delivery updates
- Feedback prompt after delivery
- Chatbot: ask about menu items, filter by veg/price
