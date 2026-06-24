import aiosmtplib
from email.message import EmailMessage
from app.core.config import settings
from app.core.logging import logger


async def send_password_reset_email(to_email: str, full_name: str, reset_token: str) -> bool:
    """
    Sends a password reset email containing a link back to the frontend's
    reset-password page with the token as a query parameter.
    """
    reset_link = f"{settings.APP_URL}/reset-password?token={reset_token}"

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM or settings.SMTP_USER
    message["To"] = to_email
    message["Subject"] = "Reset your Sample Chain of Custody password"

    message.set_content(
        f"""Hi {full_name},

We received a request to reset your password for Sample Chain of Custody.

Click the link below to set a new password. This link expires in 30 minutes:

{reset_link}

If you didn't request this, you can safely ignore this email — your password will not change.

— Sample Chain of Custody
"""
    )

    message.add_alternative(
        f"""\
<html>
  <body style="font-family: sans-serif; color: #1e293b;">
    <div style="max-width: 480px; margin: 0 auto; padding: 24px;">
      <h2 style="margin-bottom: 8px;">Reset your password</h2>
      <p>Hi {full_name},</p>
      <p>We received a request to reset your password for <strong>Sample Chain of Custody</strong>.</p>
      <p>
        <a href="{reset_link}"
           style="display:inline-block; background:#0f172a; color:#ffffff; text-decoration:none;
                  padding:12px 24px; border-radius:8px; margin: 16px 0;">
          Reset Password
        </a>
      </p>
      <p style="font-size: 13px; color: #64748b;">
        This link expires in 30 minutes. If you didn't request this, you can safely ignore this email.
      </p>
    </div>
  </body>
</html>
""",
        subtype="html",
    )

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send password reset email to {to_email}: {e}")
        return False
