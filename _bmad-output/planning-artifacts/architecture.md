# DabbahWala — Architecture Document
**BMAD Phase 3 | Version 1.0 | 2026-03-28**

---

## 1. System Overview

DabbahWala is a **lifecycle-driven marketing orchestration backend**. It ingests events from five external channels, processes contacts through three cooperating engines, and executes outreach via n8n as the execution mesh.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INPUTS                                      │
│  Telnyx SMS/Voice · Shipday Orders · Instantly Email · CSV Orders  │
│              Airtable (Menu/Playbook) · Google Docs                │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              FastAPI (dabbahwala-latest.onrender.com)               │
│                                                                     │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │ Stage Engine│  │  Contact Sweep   │  │    AI Stack          │   │
│  │ (SQL rules) │  │ (5-phase signal) │  │ Observer→Advisor     │   │
│  │  Hourly     │  │   Hourly         │  │ →Orchestrator        │   │
│  └──────┬──────┘  └────────┬─────────┘  └──────────┬───────────┘   │
│         │                  │                        │               │
│         └──────────────────┴────────────────────────┘               │
│                            │                                        │
│                      action_queue                                   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              n8n (digitalworker.dataskate.io)                       │
│                                                                     │
│  Action Queue Executor · SMS Dispatch · Broadcast Dispatch          │
│  Airtable Sync · Menu Sync · Playbook Sync · Reports               │
│  Intelligence Cron · Stage Runner · Feature Tests                   │
└────────────┬──────────────────┬──────────────────────┬──────────────┘
             │                  │                      │
             ▼                  ▼                      ▼
          Telnyx             Instantly              Airtable
          (SMS)              (Email)                (CRM/Tasks)
```

---

## 2. Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Web framework | FastAPI | Python 3.11+ |
| AI SDK | anthropic | 0.49+ |
| MCP protocol | mcp (FastMCP) | 1.3+ |
| HTTP client | httpx (async) | — |
| Data validation | Pydantic | v2 |
| DB driver | psycopg2 | — |
| Vector search | pgvector | — |
| Automation | n8n | self-hosted |

| Infrastructure | Platform |
|---------------|----------|
| API server | Render (Starter, Oregon) |
| Database | PostgreSQL 16 — Supabase (transaction pool, port 6543) |
| n8n | Self-hosted `digitalworker.dataskate.io` |
| CI/CD | GitHub Actions |

---

## 3. Database Design

**Schema:** `dabbahwala`
**Connection:** `SimpleConnectionPool` (min 1, max 10); `search_path = dabbahwala` set at connect time
**Access pattern:** `get_cursor(commit=bool)` context manager with `RealDictCursor`

### 3.1 Core Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `contacts` | Master customer record | `id`, `email`, `phone`, `lifecycle_segment`, `priority_override`, `sales_notes`, `source`, `opted_out`, `cooling_until`, `order_count`, `last_order_at` |
| `events` | Raw event log | `id`, `contact_id`, `event_type`, `metadata`, `created_at` |
| `orders` | Order records | `id`, `contact_id`, `order_ref`, `total_amount`, `delivery_date`, `order_type`, `notes` |
| `order_items` | Line items | `id`, `order_id`, `item_name`, `quantity`, `unit_price` |
| `menu_catalog` | Menu items (Airtable source of truth) | `id`, `item_name`, `category`, `is_veg`, `price`, `active`, `discarded_date`, `airtable_record_id` |
| `menu_catalog_history` | Audit trail of menu changes | `id`, `menu_item_id`, `change_type`, `old_value`, `new_value`, `changed_at` |

### 3.2 Communication Tables

| Table | Purpose |
|-------|---------|
| `telnyx_messages` | SMS tracking — direction, body, status, source, agent_name |
| `telnyx_calls` | Call tracking — duration, transcript, summary |
| `delivery_status` | Delivery updates — status, notes, location, updated_by |
| `engagement_rollups` | Materialised 7d/30d rolling metrics per contact |

### 3.3 Agent Pipeline Tables

| Table | Purpose |
|-------|---------|
| `customer_goals` | One active goal per contact: `convert_to_order` / `retain` / `reactivate` |
| `contact_observations` | Layer 1 outputs per cycle run (sentiment, intent, engagement, menu picks) |
| `action_plans` | Layer 2 outputs per cycle run (stage, channel, offer, escalation) |
| `orchestrator_log` | Layer 3 chosen action + full reasoning text + guardrails applied |
| `action_queue` | Approved actions: `pending → executing → done / failed`; polled by n8n |

### 3.4 Configuration & Routing Tables

| Table | Purpose |
|-------|---------|
| `rules` | Lifecycle rule predicates + actions (evaluated by Stage Engine) |
| `campaign_routing` | **Single source of truth** — lifecycle segment → Instantly campaign id/name/template/stats |
| `campaign_push_log` | Audit of every push_instantly_lead attempt |
| `agent_playbook` | Business rules injected into agent prompts (synced from Airtable daily) |
| `sms_templates` | SMS A/B test variants |
| `team_content` | Ground notes, ad copies, Google Docs content (chatbot RAG source) |
| `opportunities` | Conversion opportunities — signal type, confidence, status |
| `decision_log` | Lifecycle transition audit trail |
| `daily_reports` | Aggregated daily metrics (JSONB) |
| `test_runs` | E2E test suite results (JSONB) |
| `schema_migrations` | Migration tracking — filename + applied_at |

### 3.5 Growth & Experiment Tables

| Table | Purpose |
|-------|---------|
| `experiments` | Growth agent experiments — type, cohort size, results, measure_at |
| `experiment_contacts` | Contacts enrolled per experiment + conversion outcome |
| `growth_baseline` | 7-day historical baseline conversion rates |
| `goal_experiments` | Goal/competitor agent hypotheses — `hypothesis_hash UNIQUE` prevents dupes |
| `goal_experiment_contacts` | Contacts per goal experiment + conversion |
| `goal_agent_runs` | Audit log of goal agent phases |
| `discovered_signals` | Harvested SQL signals from proven experiments |
| `competitor_agent_runs` | Competitor research audit log |

### 3.6 Enums

```sql
lifecycle_segment: cold | engaged | active_customer | new_customer
                   | lapsed_customer | reactivation_candidate | cooling | optout

campaign_name: NURTURE_SLOW | PROMO_STANDARD | PROMO_AGGRESSIVE
               | NEW_CUSTOMER_ONBOARDING | REACTIVATION | ACTIVE_CUSTOMER | APP_TO_DIRECT

event_type: email_open | email_click | sms_sent | sms_received | sms_click
            | call_completed | order_placed | unsubscribe | sms_stop | delivery_update

delivery_status_type: assigned | picked_up | in_transit | delivered | failed

opportunity_action: send_sms | field_sales_call | send_email
opportunity_status: pending | dispatched | completed | expired | declined
```

### 3.7 Key Stored Functions

| Function | Purpose |
|----------|---------|
| `run_lifecycle_cycle()` | Stage Engine — evaluate rules, transition segments, enqueue `push_instantly_lead` |
| `refresh_engagement_rollups()` | Recompute 7d/30d engagement metrics from events |
| `ingest_event()` | Persist event with type validation and audit trail |
| `get_contact_detail()` | Full contact profile with all history |
| `get_communication_history()` | SMS + calls + deliveries for a contact |
| `suggest_reactivation_targets()` | Find contacts most likely to reactivate |
| `get_lifecycle_summary()` | Pipeline snapshot (count per segment) |
| `get_campaign_performance()` | Campaign stats (opens, clicks, orders) |
| `generate_daily_report()` | Aggregate daily metrics for a date |
| `create_opportunity()` | Create opportunity with deduplication |
| `store_telnyx_message()` | Persist SMS with dedup |
| `update_delivery_status()` | Upsert delivery status record |

---

## 4. API Layer

**Framework:** FastAPI
**Base URL:** `https://dabbahwala-latest.onrender.com`
**Total endpoints:** 88+

### 4.1 Router Map

| Router file | Mount prefix | Domain |
|-------------|-------------|--------|
| `auth.py` | `/` (root) | Google OAuth, session |
| `events.py` | `/api/events` | Event ingestion |
| `lifecycle.py` | `/api/lifecycle` | Stage engine |
| `campaigns.py` | `/api/campaigns` | Instantly campaigns |
| `sms.py` | `/api/telnyx` + `/api/sms` | Telnyx SMS/calls |
| `delivery.py` | `/api/delivery` | Delivery status |
| `reports.py` | `/api/reports` | Daily reports |
| `opportunities.py` | `/api/opportunities` | Opportunity management |
| `agents.py` | `/api/agents` | AI pipeline batch |
| `agent.py` | `/api/agent` | Single-agent tooling |
| `goal_agent.py` | `/api/goal-agent` | Goal agent |
| `competitor_agent.py` | `/api/competitor-agent` | Competitor agent |
| `orders.py` | `/api/shipday` | Shipday orders |
| `daily_orders.py` | `/api/daily-orders` | CSV order upload |
| `intelligence.py` | `/api/intelligence` | Contact sweep |
| `growth_agent.py` | `/api/growth` | Growth experiments |
| `playbook.py` | `/api/playbook` | Playbook rules |
| `query.py` | `/api/query` | Marketing query (20 categories) |
| `team_content.py` | `/api/team-content` | Ground notes, docs |
| `field_agent.py` | `/api/field-agent` | Field brief, outcomes |
| `chatbot.py` | `/api/chatbot` | RAG chatbot |
| `broadcasts.py` | `/api/broadcasts` | Broadcast jobs |
| `prospects.py` | `/api/prospects` | CSV import, add contact |
| `contacts.py` | `/api/contacts` | Priority, notes patch |
| `webhooks.py` | `/api/webhooks` | Instantly, Telnyx, Shipday |
| `test_harness.py` | `/api/test` | E2E harness |
| `menu.py` | `/api/menu` | Menu catalog + sync |
| `config.py` | `/api/credentials` + `/api/internal` | Keys, SMTP, Drive |
| `schedules.py` | `/api/admin` | n8n schedule management |

### 4.2 Admin Endpoints (non-router)

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /health` | None | DB connectivity |
| `GET /dashboard` | Google OAuth | HTML dashboard |
| `POST /admin/migrate/{n}` | `ADMIN_SECRET` | Run migration |
| `POST /admin/query` | `ADMIN_SECRET` | Read-only SQL |
| `POST /admin/exec` | `ADMIN_SECRET` | Write SQL |

---

## 5. Three-Engine Architecture

### 5.1 Stage Engine

- **Trigger:** `POST /api/lifecycle/run` (called by n8n Stage Runner, hourly)
- **Mechanism:** `run_lifecycle_cycle()` SQL stored function
- **What it does:** Evaluates predicates from `rules` table; transitions contact `lifecycle_segment`; enqueues `push_instantly_lead` into `action_queue` for contacts whose campaign should change
- **No Claude involved**

### 5.2 Contact Sweep (Intelligence)

- **Trigger:** `POST /api/intelligence/run-cycle` (called by n8n Intelligence Cron, hourly)
- **Five phases:**

| Phase | What happens |
|-------|-------------|
| COLLECT | Query contacts eligible for signal detection |
| PROFILE | `refresh_engagement_rollups()` — update 7d/30d engagement metrics |
| SIGNAL | Run 7 SQL signal detectors; call `create_opportunity()` for each hit |
| ROUTE | Assign signal to appropriate channel/action |
| DISPATCH | Queue any immediate automated responses |

- **No Claude involved**

### 5.3 AI Stack (Agent Pipeline)

- **Trigger:** Every 3h via n8n Agent Orchestration Cron OR real-time on inbound SMS (webhooks.py)
- **8 Claude calls per contact:**

```
Contact Profile + Events + Communication History + Menu
          │
          ▼
   Layer 1 — Observer (4 parallel calls)
   ┌──────────┐ ┌───────────┐ ┌────────┐ ┌────────────┐
   │  Menu    │ │ Sentiment │ │ Intent │ │ Engagement │
   │  (Haiku) │ │  (Haiku)  │ │(Sonnet)│ │  (Haiku)   │
   └────┬─────┘ └─────┬─────┘ └───┬────┘ └─────┬──────┘
        └─────────────┴───────────┴─────────────┘
                            │
                            ▼  contact_observations
   Layer 2 — Advisor (4 parallel calls)
   ┌───────┐ ┌─────────┐ ┌──────────┐ ┌────────────┐
   │ Stage │ │ Channel │ │  Offer   │ │ Escalation │
   │(Haiku)│ │ (Haiku) │ │ (Sonnet) │ │  (Sonnet)  │
   └───┬───┘ └────┬────┘ └────┬─────┘ └─────┬──────┘
       └──────────┴───────────┴─────────────┘
                            │
                            ▼  action_plans
   Layer 3 — Orchestrator (1 Sonnet call)
   [All Layer 2 outputs + latest delivery event + recent actions]
                            │
                            ▼  orchestrator_log
                      action_queue (one action)
   send_sms | move_campaign | escalate_airtable | none
```

---

## 6. n8n Integration

n8n is the **execution and integration mesh** — it does not contain business logic. All logic lives in FastAPI and PostgreSQL.

### 6.1 How n8n Authenticates

All workflows call `/api/credentials/` with `X-Admin-Secret` on startup, then use the returned keys for subsequent calls to Telnyx, Instantly, Airtable etc. No secrets in workflow JSON.

### 6.2 Workflow Groups

| Group | Workflows | Frequency |
|-------|-----------|-----------|
| Intelligence | Intelligence Cron, Stage Runner, Agent Orchestration, Hourly Cycle | Hourly / 3h |
| Order Intake | Daily Order Upload, Shipday Collector, Feedback Sync | Daily / hourly |
| SMS | Telnyx Inbound Collector, SMS Dispatch | Continuous / on-demand |
| Broadcast | Broadcast Dispatch | On-demand |
| Email Campaigns | Instantly Sync, Campaign Stats, Action Queue Executor | Hourly / on-demand |
| Chatbot | Docs Reindex, Marketing Query Form | Daily / on-demand |
| Field Agent | Daily Field Brief, Outcome Sync | Daily 7:30 AM |
| Reports | Daily Activity, Daily Outcome | Daily morning |
| Growth | Goal Agent Cycle, Growth Cycle, Competitor Agent | Daily / weekly |
| System | Feature Tests (5 AM), Connectivity Check (manual) | Daily / manual |

---

## 7. Claude AI Pipeline Design

### 7.1 Model Routing

| Agent | Model | Reason |
|-------|-------|--------|
| Menu, Sentiment, Engagement, Stage, Channel | `claude-haiku-4-5-20251001` | Fast classification, low cost |
| Intent, Offer, Escalation, Orchestrator | `claude-sonnet-4-6` | Complex reasoning, copy generation |
| Report agents | `claude-sonnet-4-6` | Narrative generation |
| Growth, Goal, Competitor agents | `claude-sonnet-4-6` | Strategy and hypothesis generation |

### 7.2 Prompt Caching Strategy

- All agent system prompts sent as `cache_control: ephemeral` blocks
- Static prefix (role + playbook rules) identical across contacts → 90%+ cache hit from contact #2
- Playbook SHA-256 hash: DB re-queried only when `agent_playbook` content changes

### 7.3 Playbook RAG

Each agent receives only its relevant playbook categories:
- Observer agents: `exclusion` + `priority` + `observer`
- Advisor agents: `exclusion` + `priority` + `advisor` + `messaging`
- Orchestrator: `exclusion` + `priority` only

### 7.4 Delivery-Aware Guardrails

| Delivery event | Behaviour |
|---------------|-----------|
| `delivered` | 4h threading.Timer delay → then run AI cycle |
| `delivery_failed` / `delivery_returned` | Immediate `escalate_airtable` urgency=high |
| `out_for_delivery` / `driver_assigned` | Force `none` — never interrupt in-flight order |

---

## 8. MCP Server

- **Protocol:** FastMCP (Python)
- **Location:** `mcp_server/`
- **Purpose:** Exposes PostgreSQL data to Claude Desktop for operational queries
- **DB access:** Direct Postgres connection — does NOT call FastAPI
- **35+ tools** across groups: contacts, analytics, communications, recommendations, opportunities, agents, Shipday, Instantly

---

## 9. Deployment & CI/CD

```
git push main
      │
      ├─► GitHub Actions: sync n8n workflows to hosted instance
      │
      └─► Render: auto-deploy
                │
                ├─► pip install -r requirements.txt
                ├─► scripts/render_build.sh
                │       └─► run all migrations/*.sql (idempotent)
                └─► uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | Yes | PostgreSQL connection (Supabase pooler) |
| `ANTHROPIC_API_KEY` | Yes | Claude agent calls |
| `TELNYX_API_KEY` | Yes | SMS/voice |
| `AIRTABLE_API_KEY` | Yes | CRM + playbook sync |
| `AIRTABLE_BASE_ID` | Yes | `appuy2VTIao6XVpIW` |
| `SHIPDAY_API_KEY` | Yes | Delivery tracking |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | Yes | Report emails |
| `ADMIN_SECRET` | Yes | Admin endpoint protection |
| `INSTANTLY_API_KEY` | No | Instantly campaigns |
| `N8N_API_KEY` | No | n8n API sync |
| `REPORT_EMAIL_TO` | No | Report recipient (default: `core@dabbahwala.com`) |
| `LOG_LEVEL` | No | Logging verbosity (default: INFO) |

---

## 10. Project File Structure

```
bmad-dabbahwala/
├── app/
│   ├── main.py              # FastAPI app, startup, middleware, router registration
│   ├── db.py                # Connection pool, get_cursor() context manager
│   ├── config.py            # Settings from env
│   ├── models.py            # Pydantic request/response models
│   ├── routers/             # 29 router modules (one per domain)
│   └── services/            # Shared services (llm_service, airtable_sync, drive, test_harness)
├── migrations/              # SQL migration files (numbered, idempotent)
├── n8n/                     # n8n workflow JSON files (27 workflows)
├── mcp_server/              # FastMCP server + tool definitions
│   ├── server.py
│   └── tools/
├── tests/                   # Pytest suite (one file per router domain)
├── scripts/
│   ├── render_build.sh      # Render deploy script
│   └── run_migrations.sh    # Local migration runner
├── data/                    # Sample/seed data files
├── campaigns/               # Instantly campaign JSON definitions
├── Procfile                 # Render start command
├── requirements.txt
├── requirements-dev.txt
└── pytest.ini
```
