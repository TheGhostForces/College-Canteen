"""Отправка писем через Resend."""

import resend

from app.core.config import get_settings


def send_login_code(email: str, code: str) -> None:
    """Синхронная отправка; из async-кода вызывать через asyncio.to_thread."""
    settings = get_settings()
    if settings.resend_api_key is None or not settings.mail_from:
        raise RuntimeError("Email sender is not configured (RESEND_API_KEY / MAIL_FROM)")

    resend.api_key = settings.resend_api_key.get_secret_value()
    resend.Emails.send(
        {
            "from": f"Verification <{settings.mail_from}>",
            "to": email,
            "subject": f"Код подтверждения: {code}",
            "html": f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Код подтверждения</h2>
                <p>Ваш код для входа в систему:</p>
                <div style="background: #f4f4f4; padding: 20px; font-size: 32px;
                            font-weight: bold; text-align: center; margin: 20px 0;">
                    {code}
                </div>
                <p>Код действителен {settings.login_code_ttl_minutes} минут.</p>
                <p style="color: #666; font-size: 12px;">
                    Если вы не запрашивали этот код, проигнорируйте это письмо.
                </p>
            </body>
            </html>
            """,
        }
    )
