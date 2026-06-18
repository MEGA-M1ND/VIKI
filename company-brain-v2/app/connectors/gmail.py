"""Gmail connector.


Fetches emails via the Gmail API and normalizes them to
:class:`~app.models.documents.RawDocument`. OAuth 2.0 credentials are stored
at ``~/.config/company-brain/gmail_token.json`` after the first authorization.


Requires env vars:
    CB_GMAIL_CLIENT_ID
    CB_GMAIL_CLIENT_SECRET
    CB_GMAIL_REDIRECT_URI  (default: http://localhost:8000/auth/gmail/callback)
"""


from __future__ import annotations


import base64
import email
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


from app.connectors.base import BaseConnector
from app.core.exceptions import ConnectorAuthError, ConnectorError, ConnectorRateLimitError
from app.core.logging import get_logger
from app.models.common import SourceType
from app.models.documents import RawDocument


logger = get_logger(__name__)


TOKEN_PATH = Path.home() / ".config" / "company-brain" / "gmail_token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_MAX_BODY_CHARS = 4000



def _truncate_body(text: str) -> str:
    if len(text) <= _MAX_BODY_CHARS:
        return text
    half = _MAX_BODY_CHARS // 2
    return text[:half] + "\n\n[...truncated...]\n\n" + text[-half:]



def _extract_plain_text(msg: Any) -> str:
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                try:
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode(charset, errors="replace"))
                except Exception:  # noqa: BLE001
                    pass
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                parts.append(payload.decode(charset, errors="replace"))
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(parts)



class GmailConnector(BaseConnector):
    """Reads Gmail messages and yields :class:`RawDocument` instances."""


    source = SourceType.GMAIL


    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str = "http://localhost:8080/",
        token_path: Path = TOKEN_PATH,
    ) -> None:
        self._client_id = client_id or os.environ.get("CB_GMAIL_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("CB_GMAIL_CLIENT_SECRET", "")
        self._redirect_uri = redirect_uri
        self._token_path = token_path
        self._service: Any = None


    async def authenticate(self) -> None:
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise ConnectorAuthError(
                "google-api-python-client and google-auth-oauthlib are required for Gmail",
                details={"install": "pip install google-api-python-client google-auth-oauthlib"},
            ) from exc


        creds: Any = None


        if self._token_path.exists():
            try:
                from google.oauth2.credentials import Credentials


                data = json.loads(self._token_path.read_text())
                creds = Credentials.from_authorized_user_info(data, SCOPES)
            except Exception as exc:
                logger.warning("gmail.token_load_failed", error=str(exc))


        if creds and creds.expired and creds.refresh_token:
            try:
                from google.auth.transport.requests import Request


                creds.refresh(Request())
                self._save_token(creds)
            except Exception as exc:
                raise ConnectorAuthError(
                    "Gmail token refresh failed", details={"error": str(exc)}
                ) from exc


        if not creds or not creds.valid:
            if not self._client_id or not self._client_secret:
                raise ConnectorAuthError(
                    "Gmail credentials not configured",
                    details={"hint": "Set CB_GMAIL_CLIENT_ID and CB_GMAIL_CLIENT_SECRET"},
                )
            flow = InstalledAppFlow.from_client_config(
                {
                    "installed": {
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "redirect_uris": ["http://localhost:8080/"],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                SCOPES,
            )
            creds = flow.run_local_server(port=8080, open_browser=True)
            self._save_token(creds)


        self._service = build("gmail", "v1", credentials=creds)
        logger.info("gmail.authenticated")


    def _save_token(self, creds: Any) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json())


    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _list_messages(self, query: str, max_results: int) -> list[dict]:
        if self._service is None:
            raise ConnectorError("GmailConnector not authenticated — call authenticate() first")
        result = self._service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        return result.get("messages", [])


    def _get_message(self, msg_id: str) -> dict:
        return self._service.users().messages().get(
            userId="me", id=msg_id, format="raw"
        ).execute()


    async def fetch_documents(
        self,
        *,
        tenant_id: str,
        since: datetime | None = None,
        lookback_hours: int = 24,
    ) -> AsyncIterator[RawDocument]:
        if self._service is None:
            await self.authenticate()


        cutoff = since or (datetime.now(tz=UTC) - timedelta(hours=lookback_hours))
        ts = int(cutoff.timestamp())
        query = f"after:{ts} -category:promotions -category:social"


        try:
            messages = self._list_messages(query, max_results=50)
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "rateLimitExceeded" in msg.lower():
                raise ConnectorRateLimitError("Gmail rate limit hit", details={"error": msg}) from exc
            raise ConnectorError("Gmail message list failed", details={"error": msg}) from exc


        for msg_stub in messages:
            try:
                raw = self._get_message(msg_stub["id"])
                raw_bytes = base64.urlsafe_b64decode(raw["raw"] + "==")
                parsed = email.message_from_bytes(raw_bytes)


                subject = parsed.get("Subject", "(no subject)")
                sender = parsed.get("From", "")
                body = _extract_plain_text(parsed)
                content = _truncate_body(body.strip())


                if not content:
                    continue


                yield RawDocument(
                    tenant_id=tenant_id,
                    source=SourceType.GMAIL,
                    source_id=msg_stub["id"],
                    title=subject,
                    content=content,
                    author=sender,
                    metadata={"message_id": msg_stub["id"]},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("gmail.message_fetch_failed", msg_id=msg_stub["id"], error=str(exc))


    async def health_check(self) -> bool:
        try:
            if self._service is None:
                await self.authenticate()
            self._service.users().getProfile(userId="me").execute()
            return True
        except Exception:  # noqa: BLE001
            return False