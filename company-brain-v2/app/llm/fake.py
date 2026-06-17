"""Fake LLM provider for tests and local dev (no network, no API key).

Responses are scripted by registering patterns → reply pairs. Unmatched calls
return an empty JSON object ``{}`` in json_mode or empty string otherwise.
"""

from __future__ import annotations

import json

from app.llm.base import LLMProvider


class FakeLLMProvider(LLMProvider):
    """Deterministic fake for unit tests.

    Usage::

        llm = FakeLLMProvider()
        llm.register("classify", '{"is_worth_remembering": true, "confidence": 0.9}')
        llm.register("extract", '{"facts": [{"statement": "Alice approved budget"}]}')
    """

    def __init__(self, default_response: str = "{}") -> None:
        self._responses: list[tuple[str, str]] = []
        self._default = default_response
        self.calls: list[list[dict[str, str]]] = []

    def register(self, keyword: str, response: str) -> None:
        """Register a scripted response for messages containing *keyword*."""
        self._responses.append((keyword.lower(), response))

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        self.calls.append(messages)
        combined = " ".join(m["content"].lower() for m in messages)
        for keyword, response in self._responses:
            if keyword in combined:
                return response
        return self._default if json_mode else ""

    def last_call(self) -> list[dict[str, str]] | None:
        return self.calls[-1] if self.calls else None


class EchoLLMProvider(LLMProvider):
    """Returns a fixed JSON payload (useful for smoke tests)."""

    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload)

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        return self._payload


class SequentialLLMProvider(LLMProvider):
    """Returns scripted responses in call order — one response per call.

    Useful for tests that need different responses from classify vs extract.

    Usage::

        llm = SequentialLLMProvider([
            '{"is_worth_remembering": true, "confidence": 0.9}',
            '{"facts": [...], "entities": [...]}',
        ])
    """

    def __init__(self, responses: list[str], default: str = "{}") -> None:
        self._responses = list(responses)
        self._idx = 0
        self._default = default
        self.calls: list[list[dict[str, str]]] = []

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        self.calls.append(messages)
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        return self._default
