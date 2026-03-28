import importlib
import logging
import os
import pytest


def _reload_settings(env: dict):
    """Reload app.config with a clean env, return fresh Settings instance."""
    import app.config as cfg_module
    original = os.environ.copy()
    os.environ.clear()
    os.environ.update(env)
    try:
        importlib.reload(cfg_module)
        # Return a fresh instance reflecting the reloaded module state
        return cfg_module.Settings()
    finally:
        os.environ.clear()
        os.environ.update(original)


_FULL_ENV = {
    "DATABASE_URL": "postgresql://localhost/test",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "TELNYX_API_KEY": "KEY_test",
    "AIRTABLE_API_KEY": "pat_test",
    "AIRTABLE_BASE_ID": "appTEST",
    "SHIPDAY_API_KEY": "shipday_test",
    "SMTP_HOST": "smtp.example.com",
    "SMTP_USER": "user@example.com",
    "SMTP_PASSWORD": "secret",
    "ADMIN_SECRET": "admin-secret",
}


def test_required_vars_loaded():
    s = _reload_settings(_FULL_ENV)
    assert s.database_url == "postgresql://localhost/test"
    assert s.anthropic_api_key == "sk-ant-test"
    assert s.admin_secret == "admin-secret"
    assert s.airtable_base_id == "appTEST"


def test_optional_vars_default_when_missing():
    s = _reload_settings(_FULL_ENV)
    assert s.instantly_api_key == ""
    assert s.n8n_api_key == ""
    assert s.report_email_to == "core@dabbahwala.com"
    assert s.log_level == "INFO"
    assert s.allowed_domain == "dabbahwala.com"


def test_optional_vars_overridden_by_env():
    env = {**_FULL_ENV, "REPORT_EMAIL_TO": "ops@example.com", "LOG_LEVEL": "DEBUG"}
    s = _reload_settings(env)
    assert s.report_email_to == "ops@example.com"
    assert s.log_level == "DEBUG"


def test_missing_required_vars_logged_as_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app.config"):
        s = _reload_settings({})  # no env vars at all

    assert any("Missing required env vars" in r.message for r in caplog.records)
    # All required vars should appear in the warning
    assert "DATABASE_URL" in caplog.text


def test_no_warning_when_all_required_present(caplog):
    with caplog.at_level(logging.WARNING, logger="app.config"):
        _reload_settings(_FULL_ENV)

    assert not any("Missing required env vars" in r.message for r in caplog.records)


def test_missing_required_does_not_raise():
    """App must not crash on import even with zero env vars."""
    try:
        _reload_settings({})
    except Exception as e:
        pytest.fail(f"Settings() raised unexpectedly: {e}")


def test_module_level_settings_singleton_exists():
    """The module exports a ready-to-use `settings` object."""
    import app.config as cfg
    assert hasattr(cfg, "settings")
    assert hasattr(cfg.settings, "database_url")
    assert hasattr(cfg.settings, "report_email_to")
