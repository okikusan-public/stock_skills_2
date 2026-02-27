"""Tests for src.data.graph_query module (KIK-406).

Neo4j driver is mocked -- no real database connection needed.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.no_auto_mock


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(autouse=True)
def reset_driver():
    """Reset global _driver before each test."""
    import src.data.graph_store as gs
    gs._driver = None
    yield
    gs._driver = None


@pytest.fixture
def mock_driver():
    """Provide a mock Neo4j driver with session context manager."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


@pytest.fixture
def gq_with_driver(mock_driver):
    """Set up graph_store with a mock driver, return graph_query module."""
    import src.data.graph_store as gs
    import src.data.graph_query as gq
    driver, session = mock_driver
    gs._driver = driver
    return gq, driver, session


# ===================================================================
# get_prior_report
# ===================================================================

class TestGetPriorReport:
    def test_returns_report(self, gq_with_driver):
        gq, _, session = gq_with_driver
        record = MagicMock()
        record.__getitem__ = lambda self, k: {"date": "2025-02-10", "score": 72.5, "verdict": "割安"}[k]
        record.keys = lambda: ["date", "score", "verdict"]
        session.run.return_value.single.return_value = record
        result = gq.get_prior_report("7203.T")
        assert result is not None
        assert result["date"] == "2025-02-10"
        assert result["score"] == 72.5

    def test_returns_none_when_not_found(self, gq_with_driver):
        gq, _, session = gq_with_driver
        session.run.return_value.single.return_value = None
        result = gq.get_prior_report("UNKNOWN")
        assert result is None

    def test_returns_none_no_driver(self):
        import src.data.graph_query as gq
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gq.get_prior_report("7203.T") is None

    def test_returns_none_on_error(self, gq_with_driver):
        gq, driver, _ = gq_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gq.get_prior_report("7203.T") is None


# ===================================================================
# get_screening_frequency
# ===================================================================

class TestGetScreeningFrequency:
    def test_returns_counts(self, gq_with_driver):
        gq, _, session = gq_with_driver
        r1 = MagicMock()
        r1.__getitem__ = lambda self, k: {"symbol": "7203.T", "cnt": 3}[k]
        r2 = MagicMock()
        r2.__getitem__ = lambda self, k: {"symbol": "AAPL", "cnt": 1}[k]
        session.run.return_value = iter([r1, r2])
        result = gq.get_screening_frequency(["7203.T", "AAPL", "MSFT"])
        assert result["7203.T"] == 3
        assert result["AAPL"] == 1
        assert "MSFT" not in result

    def test_returns_empty_no_driver(self):
        import src.data.graph_query as gq
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gq.get_screening_frequency(["7203.T"]) == {}

    def test_returns_empty_on_error(self, gq_with_driver):
        gq, driver, _ = gq_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gq.get_screening_frequency(["7203.T"]) == {}


# ===================================================================
# get_research_chain
# ===================================================================

class TestGetResearchChain:
    def test_returns_chain(self, gq_with_driver):
        gq, _, session = gq_with_driver
        r1 = MagicMock()
        r1.__getitem__ = lambda self, k: {"date": "2025-02-15", "summary": "Second"}[k]
        r1.keys = lambda: ["date", "summary"]
        r2 = MagicMock()
        r2.__getitem__ = lambda self, k: {"date": "2025-01-15", "summary": "First"}[k]
        r2.keys = lambda: ["date", "summary"]
        session.run.return_value = iter([r1, r2])
        result = gq.get_research_chain("stock", "7203.T")
        assert len(result) == 2
        assert result[0]["date"] == "2025-02-15"
        assert result[1]["summary"] == "First"

    def test_returns_empty_no_driver(self):
        import src.data.graph_query as gq
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gq.get_research_chain("stock", "7203.T") == []

    def test_returns_empty_on_error(self, gq_with_driver):
        gq, driver, _ = gq_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gq.get_research_chain("stock", "7203.T") == []


# ===================================================================
# get_recent_market_context
# ===================================================================

class TestGetRecentMarketContext:
    def test_returns_context(self, gq_with_driver):
        gq, _, session = gq_with_driver
        indices_json = json.dumps([{"name": "S&P500", "price": 5800}])
        record = MagicMock()
        record.__getitem__ = lambda self, k: {"date": "2025-02-17", "indices": indices_json}[k]
        session.run.return_value.single.return_value = record
        result = gq.get_recent_market_context()
        assert result is not None
        assert result["date"] == "2025-02-17"
        assert len(result["indices"]) == 1
        assert result["indices"][0]["name"] == "S&P500"

    def test_returns_none_when_not_found(self, gq_with_driver):
        gq, _, session = gq_with_driver
        session.run.return_value.single.return_value = None
        assert gq.get_recent_market_context() is None

    def test_returns_none_no_driver(self):
        import src.data.graph_query as gq
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gq.get_recent_market_context() is None

    def test_handles_bad_json(self, gq_with_driver):
        gq, _, session = gq_with_driver
        record = MagicMock()
        record.__getitem__ = lambda self, k: {"date": "2025-02-17", "indices": "not-json"}[k]
        session.run.return_value.single.return_value = record
        result = gq.get_recent_market_context()
        assert result is not None
        assert result["indices"] == []


# ===================================================================
# get_trade_context
# ===================================================================

class TestGetTradeContext:
    def test_returns_trades_and_notes(self, gq_with_driver):
        gq, _, session = gq_with_driver
        trade_rec = MagicMock()
        trade_rec.__getitem__ = lambda self, k: {"date": "2025-01-15", "type": "buy", "shares": 100, "price": 2850}[k]
        trade_rec.keys = lambda: ["date", "type", "shares", "price"]
        note_rec = MagicMock()
        note_rec.__getitem__ = lambda self, k: {"date": "2025-01-15", "type": "thesis", "content": "Strong buy"}[k]
        note_rec.keys = lambda: ["date", "type", "content"]
        # session.run called twice: first for trades, second for notes
        session.run.side_effect = [iter([trade_rec]), iter([note_rec])]
        result = gq.get_trade_context("7203.T")
        assert len(result["trades"]) == 1
        assert result["trades"][0]["shares"] == 100
        assert len(result["notes"]) == 1
        assert result["notes"][0]["content"] == "Strong buy"

    def test_returns_empty_no_driver(self):
        import src.data.graph_query as gq
        with patch("src.data.graph_store._get_driver", return_value=None):
            result = gq.get_trade_context("7203.T")
            assert result == {"trades": [], "notes": []}

    def test_returns_empty_on_error(self, gq_with_driver):
        gq, driver, _ = gq_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        result = gq.get_trade_context("7203.T")
        assert result == {"trades": [], "notes": []}


# ===================================================================
# get_recurring_picks
# ===================================================================

class TestGetRecurringPicks:
    def test_returns_picks(self, gq_with_driver):
        gq, _, session = gq_with_driver
        r1 = MagicMock()
        r1.__getitem__ = lambda self, k: {"symbol": "7203.T", "count": 3, "last_date": "2025-02-15"}[k]
        r1.keys = lambda: ["symbol", "count", "last_date"]
        session.run.return_value = iter([r1])
        result = gq.get_recurring_picks(min_count=2)
        assert len(result) == 1
        assert result[0]["symbol"] == "7203.T"
        assert result[0]["count"] == 3

    def test_returns_empty_no_driver(self):
        import src.data.graph_query as gq
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gq.get_recurring_picks() == []

    def test_returns_empty_on_error(self, gq_with_driver):
        gq, driver, _ = gq_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gq.get_recurring_picks() == []


# ===================================================================
# get_sector_catalysts (KIK-433)
# ===================================================================

class TestGetSectorCatalysts:
    def _make_record(self, ctype, text):
        rec = MagicMock()
        rec.__getitem__ = lambda self, k: {"type": ctype, "text": text}[k]
        return rec

    def test_returns_classified_catalysts(self, gq_with_driver):
        """growth_driver → positive, risk → negative."""
        gq, _, session = gq_with_driver
        r1 = self._make_record("growth_driver", "AI adoption rising")
        r2 = self._make_record("risk", "Supply chain disruption")
        r3 = self._make_record("trend", "Cloud migration")
        session.run.return_value = iter([r1, r2, r3])
        result = gq.get_sector_catalysts("Technology", days=30)
        assert result["count_positive"] == 1
        assert result["count_negative"] == 1
        assert "AI adoption rising" in result["positive"]
        assert "Supply chain disruption" in result["negative"]

    def test_fallback_when_no_match(self, gq_with_driver):
        """If sector-matched query returns 0 rows, fallback runs."""
        gq, _, session = gq_with_driver
        r1 = self._make_record("growth_driver", "General growth")
        # First call (sector-matched) returns empty; second call (fallback) returns r1
        session.run.side_effect = [iter([]), iter([r1])]
        result = gq.get_sector_catalysts("Technology", days=30)
        assert result["matched_sector"] is False
        assert result["count_positive"] == 1

    def test_returns_empty_no_driver(self):
        import src.data.graph_query as gq
        with patch("src.data.graph_store._get_driver", return_value=None):
            result = gq.get_sector_catalysts("Technology")
        assert result["count_positive"] == 0
        assert result["count_negative"] == 0

    def test_returns_empty_on_exception(self, gq_with_driver):
        gq, driver, _ = gq_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        result = gq.get_sector_catalysts("Technology")
        assert result["positive"] == []
        assert result["negative"] == []


# ===================================================================
# get_industry_research_for_sector (KIK-433)
# ===================================================================

class TestGetIndustryResearchForSector:
    def test_returns_list_with_catalysts(self, gq_with_driver):
        gq, _, session = gq_with_driver
        rec = MagicMock()
        rec.__getitem__ = lambda self, k: {
            "date": "2026-02-10",
            "target": "AI",
            "summary": "AI market is expanding.",
            "catalysts": [{"type": "growth_driver", "text": "LLM adoption"}],
        }[k]
        session.run.return_value = iter([rec])
        result = gq.get_industry_research_for_sector("Technology", days=30)
        assert len(result) == 1
        assert result[0]["target"] == "AI"
        assert result[0]["date"] == "2026-02-10"

    def test_returns_empty_no_driver(self):
        import src.data.graph_query as gq
        with patch("src.data.graph_store._get_driver", return_value=None):
            result = gq.get_industry_research_for_sector("Technology")
        assert result == []

    def test_returns_empty_on_exception(self, gq_with_driver):
        gq, driver, _ = gq_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gq.get_industry_research_for_sector("Technology") == []
