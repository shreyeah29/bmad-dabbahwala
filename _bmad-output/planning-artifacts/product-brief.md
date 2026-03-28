# DabbahWala — Product Brief
**BMAD Phase 1 | Version 1.0 | 2026-03-28**

---

## 1. What Is DabbahWala

**DabbahWala** is an automated marketing and operations backend for a fresh Indian food delivery business in Atlanta. It is not a storefront — it is the intelligence and execution layer that sits behind the business: ingesting signals from orders, SMS, email, and delivery; deciding who to contact, when, and how; and executing that outreach reliably across multiple channels.

---

## 2. Problem

Running a food delivery business with real retention and growth requires consistent, timely, personalised follow-up across SMS, email, and field sales. Doing that manually — or with disconnected tools — creates gaps: leads go cold, lapsed customers never come back, and nobody knows what worked.

The business needs one system that:
- Knows where every contact is in their journey
- Figures out who needs attention right now
- Decides the right message and channel for each person
- Executes and tracks everything automatically

---

## 3. Solution

A single FastAPI backend that unifies three cooperating engines:

| Engine | What it does |
|--------|-------------|
| **Stage Engine** | SQL rules classify every contact into a lifecycle segment and route them to the correct email campaign. Runs hourly. |
| **Contact Sweep** | Five-phase signal scanner that finds contacts ready for action and creates opportunities. Runs hourly. No AI. |
| **AI Stack** | Multi-layer Claude pipeline (Observer → Advisor → Orchestrator) that produces one concrete outreach action per contact. Runs every 3 hours + real-time on inbound SMS. |

All three share one PostgreSQL database. n8n sits alongside as the scheduled execution mesh — polling, dispatching SMS/email, syncing Airtable and menus, and delivering reports.

---

## 4. Personas

| Persona | What they need |
|---------|---------------|
| **Marketing Operator** | Campaigns, contacts, broadcasts, playbook rules, menu, daily reports |
| **Field Agent** | Daily call brief (top 10 contacts), outcome logging, Airtable task management |
| **Admin** | Deploy, migrations, credentials, n8n schedules, E2E test suite |
| **Analytics / Growth User** | Free-form data queries, AI pipeline visibility, experiment tracking, competitor research |
| **Customer** | Personalised SMS/email at the right time, easy opt-out, order confirmations, delivery updates |

---

## 5. Channels and Integrations

| System | Role |
|--------|------|
| **Telnyx** | SMS and voice — inbound/outbound, STOP handling |
| **Instantly** | Email campaigns — lifecycle-mapped sequences, open/click/reply events |
| **Shipday** | Delivery tracking — order ingestion, status webhooks, feedback |
| **Airtable** | CRM-adjacent — menu catalog (source of truth), playbook rules, field task management |
| **Anthropic Claude** | AI agent pipeline (Haiku for fast classifiers, Sonnet for reasoning) |
| **Google Drive / Docs** | Team content sync for chatbot RAG index |
| **Gmail SMTP** | Report delivery via n8n |
| **n8n** | Scheduled automation mesh — polls, dispatches, syncs, reports |

---

## 6. Lifecycle Segments

Every contact is always in exactly one of eight segments:

`cold` · `engaged` · `active_customer` · `new_customer` · `lapsed_customer` · `reactivation_candidate` · `cooling` · `optout`

Segment determines which Instantly email campaign the contact belongs to. The Stage Engine moves contacts between segments based on SQL rules applied to their order history and engagement.

---

## 7. AI Pipeline (The Core)

Eight Claude calls per contact per cycle:

- **Layer 1 (Observer — 4 calls):** Menu picks, sentiment, intent, engagement score
- **Layer 2 (Advisor — 4 calls):** Recommended stage, channel, offer copy, escalation flag
- **Layer 3 (Orchestrator — 1 call):** Reads all Layer 2 outputs + delivery context → produces exactly one action: `send_sms`, `move_campaign`, `escalate_airtable`, or `none`

The action goes into `action_queue`. n8n picks it up and executes it.

Guardrails baked in:
- Max 1 contact per 24h on same channel
- Max 3 SMS per week per contact
- Escalation always beats automation
- `do_not_contact` is absolute
- Delivery-aware delays (4h after `delivered` before any outreach)

---

## 8. What Success Looks Like

| Area | Metric |
|------|--------|
| Acquisition | Cold lead → first order conversion |
| Retention | Repeat order rate; segment migration active ↔ lapsed |
| Execution | Action queue latency and completion rate |
| Operations | Zero silent failures; alerts before business hours |
| Field | Task completion rate; outcome logging coverage |

---

## 9. Scope (Backend Only — Phase 1)

**In scope:** FastAPI backend, PostgreSQL schema, Claude agent pipeline, n8n workflow definitions, MCP server (Claude Desktop), E2E test harness.

**Out of scope (Phase 1):** Next.js frontend (`dabbahwala-ui`), consumer mobile app, in-kitchen POS, pricing strategy.
