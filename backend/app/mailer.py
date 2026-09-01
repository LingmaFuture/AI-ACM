import smtplib
from email.message import EmailMessage
from urllib.parse import unquote, urlparse

from .config import settings


def send_verification_email(recipient: str, verification_url: str) -> None:
    if not settings.smtp_url:
        print(f"[AI-ACM] verification for {recipient}: {verification_url}")
        return
    parsed = urlparse(settings.smtp_url)
    host = parsed.hostname
    if not host:
        raise ValueError("SMTP_URL 缺少主机名")
    port = parsed.port or (465 if parsed.scheme == "smtps" else 587)
    message = EmailMessage()
    message["Subject"] = "验证你的 AI-ACM 邮箱"
    message["From"] = unquote(parsed.username or "noreply@aiacm.local")
    message["To"] = recipient
    message.set_content(f"欢迎加入 AI-ACM。请在 24 小时内打开链接完成验证：\n\n{verification_url}")
    smtp_class = smtplib.SMTP_SSL if parsed.scheme == "smtps" else smtplib.SMTP
    with smtp_class(host, port, timeout=15) as client:
        if parsed.scheme != "smtps":
            client.starttls()
        if parsed.username and parsed.password:
            client.login(unquote(parsed.username), unquote(parsed.password))
        client.send_message(message)

