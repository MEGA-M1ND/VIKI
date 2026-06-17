from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import structlog
from notion_client import AsyncClient
from notion_client.errors import APIResponseError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.connectors.base import BaseConnector, RawDocument
from src.config import Settings

logger = structlog.get_logger(__name__)


def _block_to_markdown(block: dict) -> str:
    block_type = block.get("type", "")
    content = block.get(block_type, {})

    def rich_text_to_str(rich_texts: list) -> str:
        return "".join(rt.get("plain_text", "") for rt in rich_texts)

    if block_type == "paragraph":
        return rich_text_to_str(content.get("rich_text", []))

    if block_type in ("heading_1", "heading_2", "heading_3"):
        level = int(block_type[-1])
        text = rich_text_to_str(content.get("rich_text", []))
        return f"{'#' * level} {text}"

    if block_type == "bulleted_list_item":
        text = rich_text_to_str(content.get("rich_text", []))
        return f"- {text}"

    if block_type == "numbered_list_item":
        text = rich_text_to_str(content.get("rich_text", []))
        return f"1. {text}"

    if block_type == "to_do":
        checked = content.get("checked", False)
        text = rich_text_to_str(content.get("rich_text", []))
        mark = "x" if checked else " "
        return f"- [{mark}] {text}"

    if block_type == "toggle":
        text = rich_text_to_str(content.get("rich_text", []))
        return f"<details><summary>{text}</summary></details>"

    if block_type == "code":
        lang = content.get("language", "")
        text = rich_text_to_str(content.get("rich_text", []))
        return f"```{lang}\n{text}\n```"

    if block_type == "quote":
        text = rich_text_to_str(content.get("rich_text", []))
        return f"> {text}"

    if block_type == "callout":
        text = rich_text_to_str(content.get("rich_text", []))
        icon = content.get("icon", {}).get("emoji", "💡")
        return f"> {icon} {text}"

    if block_type == "divider":
        return "---"

    if block_type == "image":
        url = content.get("external", {}).get("url") or content.get("file", {}).get("url", "")
        caption = rich_text_to_str(content.get("caption", []))
        return f"![{caption}]({url})"

    if block_type == "bookmark":
        url = content.get("url", "")
        caption = rich_text_to_str(content.get("caption", []))
        return f"[{caption or url}]({url})"

    if block_type == "table_of_contents":
        return ""

    return ""


def _page_title(page: dict) -> str:
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            texts = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in texts)
    return "(untitled)"


def _page_author(page: dict) -> str | None:
    created_by = page.get("created_by", {})
    return created_by.get("name") or created_by.get("id")


class NotionConnector(BaseConnector):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncClient(auth=settings.notion_api_key)

    @retry(
        retry=retry_if_exception_type(APIResponseError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _query_database(self, database_id: str, filter_payload: dict) -> list[dict]:
        pages: list[dict] = []
        cursor = None

        while True:
            params: dict = {"database_id": database_id, "filter": filter_payload, "page_size": 100}
            if cursor:
                params["start_cursor"] = cursor

            response = await self._client.databases.query(**params)
            pages.extend(response.get("results", []))

            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")

        return pages

    @retry(
        retry=retry_if_exception_type(APIResponseError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _get_block_children(self, block_id: str) -> list[dict]:
        blocks: list[dict] = []
        cursor = None

        while True:
            params: dict = {"block_id": block_id, "page_size": 100}
            if cursor:
                params["start_cursor"] = cursor

            response = await self._client.blocks.children.list(**params)
            blocks.extend(response.get("results", []))

            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")

        return blocks

    async def _blocks_to_markdown(self, page_id: str) -> str:
        try:
            blocks = await self._get_block_children(page_id)
        except APIResponseError as exc:
            logger.warning("notion.get_blocks_failed", page_id=page_id, error=str(exc))
            return ""

        lines: list[str] = []
        for block in blocks:
            line = _block_to_markdown(block)
            if line:
                lines.append(line)

            if block.get("has_children"):
                child_md = await self._blocks_to_markdown(block["id"])
                if child_md:
                    indented = "\n".join(f"  {l}" for l in child_md.splitlines())
                    lines.append(indented)

        return "\n\n".join(lines)

    async def fetch(self, lookback_hours: int = 24) -> AsyncIterator[RawDocument]:
        since = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
        since_str = since.isoformat().replace("+00:00", "Z")

        database_ids = self._settings.notion_database_id_list
        if not database_ids:
            logger.warning("notion.no_database_ids_configured")
            return

        log = logger.bind(source="notion", lookback_hours=lookback_hours)

        for database_id in database_ids:
            filter_payload = {
                "timestamp": "last_edited_time",
                "last_edited_time": {"after": since_str},
            }

            try:
                pages = await self._query_database(database_id, filter_payload)
            except APIResponseError as exc:
                log.error("notion.query_failed", database_id=database_id, error=str(exc))
                continue

            log.info("notion.fetching", database_id=database_id, page_count=len(pages))

            for page in pages[: self._settings.ingestion_batch_size]:
                page_id = page["id"]
                title = _page_title(page)
                author = _page_author(page)
                last_edited = page.get("last_edited_time", "")
                created_time = page.get("created_time", "")

                try:
                    content = await self._blocks_to_markdown(page_id)
                except Exception as exc:
                    log.warning("notion.content_failed", page_id=page_id, error=str(exc))
                    continue

                if not content.strip():
                    log.debug("notion.empty_page_skipped", page_id=page_id)
                    continue

                try:
                    fetched_at = datetime.fromisoformat(last_edited.replace("Z", "+00:00"))
                except ValueError:
                    fetched_at = datetime.now(tz=timezone.utc)

                yield RawDocument(
                    source="notion",
                    source_id=page_id,
                    content=content,
                    metadata={
                        "database_id": database_id,
                        "url": page.get("url", ""),
                        "created_time": created_time,
                        "last_edited_time": last_edited,
                    },
                    fetched_at=fetched_at,
                    author=author,
                    subject=title,
                )

    async def health_check(self) -> bool:
        try:
            await self._client.users.me()
            return True
        except Exception as exc:
            logger.warning("notion.health_check_failed", error=str(exc))
            return False
