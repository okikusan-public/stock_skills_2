"""Tests for ThemeTrend Neo4j operations (KIK-603).

Tests merge_theme_trend (graph_store) and get_theme_trends / get_theme_trend_diff (graph_query).
Neo4j driver is mocked -- no real database connection needed.
"""

import pytest
from unittest.mock import MagicMock, patch, call

pytestmark = pytest.mark.no_auto_mock


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(autouse=True)
def reset_driver(monkeypatch):
    """Reset global _driver and mode cache before each test."""
    import src.data.graph_store as gs
    from src.data.graph_store import _common
    gs._driver = None
    _common._mode_cache = ("", 0.0)
    # Ensure NEO4J_MODE env is not set (might persist from _block_external_io)
    monkeypatch.delenv("NEO4J_MODE", raising=False)
    yield
    gs._driver = None
    _common._mode_cache = ("", 0.0)


@pytest.fixture
def mock_driver():
    """Provide a mock Neo4j driver with session context manager."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


@pytest.fixture
def gs_with_driver(mock_driver):
    """Set up graph_store with a mock driver already injected."""
    import src.data.graph_store as gs
    driver, session = mock_driver
    gs._driver = driver
    return gs, driver, session


# ===================================================================
# merge_theme_trend tests
# ===================================================================

class TestMergeThemeTrend:
    def test_merge_theme_trend_basic(self, gs_with_driver):
        gs, _, session = gs_with_driver
        result = gs.merge_theme_trend(
            theme="ai",
            date="2026-04-16",
            confidence=0.85,
            reason="AI investment boom",
            rank=1,
            region="japan",
        )
        assert result is True
        assert session.run.call_count == 1
        # Verify the Cypher contains MERGE ThemeTrend and Theme
        cypher = session.run.call_args[0][0]
        assert "ThemeTrend" in cypher
        assert "Theme" in cypher
        assert "FOR_THEME" in cypher

    def test_merge_theme_trend_id_format(self, gs_with_driver):
        gs, _, session = gs_with_driver
        gs.merge_theme_trend(
            theme="ev",
            date="2026-04-16",
            rank=2,
            region="us",
        )
        kwargs = session.run.call_args[1]
        assert kwargs["id"] == "theme_trend_2026-04-16_ev_us"

    def test_merge_theme_trend_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.merge_theme_trend(theme="ai", date="2026-04-16") is False

    def test_merge_theme_trend_mode_off(self, gs_with_driver):
        gs, _, session = gs_with_driver
        with patch("src.data.graph_store._common._get_mode", return_value="off"):
            assert gs.merge_theme_trend(theme="ai", date="2026-04-16") is False
        assert session.run.call_count == 0

    def test_merge_theme_trend_error(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("DB error")
        assert gs.merge_theme_trend(theme="ai", date="2026-04-16") is False

    def test_merge_theme_trend_updates_on_redetection(self, gs_with_driver):
        """MERGE semantics: re-detecting same theme+date+region updates the node."""
        gs, _, session = gs_with_driver
        # First call
        gs.merge_theme_trend(
            theme="ai", date="2026-04-16", confidence=0.8, rank=1, region="japan"
        )
        # Second call with updated confidence
        gs.merge_theme_trend(
            theme="ai", date="2026-04-16", confidence=0.95, rank=1, region="japan"
        )
        assert session.run.call_count == 2
        # Both use same id (MERGE ensures upsert)
        first_kwargs = session.run.call_args_list[0][1]
        second_kwargs = session.run.call_args_list[1][1]
        assert first_kwargs["id"] == second_kwargs["id"]
        assert second_kwargs["confidence"] == 0.95

    def test_merge_theme_trend_defaults(self, gs_with_driver):
        """Default values for optional parameters."""
        gs, _, session = gs_with_driver
        gs.merge_theme_trend(theme="biotech", date="2026-04-16")
        kwargs = session.run.call_args[1]
        assert kwargs["confidence"] == 0.0
        assert kwargs["reason"] == ""
        assert kwargs["rank"] == 0
        assert kwargs["region"] == ""


# ===================================================================
# get_theme_trends tests
# ===================================================================

class TestGetThemeTrends:
    def test_get_theme_trends_basic(self, gs_with_driver):
        _, driver, session = gs_with_driver
        from src.data.graph_query import market as gq_market

        mock_records = [
            {"date": "2026-04-16", "theme": "ai", "confidence": 0.9,
             "reason": "AI boom", "rank": 1, "region": "japan"},
            {"date": "2026-04-16", "theme": "ev", "confidence": 0.7,
             "reason": "EV push", "rank": 2, "region": "japan"},
        ]
        session.run.return_value = mock_records

        with patch("src.data.graph_query._common._get_driver", return_value=driver):
            result = gq_market.get_theme_trends(limit=10)

        assert len(result) == 2
        assert result[0]["theme"] == "ai"
        assert result[1]["theme"] == "ev"

    def test_get_theme_trends_with_region_filter(self, gs_with_driver):
        _, driver, session = gs_with_driver
        from src.data.graph_query import market as gq_market

        mock_records = [
            {"date": "2026-04-16", "theme": "ai", "confidence": 0.9,
             "reason": "AI boom", "rank": 1, "region": "us"},
        ]
        session.run.return_value = mock_records

        with patch("src.data.graph_query._common._get_driver", return_value=driver):
            result = gq_market.get_theme_trends(limit=10, region="us")

        assert len(result) == 1
        # Verify the WHERE clause contains region filter
        cypher = session.run.call_args[0][0]
        assert "region" in cypher

    def test_get_theme_trends_no_driver(self):
        from src.data.graph_query import market as gq_market
        with patch("src.data.graph_query._common._get_driver", return_value=None):
            assert gq_market.get_theme_trends() == []

    def test_get_theme_trends_error(self, gs_with_driver):
        _, driver, session = gs_with_driver
        from src.data.graph_query import market as gq_market
        session.run.side_effect = Exception("DB error")
        with patch("src.data.graph_query._common._get_driver", return_value=driver):
            assert gq_market.get_theme_trends() == []


# ===================================================================
# get_theme_trend_diff tests
# ===================================================================

class TestGetThemeTrendDiff:
    def test_get_theme_trend_diff_basic(self, gs_with_driver):
        _, driver, session = gs_with_driver
        from src.data.graph_query import market as gq_market

        # First call: distinct dates
        date_records = [{"date": "2026-04-16"}, {"date": "2026-04-09"}]
        # Second call: latest themes
        latest_records = [{"theme": "ai"}, {"theme": "ev"}, {"theme": "defense"}]
        # Third call: previous themes
        previous_records = [{"theme": "ai"}, {"theme": "biotech"}]

        session.run.side_effect = [date_records, latest_records, previous_records]

        with patch("src.data.graph_query._common._get_driver", return_value=driver):
            result = gq_market.get_theme_trend_diff()

        assert result["latest_date"] == "2026-04-16"
        assert result["previous_date"] == "2026-04-09"
        assert result["rising"] == ["defense", "ev"]
        assert result["falling"] == ["biotech"]
        assert result["stable"] == ["ai"]

    def test_get_theme_trend_diff_only_one_date(self, gs_with_driver):
        _, driver, session = gs_with_driver
        from src.data.graph_query import market as gq_market

        session.run.return_value = [{"date": "2026-04-16"}]

        with patch("src.data.graph_query._common._get_driver", return_value=driver):
            result = gq_market.get_theme_trend_diff()

        assert result == {}

    def test_get_theme_trend_diff_no_data(self, gs_with_driver):
        _, driver, session = gs_with_driver
        from src.data.graph_query import market as gq_market

        session.run.return_value = []

        with patch("src.data.graph_query._common._get_driver", return_value=driver):
            result = gq_market.get_theme_trend_diff()

        assert result == {}

    def test_get_theme_trend_diff_no_driver(self):
        from src.data.graph_query import market as gq_market
        with patch("src.data.graph_query._common._get_driver", return_value=None):
            assert gq_market.get_theme_trend_diff() == {}

    def test_get_theme_trend_diff_error(self, gs_with_driver):
        _, driver, session = gs_with_driver
        from src.data.graph_query import market as gq_market
        session.run.side_effect = Exception("DB error")
        with patch("src.data.graph_query._common._get_driver", return_value=driver):
            assert gq_market.get_theme_trend_diff() == {}


# ===================================================================
# nl_query integration tests
# ===================================================================

class TestNlQueryThemeTrend:
    def test_theme_trend_keyword_match(self):
        from src.data.graph_query.nl_query import _COMPILED
        patterns = {qtype for _, qtype, _ in _COMPILED}
        assert "theme_trends" in patterns

    def test_theme_trend_query_dispatch(self):
        """Verify nl_query dispatches to get_theme_trends for theme keywords."""
        from src.data.graph_query import nl_query

        mock_trends = [
            {"date": "2026-04-16", "theme": "ai", "confidence": 0.9,
             "reason": "AI boom", "rank": 1, "region": "japan"},
        ]

        with patch.object(nl_query.graph_query, "get_theme_trends", return_value=mock_trends):
            result = nl_query.query("テーマトレンド履歴")

        assert result is not None
        assert result["query_type"] == "theme_trends"
        assert len(result["result"]) == 1

    def test_theme_trend_formatter(self):
        from src.data.graph_query.nl_query import format_result
        trends = [
            {"date": "2026-04-16", "theme": "ai", "confidence": 0.85,
             "reason": "AI investment boom", "rank": 1, "region": "japan"},
        ]
        output = format_result("theme_trends", trends, {})
        assert "テーマトレンド履歴" in output
        assert "ai" in output
        assert "0.85" in output

    def test_theme_trend_formatter_empty(self):
        from src.data.graph_query.nl_query import format_result
        output = format_result("theme_trends", [], {})
        assert "見つかりませんでした" in output
