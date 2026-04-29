"""Unit tests for EmailSender service (app/services/email_sender.py)."""
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_token(monkeypatch=None) -> str:
    """Return a valid encrypted token for test use."""
    from app.utils.encryption import encrypt_oauth_token

    return encrypt_oauth_token({"access_token": "access-tok", "refresh_token": "refresh-tok"})


class TestGmailSender:
    def _sender(self):
        from app.services.email_sender import EmailSender

        return EmailSender()

    async def test_none_oauth_token_returns_token_expired(self):
        result = await self._sender().send_gmail(
            user_id="uid",
            user_email="sender@test.com",
            gmail_oauth_token=None,
            to_email="recv@test.com",
            subject="Hi",
            body="Body",
        )
        assert result.success is False
        assert result.error == "token_expired"

    async def test_invalid_encrypted_token_returns_token_expired(self):
        result = await self._sender().send_gmail(
            user_id="uid",
            user_email="sender@test.com",
            gmail_oauth_token="not-a-real-fernet-token",
            to_email="recv@test.com",
            subject="Hi",
            body="Body",
        )
        assert result.success is False
        assert result.error == "token_expired"

    async def test_successful_send_returns_message_and_thread_ids(self):
        token = _make_token()
        sender = self._sender()

        mock_creds = MagicMock()
        mock_creds.expired = False

        mock_service = MagicMock()
        mock_service.users().messages().send().execute.return_value = {
            "id": "msg-abc",
            "threadId": "thread-xyz",
        }

        with (
            patch("google.oauth2.credentials.Credentials", return_value=mock_creds),
            patch("googleapiclient.discovery.build", return_value=mock_service),
        ):
            result = await sender.send_gmail(
                user_id="uid",
                user_email="sender@test.com",
                gmail_oauth_token=token,
                to_email="recv@test.com",
                subject="Hello",
                body="Email body",
            )

        assert result.success is True
        assert result.message_id == "msg-abc"
        assert result.thread_id == "thread-xyz"

    async def test_rate_limit_429_returns_rate_limited(self):
        from googleapiclient.errors import HttpError

        token = _make_token()
        sender = self._sender()

        mock_creds = MagicMock()
        mock_creds.expired = False

        mock_http_resp = MagicMock()
        mock_http_resp.status = 429

        mock_service = MagicMock()
        mock_service.users().messages().send().execute.side_effect = HttpError(
            resp=mock_http_resp, content=b"Rate limit exceeded"
        )

        with (
            patch("google.oauth2.credentials.Credentials", return_value=mock_creds),
            patch("googleapiclient.discovery.build", return_value=mock_service),
        ):
            result = await sender.send_gmail(
                user_id="uid",
                user_email="sender@test.com",
                gmail_oauth_token=token,
                to_email="recv@test.com",
                subject="Hello",
                body="Body",
            )

        assert result.success is False
        assert result.error == "rate_limited"

    async def test_non_rate_limit_http_error_returns_send_failed(self):
        from googleapiclient.errors import HttpError

        token = _make_token()
        sender = self._sender()

        mock_creds = MagicMock()
        mock_creds.expired = False

        mock_http_resp = MagicMock()
        mock_http_resp.status = 500

        mock_service = MagicMock()
        mock_service.users().messages().send().execute.side_effect = HttpError(
            resp=mock_http_resp, content=b"Internal error"
        )

        with (
            patch("google.oauth2.credentials.Credentials", return_value=mock_creds),
            patch("googleapiclient.discovery.build", return_value=mock_service),
        ):
            result = await sender.send_gmail(
                user_id="uid",
                user_email="sender@test.com",
                gmail_oauth_token=token,
                to_email="recv@test.com",
                subject="Hello",
                body="Body",
            )

        assert result.success is False
        assert result.error.startswith("send_failed:")

    async def test_expired_token_refresh_failure_returns_token_expired(self):
        from google.auth.exceptions import RefreshError

        token = _make_token()
        sender = self._sender()

        mock_creds = MagicMock()
        mock_creds.expired = True
        mock_creds.refresh_token = "ref-tok"
        mock_creds.refresh.side_effect = RefreshError("token revoked")

        with patch("google.oauth2.credentials.Credentials", return_value=mock_creds):
            result = await sender.send_gmail(
                user_id="uid",
                user_email="sender@test.com",
                gmail_oauth_token=token,
                to_email="recv@test.com",
                subject="Hello",
                body="Body",
            )

        assert result.success is False
        assert result.error == "token_expired"

    async def test_attachment_appended_to_mime(self):
        """Verify that a PDF attachment is added as a MIMEBase part."""
        token = _make_token()
        sender = self._sender()

        mock_creds = MagicMock()
        mock_creds.expired = False

        captured_raw: list[str] = []

        def capture_send(userId, body):
            captured_raw.append(body["raw"])
            return MagicMock()

        mock_service = MagicMock()
        mock_service.users().messages().send.side_effect = lambda **kw: MagicMock(
            execute=lambda: {"id": "msg-1", "threadId": "t-1"}
        )

        import email as email_lib

        decoded_messages: list = []

        real_b64 = base64.urlsafe_b64encode

        def intercept_b64(data):
            encoded = real_b64(data)
            msg = email_lib.message_from_bytes(data)
            decoded_messages.append(msg)
            return encoded

        with (
            patch("google.oauth2.credentials.Credentials", return_value=mock_creds),
            patch("googleapiclient.discovery.build", return_value=mock_service),
            patch("app.services.email_sender.base64.urlsafe_b64encode", side_effect=intercept_b64),
        ):
            await sender.send_gmail(
                user_id="uid",
                user_email="sender@test.com",
                gmail_oauth_token=token,
                to_email="recv@test.com",
                subject="Hello",
                body="Body",
                attachment=("Resume.pdf", b"%PDF-1.4 fake-pdf-content"),
            )

        assert len(decoded_messages) == 1
        parts = decoded_messages[0].get_payload()
        assert any(
            p.get_content_type() == "application/pdf" for p in parts
        ), "Expected a PDF part in the MIME message"


class TestOutlookSender:
    def _sender(self):
        from app.services.email_sender import EmailSender

        return EmailSender()

    async def test_none_token_returns_token_expired(self):
        result = await self._sender().send_outlook(
            user_id="uid",
            user_email="sender@test.com",
            outlook_oauth_token=None,
            to_email="recv@test.com",
            subject="Hi",
            body="Body",
        )
        assert result.success is False
        assert result.error == "token_expired"

    async def test_invalid_token_returns_token_expired(self):
        result = await self._sender().send_outlook(
            user_id="uid",
            user_email="sender@test.com",
            outlook_oauth_token="garbage",
            to_email="recv@test.com",
            subject="Hi",
            body="Body",
        )
        assert result.success is False
        assert result.error == "token_expired"

    async def test_202_accepted_returns_success(self):
        token = _make_token()
        sender = self._sender()

        mock_resp = MagicMock()
        mock_resp.status_code = 202

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await sender.send_outlook(
                user_id="uid",
                user_email="sender@test.com",
                outlook_oauth_token=token,
                to_email="recv@test.com",
                subject="Hello",
                body="Body",
            )

        assert result.success is True
        assert result.error is None

    async def test_429_returns_rate_limited(self):
        token = _make_token()
        sender = self._sender()

        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await sender.send_outlook(
                user_id="uid",
                user_email="sender@test.com",
                outlook_oauth_token=token,
                to_email="recv@test.com",
                subject="Hello",
                body="Body",
            )

        assert result.success is False
        assert result.error == "rate_limited"

    async def test_non_202_returns_send_failed(self):
        token = _make_token()
        sender = self._sender()

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await sender.send_outlook(
                user_id="uid",
                user_email="sender@test.com",
                outlook_oauth_token=token,
                to_email="recv@test.com",
                subject="Hello",
                body="Body",
            )

        assert result.success is False
        assert result.error.startswith("send_failed:")

    async def test_attachment_included_in_graph_payload(self):
        """Verify the attachment is embedded in the Graph API JSON payload."""
        token = _make_token()
        sender = self._sender()

        mock_resp = MagicMock()
        mock_resp.status_code = 202

        captured: list[dict] = []

        async def capture_post(url, headers, json):
            captured.append(json)
            return mock_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = capture_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await sender.send_outlook(
                user_id="uid",
                user_email="sender@test.com",
                outlook_oauth_token=token,
                to_email="recv@test.com",
                subject="Hello",
                body="Body",
                attachment=("Resume.pdf", b"%PDF fake"),
            )

        assert len(captured) == 1
        payload = captured[0]
        attachments = payload["message"]["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["name"] == "Resume.pdf"
        assert attachments[0]["contentType"] == "application/pdf"
        assert attachments[0]["@odata.type"] == "#microsoft.graph.fileAttachment"
        assert base64.b64decode(attachments[0]["contentBytes"]) == b"%PDF fake"

    async def test_connection_error_returns_send_failed(self):
        token = _make_token()
        sender = self._sender()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await sender.send_outlook(
                user_id="uid",
                user_email="sender@test.com",
                outlook_oauth_token=token,
                to_email="recv@test.com",
                subject="Hello",
                body="Body",
            )

        assert result.success is False
        assert result.error.startswith("send_failed:")
