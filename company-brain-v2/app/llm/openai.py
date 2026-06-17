"""OpenAI-backed LLM provider.

Requires ``OPENAI_API_KEY`` in the environment. Uses ``langchain-openai`` under
the hood so chat history, retries, and structured output work uniformly.
"""

from __future__ import annotations

import os

from app.core.exceptions import ExtractionError
from app.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """ChatOpenAI-backed provider.

    Args:
        model: OpenAI model name (default: ``gpt-4o-mini``).
        api_key: API key (defaults to ``OPENAI_API_KEY`` env var).
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        try:
            from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ExtractionError(
                "langchain-openai is required for OpenAIProvider",
                details={"install": "pip install langchain-openai"},
            ) from exc

        lc_messages: list[BaseMessage] = []
        for m in messages:
            role, content = m["role"], m["content"]
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        kwargs: dict = {
            "model": self._model,
            "api_key": self._api_key,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

        client = ChatOpenAI(**kwargs)

        try:
            response = await client.ainvoke(lc_messages)
            return str(response.content)
        except Exception as exc:
            raise ExtractionError("OpenAI call failed", details={"error": str(exc)}) from exc
