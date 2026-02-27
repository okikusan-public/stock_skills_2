"""Tests for KIK-413 full-mode functions in src.data.graph_store.

Neo4j driver is mocked -- no real database connection needed.
Tests cover: _get_mode(), mode=off guards, merge_*_full() functions.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.no_auto_mock


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(autouse=True)
def reset_driver_and_mode():
    """Reset global _driver and mode cache before each test."""
    import src.data.graph_store as gs
    gs._driver = None
    gs._mode_cache = ("", 0.0)
    yield
    gs._driver = None
    gs._mode_cache = ("", 0.0)
    # Clean up env
    os.environ.pop("NEO4J_MODE", None)


@pytest.fixture
def mock_driver():
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


@pytest.fixture
def gs_full(mock_driver):
    """Set up graph_store with mock driver and full mode."""
    import src.data.graph_store as gs
    driver, session = mock_driver
    gs._driver = driver
    os.environ["NEO4J_MODE"] = "full"
    return gs, driver, session


@pytest.fixture
def gs_summary(mock_driver):
    """Set up graph_store with mock driver and summary mode."""
    import src.data.graph_store as gs
    driver, session = mock_driver
    gs._driver = driver
    os.environ["NEO4J_MODE"] = "summary"
    return gs, driver, session


@pytest.fixture
def gs_off():
    """Set up graph_store with off mode (no driver needed)."""
    import src.data.graph_store as gs
    os.environ["NEO4J_MODE"] = "off"
    return gs


# ===================================================================
# _get_mode tests
# ===================================================================

class TestGetMode:
    def test_env_off(self):
        import src.data.graph_store as gs
        os.environ["NEO4J_MODE"] = "off"
        assert gs._get_mode() == "off"

    def test_env_summary(self):
        import src.data.graph_store as gs
        os.environ["NEO4J_MODE"] = "summary"
        assert gs._get_mode() == "summary"

    def test_env_full(self):
        import src.data.graph_store as gs
        os.environ["NEO4J_MODE"] = "full"
        assert gs._get_mode() == "full"

    def test_env_case_insensitive(self):
        import src.data.graph_store as gs
        os.environ["NEO4J_MODE"] = "FULL"
        assert gs._get_mode() == "full"

    def test_auto_detect_available(self):
        import src.data.graph_store as gs
        os.environ.pop("NEO4J_MODE", None)
        gs._mode_cache = ("", 0.0)
        with patch.object(gs, "is_available", return_value=True):
            assert gs._get_mode() == "full"

    def test_auto_detect_unavailable(self):
        import src.data.graph_store as gs
        os.environ.pop("NEO4J_MODE", None)
        gs._mode_cache = ("", 0.0)
        with patch.object(gs, "is_available", return_value=False):
            assert gs._get_mode() == "off"

    def test_cache_hit(self):
        import src.data.graph_store as gs
        import time
        os.environ.pop("NEO4J_MODE", None)
        gs._mode_cache = ("summary", time.time())
        assert gs._get_mode() == "summary"

    def test_public_accessor(self):
        import src.data.graph_store as gs
        os.environ["NEO4J_MODE"] = "full"
        assert gs.get_mode() == "full"


# ===================================================================
# Mode=off guard tests
# ===================================================================

class TestModeOffGuard:
    def test_merge_stock_off(self, gs_off):
        assert gs_off.merge_stock("7203.T") is False

    def test_merge_screen_off(self, gs_off):
        assert gs_off.merge_screen("2025-01-01", "value", "japan", 5, ["7203.T"]) is False

    def test_merge_report_off(self, gs_off):
        assert gs_off.merge_report("2025-01-01", "7203.T", 50.0, "test") is False

    def test_merge_trade_off(self, gs_off):
        assert gs_off.merge_trade("2025-01-01", "buy", "7203.T", 100, 2850, "JPY") is False

    def test_merge_health_off(self, gs_off):
        assert gs_off.merge_health("2025-01-01", {}, ["7203.T"]) is False

    def test_merge_note_off(self, gs_off):
        assert gs_off.merge_note("id1", "2025-01-01", "thesis", "test") is False

    def test_tag_theme_off(self, gs_off):
        assert gs_off.tag_theme("7203.T", "AI") is False

    def test_merge_research_off(self, gs_off):
        assert gs_off.merge_research("2025-01-01", "stock", "7203.T") is False

    def test_merge_watchlist_off(self, gs_off):
        assert gs_off.merge_watchlist("test", ["7203.T"]) is False

    def test_link_research_supersedes_off(self, gs_off):
        assert gs_off.link_research_supersedes("stock", "7203.T") is False

    def test_merge_market_context_off(self, gs_off):
        assert gs_off.merge_market_context("2025-01-01", []) is False


# ===================================================================
# merge_report_full tests
# ===================================================================

class TestMergeReportFull:
    def test_full_mode_sets_extended_props(self, gs_full):
        gs, _, session = gs_full
        result = gs.merge_report_full(
            "2025-01-01", "7203.T", 72.5, "割安",
            price=2850.0, per=8.5, pbr=0.9,
            dividend_yield=0.032, roe=12.5, market_cap=30000000000000,
        )
        assert result is True
        # merge_report base call + SET extended props = at least 3 session.run calls
        assert session.run.call_count >= 3

    def test_summary_mode_falls_back(self, gs_summary):
        gs, _, session = gs_summary
        result = gs.merge_report_full(
            "2025-01-01", "7203.T", 72.5, "割安",
            price=2850.0,
        )
        assert result is True
        # Should only call base merge_report (2 runs: MERGE report + MERGE ANALYZED)
        assert session.run.call_count == 2

    def test_off_mode_returns_false(self, gs_off):
        result = gs_off.merge_report_full("2025-01-01", "7203.T", 50, "test")
        assert result is False


# ===================================================================
# merge_research_full tests
# ===================================================================

class TestMergeResearchFull:
    def test_full_mode_creates_sub_nodes(self, gs_full):
        gs, _, session = gs_full
        grok = {
            "recent_news": ["News headline 1", "News headline 2"],
            "x_sentiment": {"score": 0.7, "summary": "Bullish"},
            "catalysts": {
                "positive": ["Strong demand"],
                "negative": ["Regulation risk"],
            },
            "analyst_views": ["Consensus Buy, PT $200"],
        }
        x_sent = {"positive": ["Institutional buying"], "negative": ["High valuation"]}
        news = [{"title": "NVDA earnings beat", "publisher": "Reuters", "link": "http://example.com"}]

        result = gs.merge_research_full(
            "2025-01-01", "stock", "NVDA", "Strong AI play",
            grok_research=grok, x_sentiment=x_sent, news=news,
        )
        assert result is True
        # Base: MERGE research + MERGE RESEARCHED = 2
        # News: 2 grok + 1 yahoo = 3 news + 3 MENTIONS = 6
        # Sentiment: grok + yahoo = 2
        # Catalysts: 1 pos + 1 neg = 2
        # AnalystView: 1
        # Total >= 13
        assert session.run.call_count >= 10

    def test_full_mode_no_grok(self, gs_full):
        gs, _, session = gs_full
        result = gs.merge_research_full(
            "2025-01-01", "stock", "7203.T", "Basic",
        )
        assert result is True
        # Only base merge_research calls
        assert session.run.call_count == 2

    def test_summary_mode_falls_back(self, gs_summary):
        gs, _, session = gs_summary
        result = gs.merge_research_full(
            "2025-01-01", "stock", "7203.T", "Test",
            grok_research={"recent_news": ["headline"]},
        )
        assert result is True
        # Should only call base merge_research
        assert session.run.call_count == 2

    def test_market_type_no_mentions(self, gs_full):
        gs, _, session = gs_full
        grok = {"recent_news": ["Market headline"]}
        result = gs.merge_research_full(
            "2025-01-01", "market", "金相場", "",
            grok_research=grok,
        )
        assert result is True
        # No MENTIONS relationship for market type
        calls_str = str(session.run.call_args_list)
        assert "MENTIONS" not in calls_str

    def test_market_research_creates_sub_nodes(self, gs_full):
        """KIK-430: market research expands Sentiment/UpcomingEvent/SectorRotation/Indicator."""
        gs, _, session = gs_full
        grok = {
            "sentiment": {"score": 0.6, "summary": "やや強気"},
            "upcoming_events": ["FOMC 3/20", "日銀決定会合 3/14"],
            "sector_rotation": ["ハイテク→バリュー"],
            "macro_factors": ["米金利上昇", "円安進行"],
        }
        result = gs.merge_research_full(
            "2025-03-01", "market", "日経平均", "Market overview",
            grok_research=grok,
        )
        assert result is True
        calls_str = str(session.run.call_args_list)
        # Sentiment
        assert "Sentiment" in calls_str
        assert "market_research" in calls_str
        # UpcomingEvent
        assert "UpcomingEvent" in calls_str
        assert "FOMC" in calls_str
        # SectorRotation
        assert "SectorRotation" in calls_str
        # Indicator (macro_factors)
        assert "Indicator" in calls_str
        assert "INCLUDES" in calls_str

    def test_industry_research_creates_sub_nodes(self, gs_full):
        """KIK-430: industry research expands Catalyst nodes + key_player MENTIONS."""
        gs, _, session = gs_full
        grok = {
            "trends": ["AI需要拡大", "微細化競争"],
            "key_players": [
                {"name": "NVIDIA", "symbol": "NVDA"},
                {"name": "TSMC", "symbol": "TSM"},
            ],
            "growth_drivers": ["データセンター投資"],
            "risks": ["米中対立"],
            "regulatory": ["輸出規制強化"],
        }
        result = gs.merge_research_full(
            "2025-03-01", "industry", "半導体", "Industry overview",
            grok_research=grok,
        )
        assert result is True
        calls_str = str(session.run.call_args_list)
        # Catalyst nodes
        assert "Catalyst" in calls_str
        assert "trend" in calls_str
        assert "growth_driver" in calls_str
        assert "risk" in calls_str
        assert "regulatory" in calls_str
        # key_players MENTIONS
        assert "MENTIONS" in calls_str
        assert "NVDA" in calls_str

    def test_industry_key_players_string(self, gs_full):
        """KIK-430: key_players as list of strings."""
        gs, _, session = gs_full
        grok = {
            "key_players": ["NVIDIA", "AMD"],
        }
        result = gs.merge_research_full(
            "2025-03-01", "industry", "半導体", "",
            grok_research=grok,
        )
        assert result is True
        calls_str = str(session.run.call_args_list)
        assert "MENTIONS" in calls_str
        assert "NVIDIA" in calls_str


# ===================================================================
# merge_market_context_full tests
# ===================================================================

class TestMergeMarketContextFull:
    def test_full_mode_creates_sub_nodes(self, gs_full):
        gs, _, session = gs_full
        indices = [
            {"name": "S&P500", "symbol": "^GSPC", "price": 5800, "daily_change": 0.5, "weekly_change": 1.2},
            {"name": "日経平均", "symbol": "^N225", "price": 40000, "daily_change": -0.3, "weekly_change": 0.8},
        ]
        grok = {
            "upcoming_events": ["FOMC meeting 3/20", "BOJ meeting 3/13"],
            "sector_rotation": ["Tech to Value"],
            "sentiment": {"score": 0.5, "summary": "Neutral"},
        }
        result = gs.merge_market_context_full(
            "2025-01-01", indices, grok_research=grok,
        )
        assert result is True
        # Base: MERGE MarketContext = 1
        # Indicator: 2
        # UpcomingEvent: 2
        # SectorRotation: 1
        # Sentiment: 1
        # Total >= 7
        assert session.run.call_count >= 7

    def test_full_mode_no_grok(self, gs_full):
        gs, _, session = gs_full
        indices = [{"name": "S&P500", "price": 5800}]
        result = gs.merge_market_context_full("2025-01-01", indices)
        assert result is True
        # Base MERGE + 1 indicator = 2
        assert session.run.call_count == 2

    def test_summary_mode_falls_back(self, gs_summary):
        gs, _, session = gs_summary
        result = gs.merge_market_context_full(
            "2025-01-01", [{"name": "test", "price": 100}],
            grok_research={"upcoming_events": ["event"]},
        )
        assert result is True
        # Only base merge_market_context
        assert session.run.call_count == 1

    def test_driver_error_returns_false(self, gs_full):
        gs, driver, session = gs_full
        session.run.side_effect = Exception("DB error")
        result = gs.merge_market_context_full("2025-01-01", [], grok_research={"upcoming_events": ["x"]})
        # Base merge_market_context fails → returns False, should not raise
        assert result is False


# ===================================================================
# _truncate tests
# ===================================================================

class TestTruncate:
    def test_short_string_unchanged(self):
        from src.data.graph_store import _truncate
        assert _truncate("hello") == "hello"

    def test_long_string_truncated(self):
        from src.data.graph_store import _truncate
        assert len(_truncate("a" * 600, 500)) == 500

    def test_empty_string(self):
        from src.data.graph_store import _truncate
        assert _truncate("") == ""

    def test_none_returns_empty(self):
        from src.data.graph_store import _truncate
        assert _truncate(None) == ""

    def test_non_string_converted(self):
        from src.data.graph_store import _truncate
        assert _truncate(12345) == "12345"

    def test_custom_max_len(self):
        from src.data.graph_store import _truncate
        assert _truncate("abcdefgh", 5) == "abcde"
