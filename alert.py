"""異常時にGmail経由でアラートメールを送る。

健康ボット(notifier.py)と同じ GMAIL_ADDRESS / GMAIL_APP_PASSWORD / GMAIL_TO を再利用する。
アラート送信自体の失敗でスクリプトを止めたくないため、例外は投げずFalseを返す。
"""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send_alert(subject: str, body: str) -> bool:
    address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    to_address = os.environ.get("GMAIL_TO") or address
    if not address or not app_password:
        return False

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = f"[MOT異常通知] {subject}"
    msg["From"] = address
    msg["To"] = to_address

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(address, app_password)
            server.sendmail(address, [to_address], msg.as_string())
        return True
    except Exception:
        return False
