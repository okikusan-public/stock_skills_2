"""Tests for ISP-compliant Protocol interfaces (KIK-516).

Verifies that:
1. Each Protocol is well-formed (importable, usable as type hint).
2. The existing yahoo_client module structurally satisfies the Protocols.
3. The existing grok_client module structurally satisfies the Protocols.
4. A minimal mock satisfying only ScreeningProvider works in QueryScreener.
"""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Import the Protocols under test
# ---------------------------------------------------------------------------

from src.core.ports.market_data import (
    MacroDataProvider,
    PriceHistoryProvider,
    ScreeningProvider,
    StockInfoProvider,
)
from src.core.ports.research import (
    GrokAvailability,
    ResearchSearcher,
    TextSynthesizer,
    TrendingSearcher,
)


# ---------------------------------------------------------------------------
# Helper: minimal concrete implementations for structural checks
# ---------------------------------------------------------------------------

class _MinimalScreeningProvider:
    """Minimal object that satisfies only ScreeningProvider."""

    def screen_stocks(
        self,
        query,
        size: int = 250,
        sort_field: str = "intradaymarketcap",
        sort_asc: bool = False,
        max_results: int = 0,
    ) -> list[dict]:
        return []


class _MinimalStockInfoProvider:
    """Minimal object that satisfies StockInfoProvider."""

    def get_stock_info(self, symbol: str) -> Optional[dict]:
        return None

    def get_stock_detail(self, symbol: str) -> Optional[dict]:
        return None

    def get_multiple_stocks(self, symbols: list[str]) -> dict[str, Optional[dict]]:
        return {}


class _MinimalPriceHistoryProvider:
    """Minimal object that satisfies PriceHistoryProvider."""

    def get_price_history(
        self, symbol: str, period: str = "1y"
    ) -> Optional[pd.DataFrame]:
        return None

    def get_stock_news(self, symbol: str, count: int = 10) -> list[dict]:
        return []


class _MinimalMacroDataProvider:
    """Minimal object that satisfies MacroDataProvider."""

    def get_macro_indicators(self) -> list[dict]:
        return []


class _MinimalResearchSearcher:
    """Minimal object that satisfies ResearchSearcher."""

    def search_stock_deep(
        self, symbol: str, company_name: str = "", timeout: int = 30, context: str = ""
    ) -> dict:
        return {}

    def search_x_sentiment(
        self, symbol: str, company_name: str = "", timeout: int = 30, context: str = ""
    ) -> dict:
        return {}

    def search_industry(
        self, industry_or_theme: str, timeout: int = 30, context: str = ""
    ) -> dict:
        return {}

    def search_market(
        self, market_or_index: str, timeout: int = 30, context: str = ""
    ) -> dict:
        return {}

    def search_business(
        self, symbol: str, company_name: str = "", timeout: int = 60, context: str = ""
    ) -> dict:
        return {}


class _MinimalTrendingSearcher:
    """Minimal object that satisfies TrendingSearcher."""

    def search_trending_stocks(
        self, region: str = "japan", theme: Optional[str] = None, timeout: int = 60
    ) -> dict:
        return {}

    def get_trending_themes(self, region: str = "global", timeout: int = 30) -> dict:
        return {}


class _MinimalTextSynthesizer:
    """Minimal object that satisfies TextSynthesizer."""

    def synthesize_text(self, prompt: str, timeout: int = 20) -> str:
        return ""


class _MinimalGrokAvailability:
    """Minimal object that satisfies GrokAvailability."""

    def is_available(self) -> bool:
        return False

    def get_error_status(self) -> dict:
        return {"status": "not_configured", "status_code": None, "message": ""}


# ---------------------------------------------------------------------------
# Protocol well-formedness tests
# ---------------------------------------------------------------------------

class TestProtocolsAreImportable:
    """Verify that all Protocols can be imported and used as type hints."""

    def test_stock_info_provider_importable(self):
        assert StockInfoProvider is not None

    def test_screening_provider_importable(self):
        assert ScreeningProvider is not None

    def test_price_history_provider_importable(self):
        assert PriceHistoryProvider is not None

    def test_macro_data_provider_importable(self):
        assert MacroDataProvider is not None

    def test_research_searcher_importable(self):
        assert ResearchSearcher is not None

    def test_trending_searcher_importable(self):
        assert TrendingSearcher is not None

    def test_text_synthesizer_importable(self):
        assert TextSynthesizer is not None

    def test_grok_availability_importable(self):
        assert GrokAvailability is not None


# ---------------------------------------------------------------------------
# Structural compatibility: minimal implementations satisfy Protocols
# ---------------------------------------------------------------------------

class TestMinimalImplementationsSatisfyProtocols:
    """Verify that minimal concrete classes satisfy each Protocol."""

    def test_minimal_screening_provider_satisfies_protocol(self):
        obj = _MinimalScreeningProvider()
        assert isinstance(obj, ScreeningProvider)

    def test_minimal_stock_info_provider_satisfies_protocol(self):
        obj = _MinimalStockInfoProvider()
        assert isinstance(obj, StockInfoProvider)

    def test_minimal_price_history_provider_satisfies_protocol(self):
        obj = _MinimalPriceHistoryProvider()
        assert isinstance(obj, PriceHistoryProvider)

    def test_minimal_macro_data_provider_satisfies_protocol(self):
        obj = _MinimalMacroDataProvider()
        assert isinstance(obj, MacroDataProvider)

    def test_minimal_research_searcher_satisfies_protocol(self):
        obj = _MinimalResearchSearcher()
        assert isinstance(obj, ResearchSearcher)

    def test_minimal_trending_searcher_satisfies_protocol(self):
        obj = _MinimalTrendingSearcher()
        assert isinstance(obj, TrendingSearcher)

    def test_minimal_text_synthesizer_satisfies_protocol(self):
        obj = _MinimalTextSynthesizer()
        assert isinstance(obj, TextSynthesizer)

    def test_minimal_grok_availability_satisfies_protocol(self):
        obj = _MinimalGrokAvailability()
        assert isinstance(obj, GrokAvailability)


# ---------------------------------------------------------------------------
# Protocol violation: missing method does NOT satisfy Protocol
# ---------------------------------------------------------------------------

class TestProtocolViolations:
    """Verify that incomplete implementations do NOT satisfy Protocols."""

    def test_object_missing_screen_stocks_does_not_satisfy_screening_provider(self):
        class _NoScreenStocks:
            pass

        obj = _NoScreenStocks()
        assert not isinstance(obj, ScreeningProvider)

    def test_object_missing_get_stock_info_does_not_satisfy_stock_info_provider(self):
        class _PartialStockInfo:
            def get_stock_detail(self, symbol: str):
                return None
            # Missing: get_stock_info, get_multiple_stocks

        obj = _PartialStockInfo()
        assert not isinstance(obj, StockInfoProvider)

    def test_object_missing_search_stock_deep_does_not_satisfy_research_searcher(self):
        class _PartialResearch:
            def search_x_sentiment(self, symbol, **kw):
                return {}
            # Missing: search_stock_deep, search_industry, search_market, search_business

        obj = _PartialResearch()
        assert not isinstance(obj, ResearchSearcher)


# ---------------------------------------------------------------------------
# Structural compatibility: yahoo_client module satisfies Protocols
# ---------------------------------------------------------------------------

class TestYahooClientSatisfiesProtocols:
    """Verify that the real yahoo_client module satisfies all four Protocols."""

    def setup_method(self):
        from src.data import yahoo_client
        self.yahoo_client = yahoo_client

    def test_yahoo_client_satisfies_stock_info_provider(self):
        """yahoo_client has get_stock_info, get_stock_detail, get_multiple_stocks."""
        assert hasattr(self.yahoo_client, "get_stock_info")
        assert hasattr(self.yahoo_client, "get_stock_detail")
        assert hasattr(self.yahoo_client, "get_multiple_stocks")

    def test_yahoo_client_satisfies_screening_provider(self):
        """yahoo_client has screen_stocks."""
        assert hasattr(self.yahoo_client, "screen_stocks")

    def test_yahoo_client_satisfies_price_history_provider(self):
        """yahoo_client has get_price_history and get_stock_news."""
        assert hasattr(self.yahoo_client, "get_price_history")
        assert hasattr(self.yahoo_client, "get_stock_news")

    def test_yahoo_client_satisfies_macro_data_provider(self):
        """yahoo_client has get_macro_indicators."""
        assert hasattr(self.yahoo_client, "get_macro_indicators")

    def test_yahoo_client_functions_are_callable(self):
        """All Protocol methods are callable on yahoo_client."""
        assert callable(self.yahoo_client.get_stock_info)
        assert callable(self.yahoo_client.get_stock_detail)
        assert callable(self.yahoo_client.get_multiple_stocks)
        assert callable(self.yahoo_client.screen_stocks)
        assert callable(self.yahoo_client.get_price_history)
        assert callable(self.yahoo_client.get_stock_news)
        assert callable(self.yahoo_client.get_macro_indicators)


# ---------------------------------------------------------------------------
# Structural compatibility: grok_client module satisfies Protocols
# ---------------------------------------------------------------------------

class TestGrokClientSatisfiesProtocols:
    """Verify that the real grok_client module satisfies all Protocols."""

    def setup_method(self):
        from src.data import grok_client
        self.grok_client = grok_client

    def test_grok_client_satisfies_research_searcher(self):
        """grok_client has all five research search functions."""
        assert hasattr(self.grok_client, "search_stock_deep")
        assert hasattr(self.grok_client, "search_x_sentiment")
        assert hasattr(self.grok_client, "search_industry")
        assert hasattr(self.grok_client, "search_market")
        assert hasattr(self.grok_client, "search_business")

    def test_grok_client_satisfies_trending_searcher(self):
        """grok_client has search_trending_stocks and get_trending_themes."""
        assert hasattr(self.grok_client, "search_trending_stocks")
        assert hasattr(self.grok_client, "get_trending_themes")

    def test_grok_client_satisfies_text_synthesizer(self):
        """grok_client has synthesize_text."""
        assert hasattr(self.grok_client, "synthesize_text")

    def test_grok_client_satisfies_grok_availability(self):
        """grok_client has is_available and get_error_status."""
        assert hasattr(self.grok_client, "is_available")
        assert hasattr(self.grok_client, "get_error_status")

    def test_grok_client_functions_are_callable(self):
        """All Protocol methods are callable on grok_client."""
        assert callable(self.grok_client.search_stock_deep)
        assert callable(self.grok_client.search_x_sentiment)
        assert callable(self.grok_client.search_industry)
        assert callable(self.grok_client.search_market)
        assert callable(self.grok_client.search_business)
        assert callable(self.grok_client.search_trending_stocks)
        assert callable(self.grok_client.get_trending_themes)
        assert callable(self.grok_client.synthesize_text)
        assert callable(self.grok_client.is_available)
        assert callable(self.grok_client.get_error_status)


# ---------------------------------------------------------------------------
# Integration: QueryScreener accepts any ScreeningProvider
# ---------------------------------------------------------------------------

class TestQueryScreenerAcceptsScreeningProvider:
    """Verify that QueryScreener works with any ScreeningProvider implementation."""

    def test_query_screener_accepts_minimal_screening_provider(self):
        """A minimal ScreeningProvider (not the real yahoo_client) works in QueryScreener."""
        from src.core.screening.query_screener import QueryScreener

        provider = _MinimalScreeningProvider()
        # QueryScreener should accept any ScreeningProvider without error
        screener = QueryScreener(yahoo_client=provider)
        assert screener.yahoo_client is provider

    def test_query_screener_accepts_mock_screening_provider(self):
        """A MagicMock satisfying ScreeningProvider interface works in QueryScreener."""
        from src.core.screening.query_screener import QueryScreener

        mock_provider = MagicMock()
        mock_provider.screen_stocks.return_value = []

        screener = QueryScreener(yahoo_client=mock_provider)
        assert screener.yahoo_client is mock_provider

    def test_query_screener_calls_screen_stocks_on_provider(self, monkeypatch):
        """QueryScreener delegates screen_stocks to the injected provider."""
        from src.core.screening.query_screener import QueryScreener

        mock_provider = MagicMock(spec=_MinimalScreeningProvider)
        mock_provider.screen_stocks.return_value = []

        screener = QueryScreener(yahoo_client=mock_provider)

        # screen() takes region + optional preset; it calls yahoo_client.screen_stocks internally
        screener.screen(region="japan", preset="value", top_n=5)
        mock_provider.screen_stocks.assert_called_once()


# ---------------------------------------------------------------------------
# Ports package exports
# ---------------------------------------------------------------------------

class TestPortsPackageExports:
    """Verify that src.core.ports exports all expected names."""

    def test_all_protocols_exported_from_ports(self):
        from src.core import ports

        expected = [
            "StockInfoProvider",
            "ScreeningProvider",
            "PriceHistoryProvider",
            "MacroDataProvider",
            "ResearchSearcher",
            "TrendingSearcher",
            "TextSynthesizer",
            "GrokAvailability",
        ]
        for name in expected:
            assert hasattr(ports, name), f"src.core.ports missing: {name}"
