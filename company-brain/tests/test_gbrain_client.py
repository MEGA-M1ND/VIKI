import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.gbrain_client.mcp_client import GBrainMCPClient


# ---- Helpers ----


def make_settings(**kwargs):
    settings = MagicMock()
    settings.gbrain_mcp_url = kwargs.get("gbrain_mcp_url", "http://localhost:3721/mcp")
    settings.gbrain_token = kwargs.get("gbrain_token", "test-token")
    return settings


def make_mcp_sse(tool_result: dict | list | str) -> str:
    """Return SSE-formatted MCP response text as GBrain HTTP server sends it."""
    if isinstance(tool_result, str):
        inner_text = tool_result
    else:
        inner_text = json.dumps(tool_result)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": inner_text}]
        },
    }
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


def make_mcp_error_sse(message: str) -> str:
    """Return SSE-formatted MCP error response."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32000, "message": message},
    }
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


def mock_http_response(text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


# ---- Tests ----


class TestGBrainMCPClient:
    @pytest.fixture
    def client(self):
        return GBrainMCPClient(make_settings())

    @pytest.mark.asyncio
    async def test_search_returns_results(self, client):
        mock_results = [
            {"slug": "email/2024-01-10/launch", "score": 0.87, "snippet": "Launch decision"},
            {"slug": "notion/2024-01-09/planning", "score": 0.75, "snippet": "Planning notes"},
        ]
        sse_text = make_mcp_sse(mock_results)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_http
            mock_http.post.return_value = mock_http_response(sse_text)

            results = await client.search("launch decision", limit=5)

        assert len(results) == 2
        assert results[0]["slug"] == "email/2024-01-10/launch"
        assert results[0]["score"] == 0.87

    @pytest.mark.asyncio
    async def test_think_returns_string(self, client):
        answer = "Based on company records, the launch was decided on January 15th."
        sse_text = make_mcp_sse({"answer": answer})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_http
            mock_http.post.return_value = mock_http_response(sse_text)

            result = await client.think("When was the launch decided?")

        assert result == answer

    @pytest.mark.asyncio
    async def test_put_page_sends_correct_payload(self, client):
        sse_text = make_mcp_sse({"slug": "gmail/2024-01-10/test", "status": "created"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_http
            mock_http.post.return_value = mock_http_response(sse_text)

            result = await client.put_page(
                slug="gmail/2024-01-10/test",
                content="# Test\n\nContent here.",
                metadata={"source": "gmail"},
            )

        assert mock_http.post.called
        call_kwargs = mock_http.post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert payload["params"]["name"] == "put_page"
        assert payload["params"]["arguments"]["slug"] == "gmail/2024-01-10/test"

    @pytest.mark.asyncio
    async def test_get_page_returns_none_when_not_found(self, client):
        sse_text = make_mcp_error_sse("page not found")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_http
            mock_http.post.return_value = mock_http_response(sse_text)

            result = await client.get_page("nonexistent/page")

        assert result is None

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, client):
        sse_text = make_mcp_sse([{"slug": "test", "score": 0.9}])

        call_count = 0

        async def flaky_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("Timeout", request=MagicMock())
            return mock_http_response(sse_text)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_http
            mock_http.post.side_effect = flaky_post

            results = await client.search("test")

        assert call_count == 2
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_health_returns_true(self, client):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_http
            mock_http.get.return_value = MagicMock(status_code=200)

            result = await client.health()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_returns_false_on_error(self, client):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_http
            mock_http.get.side_effect = httpx.ConnectError("refused", request=MagicMock())

            result = await client.health()

        assert result is False

    @pytest.mark.asyncio
    async def test_bearer_token_sent_in_headers(self, client):
        sse_text = make_mcp_sse([])

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_http
            mock_http.post.return_value = mock_http_response(sse_text)

            await client.search("test")

        call_kwargs = mock_http.post.call_args
        headers = call_kwargs[1].get("headers", {})
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-token"

    @pytest.mark.asyncio
    async def test_tool_error_raises_runtime_error(self, client):
        sse_text = make_mcp_error_sse("internal brain error")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_http
            mock_http.post.return_value = mock_http_response(sse_text)

            with pytest.raises(RuntimeError, match="GBrain tool"):
                await client.think("anything")
