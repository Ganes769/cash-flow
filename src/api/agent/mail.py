import os

import httpx
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = (os.getenv("RESEND_API_KEY") or "").strip()
MAIL_FROM = (os.getenv("MAIL_FROM") or "").strip()


class MailNotConfiguredError(RuntimeError):
    pass


class MailDeliveryError(RuntimeError):
    pass


def send_collection_email(to: str, subject: str, body: str) -> str:
    if not RESEND_API_KEY or not MAIL_FROM:
        raise MailNotConfiguredError(
            "Set RESEND_API_KEY and MAIL_FROM before sending email."
        )

    response = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={
            "from": MAIL_FROM,
            "to": [to],
            "subject": subject,
            "text": body,
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise MailDeliveryError(
            f"Resend rejected the email ({response.status_code})."
        )
    payload = response.json()
    message_id = payload.get("id")
    if not message_id:
        raise MailDeliveryError("Resend did not return a message id.")
    return str(message_id)
