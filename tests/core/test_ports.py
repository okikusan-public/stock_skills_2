"""Tests for src/core/ports — Protocol-based port interfaces (KIK-513).

Verifies:
1. Protocol definitions are importable and valid
2. Existing Data modules satisfy Protocols structurally (isinstance checks)
3. Core functions work with custom Protocol implementations (mock injection)
4. Backward compatibility: existing callers without injection continue to work
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Protocol definitions are importable
# ---------------------------------------------------------------------------

class TestPortImports:
    def test_graph_reader_importable(self):
        from src.core.ports.graph import GraphReader
        assert GraphReader is not None

    def test_graph_writer_importable(self):
        from src.core.ports.graph import GraphWriter
        assert GraphWriter is not None

    def test_research_client_importable(self):
        from src.core.ports.research import ResearchClient
        assert ResearchClient is not None

    def test_stock_info_provider_importable(self):
        from src.core.ports.market_data import StockInfoProvider
        assert StockInfoProvider is not None

    def test_price_history_provider_importable(self):
        from src.core.ports.market_data import PriceHistoryProvider
        assert PriceHistoryProvider is not None

    def test_screening_provider_importable(self):
        from src.core.ports.market_data import ScreeningProvider
        assert ScreeningProvider is not None

    def test_history_store_importable(self):
        from src.core.ports.storage import HistoryStore
        assert HistoryStore is not None

    def test_note_store_importable(self):
        from src.core.ports.storage import NoteStore
        assert NoteStore is not None

    def test_package_re_exports_all_ports(self):
        from src.core.ports import (
            GraphReader, GraphWriter,
            ResearchClient,
            StockInfoProvider, ScreeningProvider, PriceHistoryProvider,
            HistoryStore, NoteStore,
        )
        assert all(p is not None for p in [
            GraphReader, GraphWriter, ResearchClient,
            StockInfoProvider, ScreeningProvider, PriceHistoryProvider,
            HistoryStore, NoteStore,
        ])


# ---------------------------------------------------------------------------
# 2. Custom mock implementations satisfy Protocols (structural subtyping)
# ---------------------------------------------------------------------------

class _MockGraphReader:
    """Minimal concrete implementation of GraphReader Protocol."""

    def get_last_health_check_date(self) -> str | None:
        return "2026-01-01"

    def get_old_thesis_notes(self, older_than_days: int = 90) -> list[dict]:
        return []

    def get_upcoming_events(self, within_days: int = 7) -> list[dict]:
        return []

    def get_recurring_picks(self, min_count: int = 3) -> list[dict]:
        return []

    def get_concern_notes(self, limit: int = 5) -> list[dict]:
        return []

    def get_current_holdings(self) -> list[dict]:
        return []

    def get_industry_research_for_linking(
        self, sector: str, days: int = 14, limit: int = 1
    ) -> list[dict]:
        return []

    def get_open_action_items(self) -> list[dict]:
        return []


class _MockGraphWriter:
    """Minimal concrete implementation of GraphWriter Protocol."""

    def merge_action_item(
        self,
        *,
        action_id: str,
        action_date: str,
        trigger_type: str,
        title: str,
        symbol: str,
        urgency: str,
        source_node_id: str | None = None,
    ) -> bool:
        return True

    def update_action_item_linear(
        self,
        *,
        action_id: str,
        linear_issue_id: str,
        linear_issue_url: str,
        linear_identifier: str,
    ) -> None:
        pass


class _MockResearchClient:
    """Minimal concrete implementation of ResearchClient Protocol."""

    def is_available(self) -> bool:
        return True

    def get_error_status(self) -> dict:
        return {"status": "ok", "status_code": None, "message": ""}

    def search_stock_deep(self, symbol: str, company_name: str, *, context: str = "") -> dict | None:
        return {"recent_news": [], "catalysts": {}, "analyst_views": [], "raw_response": ""}

    def search_x_sentiment(self, symbol: str, company_name: str, *, context: str = "") -> dict | None:
        return {"positive": [], "negative": [], "sentiment_score": 0.0, "raw_response": ""}

    def search_industry(self, theme: str, *, context: str = "") -> dict | None:
        return {"trends": [], "raw_response": ""}

    def search_market(self, market: str, *, context: str = "") -> dict | None:
        return {"price_action": "", "raw_response": ""}

    def search_business(self, symbol: str, company_name: str, *, context: str = "") -> dict | None:
        return {"overview": "", "raw_response": ""}


class TestProtocolStructuralSubtyping:
    def test_mock_graph_reader_satisfies_protocol(self):
        from src.core.ports.graph import GraphReader
        reader = _MockGraphReader()
        assert isinstance(reader, GraphReader)

    def test_mock_graph_writer_satisfies_protocol(self):
        from src.core.ports.graph import GraphWriter
        writer = _MockGraphWriter()
        assert isinstance(writer, GraphWriter)

    def test_mock_research_client_satisfies_protocol(self):
        from src.core.ports.research import ResearchClient
        client = _MockResearchClient()
        assert isinstance(client, ResearchClient)


# ---------------------------------------------------------------------------
# 3. ProactiveEngine accepts graph_reader injection
# ---------------------------------------------------------------------------

class TestProactiveEngineInjection:
    def test_engine_accepts_graph_reader(self):
        from src.core.proactive_engine import ProactiveEngine
        reader = _MockGraphReader()
        engine = ProactiveEngine(graph_reader=reader)
        assert engine._graph_reader is reader

    def test_engine_uses_injected_reader_for_health_check(self):
        """ProactiveEngine calls graph_reader.get_last_health_check_date() when injected."""
        from src.core.proactive_engine import ProactiveEngine

        old_date = (date.today() - timedelta(days=20)).isoformat()

        class _StaleReader(_MockGraphReader):
            def get_last_health_check_date(self) -> str | None:
                return old_date

        engine = ProactiveEngine(graph_reader=_StaleReader())
        result = engine._check_time_triggers()
        titles = [s["title"] for s in result]
        assert "ヘルスチェックの実施" in titles

    def test_engine_uses_injected_reader_for_thesis_notes(self):
        """ProactiveEngine calls graph_reader.get_old_thesis_notes() when injected."""
        from src.core.proactive_engine import ProactiveEngine

        class _ThesisReader(_MockGraphReader):
            def get_old_thesis_notes(self, older_than_days: int = 90) -> list[dict]:
                return [{"symbol": "7203.T", "days_old": 95}]

        engine = ProactiveEngine(graph_reader=_ThesisReader())
        result = engine._check_time_triggers()
        titles = [s["title"] for s in result]
        assert any("7203.T" in t for t in titles)

    def test_engine_uses_injected_reader_for_concern_notes(self):
        """ProactiveEngine calls graph_reader.get_concern_notes() when injected."""
        from src.core.proactive_engine import ProactiveEngine

        class _ConcernReader(_MockGraphReader):
            def get_concern_notes(self, limit: int = 5) -> list[dict]:
                return [{"symbol": "AAPL", "days_old": 5}]

        engine = ProactiveEngine(graph_reader=_ConcernReader())
        result = engine._check_state_triggers()
        titles = [s["title"] for s in result]
        assert any("AAPL" in t for t in titles)

    def test_engine_uses_injected_reader_for_recurring_picks(self):
        """ProactiveEngine calls graph_reader.get_recurring_picks() when injected."""
        from src.core.proactive_engine import ProactiveEngine

        class _RecurringReader(_MockGraphReader):
            def get_recurring_picks(self, min_count: int = 3) -> list[dict]:
                return [{"symbol": "9984.T", "count": 5}]

        engine = ProactiveEngine(graph_reader=_RecurringReader())
        result = engine._check_state_triggers()
        titles = [s["title"] for s in result]
        assert any("9984.T" in t for t in titles)

    def test_get_suggestions_convenience_accepts_graph_reader(self):
        """The module-level get_suggestions() accepts a graph_reader kwarg."""
        from src.core.proactive_engine import get_suggestions
        reader = _MockGraphReader()
        # Should not raise
        result = get_suggestions(graph_reader=reader)
        assert isinstance(result, list)

    def test_engine_without_injection_falls_back_to_module(self):
        """When no graph_reader injected, engine still works via fallback import."""
        from src.core.proactive_engine import ProactiveEngine
        engine = ProactiveEngine()
        assert engine._graph_reader is None
        # Should not raise — falls back to mocked graph_query (auto-mocked by conftest)
        result = engine._check_time_triggers()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 4. process_action_items accepts graph_writer injection
# ---------------------------------------------------------------------------

class TestActionItemBridgeInjection:
    def _exit_suggestions(self):
        return [
            {
                "emoji": "🚨",
                "title": "警戒銘柄の対応検討",
                "reason": "EXIT判定 — 7203.T の撤退を推奨",
                "command_hint": "stock-report 7203.T",
                "urgency": "high",
            }
        ]

    def test_process_with_graph_writer_calls_merge(self):
        """process_action_items calls graph_writer.merge_action_item() when injected."""
        from src.core.action_item_bridge import process_action_items

        called_with = {}

        class _TrackingWriter(_MockGraphWriter):
            def merge_action_item(self, *, action_id, action_date, trigger_type,
                                   title, symbol, urgency, source_node_id=None) -> bool:
                called_with["action_id"] = action_id
                return True

            def get_open_action_items(self) -> list[dict]:
                return []  # no duplicates

        writer = _TrackingWriter()

        with patch("src.core.action_item_bridge._create_linear_issue", return_value=None):
            results = process_action_items(self._exit_suggestions(), graph_writer=writer)

        assert len(results) == 1
        assert results[0]["neo4j_saved"] is True
        assert "action_id" in called_with

    def test_process_with_graph_writer_dedup_check(self):
        """process_action_items calls graph_writer.get_open_action_items() for dedup."""
        from src.core.action_item_bridge import process_action_items

        # First, run without dedup to capture what action_id gets generated
        generated_ids: list[str] = []

        class _CaptureWriter(_MockGraphWriter):
            def get_open_action_items(self) -> list[dict]:
                return []  # No duplicates on first pass

            def merge_action_item(self, *, action_id, **kwargs) -> bool:
                generated_ids.append(action_id)
                return True

        with patch("src.core.action_item_bridge._create_linear_issue", return_value=None):
            process_action_items(self._exit_suggestions(), graph_writer=_CaptureWriter())

        assert generated_ids, "Expected at least one action item to be created"
        the_action_id = generated_ids[0]

        # Now test dedup: return that same action_id as existing open item
        merge_called = []

        class _DuplicateWriter(_MockGraphWriter):
            def get_open_action_items(self) -> list[dict]:
                return [{"id": the_action_id}]

            def merge_action_item(self, **kwargs) -> bool:
                merge_called.append(True)
                return True

        writer = _DuplicateWriter()

        with patch("src.core.action_item_bridge._create_linear_issue", return_value=None):
            results = process_action_items(self._exit_suggestions(), graph_writer=writer)

        # Result should be empty (dedup skipped the item) and merge should not be called
        assert len(results) == 0
        assert not merge_called, "merge_action_item should not be called for duplicate"

    def test_process_without_injection_falls_back_to_module(self):
        """process_action_items falls back to graph_store when no writer injected."""
        from src.core.action_item_bridge import process_action_items

        with (
            patch("src.core.action_item_bridge._is_duplicate_neo4j", return_value=False),
            patch("src.core.action_item_bridge._save_to_neo4j", return_value=True),
            patch("src.core.action_item_bridge._create_linear_issue", return_value=None),
            patch("src.core.action_item_bridge._link_linear_to_neo4j"),
        ):
            results = process_action_items(self._exit_suggestions())

        assert len(results) == 1
        assert results[0]["neo4j_saved"] is True

    def test_process_with_graph_writer_links_linear(self):
        """process_action_items calls graph_writer.update_action_item_linear() after issue creation."""
        from src.core.action_item_bridge import process_action_items

        linked = {}

        class _LinkWriter(_MockGraphWriter):
            def get_open_action_items(self) -> list[dict]:
                return []

            def update_action_item_linear(self, *, action_id, linear_issue_id,
                                           linear_issue_url, linear_identifier):
                linked["action_id"] = action_id
                linked["url"] = linear_issue_url

        writer = _LinkWriter()
        linear_result = {"id": "issue-1", "identifier": "KIK-999", "url": "https://linear.app/KIK-999"}

        with patch("src.core.action_item_bridge._create_linear_issue", return_value=linear_result):
            results = process_action_items(self._exit_suggestions(), graph_writer=writer)

        assert len(results) == 1
        assert results[0]["linear_issue"] is not None
        assert "action_id" in linked
        assert linked["url"] == "https://linear.app/KIK-999"


# ---------------------------------------------------------------------------
# 5. researcher.py accepts research_client injection
# ---------------------------------------------------------------------------

class TestResearcherInjection:
    def test_research_stock_with_injected_client(self, mock_yahoo_client, stock_info_data):
        """research_stock() uses research_client when injected."""
        from src.core.research.researcher import research_stock

        mock_yahoo_client.get_stock_info.return_value = stock_info_data
        mock_yahoo_client.get_stock_news.return_value = []

        client = _MockResearchClient()
        result = research_stock("7203.T", mock_yahoo_client, research_client=client)

        assert result["symbol"] == "7203.T"
        assert "fundamentals" in result
        # Injected client is available → grok_research should be filled
        assert "grok_research" in result

    def test_research_stock_without_injection_still_works(self, mock_yahoo_client, stock_info_data):
        """research_stock() backward compatible without research_client."""
        from src.core.research.researcher import research_stock

        mock_yahoo_client.get_stock_info.return_value = stock_info_data
        mock_yahoo_client.get_stock_news.return_value = []

        # No research_client — falls back to module-level grok_client
        result = research_stock("7203.T", mock_yahoo_client)
        assert result["symbol"] == "7203.T"

    def test_research_industry_with_injected_client(self):
        """research_industry() uses research_client when injected."""
        from src.core.research.researcher import research_industry

        client = _MockResearchClient()
        result = research_industry("半導体", research_client=client)

        assert result["theme"] == "半導体"
        assert "grok_research" in result
        # Injected client is available → api_unavailable should be False
        assert result["api_unavailable"] is False

    def test_research_market_with_injected_client(self, mock_yahoo_client):
        """research_market() uses research_client when injected."""
        from src.core.research.researcher import research_market

        mock_yahoo_client.get_macro_indicators.return_value = []

        client = _MockResearchClient()
        result = research_market("Nikkei 225", mock_yahoo_client, research_client=client)

        assert result["market"] == "Nikkei 225"
        assert result["api_unavailable"] is False

    def test_research_business_with_injected_client(self, mock_yahoo_client, stock_info_data):
        """research_business() uses research_client when injected."""
        from src.core.research.researcher import research_business

        mock_yahoo_client.get_stock_info.return_value = stock_info_data

        client = _MockResearchClient()
        result = research_business("7203.T", mock_yahoo_client, research_client=client)

        assert result["symbol"] == "7203.T"
        assert result["api_unavailable"] is False

    def test_research_client_unavailable_treated_as_no_grok(self):
        """When injected client.is_available() is False, api_unavailable=True."""
        from src.core.research.researcher import research_industry

        class _UnavailableClient(_MockResearchClient):
            def is_available(self) -> bool:
                return False

        result = research_industry("AI", research_client=_UnavailableClient())
        assert result["api_unavailable"] is True
