"""Protocol interfaces for grok_client (KIK-513 DIP + KIK-516 ISP).

ISP-split (KIK-516) — narrow, role-specific interfaces:
  ResearchSearcher      — search_stock_deep, search_x_sentiment, search_industry,
                          search_market, search_business
  TrendingSearcher      — search_trending_stocks, get_trending_themes
  TextSynthesizer       — synthesize_text
  GrokAvailability      — is_available, get_error_status

DIP composite (KIK-513) — broad interface for dependency injection:
  ResearchClient        — is_available + get_error_status + all search methods

Structural compatibility:
  The ``src.data.grok_client`` module satisfies all Protocols
  without any modifications — these are additive type annotations only.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# ISP-split Protocols (KIK-516)
# ---------------------------------------------------------------------------


@runtime_checkable
class ResearchSearcher(Protocol):
    """Searches X/web for stock, market, industry, and business research.

    Implemented by: src.data.grok_client
    """

    def search_stock_deep(
        self,
        symbol: str,
        company_name: str = "",
        timeout: int = 30,
        context: str = "",
    ) -> dict:
        """Deep research on a stock via X and web search.

        Parameters
        ----------
        symbol : str
            Ticker (e.g. "7203.T", "AAPL").
        company_name : str
            Company name for better prompt context.
        timeout : int
            Request timeout in seconds.
        context : str
            Optional investor context from Neo4j (KIK-488).

        Returns
        -------
        dict
            Keys: recent_news, catalysts, analyst_views,
            x_sentiment, competitive_notes, raw_response.
        """
        ...

    def search_x_sentiment(
        self,
        symbol: str,
        company_name: str = "",
        timeout: int = 30,
        context: str = "",
    ) -> dict:
        """Search X for market sentiment on a stock.

        Parameters
        ----------
        symbol : str
            Ticker symbol.
        company_name : str
            Company name for better search context.
        timeout : int
            Request timeout in seconds.
        context : str
            Optional investor context.

        Returns
        -------
        dict
            Keys: positive (list[str]), negative (list[str]),
            sentiment_score (float, -1 to 1), raw_response (str).
        """
        ...

    def search_industry(
        self,
        industry_or_theme: str,
        timeout: int = 30,
        context: str = "",
    ) -> dict:
        """Research an industry or investment theme via X and web.

        Parameters
        ----------
        industry_or_theme : str
            Industry name or theme (e.g. "半導体", "EV", "AI").
        timeout : int
            Request timeout in seconds.
        context : str
            Optional investor context.

        Returns
        -------
        dict
            See EMPTY_INDUSTRY for the schema.
        """
        ...

    def search_market(
        self,
        market_or_index: str,
        timeout: int = 30,
        context: str = "",
    ) -> dict:
        """Research a market or index via X and web search.

        Parameters
        ----------
        market_or_index : str
            Market or index name (e.g. "日経平均", "S&P500").
        timeout : int
            Request timeout in seconds.
        context : str
            Optional investor context.

        Returns
        -------
        dict
            See EMPTY_MARKET for the schema.
        """
        ...

    def search_business(
        self,
        symbol: str,
        company_name: str = "",
        timeout: int = 60,
        context: str = "",
    ) -> dict:
        """Research a company's business model via X and web search.

        Parameters
        ----------
        symbol : str
            Ticker symbol.
        company_name : str
            Company name for prompt accuracy.
        timeout : int
            Request timeout in seconds.
        context : str
            Optional investor context.

        Returns
        -------
        dict
            Keys: overview, segments, revenue_model, competitive_advantages,
            kpis, growth_strategy, risks, raw_response.
        """
        ...


@runtime_checkable
class TrendingSearcher(Protocol):
    """Discovers trending stocks and themes from X/web (KIK-440).

    Implemented by: src.data.grok_client
    """

    def search_trending_stocks(
        self,
        region: str = "japan",
        theme: Optional[str] = None,
        timeout: int = 60,
    ) -> dict:
        """Search X for currently trending stocks in a market region.

        Parameters
        ----------
        region : str
            Market region (japan/us/asean/sg/hk/kr/tw).
        theme : str | None
            Optional theme/sector filter (AI/EV/semiconductor/etc).
        timeout : int
            Request timeout in seconds.

        Returns
        -------
        dict
            Keys: stocks (list of {ticker, name, reason}),
            market_context (str), raw_response (str).
        """
        ...

    def get_trending_themes(
        self,
        region: str = "global",
        timeout: int = 30,
    ) -> dict:
        """Discover trending investment themes via Grok X/Web search.

        Parameters
        ----------
        region : str
            Region scope for theme detection.
        timeout : int
            Request timeout in seconds.

        Returns
        -------
        dict
            Keys: themes (list of {name, description, tickers}),
            raw_response (str).
        """
        ...


@runtime_checkable
class TextSynthesizer(Protocol):
    """Synthesises free-form text using the Grok API (KIK-452).

    Implemented by: src.data.grok_client
    Used for: summarising Neo4j graph context data.
    """

    def synthesize_text(self, prompt: str, timeout: int = 20) -> str:
        """Run a pure text-synthesis call (no search tools).

        Parameters
        ----------
        prompt : str
            Synthesis prompt (Japanese or English).
        timeout : int
            Request timeout in seconds.

        Returns
        -------
        str
            Generated text, or "" if unavailable/error.
        """
        ...


@runtime_checkable
class GrokAvailability(Protocol):
    """Reports API availability and error state (KIK-431).

    Implemented by: src.data.grok_client
    """

    def is_available(self) -> bool:
        """Return True when the API key is configured and no fatal error."""
        ...

    def get_error_status(self) -> dict:
        """Return the current error state dict.

        Returns
        -------
        dict
            Keys: status (str), status_code (int | None), message (str).
        """
        ...


# ---------------------------------------------------------------------------
# DIP composite Protocol (KIK-513)
# ---------------------------------------------------------------------------


@runtime_checkable
class ResearchClient(Protocol):
    """Broad interface for dependency injection of grok_client (KIK-513).

    Combines GrokAvailability + ResearchSearcher into a single Protocol
    for callers that need the full research API surface.

    Implemented by: src.data.grok_client
    """

    def is_available(self) -> bool:
        """Return True if the client is configured and ready to use."""
        ...

    def get_error_status(self) -> dict:
        """Return the current API error status dict."""
        ...

    def search_stock_deep(
        self,
        symbol: str,
        company_name: str = "",
        timeout: int = 30,
        context: str = "",
    ) -> dict:
        """Run deep research for a single stock."""
        ...

    def search_x_sentiment(
        self,
        symbol: str,
        company_name: str = "",
        timeout: int = 30,
        context: str = "",
    ) -> dict:
        """Fetch X (Twitter) sentiment for *symbol*."""
        ...

    def search_industry(
        self,
        industry_or_theme: str,
        timeout: int = 30,
        context: str = "",
    ) -> dict:
        """Run industry/theme research."""
        ...

    def search_market(
        self,
        market_or_index: str,
        timeout: int = 30,
        context: str = "",
    ) -> dict:
        """Run market overview research."""
        ...

    def search_business(
        self,
        symbol: str,
        company_name: str = "",
        timeout: int = 60,
        context: str = "",
    ) -> dict:
        """Run business model research for *symbol*."""
        ...
