# DabbahWala — Epics Overview
**BMAD Phase 3 | Version 1.0 | 2026-03-28**

---

## Implementation Order

Epics must be implemented in dependency order. Each layer depends on the one before it.

```
LAYER 0 — Foundation
  E01 Platform Bootstrap
  E02 Auth & Dashboard
  E03 Credentials & Internal

LAYER 1 — Data & Events
  E04 Core Data & Events

LAYER 2 — Lifecycle & Intelligence
  E05 Lifecycle & Stage Engine
  E06 Intelligence & Opportunities

LAYER 3 — AI Core
  E07 AI Agent Pipeline
  E08 Single-Agent Tooling

LAYER 4 — Channels
  E09 Telnyx SMS
  E10 Webhooks & Delivery

LAYER 5 — Data Ingestion
  E11 Orders & Shipday
  E12 Daily CSV Orders

LAYER 6 — Campaign Management
  E13 Instantly Campaigns
  E14 Prospects & Contacts
  E15 Broadcasts

LAYER 7 — Content & Rules
  E16 Menu & History
  E17 Playbook Rules
  E18 Team Content

LAYER 8 — Reporting & Intelligence UI
  E19 Reports
  E20 Field Agent
  E21 Chatbot
  E22 Marketing Query

LAYER 9 — Growth Intelligence
  E23 Growth / Goal / Competitor Agents

LAYER 10 — Operations
  E24 Test Harness & Admin Schedules
  E25 MCP Server
  E26 n8n Workflow Suite
```

---

## Epic Summary

| Epic | Name | FRs | Layer |
|------|------|-----|-------|
| E01 | Platform Bootstrap | FR-PLAT-01 to 09 | 0 |
| E02 | Auth & Dashboard | FR-AUTH-01 to 04 | 0 |
| E03 | Credentials & Internal | FR-CRED-01 to 04 | 0 |
| E04 | Core Data & Events | FR-EVT-01 to 03 | 1 |
| E05 | Lifecycle & Stage Engine | FR-LIFE-01 to 05 | 2 |
| E06 | Intelligence & Opportunities | FR-INTEL-01 to 06, FR-OPP-01 to 07 | 2 |
| E07 | AI Agent Pipeline | FR-AGENT-01 to 17 | 3 |
| E08 | Single-Agent Tooling | FR-SA-01 | 3 |
| E09 | Telnyx SMS | FR-SMS-01 to 04 | 4 |
| E10 | Webhooks & Delivery | FR-WH-01 to 06 | 4 |
| E11 | Orders & Shipday | FR-ORD-01 to 06 | 5 |
| E12 | Daily CSV Orders | FR-DAILY-01 | 5 |
| E13 | Instantly Campaigns | FR-CAMP-01 to 08 | 6 |
| E14 | Prospects & Contacts | FR-PROS-01 to 05, FR-CONT-01 to 02 | 6 |
| E15 | Broadcasts | FR-BC-01 to 06 | 6 |
| E16 | Menu & History | FR-MENU-01 to 06 | 7 |
| E17 | Playbook Rules | FR-PB-01 to 05 | 7 |
| E18 | Team Content | FR-TC-01 to 04 | 7 |
| E19 | Reports | FR-REP-01 to 03 | 8 |
| E20 | Field Agent | FR-FA-01 to 07 | 8 |
| E21 | Chatbot | FR-CHAT-01 to 05 | 8 |
| E22 | Marketing Query | FR-QRY-01 to 05 | 8 |
| E23 | Growth / Goal / Competitor | FR-GROW-01 to 04, FR-GOAL-01 to 05, FR-COMP-01 to 03 | 9 |
| E24 | Test Harness & Admin Schedules | FR-TEST-01 to 05, FR-SCH-01 to 02 | 10 |
| E25 | MCP Server | FR-MCP-01 to 04 | 10 |
| E26 | n8n Workflow Suite | FR-N8N-01 to 27 | 10 |

---

## Definition of Done (per Epic)

An epic is complete when:
1. All FR IDs in scope have passing pytest unit tests
2. All affected endpoints return correct responses (manual or harness verified)
3. Relevant SQL migrations are idempotent and numbered correctly
4. No hardcoded secrets
5. Structured logging in place for all new endpoints
6. Test harness group updated (if applicable)
