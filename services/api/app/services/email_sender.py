import base64
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import structlog

from ..utils.encryption import decrypt_oauth_token, encrypt_oauth_token

logger = structlog.get_logger()


@dataclass
class SendResult:
    success: bool
    message_id: str | None = None
    thread_id: str | None = None
    error: str | None = None


class EmailSender:
    async def send_gmail(
        self,
        user_id,
        user_email: str,
        gmail_oauth_token: str | None,
        to_email: str,
        subject: str,
        body: str,
        attachment: tuple[str, bytes] | None = None,
    ) -> SendResult:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google.auth.exceptions import RefreshError
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from ..config import settings
        from supabase import create_client

        token_data = decrypt_oauth_token(gmail_oauth_token)
        if not token_data:
            return SendResult(success=False, error="token_expired")

        creds = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        )

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                new_token = {
                    "access_token": creds.token,
                    "refresh_token": creds.refresh_token,
                }
                sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
                sb.table("user_profiles").update(
                    {"gmail_oauth_token": encrypt_oauth_token(new_token)}
                ).eq("user_id", str(user_id)).execute()
            except RefreshError:
                return SendResult(success=False, error="token_expired")

        message = MIMEMultipart()
        message["to"] = to_email
        message["from"] = user_email
        message["subject"] = subject
        message.attach(MIMEText(body, "plain"))

        if attachment:
            filename, pdf_bytes = attachment
            att = MIMEBase("application", "pdf")
            att.set_payload(pdf_bytes)
            encoders.encode_base64(att)
            att.add_header("Content-Disposition", f"attachment; filename={filename}")
            message.attach(att)

        service = build("gmail", "v1", credentials=creds)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        try:
            sent = service.users().messages().send(
                userId="me",
                body={"raw": raw},
            ).execute()
            return SendResult(
                success=True,
                message_id=sent["id"],
                thread_id=sent.get("threadId"),
            )
        except HttpError as e:
            if e.resp.status == 429:
                return SendResult(success=False, error="rate_limited")
            return SendResult(success=False, error=f"send_failed: {str(e)}")

    async def send_outlook(
        self,
        user_id,
        user_email: str,
        outlook_oauth_token: str | None,
        to_email: str,
        subject: str,
        body: str,
        attachment: tuple[str, bytes] | None = None,
    ) -> SendResult:
        import httpx
        from ..utils.encryption import decrypt_oauth_token
        from ..config import settings

        token_data = decrypt_oauth_token(outlook_oauth_token)
        if not token_data:
            return SendResult(success=False, error="token_expired")

        access_token = token_data.get("access_token")

        payload: dict = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to_email}}],
            },
            "saveToSentItems": True,
        }

        if attachment:
            filename, pdf_bytes = attachment
            payload["message"]["attachments"] = [{
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentBytes": base64.b64encode(pdf_bytes).decode(),
                "contentType": "application/pdf",
            }]

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    "https://graph.microsoft.com/v1.0/me/sendMail",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=payload,
                )
                if resp.status_code == 202:
                    return SendResult(success=True)
                if resp.status_code == 429:
                    return SendResult(success=False, error="rate_limited")
                return SendResult(success=False, error=f"send_failed: {resp.text}")
            except Exception as e:
                return SendResult(success=False, error=f"send_failed: {str(e)}")


email_sender = EmailSender()
