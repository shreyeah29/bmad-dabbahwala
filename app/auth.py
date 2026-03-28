import logging
import os
import secrets
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory session store: session_id -> {"email": ..., "name": ...}
_sessions: dict[str, dict] = {}

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

_LOGIN_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>DabbahWala — Login</title>
  <style>
    body { font-family: sans-serif; display: flex; align-items: center;
           justify-content: center; height: 100vh; margin: 0; background: #f5f5f5; }
    .card { background: white; padding: 2rem 3rem; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,.1); text-align: center; }
    a.btn { display: inline-block; margin-top: 1rem; padding: .75rem 1.5rem;
            background: #4285F4; color: white; text-decoration: none;
            border-radius: 4px; font-size: 1rem; }
  </style>
</head>
<body>
  <div class="card">
    <h1>DabbahWala</h1>
    <p>Marketing Operations Dashboard</p>
    <a class="btn" href="/auth/google">Sign in with Google</a>
  </div>
</body>
</html>"""


@router.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(content=_LOGIN_HTML)


@router.get("/auth/google")
def google_redirect():
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{_GOOGLE_AUTH_URL}?{query}")


@router.get("/auth/callback")
async def google_callback(request: Request, code: str = ""):
    if not code:
        return RedirectResponse(url="/login")

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_resp = await client.post(_GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
        if token_resp.status_code != 200:
            logger.warning("Google token exchange failed: %s", token_resp.text[:200])
            return RedirectResponse(url="/login")

        access_token = token_resp.json().get("access_token", "")

        # Fetch user info
        userinfo_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            logger.warning("Google userinfo fetch failed: %s", userinfo_resp.text[:200])
            return RedirectResponse(url="/login")

        userinfo = userinfo_resp.json()

    email: str = userinfo.get("email", "")
    if not email.endswith(f"@{settings.allowed_domain}"):
        logger.warning("Login rejected — domain not allowed: %s", email)
        return JSONResponse(
            status_code=403,
            content={"detail": f"Only @{settings.allowed_domain} accounts are allowed"},
        )

    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = {"email": email, "name": userinfo.get("name", "")}
    logger.info("Session created for %s", email)

    response = RedirectResponse(url="/dashboard")
    response.set_cookie("session_id", session_id, httponly=True, samesite="lax")
    return response


@router.get("/auth/logout")
def logout(request: Request):
    session_id = request.cookies.get("session_id", "")
    _sessions.pop(session_id, None)
    response = RedirectResponse(url="/login")
    response.delete_cookie("session_id")
    return response


def get_current_user(request: Request) -> Optional[dict]:
    """Return session dict for the current request, or None if not authenticated."""
    session_id = request.cookies.get("session_id", "")
    return _sessions.get(session_id)


@router.get("/auth/me")
def auth_me(request: Request):
    user = get_current_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return {"email": user["email"], "name": user["name"]}


_DASHBOARD_HTML = os.path.join(os.path.dirname(__file__), "dashboard.html")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    if get_current_user(request) is None:
        return RedirectResponse(url="/login")
    return FileResponse(_DASHBOARD_HTML, media_type="text/html")
