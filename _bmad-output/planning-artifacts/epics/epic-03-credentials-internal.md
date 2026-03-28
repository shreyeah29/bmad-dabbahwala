# Epic 3: Credentials & Internal Services

**Layer:** 0 — Foundation
**FRs:** FR-CRED-01 to FR-CRED-04
**Depends on:** E01
**Status:** backlog

## Goal
Single endpoint for n8n to bootstrap its runtime API keys. SMTP proxy, Google Drive, and Google Docs access for n8n workflows.

---

## Stories

### Story 3.1: Credentials Bootstrap Endpoint
`GET /api/credentials/` — returns all runtime API keys and config as JSON; requires `X-Admin-Secret` header. Used by n8n workflows to fetch keys at startup without hardcoding secrets in workflow JSON.

**Acceptance Criteria:**
- Returns 403 if `X-Admin-Secret` header missing or wrong
- Returns JSON object with all configured API keys
- Keys read from env vars at request time (not cached)
- Logged at INFO on each call (redacted values)

---

### Story 3.2: SMTP Email Proxy
`POST /api/internal/send-email` — accepts `{to, subject, body_html, body_text}` and sends via SMTP. Used by n8n for report delivery and operational alerts.

**Acceptance Criteria:**
- Sends email using `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` env vars
- Accepts both HTML and plain text body
- Returns `{"status":"ok"}` on success or error detail on failure
- `REPORT_EMAIL_TO` used as default recipient if `to` not specified

---

### Story 3.3: Google Drive Integration
`POST /api/internal/drive/upload` — upload a file to Google Drive.
`GET /api/internal/drive/files` — list files in configured Drive folder.

**Acceptance Criteria:**
- Upload accepts filename + content; returns Drive file ID
- List returns `[{id, name, modified_at}]`
- Uses Google Drive OAuth2 (credentials from env)
- Used by n8n for CSV template distribution

---

### Story 3.4: Google Docs Reader
`GET /api/internal/docs/{doc_id}` — fetch the text content of a Google Doc by ID.

**Acceptance Criteria:**
- Returns `{"doc_id": ..., "content": "..."}` with full text
- Returns 404 if doc not found
- Used by n8n chatbot reindex workflow

---
