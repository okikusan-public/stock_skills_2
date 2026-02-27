"""Tests for KIK-413 semantic query functions in src.data.graph_query.

Neo4j driver is mocked -- no real database connection needed.
Tests cover: get_stock_news_history, get_sentiment_trend, get_catalysts,
get_report_trend, get_upcoming_events.
"""

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.no_auto_mock


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(autouse=True)
def reset_driver():
    import src.data.graph_store as gs
    gs._driver = None
    yield
    gs._driver = None


@pytest.fixture
def mock_session():
    """Provide a mock session via graph_store's driver."""
    import src.data.graph_store as gs
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    gs._driver = driver
    return session


# ===================================================================
# get_stock_news_history
# ===================================================================

class TestGetStockNewsHistory:
    def test_success(self, mock_session):
        from src.data.graph_query import get_stock_news_history
        mock_session.run.return_value = [
            {"date": "2025-01-15", "title": "NVDA earnings beat", "source": "grok"},
            {"date": "2025-01-14", "title": "AI demand surge", "source": "yahoo"},
        ]
        result = get_stock_news_history("NVDA")
        assert len(result) == 2
        assert result[0]["title"] == "NVDA earnings beat"

    def test_no_driver(self):
        from src.data.graph_query import get_stock_news_history
        with patch("src.data.graph_query._get_driver", return_value=None):
            assert get_stock_news_history("NVDA") == []

    def test_error(self, mock_session):
        from src.data.graph_query import get_stock_news_history
        mock_session.run.side_effect = Exception("DB error")
        assert get_stock_news_history("NVDA") == []


# ===================================================================
# get_sentiment_trend
# ===================================================================

class TestGetSentimentTrend:
    def test_success(self, mock_session):
        from src.data.graph_query import get_sentiment_trend
        mock_session.run.return_value = [
            {"date": "2025-01-15", "source": "grok_x", "score": 0.7, "summary": "Bullish"},
        ]
        result = get_sentiment_trend("NVDA")
        assert len(result) == 1
        assert result[0]["score"] == 0.7

    def test_no_driver(self):
        from src.data.graph_query import get_sentiment_trend
        with patch("src.data.graph_query._get_driver", return_value=None):
            assert get_sentiment_trend("NVDA") == []

    def test_error(self, mock_session):
        from src.data.graph_query import get_sentiment_trend
        mock_session.run.side_effect = Exception("DB error")
        assert get_sentiment_trend("NVDA") == []


# ===================================================================
# get_catalysts
# ===================================================================

class TestGetCatalysts:
    def test_success(self, mock_session):
        from src.data.graph_query import get_catalysts
        mock_session.run.return_value = [
            {"type": "positive", "text": "Strong demand"},
            {"type": "negative", "text": "Regulation risk"},
            {"type": "positive", "text": "New product launch"},
        ]
        result = get_catalysts("NVDA")
        assert len(result["positive"]) == 2
        assert len(result["negative"]) == 1

    def test_no_driver(self):
        from src.data.graph_query import get_catalysts
        with patch("src.data.graph_query._get_driver", return_value=None):
            result = get_catalysts("NVDA")
            assert result == {"positive": [], "negative": []}

    def test_error(self, mock_session):
        from src.data.graph_query import get_catalysts
        mock_session.run.side_effect = Exception("DB error")
        result = get_catalysts("NVDA")
        assert result == {"positive": [], "negative": []}


# ===================================================================
# get_report_trend
# ===================================================================

class TestGetReportTrend:
    def test_success(self, mock_session):
        from src.data.graph_query import get_report_trend
        mock_session.run.return_value = [
            {"date": "2025-01-15", "score": 72.5, "verdict": "割安", "price": 2850, "per": 8.5, "pbr": 0.9},
            {"date": "2025-01-01", "score": 65.0, "verdict": "適正", "price": 2700, "per": 9.2, "pbr": 1.0},
        ]
        result = get_report_trend("7203.T")
        assert len(result) == 2
        assert result[0]["price"] == 2850

    def test_no_driver(self):
        from src.data.graph_query import get_report_trend
        with patch("src.data.graph_query._get_driver", return_value=None):
            assert get_report_trend("7203.T") == []

    def test_error(self, mock_session):
        from src.data.graph_query import get_report_trend
        mock_session.run.side_effect = Exception("DB error")
        assert get_report_trend("7203.T") == []


# ===================================================================
# get_upcoming_events
# ===================================================================

class TestGetUpcomingEvents:
    def test_success(self, mock_session):
        from src.data.graph_query import get_upcoming_events
        mock_session.run.return_value = [
            {"date": "2025-01-20", "text": "FOMC meeting"},
            {"date": "2025-01-22", "text": "BOJ decision"},
        ]
        result = get_upcoming_events()
        assert len(result) == 2
        assert result[0]["text"] == "FOMC meeting"

    def test_no_driver(self):
        from src.data.graph_query import get_upcoming_events
        with patch("src.data.graph_query._get_driver", return_value=None):
            assert get_upcoming_events() == []

    def test_error(self, mock_session):
        from src.data.graph_query import get_upcoming_events
        mock_session.run.side_effect = Exception("DB error")
        assert get_upcoming_events() == []


# ===================================================================
# NL query integration (graph_nl_query templates for KIK-413)
# ===================================================================

class TestNLQueryTemplates:
    """Test that new NL templates match and dispatch correctly."""

    def test_news_template(self):
        from src.data.graph_nl_query import query
        with patch("src.data.graph_query.get_stock_news_history", return_value=[]) as mock:
            result = query("NVDAのニュース履歴を見せて")
            assert result is not None
            assert result["query_type"] == "stock_news"
            mock.assert_called_once_with("NVDA")

    def test_sentiment_template(self):
        from src.data.graph_nl_query import query
        with patch("src.data.graph_query.get_sentiment_trend", return_value=[]) as mock:
            result = query("NVDAのセンチメント推移")
            assert result is not None
            assert result["query_type"] == "sentiment_trend"
            mock.assert_called_once_with("NVDA")

    def test_catalyst_template(self):
        from src.data.graph_nl_query import query
        with patch("src.data.graph_query.get_catalysts", return_value={"positive": [], "negative": []}) as mock:
            result = query("NVDAのカタリスト")
            assert result is not None
            assert result["query_type"] == "catalysts"
            mock.assert_called_once_with("NVDA")

    def test_report_trend_template(self):
        from src.data.graph_nl_query import query
        with patch("src.data.graph_query.get_report_trend", return_value=[]) as mock:
            result = query("7203.TのPER推移")
            assert result is not None
            assert result["query_type"] == "report_trend"
            mock.assert_called_once_with("7203.T")

    def test_upcoming_events_template(self):
        from src.data.graph_nl_query import query
        with patch("src.data.graph_query.get_upcoming_events", return_value=[]) as mock:
            result = query("今後のイベント")
            assert result is not None
            assert result["query_type"] == "upcoming_events"
            mock.assert_called_once()

    def test_indicator_template(self):
        from src.data.graph_nl_query import query
        with patch("src.data.graph_query.get_recent_market_context", return_value=None) as mock:
            result = query("マクロ指標の推移")
            # Returns None because get_recent_market_context returned None
            assert result is None


# ===================================================================
# Formatter tests
# ===================================================================

class TestFormatters:
    def test_fmt_stock_news(self):
        from src.data.graph_nl_query import format_result
        result = [
            {"date": "2025-01-15", "title": "NVDA beats expectations", "source": "grok"},
        ]
        text = format_result("stock_news", result, {"symbol": "NVDA"})
        assert "NVDA" in text
        assert "NVDA beats expectations" in text

    def test_fmt_stock_news_empty(self):
        from src.data.graph_nl_query import format_result
        text = format_result("stock_news", [], {"symbol": "NVDA"})
        assert "見つかりませんでした" in text

    def test_fmt_sentiment_trend(self):
        from src.data.graph_nl_query import format_result
        result = [{"date": "2025-01-15", "source": "grok_x", "score": 0.7, "summary": "Bullish"}]
        text = format_result("sentiment_trend", result, {"symbol": "NVDA"})
        assert "0.7" in text
        assert "Bullish" in text

    def test_fmt_catalysts(self):
        from src.data.graph_nl_query import format_result
        result = {"positive": ["Strong demand"], "negative": ["Regulation"]}
        text = format_result("catalysts", result, {"symbol": "NVDA"})
        assert "ポジティブ" in text
        assert "Strong demand" in text

    def test_fmt_catalysts_empty(self):
        from src.data.graph_nl_query import format_result
        text = format_result("catalysts", {"positive": [], "negative": []}, {"symbol": "NVDA"})
        assert "見つかりませんでした" in text

    def test_fmt_report_trend(self):
        from src.data.graph_nl_query import format_result
        result = [{"date": "2025-01-15", "score": 72.5, "verdict": "割安", "price": 2850, "per": 8.5, "pbr": 0.9}]
        text = format_result("report_trend", result, {"symbol": "7203.T"})
        assert "72.5" in text
        assert "割安" in text

    def test_fmt_upcoming_events(self):
        from src.data.graph_nl_query import format_result
        result = [{"date": "2025-01-20", "text": "FOMC meeting"}]
        text = format_result("upcoming_events", result, {})
        assert "FOMC meeting" in text

    def test_fmt_upcoming_events_empty(self):
        from src.data.graph_nl_query import format_result
        text = format_result("upcoming_events", [], {})
        assert "見つかりませんでした" in text
