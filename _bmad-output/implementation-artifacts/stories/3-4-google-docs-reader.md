# Story 3.4 — Google Docs Reader

**Epic:** E03 Credentials & Internal Services
**Status:** done
**Created:** 2026-03-28

---

## What to build

`GET /api/internal/docs/{doc_id}` — fetch text content of a Google Doc by ID.

## Files modified

- `app/routers/internal.py` — added Docs reader endpoint + `_get_docs_token()` + `_extract_doc_text()`
- `app/config.py` — added `google_docs_refresh_token`
- `tests/test_docs.py` — new: 7 tests (3 unit + 4 endpoint)

## Acceptance Criteria

- [x] Returns `{"doc_id": ..., "content": "..."}` with full text
- [x] Returns 404 if doc not found
- [x] Token failure returns 500
- [x] All tests pass
