"""ISP-compliant Protocol interfaces for yahoo_client roles (KIK-516).

Each Protocol covers exactly one responsibility so that callers only
depend on the slice of the interface they actually use.

Structural compatibility:
  The ``src.data.yahoo_client`` module satisfies all four Protocols
  without any modifications — these are additive type annotations only.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

import pandas as pd
from yfinance import EquityQuery


@runtime_checkable
class StockInfoProvider(Protocol):
    """Provides per-symbol fundamental data and batch fetching.

    Implemented by: src.data.yahoo_client
    """

    def get_stock_info(self, symbol: str) -> Optional[dict]:
        """Return fundamental data for a single symbol.

        Parameters
        ----------
        symbol : str
            Yahoo Finance ticker (e.g. "7203.T", "AAPL").

        Returns
        -------
        dict | None
            Normalised fields: per, pbr, roe, dividend_yield, …
            Returns None on error.
        """
        ...

    def get_stock_detail(self, symbol: str) -> Optional[dict]:
        """Return extended detail for a single symbol.

        Parameters
        ----------
        symbol : str
            Yahoo Finance ticker.

        Returns
        -------
        dict | None
            Extended fields including shareholder return history.
            Returns None on error.
        """
        ...

    def get_multiple_stocks(self, symbols: list[str]) -> dict[str, Optional[dict]]:
        """Return fundamental data for a batch of symbols.

        Parameters
        ----------
        symbols : list[str]
            Yahoo Finance tickers.

        Returns
        -------
        dict[str, dict | None]
            Mapping of symbol → info dict (None on per-symbol error).
        """
        ...


@runtime_checkable
class ScreeningProvider(Protocol):
    """Executes EquityQuery-based bulk screening via Yahoo Finance.

    Implemented by: src.data.yahoo_client
    """

    def screen_stocks(
        self,
        query: EquityQuery,
        size: int = 250,
        sort_field: str = "intradaymarketcap",
        sort_asc: bool = False,
        max_results: int = 0,
    ) -> list[dict]:
        """Screen stocks matching *query* using yf.screen().

        Parameters
        ----------
        query : EquityQuery
            Pre-built screening conditions.
        size : int
            Results per page (max 250).
        sort_field : str
            Sort field name.
        sort_asc : bool
            Ascending sort when True.
        max_results : int
            Total results cap; 0 means unlimited.

        Returns
        -------
        list[dict]
            Raw Yahoo Finance quote dicts.
        """
        ...


@runtime_checkable
class PriceHistoryProvider(Protocol):
    """Provides OHLCV price history and recent news for a symbol.

    Implemented by: src.data.yahoo_client
    """

    def get_price_history(
        self,
        symbol: str,
        period: str = "1y",
    ) -> Optional[pd.DataFrame]:
        """Return OHLCV price history as a DataFrame.

        Parameters
        ----------
        symbol : str
            Yahoo Finance ticker.
        period : str
            yfinance period string (e.g. "1y", "6mo").

        Returns
        -------
        pd.DataFrame | None
            Columns: Open, High, Low, Close, Volume.
            Returns None on error or empty result.
        """
        ...

    def get_stock_news(self, symbol: str, count: int = 10) -> list[dict]:
        """Return recent news articles for a symbol.

        Parameters
        ----------
        symbol : str
            Yahoo Finance ticker.
        count : int
            Maximum number of articles to return.

        Returns
        -------
        list[dict]
            Each dict contains at minimum: title, link, published.
        """
        ...


@runtime_checkable
class MacroDataProvider(Protocol):
    """Provides macro-economic indicator data.

    Implemented by: src.data.yahoo_client
    """

    def get_macro_indicators(self) -> list[dict]:
        """Return current values for macro indicators (S&P500, VIX, etc.).

        Returns
        -------
        list[dict]
            Each dict: name, symbol, price, daily_change, weekly_change,
            is_point_diff.
        """
        ...
