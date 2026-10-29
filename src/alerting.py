import os
import smtplib
from email.message import EmailMessage


def build_failure_message(context) -> EmailMessage:
    ti = context["task_instance"]
    run = context["dag_run"]
    exception = context.get("exception")

    msg = EmailMessage()
    msg["Subject"] = f"[Airflow] 최종 실패: {ti.dag_id}.{ti.task_id}"
    msg.set_content(
        "\n".join(
            [
                f"DAG: {ti.dag_id}",
                f"task: {ti.task_id}",
                f"run_id: {run.run_id}",
                f"logical_date: {run.logical_date}",
                f"시도 횟수: {ti.try_number}",
                f"예외: {type(exception).__name__}: {exception}" if exception else "예외: (없음)",
            ]
        )
    )
    return msg


def send_failure_email(context) -> None:
    """task가 재시도를 모두 쓰고 최종 실패했을 때 on_failure_callback으로 호출한다."""
    msg = build_failure_message(context)
    msg["From"] = os.environ["ALERT_EMAIL_FROM"]
    msg["To"] = os.environ["ALERT_EMAIL_TO"]

    with smtplib.SMTP(os.environ["ALERT_SMTP_HOST"], int(os.environ["ALERT_SMTP_PORT"]), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.environ["ALERT_SMTP_USER"], os.environ["ALERT_SMTP_PASSWORD"])
        smtp.send_message(msg)
