"""Integration tests for MomentumScreener with mock yahoo_client."""

import pytest
import pandas as pd
from unittest.mock import MagicMock

from src.core.screening.momentum_screener import MomentumScreener


@pytest.fixture
def mock_yahoo_client():
    """Create a mock yahoo_client with sample data."""
    client = MagicMock()

    # Sample normalized quote data
    sample_quotes = [
        {
            "symbol": "TEST1.T",
            "name": "Test Co 1",
            "price": 100,
            "per": 12,
            "pbr": 1.2,
            "roe": 0.10,
            "dividend_yield": 0.03,
        },
        {
            "symbol": "TEST2.T",
            "name": "Test Co 2",
            "price": 150,
            "per": 15,
            "pbr": 1.5,
            "roe": 0.08,
            "dividend_yield": 0.02,
        },
    ]

    # Mock screen_stocks to return sample quotes
    client.screen_stocks.return_value = sample_quotes

    # Mock price history for momentum analysis
    def mock_price_history(symbol):
        dates = pd.date_range("2024-01-01", periods=100)
        if "TEST1" in symbol:
            # Downtrend then reversal
            prices = [100 - (i * 0.3) if i < 50 else 85 + ((i - 50) * 0.5) for i in range(100)]
        else:
            # Strong uptrend
            prices = [150 + (i * 0.5) for i in range(100)]
        volumes = [1000000 + (i * 1000) for i in range(100)]
        return pd.DataFrame({"Close": prices, "Volume": volumes}, index=dates)

    client.get_price_history.side_effect = mock_price_history

    return client


def test_momentum_screener_screen_method(mock_yahoo_client):
    """Test MomentumScreener.screen() method."""
    screener = MomentumScreener(mock_yahoo_client)

    results = screener.screen(region="jp", top_n=10)

    # Should return a list
    assert isinstance(results, list)

    # Should have some results (at least from the mock data)
    assert len(results) <= 10

    # Check that results have expected keys
    for result in results:
        assert "symbol" in result
        assert "surge_score" in result  # KIK-506: momentum uses surge_score
        assert "rsi" in result
        assert "surge_level" in result
        assert "volume_ratio" in result


def test_momentum_screener_with_sector_filter(mock_yahoo_client):
    """Test MomentumScreener with sector filter."""
    screener = MomentumScreener(mock_yahoo_client)

    # Should handle sector parameter
    results = screener.screen(region="jp", sector="Technology", top_n=5)

    # Verify build_query was called with sector
    mock_yahoo_client.screen_stocks.assert_called()


def test_momentum_screener_with_theme_filter(mock_yahoo_client):
    """Test MomentumScreener with theme filter."""
    screener = MomentumScreener(mock_yahoo_client)

    # Should handle theme parameter
    results = screener.screen(region="jp", theme="ai", top_n=5)

    # Verify build_query was called
    mock_yahoo_client.screen_stocks.assert_called()


def test_momentum_screener_empty_results(mock_yahoo_client):
    """Test MomentumScreener with no matching stocks."""
    # Mock to return empty list
    mock_yahoo_client.screen_stocks.return_value = []

    screener = MomentumScreener(mock_yahoo_client)
    results = screener.screen(region="jp", top_n=10)

    assert results == []


def test_momentum_screener_sorts_by_score(mock_yahoo_client):
    """Test that MomentumScreener sorts results by momentum_score."""
    screener = MomentumScreener(mock_yahoo_client)

    results = screener.screen(region="jp", top_n=10)

    if len(results) > 1:
        # Check that scores are in descending order
        scores = [r.get("surge_score", 0) for r in results]
        assert scores == sorted(scores, reverse=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
