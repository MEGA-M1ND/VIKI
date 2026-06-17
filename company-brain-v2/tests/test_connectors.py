"""Tests for the Gmail and Notion connectors using mocked provider clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.models import RawDocument, SourceType

# ── GmailConnector ────────────────────────────────────────────────────────────

class TestGmailConnector:
    def test_source_type(self) -> None:
        from app.connectors.gmail import GmailConnector

        conn = GmailConnector(client_id="cid", client_secret="cs")
        assert conn.source is SourceType.GMAIL

    async def test_fetch_documents_yields_raw_documents(self) -> None:
        from app.connectors.gmail import GmailConnector

        conn = GmailConnector(client_id="cid", client_secret="cs")

        # Build a fake raw email payload
        import base64
        import email as email_lib

        msg = email_lib.message.EmailMessage()
        msg["Subject"] = "Q2 Budget"
        msg["From"] = "alice@example.com"
        msg.set_payload("Alice approved $500k for infra.")
        raw_bytes = msg.as_bytes()
        encoded = base64.urlsafe_b64encode(raw_bytes).decode()

        # Stub out the Gmail service
        fake_service = MagicMock()
        fake_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg-1"}]
        }
        fake_service.users().messages().get().execute.return_value = {"raw": encoded}

        conn._service = fake_service

        docs = []
        async for doc in conn.fetch_documents(tenant_id="default", lookback_hours=1):
            docs.append(doc)

        assert len(docs) == 1
        assert isinstance(docs[0], RawDocument)
        assert docs[0].title == "Q2 Budget"
        assert docs[0].author == "alice@example.com"
        assert "500k" in docs[0].content

    async def test_health_check_returns_true_on_success(self) -> None:
        from app.connectors.gmail import GmailConnector

        conn = GmailConnector(client_id="cid", client_secret="cs")
        fake_service = MagicMock()
        fake_service.users().getProfile().execute.return_value = {"emailAddress": "me@ex.com"}
        conn._service = fake_service

        assert await conn.health_check() is True

    async def test_health_check_returns_false_on_error(self) -> None:
        from app.connectors.gmail import GmailConnector

        conn = GmailConnector(client_id="cid", client_secret="cs")
        fake_service = MagicMock()
        fake_service.users().getProfile().execute.side_effect = RuntimeError("auth error")
        conn._service = fake_service

        assert await conn.health_check() is False


# ── NotionConnector ───────────────────────────────────────────────────────────

class TestNotionConnector:
    def test_source_type(self) -> None:
        from app.connectors.notion import NotionConnector

        conn = NotionConnector(token="secret_xyz", database_ids=["db1"])
        assert conn.source is SourceType.NOTION

    async def test_fetch_documents_yields_pages(self) -> None:
        from app.connectors.notion import NotionConnector

        conn = NotionConnector(token="secret_xyz", database_ids=["db1"])

        fake_client = AsyncMock()
        fake_client.databases.query = AsyncMock(
            return_value={
                "results": [
                    {
                        "id": "page-1",
                        "url": "https://notion.so/page-1",
                        "last_edited_time": "2024-01-01T00:00:00Z",
                        "last_edited_by": {"id": "user-1"},
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Project Alpha"}],
                            }
                        },
                    }
                ],
                "has_more": False,
                "next_cursor": None,
            }
        )
        fake_client.blocks.children.list = AsyncMock(
            return_value={
                "results": [
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "Important decision made."}]},
                    }
                ]
            }
        )
        conn._client = fake_client

        docs = []
        async for doc in conn.fetch_documents(tenant_id="acme", lookback_hours=24):
            docs.append(doc)

        assert len(docs) == 1
        assert docs[0].title == "Project Alpha"
        assert "Important decision" in docs[0].content

    async def test_no_databases_yields_nothing(self) -> None:
        from app.connectors.notion import NotionConnector

        conn = NotionConnector(token="secret_xyz", database_ids=[])
        conn._client = AsyncMock()

        docs = []
        async for doc in conn.fetch_documents(tenant_id="default", lookback_hours=1):
            docs.append(doc)

        assert docs == []
