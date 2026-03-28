# DabbahWala n8n Workflows

All workflows call the FastAPI backend at `https://dabbahwala-latest.onrender.com`.

## Workflow Inventory

### Core Automation (Story 26.1)
| File | Trigger | Description |
|------|---------|-------------|
| `daily_agent_sweep.json` | Cron: 8am daily | Run agent cycle for all active contacts |
| `lapsed_reactivation.json` | Cron: Mon 9am | Run agent cycle for all lapsed contacts |
| `inbound_sms_handler.json` | Webhook | Relay inbound SMS → telnyx message endpoint |
| `order_delivered_followup.json` | Webhook: Shipday | Trigger agent cycle 4h after delivery |

### Data Sync (Story 26.2)
| File | Trigger | Description |
|------|---------|-------------|
| `shipday_order_sync.json` | Cron: every 2h | Ingest new orders from Shipday |
| `airtable_menu_sync.json` | Cron: daily 6am | Sync menu catalog from Airtable |
| `airtable_playbook_sync.json` | Cron: daily 6am | Sync playbook rules from Airtable |
| `airtable_content_sync.json` | Cron: daily 6am | Sync team content from Airtable |
| `instantly_campaign_sync.json` | Cron: daily 7am | Sync campaign routing from Instantly |

### Reporting & Field (Story 26.3)
| File | Trigger | Description |
|------|---------|-------------|
| `daily_report_email.json` | Cron: 7am daily | Generate + email daily report |
| `weekly_report_email.json` | Cron: Mon 7am | Generate + email weekly summary |
| `field_brief_delivery.json` | Cron: 8am daily | Send daily call brief to field agents |

### Growth & System (Story 26.4)
| File | Trigger | Description |
|------|---------|-------------|
| `growth_analysis_weekly.json` | Cron: Mon 9am | Run AI growth analysis + log |
| `broadcast_scheduler.json` | Cron: every 15m | Dispatch any scheduled broadcasts |
| `action_queue_processor.json` | Cron: every 5m | Process pending action_queue items |

### CI/CD (Story 26.5)
| File | Description |
|------|-------------|
| `cicd_sync.sh` | Shell script to import all workflows to n8n via API |

## Deployment
Run `bash n8n_workflows/cicd_sync.sh` after any workflow update to push to n8n instance.
