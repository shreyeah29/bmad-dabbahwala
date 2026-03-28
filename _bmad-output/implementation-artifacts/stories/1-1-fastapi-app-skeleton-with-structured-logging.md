# Story 1.1 — FastAPI App Skeleton with Structured Logging

**Epic:** E01 Platform Bootstrap
**Status:** done
**Created:** 2026-03-28

---

## What to build

Create the FastAPI application entry point (`app/main.py`) with:
1. FastAPI instance with title/description/version
2. HTTP request logging middleware — logs every request: method, path, status code, duration ms, client IP
3. Global exception handler — catches all unhandled exceptions, returns JSON `{"detail": "...", "type": "..."}` with 500 status
4. `LOG_LEVEL` env var controls logging verbosity (default INFO)
5. Logging format: `%(asctime)s [%(levelname)s] %(name)s — %(message)s`

## Files to create

- `app/__init__.py` — empty
- `app/main.py` — FastAPI app, middleware, exception handler
- `requirements.txt` — core dependencies
- `requirements-dev.txt` — dev/test dependencies
- `pytest.ini` — pytest config
- `.env.example` — env var template
- `.gitignore`

## Tech constraints

- FastAPI + uvicorn
- Python 3.11+
- No routers registered yet (added in later stories)
- `LOG_LEVEL` read from `os.environ` at startup

## Acceptance Criteria

- [ ] `uvicorn app.main:app` starts without errors
- [ ] Every request logs: method, path, status code, duration ms, client IP
- [ ] Uncaught exceptions return JSON 500 with `detail` and `type` fields
- [ ] `LOG_LEVEL=DEBUG` enables debug logging
- [ ] `GET /` returns 404 (no routes yet — that's correct)
- [ ] pytest passes with the basic test

## Test to write

`tests/__init__.py` + `tests/test_main.py`:
- Test health-like ping (will return 404 — just confirm app boots)
- Test global exception handler returns correct JSON shape
- Test logging middleware doesn't crash on normal requests
