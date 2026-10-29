from types import SimpleNamespace
from unittest.mock import MagicMock

import alerting

CONTEXT = {
    "task_instance": SimpleNamespace(dag_id="d", task_id="t", try_number=4),
    "dag_run": SimpleNamespace(run_id="manual__x", logical_date=None),
    "exception": RuntimeError("boom"),
}


def test_message_has_what_the_reader_needs_to_find_the_failure():
    msg = alerting.build_failure_message(CONTEXT)

    body = msg.get_content()
    assert "d.t" in msg["Subject"]
    assert "manual__x" in body and "RuntimeError: boom" in body and "4" in body


def test_send_logs_in_with_env_and_never_puts_the_password_in_the_message(monkeypatch):
    env = {
        "ALERT_SMTP_HOST": "smtp.example.com", "ALERT_SMTP_PORT": "587", "ALERT_SMTP_USER": "u",
        "ALERT_SMTP_PASSWORD": "secret-pw", "ALERT_EMAIL_FROM": "f@example.com", "ALERT_EMAIL_TO": "t@example.com",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    smtp = MagicMock()
    monkeypatch.setattr(alerting.smtplib, "SMTP", lambda *a, **k: smtp)
    smtp.__enter__.return_value = smtp

    alerting.send_failure_email(CONTEXT)

    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("u", "secret-pw")
    sent = smtp.send_message.call_args.args[0]
    assert sent["To"] == "t@example.com"
    assert "secret-pw" not in sent.as_string()
