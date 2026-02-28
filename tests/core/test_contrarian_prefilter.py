"""Tests for contrarian pre-filter (KIK-531)."""

import pytest

from src.core.screening.contrarian_screener import _pre_filter_contrarian


class TestPreFilterContrarian:
    """Test _pre_filter_contrarian() with various EquityQuery raw field combos."""

    def test_passes_stock_with_no_fields(self):
        """Stocks without the optional fields should pass through."""
        quotes = [{"symbol": "AAAA"}]
        result = _pre_filter_contrarian(quotes)
        assert len(result) == 1

    def test_filters_rising_stock(self):
        """Stock with fiftyDayAverageChangePercent > 0.05 → filtered out."""
        quotes = [
            {"symbol": "RISING", "fiftyDayAverageChangePercent": 0.10},
        ]
        result = _pre_filter_contrarian(quotes)
        assert len(result) == 0

    def test_passes_declining_stock(self):
        """Stock with negative fiftyDayAverageChangePercent → kept."""
        quotes = [
            {"symbol": "FALLING", "fiftyDayAverageChangePercent": -0.15},
        ]
        result = _pre_filter_contrarian(quotes)
        assert len(result) == 1

    def test_filters_near_52wk_high(self):
        """Stock within 5% of 52-week high → filtered out."""
        quotes = [
            {"symbol": "NEAR_HIGH", "fiftyTwoWeekHighChangePercent": -0.02},
        ]
        result = _pre_filter_contrarian(quotes)
        assert len(result) == 0

    def test_passes_far_from_52wk_high(self):
        """Stock far below 52-week high → kept."""
        quotes = [
            {"symbol": "LOW", "fiftyTwoWeekHighChangePercent": -0.30},
        ]
        result = _pre_filter_contrarian(quotes)
        assert len(result) == 1

    def test_both_fields_trigger_filter(self):
        """Either condition alone is sufficient to filter."""
        quotes = [
            # Rising + near high → filtered (both conditions)
            {"symbol": "A", "fiftyDayAverageChangePercent": 0.08,
             "fiftyTwoWeekHighChangePercent": -0.01},
            # Falling + near high → filtered (52wk condition)
            {"symbol": "B", "fiftyDayAverageChangePercent": -0.10,
             "fiftyTwoWeekHighChangePercent": -0.03},
            # Rising + far from high → filtered (50d condition)
            {"symbol": "C", "fiftyDayAverageChangePercent": 0.12,
             "fiftyTwoWeekHighChangePercent": -0.25},
            # Falling + far from high → kept
            {"symbol": "D", "fiftyDayAverageChangePercent": -0.05,
             "fiftyTwoWeekHighChangePercent": -0.20},
        ]
        result = _pre_filter_contrarian(quotes)
        assert len(result) == 1
        assert result[0]["symbol"] == "D"

    def test_boundary_values(self):
        """Values exactly at the threshold should NOT be filtered."""
        quotes = [
            # Exactly 0.05 → NOT > 0.05, so kept
            {"symbol": "EDGE_50D", "fiftyDayAverageChangePercent": 0.05},
            # Exactly -0.05 → NOT > -0.05, so kept
            {"symbol": "EDGE_52W", "fiftyTwoWeekHighChangePercent": -0.05},
        ]
        result = _pre_filter_contrarian(quotes)
        assert len(result) == 2

    def test_empty_input(self):
        result = _pre_filter_contrarian([])
        assert result == []
