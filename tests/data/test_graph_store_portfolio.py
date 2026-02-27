"""Tests for graph_store portfolio sync functions (KIK-414).

Neo4j driver is mocked -- no real database connection needed.
"""

import pytest
from unittest.mock import MagicMock, patch, call

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
def gs_with_driver(mock_driver):
    """Set up graph_store with a mock driver already injected."""
    import src.data.graph_store as gs
    driver, session = mock_driver
    gs._driver = driver
    return gs, driver, session


# ===================================================================
# sync_portfolio tests
# ===================================================================

class TestSyncPortfolio:
    def test_basic_sync(self, gs_with_driver):
        """Normal sync: creates Portfolio anchor, MERGE stock+HOLDS, deletes stale."""
        gs, _, session = gs_with_driver
        holdings = [
            {"symbol": "7203.T", "shares": 100, "cost_price": 2850,
             "cost_currency": "JPY", "purchase_date": "2026-01-01"},
            {"symbol": "AAPL", "shares": 10, "cost_price": 250,
             "cost_currency": "USD", "purchase_date": "2026-01-15"},
        ]
        with patch.object(gs, "_get_mode", return_value="full"):
            result = gs.sync_portfolio(holdings)
        assert result is True
        # Portfolio MERGE + 2 stock MERGEs + 2 HOLDS MERGEs + 1 stale DELETE = 6
        assert session.run.call_count == 6

    def test_skips_cash(self, gs_with_driver):
        """CASH positions should be skipped."""
        gs, _, session = gs_with_driver
        holdings = [
            {"symbol": "JPY.CASH", "shares": 1000000, "cost_price": 1},
            {"symbol": "7203.T", "shares": 100, "cost_price": 2850},
        ]
        with patch.object(gs, "_get_mode", return_value="full"):
            result = gs.sync_portfolio(holdings)
        assert result is True
        # Portfolio MERGE + 1 stock MERGE + 1 HOLDS MERGE + 1 stale DELETE = 4
        assert session.run.call_count == 4

    def test_empty_holdings(self, gs_with_driver):
        """Empty holdings should delete all HOLDS relationships."""
        gs, _, session = gs_with_driver
        with patch.object(gs, "_get_mode", return_value="full"):
            result = gs.sync_portfolio([])
        assert result is True
        # Portfolio MERGE + 1 delete-all-HOLDS = 2
        assert session.run.call_count == 2

    def test_no_driver(self):
        """Returns False when no driver available."""
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.sync_portfolio([{"symbol": "AAPL"}]) is False

    def test_mode_off(self, gs_with_driver):
        """Returns False when NEO4J_MODE is off."""
        gs, _, session = gs_with_driver
        with patch.object(gs, "_get_mode", return_value="off"):
            assert gs.sync_portfolio([{"symbol": "AAPL"}]) is False
        assert session.run.call_count == 0

    def test_error_handling(self, gs_with_driver):
        """Returns False on database error."""
        gs, driver, session = gs_with_driver
        session.run.side_effect = Exception("DB error")
        with patch.object(gs, "_get_mode", return_value="full"):
            assert gs.sync_portfolio([{"symbol": "AAPL"}]) is False


# ===================================================================
# is_held tests
# ===================================================================

class TestIsHeld:
    def test_held(self, gs_with_driver):
        """Returns True when stock is held."""
        gs, _, session = gs_with_driver
        mock_result = MagicMock()
        mock_result.single.return_value = {"cnt": 1}
        session.run.return_value = mock_result
        assert gs.is_held("7203.T") is True

    def test_not_held(self, gs_with_driver):
        """Returns False when stock is not held."""
        gs, _, session = gs_with_driver
        mock_result = MagicMock()
        mock_result.single.return_value = {"cnt": 0}
        session.run.return_value = mock_result
        assert gs.is_held("NVDA") is False

    def test_no_driver(self):
        """Returns False when no driver available."""
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.is_held("AAPL") is False

    def test_error_handling(self, gs_with_driver):
        """Returns False on database error."""
        gs, _, session = gs_with_driver
        session.run.side_effect = Exception("DB error")
        assert gs.is_held("AAPL") is False


# ===================================================================
# get_held_symbols tests
# ===================================================================

class TestGetHeldSymbols:
    def test_success(self, gs_with_driver):
        """Returns list of held symbols."""
        gs, _, session = gs_with_driver
        session.run.return_value = [
            {"symbol": "7203.T"},
            {"symbol": "AAPL"},
        ]
        result = gs.get_held_symbols()
        assert result == ["7203.T", "AAPL"]

    def test_no_driver(self):
        """Returns empty list when no driver available."""
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.get_held_symbols() == []

    def test_error_handling(self, gs_with_driver):
        """Returns empty list on database error."""
        gs, _, session = gs_with_driver
        session.run.side_effect = Exception("DB error")
        assert gs.get_held_symbols() == []
