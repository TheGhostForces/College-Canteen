import resend
from settings import API_FOR_SENDER, SENDER_EMAIL

resend.api_key = API_FOR_SENDER
#    onboarding@resend.dev       for dev
def send_code_to_email(email: str, code: int):
    resend.Emails.send({
        "from": f"Verification <{SENDER_EMAIL}>",
        "to": email,
        "subject": f"Код подтверждения: {code}",
        "html": f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Код подтверждения</h2>
            <p>Ваш код для входа в систему:</p>
            <div style="background: #f4f4f4; padding: 20px; 
                      font-size: 32px; font-weight: bold; 
                      text-align: center; margin: 20px 0;">
                {code}
            </div>
            <p>Код действителен 10 минут.</p>
            <p style="color: #666; font-size: 12px;">
                Если вы не запрашивали этот код, проигнорируйте это письмо.
            </p>
        </body>
        </html>
        """
    })