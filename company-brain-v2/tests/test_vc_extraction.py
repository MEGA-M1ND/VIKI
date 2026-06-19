"""Tests for VC-aware extraction prompt + parser (Phase 2)."""

from __future__ import annotations

import asyncio
import json

from app.llm.fake import FakeLLMProvider
from app.prompts.extraction import build_vc_extract_messages, parse_vc_extraction


def test_extraction_rejects_newsletter() -> None:
    """A bulk mailing with an unsubscribe footer yields no facts."""
    llm = FakeLLMProvider()
    llm.register("unsubscribe", "[]")

    content = (
        "List-Unsubscribe: <https://example.com/u>\n"
        "Our weekly newsletter! View in browser. Click unsubscribe to opt out."
    )
    messages = build_vc_extract_messages(
        source="gmail",
        title="Weekly Digest",
        author="news@example.com",
        content=content,
    )

    raw = asyncio.run(llm.chat(messages, json_mode=True))
    result = parse_vc_extraction(raw)

    assert result == []


def test_extraction_extracts_founder_signal() -> None:
    """A 'raising' email yields a FOUNDER_SIGNAL with the raise amount."""
    llm = FakeLLMProvider()
    fake_response = json.dumps(
        [
            {
                "fact_type": "FOUNDER_SIGNAL",
                "statement": "Alice is raising a $2M seed round for Acme.",
                "entities": {
                    "company": "Acme",
                    "person": "Alice",
                    "raise_amount": 2000000,
                },
                "confidence": 0.9,
                "signal_date": "2026-06-01",
            }
        ]
    )
    llm.register("raising", fake_response)

    content = "Hi, I'm Alice from Acme and we are raising a $2M seed round."
    messages = build_vc_extract_messages(
        source="gmail",
        title="Intro",
        author="alice@acme.com",
        content=content,
    )

    raw = asyncio.run(llm.chat(messages, json_mode=True))
    result = parse_vc_extraction(raw)

    assert len(result) == 1
    item = result[0]
    assert item["fact_type"] == "FOUNDER_SIGNAL"
    assert item["entities"]["raise_amount"] == 2000000
    assert item["confidence"] == 0.9


def test_parser_tolerates_markdown_fences() -> None:
    """The parser strips ```json code fences before decoding."""
    raw = '```json\n[{"fact_type": "GENERAL_FACT", "statement": "x"}]\n```'
    result = parse_vc_extraction(raw)
    assert len(result) == 1
    assert result[0]["fact_type"] == "GENERAL_FACT"
    assert result[0]["entities"] == {}


def test_parser_returns_empty_on_garbage() -> None:
    """Invalid / empty input yields an empty list, never raises."""
    assert parse_vc_extraction("") == []
    assert parse_vc_extraction("not json") == []
    assert parse_vc_extraction("{}") == []  # object, not array
