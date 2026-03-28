import logging
import os

logger = logging.getLogger(__name__)

# Required env vars — app will warn at startup if any are missing
_REQUIRED = [
    "DATABASE_URL",
    "ANTHROPIC_API_KEY",
    "TELNYX_API_KEY",
    "AIRTABLE_API_KEY",
    "AIRTABLE_BASE_ID",
    "SHIPDAY_API_KEY",
    "SMTP_HOST",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "ADMIN_SECRET",
]


class Settings:
    """
    Single source of truth for all runtime configuration.
    Reads from environment variables at instantiation time.
    Missing required vars are warned (not raised) — the app starts and
    fails at the call site where the missing value is first used.
    """

    # ── Required ──────────────────────────────────────────────────────────────
    database_url: str
    anthropic_api_key: str
    telnyx_api_key: str
    airtable_api_key: str
    airtable_base_id: str
    shipday_api_key: str
    smtp_host: str
    smtp_user: str
    smtp_password: str
    admin_secret: str

    # ── Optional ──────────────────────────────────────────────────────────────
    instantly_api_key: str
    n8n_api_key: str
    report_email_to: str
    log_level: str
    allowed_domain: str

    def __init__(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL", "")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.telnyx_api_key = os.environ.get("TELNYX_API_KEY", "")
        self.airtable_api_key = os.environ.get("AIRTABLE_API_KEY", "")
        self.airtable_base_id = os.environ.get("AIRTABLE_BASE_ID", "")
        self.shipday_api_key = os.environ.get("SHIPDAY_API_KEY", "")
        self.smtp_host = os.environ.get("SMTP_HOST", "")
        self.smtp_user = os.environ.get("SMTP_USER", "")
        self.smtp_password = os.environ.get("SMTP_PASSWORD", "")
        self.admin_secret = os.environ.get("ADMIN_SECRET", "")

        self.instantly_api_key = os.environ.get("INSTANTLY_API_KEY", "")
        self.n8n_api_key = os.environ.get("N8N_API_KEY", "")
        self.report_email_to = os.environ.get("REPORT_EMAIL_TO", "core@dabbahwala.com")
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.allowed_domain = os.environ.get("ALLOWED_DOMAIN", "dabbahwala.com")

        self._warn_missing()

    def _warn_missing(self) -> None:
        missing = [
            var for var in _REQUIRED
            if not getattr(self, var.lower(), None)
        ]
        if missing:
            logger.warning(
                "Missing required env vars: %s — app will fail when these are first used",
                ", ".join(missing),
            )


settings = Settings()
