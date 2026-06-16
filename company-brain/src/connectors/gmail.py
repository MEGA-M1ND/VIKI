import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.connectors.base import BaseConnector, RawDocument
from src.config import Settings

logger = structlog.get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_PATH = Path.home() / ".config" / "company-brain" / "gmail_token.json"
CREDENTIALS_PATH = Path.home() / ".config" / "company-brain" / "gmail_credentials.json"
MAX_BODY_CHARS = 4000
HALF_BODY = 2000


def _truncate_body(text: str) -> str:
    if len(text) <= MAX_BODY_CHARS:
        return text
    return text[:HALF_BODY] + "\n\n[...truncated...]\n\n" + text[-HALF_BODY:]


def _decode_part(part: dict) -> str:
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def _extract_plain_text(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        return _decode_part(payload)

    if mime_type == "text/html":
        # Prefer plain text; only fall back to HTML if no plain part found higher up
        return ""

    parts = payload.get("parts", [])
    plain_texts = []
    html_fallback = ""

    for part in parts:
        sub_mime = part.get("mimeType", "")
        if sub_mime == "text/plain":
            plain_texts.append(_decode_part(part))
        elif sub_mime == "text/html" and not html_fallback:
            html_fallback = _decode_part(part)
        elif sub_mime.startswith("multipart/"):
            nested = _extract_plain_text(part)
            if nested:
                plain_texts.append(nested)

    if plain_texts:
        return "\n".join(plain_texts)
    return html_fallback


def _get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


class GmailConnector(BaseConnector):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._service = None

    def _load_credentials(self) -> Credentials | None:
        if TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            if creds and creds.valid:
                return creds
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())
                return creds
        return None

    def _build_service(self) -> None:
        creds = self._load_credentials()
        if creds is None:
            raise RuntimeError(
                "Gmail credentials not found. Run the OAuth flow at /auth/gmail first."
            )
        self._service = build("gmail", "v1", credentials=creds)

    def get_auth_url(self) -> str:
        client_config = {
            "installed": {
                "client_id": self._settings.gmail_client_id,
                "client_secret": self._settings.gmail_client_secret,
                "redirect_uris": [self._settings.gmail_redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        flow.redirect_uri = self._settings.gmail_redirect_uri
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        return auth_url

    def handle_oauth_callback(self, code: str) -> None:
        client_config = {
            "installed": {
                "client_id": self._settings.gmail_client_id,
                "client_secret": self._settings.gmail_client_secret,
                "redirect_uris": [self._settings.gmail_redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        flow.redirect_uri = self._settings.gmail_redirect_uri
        flow.fetch_token(code=code)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(flow.credentials.to_json())
        logger.info("gmail.oauth_token_saved", path=str(TOKEN_PATH))

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _list_message_ids(self, query: str) -> list[str]:
        result = self._service.users().messages().list(userId="me", q=query, maxResults=500).execute()
        messages = result.get("messages", [])
        return [m["id"] for m in messages]

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _get_message(self, msg_id: str) -> dict:
        return self._service.users().messages().get(userId="me", id=msg_id, format="full").execute()

    async def fetch(self, lookback_hours: int = 24) -> AsyncIterator[RawDocument]:
        if self._service is None:
            self._build_service()

        since = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
        timestamp = int(since.timestamp())
        query = (
            f"after:{timestamp} "
            "-category:promotions "
            "-category:social "
            "-from:noreply "
            "-from:no-reply "
            "-label:automated"
        )

        log = logger.bind(source="gmail", lookback_hours=lookback_hours)

        try:
            msg_ids = self._list_message_ids(query)
        except HttpError as exc:
            log.error("gmail.list_failed", error=str(exc))
            return

        log.info("gmail.fetching", message_count=len(msg_ids))

        for msg_id in msg_ids[: self._settings.ingestion_batch_size]:
            try:
                msg = self._get_message(msg_id)
            except HttpError as exc:
                log.warning("gmail.get_message_failed", msg_id=msg_id, error=str(exc))
                continue

            payload = msg.get("payload", {})
            headers = payload.get("headers", [])

            subject = _get_header(headers, "Subject") or "(no subject)"
            sender = _get_header(headers, "From")
            date_str = _get_header(headers, "Date")
            thread_id = msg.get("threadId", "")
            internal_date = int(msg.get("internalDate", "0")) / 1000

            body = _extract_plain_text(payload)
            body = _truncate_body(body.strip())

            if not body:
                log.debug("gmail.empty_body_skipped", msg_id=msg_id)
                continue

            fetched_at = datetime.fromtimestamp(internal_date, tz=timezone.utc)

            yield RawDocument(
                source="gmail",
                source_id=msg_id,
                content=body,
                metadata={
                    "thread_id": thread_id,
                    "date": date_str,
                    "labels": msg.get("labelIds", []),
                },
                fetched_at=fetched_at,
                author=sender,
                subject=subject,
            )

    async def health_check(self) -> bool:
        try:
            if self._service is None:
                self._build_service()
            self._service.users().getProfile(userId="me").execute()
            return True
        except Exception as exc:
            logger.warning("gmail.health_check_failed", error=str(exc))
            return False
