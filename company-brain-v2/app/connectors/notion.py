"""Notion connector.

Fetches pages from one or more Notion databases and normalizes them to
:class:`~app.models.documents.RawDocument`. Uses the official notion-client
library with async support.

Requires env vars:
    CB_NOTION_TOKEN        — Notion integration token
    CB_NOTION_DATABASE_IDS — comma-separated database IDs to sync
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from app.connectors.base import BaseConnector
from app.core.exceptions import ConnectorAuthError, ConnectorError
from app.core.logging import get_logger
from app.models.common import SourceType
from app.models.documents import RawDocument

logger = get_logger(__name__)


def _block_to_markdown(block: dict[str, Any]) -> str:
    """Recursively convert a single Notion block to a Markdown string."""
    kind = block.get("type", "")
    data = block.get(kind, {})
    rich_texts = data.get("rich_text", [])
    text = "".join(rt.get("plain_text", "") for rt in rich_texts)

    match kind:
        case "paragraph":
            return text
        case "heading_1":
            return f"# {text}"
        case "heading_2":
            return f"## {text}"
        case "heading_3":
            return f"### {text}"
        case "bulleted_list_item":
            return f"- {text}"
        case "numbered_list_item":
            return f"1. {text}"
        case "to_do":
            checked = "x" if data.get("checked") else " "
            return f"- [{checked}] {text}"
        case "code":
            lang = data.get("language", "")
            return f"```{lang}\n{text}\n```"
        case "quote":
            return f"> {text}"
        case "callout":
            emoji = data.get("icon", {}).get("emoji", "ℹ️")
            return f"{emoji} {text}"
        case "divider":
            return "---"
        case "image":
            url = data.get("external", {}).get("url") or data.get("file", {}).get("url", "")
            caption_parts = data.get("caption", [])
            caption = "".join(c.get("plain_text", "") for c in caption_parts)
            return f"![{caption}]({url})" if url else ""
        case "bookmark":
            url = data.get("url", "")
            return f"[{url}]({url})"
        case _:
            return text


def _page_title(page: dict[str, Any]) -> str:
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            return "".join(p.get("plain_text", "") for p in parts)
    return "(untitled)"


class NotionConnector(BaseConnector):
    """Reads Notion database pages and yields :class:`RawDocument` instances."""

    source = SourceType.NOTION

    def __init__(
        self,
        token: str | None = None,
        database_ids: list[str] | None = None,
    ) -> None:
        self._token = token or os.environ.get("CB_NOTION_TOKEN", "")
        raw_ids = os.environ.get("CB_NOTION_DATABASE_IDS", "")
        self._database_ids: list[str] = database_ids or [
            i.strip() for i in raw_ids.split(",") if i.strip()
        ]
        self._client: Any = None

    async def authenticate(self) -> None:
        try:
            from notion_client import AsyncClient
        except ImportError as exc:
            raise ConnectorAuthError(
                "notion-client is required for Notion",
                details={"install": "pip install notion-client"},
            ) from exc

        if not self._token:
            raise ConnectorAuthError(
                "Notion token not configured",
                details={"hint": "Set CB_NOTION_TOKEN"},
            )
        self._client = AsyncClient(auth=self._token)
        logger.info("notion.authenticated")

    async def fetch_documents(
        self,
        *,
        tenant_id: str,
        since: datetime | None = None,
        lookback_hours: int = 24,
    ) -> AsyncIterator[RawDocument]:
        if self._client is None:
            await self.authenticate()

        cutoff = since or (datetime.now(tz=UTC) - timedelta(hours=lookback_hours))
        cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        if not self._database_ids:
            logger.warning("notion.no_databases_configured")
            return

        for db_id in self._database_ids:
            has_more = True
            cursor: str | None = None

            while has_more:
                try:
                    params: dict[str, Any] = {
                        "database_id": db_id,
                        "filter": {
                            "timestamp": "last_edited_time",
                            "last_edited_time": {"on_or_after": cutoff_iso},
                        },
                    }
                    if cursor:
                        params["start_cursor"] = cursor

                    resp = await self._client.databases.query(**params)
                except Exception as exc:
                    logger.error("notion.query_failed", db_id=db_id, error=str(exc))
                    raise ConnectorError(
                        "Notion database query failed",
                        details={"db_id": db_id, "error": str(exc)},
                    ) from exc

                for page in resp.get("results", []):
                    doc = await self._page_to_document(page, tenant_id)
                    if doc:
                        yield doc

                has_more = resp.get("has_more", False)
                cursor = resp.get("next_cursor")

    async def _page_to_document(
        self, page: dict[str, Any], tenant_id: str
    ) -> RawDocument | None:
        page_id = page["id"]
        title = _page_title(page)
        url = page.get("url", "")
        last_edited = page.get("last_edited_time", "")
        author_id = page.get("last_edited_by", {}).get("id", "")

        try:
            blocks_resp = await self._client.blocks.children.list(block_id=page_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("notion.blocks_failed", page_id=page_id, error=str(exc))
            return None

        lines: list[str] = []
        for block in blocks_resp.get("results", []):
            md = _block_to_markdown(block)
            if md:
                lines.append(md)

        content = "\n\n".join(lines).strip()
        if not content:
            content = title

        return RawDocument(
            tenant_id=tenant_id,
            source=SourceType.NOTION,
            source_id=page_id,
            title=title,
            content=content,
            author=author_id,
            metadata={"url": url, "last_edited": last_edited},
        )

    async def health_check(self) -> bool:
        try:
            if self._client is None:
                await self.authenticate()
            await self._client.users.me()
            return True
        except Exception:  # noqa: BLE001
            return False
