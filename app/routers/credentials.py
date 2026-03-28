import logging

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


def _check_admin_header(x_admin_secret: str) -> bool:
    return bool(settings.admin_secret) and x_admin_secret == settings.admin_secret


@router.get("/")
def get_credentials(x_admin_secret: str = Header(default="")):
    if not _check_admin_header(x_admin_secret):
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    logger.info(
        "Credentials fetched — keys: DATABASE_URL=%s ANTHROPIC=%s TELNYX=%s "
        "AIRTABLE=%s SHIPDAY=%s INSTANTLY=%s N8N=%s SMTP=%s",
        "set" if settings.database_url else "unset",
        "set" if settings.anthropic_api_key else "unset",
        "set" if settings.telnyx_api_key else "unset",
        "set" if settings.airtable_api_key else "unset",
        "set" if settings.shipday_api_key else "unset",
        "set" if settings.instantly_api_key else "unset",
        "set" if settings.n8n_api_key else "unset",
        "set" if settings.smtp_host else "unset",
    )

    return {
        "database_url": settings.database_url,
        "anthropic_api_key": settings.anthropic_api_key,
        "telnyx_api_key": settings.telnyx_api_key,
        "airtable_api_key": settings.airtable_api_key,
        "airtable_base_id": settings.airtable_base_id,
        "shipday_api_key": settings.shipday_api_key,
        "instantly_api_key": settings.instantly_api_key,
        "n8n_api_key": settings.n8n_api_key,
        "smtp_host": settings.smtp_host,
        "smtp_user": settings.smtp_user,
        "smtp_password": settings.smtp_password,
        "report_email_to": settings.report_email_to,
        "allowed_domain": settings.allowed_domain,
        "google_client_id": settings.google_client_id,
        "google_client_secret": settings.google_client_secret,
        "google_redirect_uri": settings.google_redirect_uri,
    }
