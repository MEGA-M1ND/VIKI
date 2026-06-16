from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.base import RawDocument
from src.pipeline.state import ExtractionState
from src.pipeline.nodes import classify_node, extract_node, deduplicate_node, write_node
from src.pipeline.graph import build_extraction_graph, should_extract, should_write
from src.gbrain_client.page_builder import build_gbrain_page


# ---- Helpers ----


def make_doc(**kwargs) -> RawDocument:
    defaults = {
        "source": "gmail",
        "source_id": "msg123",
        "content": "We decided to launch the product on January 15th. Alice will lead the rollout.",
        "metadata": {},
        "fetched_at": datetime(2024, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
        "author": "bob@example.com",
        "subject": "Launch Decision",
    }
    defaults.update(kwargs)
    return RawDocument(**defaults)


def make_state(**kwargs) -> ExtractionState:
    doc = make_doc()
    defaults: ExtractionState = {
        "document": doc,
        "is_worth_remembering": None,
        "classifier_reasoning": None,
        "confidence": None,
        "extracted_facts": None,
        "entities": None,
        "summary": None,
        "existing_similar_pages": None,
        "is_duplicate": None,
        "gbrain_page_slug": None,
        "write_status": None,
        "error": None,
    }
    defaults.update(kwargs)
    return defaults


# ---- Routing tests ----


class TestGraphRouting:
    def test_should_extract_true(self):
        state = make_state(is_worth_remembering=True)
        assert should_extract(state) == "extract"

    def test_should_extract_false(self):
        state = make_state(is_worth_remembering=False)
        from langgraph.graph import END
        assert should_extract(state) == END

    def test_should_extract_none(self):
        state = make_state(is_worth_remembering=None)
        from langgraph.graph import END
        assert should_extract(state) == END

    def test_should_write_not_duplicate(self):
        state = make_state(is_duplicate=False)
        assert should_write(state) == "write"

    def test_should_write_duplicate(self):
        state = make_state(is_duplicate=True)
        from langgraph.graph import END
        assert should_write(state) == END

    def test_should_write_none(self):
        state = make_state(is_duplicate=None)
        assert should_write(state) == "write"


# ---- Classify node tests ----


class TestClassifyNode:
    @pytest.mark.asyncio
    async def test_classify_worth_remembering(self):
        mock_response = MagicMock()
        mock_response.content = '{"worth_remembering": true, "confidence": 0.9, "reasoning": "Contains a launch decision."}'

        with patch("src.pipeline.nodes.get_settings") as mock_settings, \
             patch("src.pipeline.nodes.ChatOpenAI") as mock_llm_cls:
            mock_settings.return_value.classifier_confidence_threshold = 0.7
            mock_settings.return_value.openai_model = "gpt-4o"
            mock_settings.return_value.openai_api_key = "sk-test"

            mock_llm = MagicMock()
            mock_llm_cls.return_value = mock_llm
            chain_mock = AsyncMock(return_value=mock_response)
            mock_llm.__or__ = MagicMock(return_value=chain_mock)

            with patch("src.pipeline.nodes.CLASSIFIER_PROMPT") as mock_prompt:
                mock_prompt.__or__ = MagicMock(return_value=chain_mock)

                state = make_state()
                result = await classify_node(state)

        assert result["is_worth_remembering"] is True
        assert result["confidence"] == 0.9
        assert "launch decision" in result["classifier_reasoning"].lower()

    @pytest.mark.asyncio
    async def test_classify_low_confidence_forces_false(self):
        mock_response = MagicMock()
        mock_response.content = '{"worth_remembering": true, "confidence": 0.3, "reasoning": "Maybe."}'

        with patch("src.pipeline.nodes.get_settings") as mock_settings, \
             patch("src.pipeline.nodes.ChatOpenAI") as mock_llm_cls:
            mock_settings.return_value.classifier_confidence_threshold = 0.7
            mock_settings.return_value.openai_model = "gpt-4o"
            mock_settings.return_value.openai_api_key = "sk-test"

            chain_mock = AsyncMock(return_value=mock_response)
            mock_llm = MagicMock()
            mock_llm_cls.return_value = mock_llm

            with patch("src.pipeline.nodes.CLASSIFIER_PROMPT") as mock_prompt:
                mock_prompt.__or__ = MagicMock(return_value=chain_mock)

                state = make_state()
                result = await classify_node(state)

        assert result["is_worth_remembering"] is False

    @pytest.mark.asyncio
    async def test_classify_handles_llm_error(self):
        with patch("src.pipeline.nodes.get_settings") as mock_settings, \
             patch("src.pipeline.nodes.ChatOpenAI") as mock_llm_cls:
            mock_settings.return_value.classifier_confidence_threshold = 0.7
            mock_settings.return_value.openai_model = "gpt-4o"
            mock_settings.return_value.openai_api_key = "sk-test"

            chain_mock = AsyncMock(side_effect=Exception("LLM unavailable"))
            mock_llm = MagicMock()
            mock_llm_cls.return_value = mock_llm

            with patch("src.pipeline.nodes.CLASSIFIER_PROMPT") as mock_prompt:
                mock_prompt.__or__ = MagicMock(return_value=chain_mock)

                state = make_state()
                result = await classify_node(state)

        assert result["is_worth_remembering"] is False
        assert result["error"] is None  # error field not set in classify, just returns safe default


# ---- Extract node tests ----


class TestExtractNode:
    @pytest.mark.asyncio
    async def test_extract_populates_state(self):
        mock_response = MagicMock()
        mock_response.content = """{
            "summary": "The team decided to launch on Jan 15. Alice leads rollout.",
            "entities": [
                {"name": "Alice", "type": "person"},
                {"name": "Product Launch", "type": "project"}
            ],
            "key_facts": ["Launch date: January 15", "Alice leads rollout"]
        }"""

        with patch("src.pipeline.nodes.get_settings") as mock_settings, \
             patch("src.pipeline.nodes.ChatOpenAI") as mock_llm_cls:
            mock_settings.return_value.openai_model = "gpt-4o"
            mock_settings.return_value.openai_api_key = "sk-test"

            chain_mock = AsyncMock(return_value=mock_response)
            mock_llm = MagicMock()
            mock_llm_cls.return_value = mock_llm

            with patch("src.pipeline.nodes.EXTRACTOR_PROMPT") as mock_prompt:
                mock_prompt.__or__ = MagicMock(return_value=chain_mock)

                state = make_state(is_worth_remembering=True, confidence=0.85)
                result = await extract_node(state)

        assert result["summary"] == "The team decided to launch on Jan 15. Alice leads rollout."
        assert len(result["entities"]) == 2
        assert len(result["extracted_facts"]) == 2


# ---- Deduplicate node tests ----


class TestDeduplicateNode:
    @pytest.mark.asyncio
    async def test_deduplicate_not_duplicate(self):
        with patch("src.pipeline.nodes.get_settings"), \
             patch("src.pipeline.nodes.GBrainMCPClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.search.return_value = [{"slug": "some/page", "score": 0.5}]
            mock_client_cls.return_value = mock_client

            state = make_state(summary="New unique content about something fresh")
            result = await deduplicate_node(state)

        assert result["is_duplicate"] is False
        assert len(result["existing_similar_pages"]) == 0

    @pytest.mark.asyncio
    async def test_deduplicate_is_duplicate(self):
        with patch("src.pipeline.nodes.get_settings"), \
             patch("src.pipeline.nodes.GBrainMCPClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.search.return_value = [{"slug": "existing/page", "score": 0.95}]
            mock_client_cls.return_value = mock_client

            state = make_state(summary="Duplicate content")
            result = await deduplicate_node(state)

        assert result["is_duplicate"] is True

    @pytest.mark.asyncio
    async def test_deduplicate_search_failure_not_duplicate(self):
        with patch("src.pipeline.nodes.get_settings"), \
             patch("src.pipeline.nodes.GBrainMCPClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.search.side_effect = Exception("Search unavailable")
            mock_client_cls.return_value = mock_client

            state = make_state(summary="Some content")
            result = await deduplicate_node(state)

        assert result["is_duplicate"] is False


# ---- Write node tests ----


class TestWriteNode:
    @pytest.mark.asyncio
    async def test_write_success(self):
        with patch("src.pipeline.nodes.get_settings"), \
             patch("src.pipeline.nodes.GBrainMCPClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.put_page.return_value = {"slug": "gmail/2024-01-10/launch-decision"}
            mock_client_cls.return_value = mock_client

            state = make_state(
                is_worth_remembering=True,
                confidence=0.9,
                summary="Launch decision summary",
                entities=[{"name": "Alice", "type": "person"}],
                extracted_facts=[{"fact": "Launch on Jan 15"}],
            )
            result = await write_node(state)

        assert result["write_status"] == "success"
        assert result["gbrain_page_slug"] is not None

    @pytest.mark.asyncio
    async def test_write_failure_logs_to_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        with patch("src.pipeline.nodes.get_settings"), \
             patch("src.pipeline.nodes.GBrainMCPClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.put_page.side_effect = RuntimeError("GBrain down")
            mock_client_cls.return_value = mock_client

            state = make_state(
                is_worth_remembering=True,
                confidence=0.9,
                summary="Some content",
                entities=[],
                extracted_facts=[],
            )
            result = await write_node(state)

        assert result["write_status"] == "failed"
        assert (tmp_path / "failed_writes.jsonl").exists()


# ---- Page builder tests ----


class TestPageBuilder:
    def test_build_slug_format(self):
        state = make_state(
            summary="Launch decision",
            entities=[{"name": "Alice", "type": "person"}],
            extracted_facts=[{"fact": "Launch Jan 15"}],
            confidence=0.9,
        )
        slug, content = build_gbrain_page(state)
        assert slug.startswith("gmail/2024-01-10/")
        assert "launch-decision" in slug

    def test_build_content_has_frontmatter(self):
        state = make_state(
            summary="Test summary",
            entities=[],
            extracted_facts=[],
            confidence=0.85,
        )
        _, content = build_gbrain_page(state)
        assert "---" in content
        assert "type: email" in content
        assert "source: gmail" in content
        assert "confidence: 0.85" in content

    def test_build_content_has_sections(self):
        state = make_state(
            summary="Decision was made.",
            entities=[{"name": "Bob", "type": "person"}],
            extracted_facts=[{"fact": "Key decision made"}],
            confidence=0.9,
        )
        _, content = build_gbrain_page(state)
        assert "## Key Facts" in content
        assert "## Entities Mentioned" in content
        assert "## Raw Content" in content

    def test_slugify_special_chars(self):
        state = make_state(
            subject="Q2 Budget: Final Call! (2024)",
            summary="",
            entities=[],
            extracted_facts=[],
        )
        slug, _ = build_gbrain_page(state)
        assert "!" not in slug
        assert "(" not in slug
        assert ":" not in slug


# ---- Full graph integration test ----


class TestExtractionGraph:
    @pytest.mark.asyncio
    async def test_graph_skips_on_not_worth_remembering(self):
        graph = build_extraction_graph()

        classify_response = MagicMock()
        classify_response.content = '{"worth_remembering": false, "confidence": 0.95, "reasoning": "Automated status update."}'

        with patch("src.pipeline.nodes.get_settings") as mock_settings, \
             patch("src.pipeline.nodes.ChatOpenAI") as mock_llm_cls:
            mock_settings.return_value.classifier_confidence_threshold = 0.7
            mock_settings.return_value.openai_model = "gpt-4o"
            mock_settings.return_value.openai_api_key = "sk-test"

            chain_mock = AsyncMock(return_value=classify_response)
            mock_llm = MagicMock()
            mock_llm_cls.return_value = mock_llm

            with patch("src.pipeline.nodes.CLASSIFIER_PROMPT") as mock_prompt:
                mock_prompt.__or__ = MagicMock(return_value=chain_mock)

                initial = make_state()
                result = await graph.ainvoke(initial)

        assert result["is_worth_remembering"] is False
        assert result["write_status"] is None

    @pytest.mark.asyncio
    async def test_graph_skips_write_on_duplicate(self):
        graph = build_extraction_graph()

        classify_resp = MagicMock()
        classify_resp.content = '{"worth_remembering": true, "confidence": 0.9, "reasoning": "Important."}'
        extract_resp = MagicMock()
        extract_resp.content = '{"summary": "Summary here.", "entities": [], "key_facts": ["fact1"]}'

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return classify_resp if call_count == 1 else extract_resp

        with patch("src.pipeline.nodes.get_settings") as mock_settings, \
             patch("src.pipeline.nodes.ChatOpenAI") as mock_llm_cls, \
             patch("src.pipeline.nodes.GBrainMCPClient") as mock_client_cls:
            mock_settings.return_value.classifier_confidence_threshold = 0.7
            mock_settings.return_value.openai_model = "gpt-4o"
            mock_settings.return_value.openai_api_key = "sk-test"

            chain_mock = AsyncMock(side_effect=side_effect)
            mock_llm = MagicMock()
            mock_llm_cls.return_value = mock_llm

            mock_client = AsyncMock()
            mock_client.search.return_value = [{"slug": "existing/page", "score": 0.95}]
            mock_client_cls.return_value = mock_client

            with patch("src.pipeline.nodes.CLASSIFIER_PROMPT") as cp, \
                 patch("src.pipeline.nodes.EXTRACTOR_PROMPT") as ep:
                cp.__or__ = MagicMock(return_value=chain_mock)
                ep.__or__ = MagicMock(return_value=chain_mock)

                initial = make_state()
                result = await graph.ainvoke(initial)

        assert result["is_duplicate"] is True
        assert result["write_status"] is None
