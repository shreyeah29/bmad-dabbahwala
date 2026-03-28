# Story 3.3 — Google Drive Integration

**Epic:** E03 Credentials & Internal Services
**Status:** done
**Created:** 2026-03-28

---

## What to build

- `POST /api/internal/drive/upload` — upload file to Google Drive, returns file ID
- `GET /api/internal/drive/files` — list files in configured Drive folder

## Files modified

- `app/routers/internal.py` — added Drive upload/list endpoints + `_get_drive_token()`
- `app/config.py` — added `google_drive_refresh_token`, `google_drive_folder_id`
- `tests/test_drive.py` — new: 7 tests

## Acceptance Criteria

- [x] Upload accepts filename + content; returns Drive file ID
- [x] List returns `[{id, name, modified_at}]`
- [x] Token failure returns 500
- [x] API error returns 500
- [x] All tests pass
