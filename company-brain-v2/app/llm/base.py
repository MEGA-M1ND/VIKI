"""LLM provider interface.

All LLM access goes through :class:`LLMProvider`. This keeps prompt engineering
isolated from infrastructure: swap in a fake for tests, a local model for dev,
or a different provider for prod — no other code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base for LLM backends."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        """Send a chat conversation and return the assistant reply text.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            json_mode: If ``True``, request JSON-only output from the model.
            temperature: Sampling temperature.

        Returns:
            The assistant's reply as a plain string.

        Raises:
            ExtractionError: The LLM call failed or returned unparseable output.
        """
        raise NotImplementedError

    async def complete(
        self,
        prompt: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        """Single-turn completion. Wraps :meth:`chat` with a user message."""
        return await self.chat(
            [{"role": "user", "content": prompt}],
            json_mode=json_mode,
            temperature=temperature,
        )
