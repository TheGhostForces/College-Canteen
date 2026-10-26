import logging
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import mailer


def settings(**kwargs):
    return Settings(postgres_password="test", secret_key="x" * 32, _env_file=None, **kwargs)


def test_console_backend_logs_code_without_sending(monkeypatch, caplog):
    monkeypatch.setattr(mailer, "get_settings", lambda: settings(mail_backend="console"))
    send = Mock()
    monkeypatch.setattr(mailer.resend.Emails, "send", send)

    with caplog.at_level(logging.WARNING, logger="canteen.mailer"):
        mailer.send_login_code("student@example.com", "123456")

    assert "LOCAL LOGIN CODE | student@example.com | 123456" in caplog.text
    send.assert_not_called()


def test_resend_is_default_and_does_not_log_code(monkeypatch, caplog):
    config = settings(resend_api_key=None, mail_from=None)
    assert config.mail_backend == "resend"
    monkeypatch.setattr(mailer, "get_settings", lambda: config)

    with pytest.raises(RuntimeError, match="Email sender is not configured"):
        mailer.send_login_code("student@example.com", "123456")

    assert "123456" not in caplog.text


def test_resend_sends_email(monkeypatch, caplog):
    monkeypatch.setattr(
        mailer,
        "get_settings",
        lambda: settings(mail_backend="resend", resend_api_key="test-key", mail_from="test@example.com"),
    )
    send = Mock()
    monkeypatch.setattr(mailer.resend.Emails, "send", send)
    monkeypatch.setattr(mailer.resend, "api_key", None)

    mailer.send_login_code("student@example.com", "123456")

    send.assert_called_once()
    assert send.call_args.args[0]["to"] == "student@example.com"
    assert "123456" in send.call_args.args[0]["html"]
    assert "123456" not in caplog.text


def test_unknown_mail_backend_is_rejected():
    with pytest.raises(ValidationError):
        settings(mail_backend="invalid")
