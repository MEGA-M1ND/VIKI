from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.base import RawDocument
from src.connectors.gmail import GmailConnector, _extract_plain_text, _truncate_body
from src.connectors.notion import NotionConnector, _block_to_markdown, _page_title


# ---- Helpers ----


def make_settings(**kwargs):
    defaults = {
        "openai_api_key": "sk-test",
        "gmail_client_id": "client-id",
        "gmail_client_secret": "secret",
        "gmail_redirect_uri": "http://localhost:8000/auth/gmail/callback",
        "notion_api_key": "secret_test",
        "notion_database_ids": "db1,db2",
        "gbrain_mcp_url": "http://localhost:3721/mcp",
        "gbrain_token": "token",
        "ingestion_batch_size": 50,
        "ingestion_lookback_hours": 24,
        "classifier_confidence_threshold": 0.7,
    }
    defaults.update(kwargs)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    settings.notion_database_id_list = ["db1", "db2"]
    return settings


# ---- Gmail tests ----


class TestGmailHelpers:
    def test_truncate_short_body(self):
        text = "Hello world"
        assert _truncate_body(text) == text

    def test_truncate_long_body(self):
        text = "A" * 5000
        result = _truncate_body(text)
        assert "[...truncated...]" in result
        assert len(result) < 5000

    def test_extract_plain_text_simple(self):
        import base64

        body_text = "Hello, this is a test email."
        encoded = base64.urlsafe_b64encode(body_text.encode()).decode()
        payload = {"mimeType": "text/plain", "body": {"data": encoded}}
        assert _extract_plain_text(payload) == body_text

    def test_extract_plain_text_multipart(self):
        import base64

        plain = "Plain text content"
        encoded = base64.urlsafe_b64encode(plain.encode()).decode()
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": encoded}},
                {"mimeType": "text/html", "body": {"data": encoded}},
            ],
        }
        result = _extract_plain_text(payload)
        assert result == plain


class TestGmailConnector:
    @pytest.fixture
    def connector(self):
        return GmailConnector(make_settings())

    @pytest.mark.asyncio
    async def test_fetch_yields_raw_documents(self, connector):
        import base64

        plain_text = "Important meeting decision: we will launch on Monday."
        encoded = base64.urlsafe_b64encode(plain_text.encode()).decode()

        mock_msg = {
            "id": "msg123",
            "threadId": "thread456",
            "labelIds": ["INBOX"],
            "internalDate": "1700000000000",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Subject", "value": "Launch Decision"},
                    {"name": "From", "value": "alice@example.com"},
                    {"name": "Date", "value": "Mon, 1 Jan 2024 10:00:00 +0000"},
                ],
                "body": {"data": encoded},
            },
        }

        mock_service = MagicMock()
        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg123"}]
        }
        mock_service.users().messages().get().execute.return_value = mock_msg

        connector._service = mock_service

        docs = []
        async for doc in connector.fetch(lookback_hours=24):
            docs.append(doc)

        # Settings fixture has db1,db2 — mock returns 1 page per DB = 2 total
        assert len(docs) >= 1
        doc = docs[0]
        assert isinstance(doc, RawDocument)
        assert doc.source == "gmail"
        assert doc.source_id == "msg123"
        assert doc.subject == "Launch Decision"
        assert doc.author == "alice@example.com"
        assert plain_text in doc.content

    @pytest.mark.asyncio
    async def test_fetch_skips_empty_body(self, connector):
        mock_msg = {
            "id": "msg_empty",
            "threadId": "thread_empty",
            "labelIds": ["INBOX"],
            "internalDate": "1700000000000",
            "payload": {
                "mimeType": "text/plain",
                "headers": [{"name": "Subject", "value": "Empty"}],
                "body": {"data": ""},
            },
        }

        mock_service = MagicMock()
        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg_empty"}]
        }
        mock_service.users().messages().get().execute.return_value = mock_msg
        connector._service = mock_service

        docs = [doc async for doc in connector.fetch()]
        assert len(docs) == 0

    @pytest.mark.asyncio
    async def test_health_check_success(self, connector):
        mock_service = MagicMock()
        mock_service.users().getProfile().execute.return_value = {"emailAddress": "me@test.com"}
        connector._service = mock_service
        assert await connector.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, connector):
        connector._service = None
        with patch.object(connector, "_build_service", side_effect=RuntimeError("No creds")):
            result = await connector.health_check()
        assert result is False


# ---- Notion tests ----


class TestNotionHelpers:
    def test_block_to_markdown_paragraph(self):
        block = {
            "type": "paragraph",
            "paragraph": {"rich_text": [{"plain_text": "Hello world"}]},
        }
        assert _block_to_markdown(block) == "Hello world"

    def test_block_to_markdown_heading(self):
        block = {
            "type": "heading_2",
            "heading_2": {"rich_text": [{"plain_text": "Section Title"}]},
        }
        assert _block_to_markdown(block) == "## Section Title"

    def test_block_to_markdown_bullet(self):
        block = {
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"plain_text": "Item one"}]},
        }
        assert _block_to_markdown(block) == "- Item one"

    def test_block_to_markdown_code(self):
        block = {
            "type": "code",
            "code": {
                "language": "python",
                "rich_text": [{"plain_text": "print('hello')"}],
            },
        }
        result = _block_to_markdown(block)
        assert "```python" in result
        assert "print('hello')" in result

    def test_block_to_markdown_unknown(self):
        block = {"type": "unsupported_block", "unsupported_block": {}}
        assert _block_to_markdown(block) == ""

    def test_page_title_extraction(self):
        page = {
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"plain_text": "My Page Title"}],
                }
            }
        }
        assert _page_title(page) == "My Page Title"

    def test_page_title_missing(self):
        assert _page_title({"properties": {}}) == "(untitled)"


class TestNotionConnector:
    @pytest.fixture
    def connector(self):
        settings = make_settings()
        conn = NotionConnector.__new__(NotionConnector)
        conn._settings = settings
        conn._client = AsyncMock()
        return conn

    @pytest.mark.asyncio
    async def test_fetch_yields_documents(self, connector):
        connector._client.databases.query = AsyncMock(
            return_value={
                "results": [
                    {
                        "id": "page-abc",
                        "url": "https://notion.so/page-abc",
                        "created_time": "2024-01-01T00:00:00.000Z",
                        "last_edited_time": "2024-01-15T12:00:00.000Z",
                        "created_by": {"name": "Bob"},
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Project Alpha Update"}],
                            }
                        },
                    }
                ],
                "has_more": False,
            }
        )
        connector._client.blocks.children.list = AsyncMock(
            return_value={
                "results": [
                    {
                        "id": "block1",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "We decided to launch next week."}]},
                        "has_children": False,
                    }
                ],
                "has_more": False,
            }
        )

        docs = [doc async for doc in connector.fetch(lookback_hours=24)]
        # settings fixture has db1,db2 — mock returns same page per DB = 2 total
        assert len(docs) >= 1
        doc = docs[0]
        assert doc.source == "notion"
        assert doc.source_id == "page-abc"
        assert doc.subject == "Project Alpha Update"
        assert "decided to launch" in doc.content

    @pytest.mark.asyncio
    async def test_fetch_skips_empty_pages(self, connector):
        connector._client.databases.query = AsyncMock(
            return_value={
                "results": [
                    {
                        "id": "page-empty",
                        "url": "",
                        "created_time": "2024-01-01T00:00:00.000Z",
                        "last_edited_time": "2024-01-15T12:00:00.000Z",
                        "created_by": {},
                        "properties": {
                            "Name": {"type": "title", "title": [{"plain_text": "Empty Page"}]}
                        },
                    }
                ],
                "has_more": False,
            }
        )
        connector._client.blocks.children.list = AsyncMock(
            return_value={"results": [], "has_more": False}
        )

        docs = [doc async for doc in connector.fetch()]
        assert len(docs) == 0

    @pytest.mark.asyncio
    async def test_health_check_success(self, connector):
        connector._client.users.me = AsyncMock(return_value={"id": "user-1"})
        assert await connector.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, connector):
        connector._client.users.me = AsyncMock(side_effect=Exception("Auth failed"))
        assert await connector.health_check() is False
