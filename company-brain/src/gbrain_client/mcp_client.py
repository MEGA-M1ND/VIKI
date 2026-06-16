import time
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import Settings

logger = structlog.get_logger(__name__)

_RETRYABLE = (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)


class GBrainMCPClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.gbrain_mcp_url.rstrip("/")
        self._token = settings.gbrain_token
        self._timeout = 30.0

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        reraise=True,
    )
    async def _call_tool(self, tool_name: str, params: dict[str, Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": params},
        }

        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._base_url,
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()

        latency_ms = round((time.monotonic() - t0) * 1000)
        data = response.json()

        if "error" in data:
            logger.error(
                "gbrain.tool_error",
                tool=tool_name,
                error=data["error"],
                latency_ms=latency_ms,
            )
            raise RuntimeError(f"GBrain tool '{tool_name}' error: {data['error']}")

        logger.info("gbrain.tool_called", tool=tool_name, latency_ms=latency_ms, status="ok")

        result = data.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list):
            first = content[0]
            if first.get("type") == "text":
                import json

                try:
                    return json.loads(first["text"])
                except (json.JSONDecodeError, KeyError):
                    return first.get("text", result)
        return result

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        result = await self._call_tool("brain_search", {"query": query, "limit": limit})
        if isinstance(result, list):
            return result
        return result.get("results", []) if isinstance(result, dict) else []

    async def think(self, query: str) -> str:
        result = await self._call_tool("brain_synthesize", {"query": query})
        if isinstance(result, str):
            return result
        return result.get("answer", "") if isinstance(result, dict) else str(result)

    async def put_page(self, slug: str, content: str, metadata: dict) -> dict:
        result = await self._call_tool("put_page", {"slug": slug, "content": content, **metadata})
        return result if isinstance(result, dict) else {"slug": slug}

    async def get_page(self, slug: str) -> dict | None:
        try:
            result = await self._call_tool("get_page", {"slug": slug})
            return result if isinstance(result, dict) else None
        except RuntimeError as exc:
            if "not found" in str(exc).lower():
                return None
            raise

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                base = self._base_url.replace("/mcp", "")
                response = await client.get(f"{base}/health", headers=self._headers())
                return response.status_code == 200
        except Exception as exc:
            logger.warning("gbrain.health_check_failed", error=str(exc))
            return False
