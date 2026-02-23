"""Tests for ETF field extraction in yahoo_client (KIK-469)."""

import pytest


class TestGetStockInfoETFFields:
    """Test quoteType extraction in get_stock_info."""

    def test_quote_type_extracted(self, etf_info_data):
        """ETF info should have quoteType field."""
        assert etf_info_data["quoteType"] == "ETF"

    def test_stock_has_no_quote_type(self, stock_info_data):
        """Regular stock info should not have quoteType (or None)."""
        # stock_info.json fixture doesn't have quoteType key
        assert stock_info_data.get("quoteType") is None

    def test_etf_has_no_per(self, etf_info_data):
        """ETF should have None for PER."""
        assert etf_info_data["per"] is None

    def test_etf_has_no_sector(self, etf_info_data):
        """ETF should have None for sector."""
        assert etf_info_data["sector"] is None


class TestGetStockDetailETFFields:
    """Test ETF-specific fields in get_stock_detail."""

    def test_expense_ratio(self, etf_detail_data):
        """ETF detail should have expense_ratio."""
        assert etf_detail_data["expense_ratio"] == 0.0009

    def test_total_assets_fund(self, etf_detail_data):
        """ETF detail should have total_assets_fund (AUM)."""
        assert etf_detail_data["total_assets_fund"] == 20_000_000_000

    def test_fund_category(self, etf_detail_data):
        """ETF detail should have fund_category."""
        assert etf_detail_data["fund_category"] == "Europe Stock"

    def test_fund_family(self, etf_detail_data):
        """ETF detail should have fund_family."""
        assert etf_detail_data["fund_family"] == "Vanguard"

    def test_quote_type_in_detail(self, etf_detail_data):
        """ETF detail should have quoteType."""
        assert etf_detail_data["quoteType"] == "ETF"

    def test_stock_detail_no_etf_fields(self, stock_detail_data):
        """Regular stock detail should not have ETF-specific fields."""
        assert stock_detail_data.get("expense_ratio") is None
        assert stock_detail_data.get("total_assets_fund") is None
        assert stock_detail_data.get("fund_category") is None
        assert stock_detail_data.get("fund_family") is None

    def test_total_assets_fund_separate_from_total_assets(self, etf_detail_data):
        """total_assets_fund (AUM) should be separate from total_assets (balance sheet)."""
        # ETF has total_assets_fund but total_assets (balance sheet) is None
        assert etf_detail_data["total_assets_fund"] == 20_000_000_000
        assert etf_detail_data.get("total_assets") is None
