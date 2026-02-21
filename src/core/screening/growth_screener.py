"""GrowthScreener: growth-oriented screening (growth/high-growth/small-cap-growth)."""

from typing import Optional

from src.core.screening.query_builder import build_query, load_preset
from src.core.screening.query_screener import QueryScreener


class GrowthScreener:
    """Screen stocks for growth characteristics.

    Two-step pipeline:
      Step 1: EquityQuery for growth filtering (criteria from preset)
      Step 2: Fetch stock detail for EPS/revenue growth, sort by sort_by field

    Supports three modes via constructor parameters:
      - growth (default): EPS growth > 0 required, sorted by eps_growth
      - high-growth: profit not required, sorted by revenue_growth
      - small-cap-growth: profit not required, sorted by revenue_growth,
        with market cap ceiling via criteria_overrides
    """

    def __init__(
        self,
        yahoo_client,
        preset: str = "growth",
        sort_by: str = "eps_growth",
        require_positive_eps: bool = True,
    ):
        """Initialise the screener.

        Parameters
        ----------
        yahoo_client : module or object
            Must expose ``screen_stocks()`` and ``get_stock_detail()``.
        preset : str
            Preset name to load from screening_presets.yaml.
        sort_by : str
            Field to sort results by ('eps_growth' or 'revenue_growth').
        require_positive_eps : bool
            When True, filter out stocks with eps_growth <= 0.
            Set to False for high-growth/small-cap-growth (profit not required).
        """
        self.yahoo_client = yahoo_client
        self.preset = preset
        self.sort_by = sort_by
        self.require_positive_eps = require_positive_eps

    def screen(
        self,
        region: str = "jp",
        top_n: int = 20,
        sector: Optional[str] = None,
        theme: Optional[str] = None,
        criteria_overrides: Optional[dict] = None,
    ) -> list[dict]:
        """Run the two-step growth screening pipeline.

        Parameters
        ----------
        region : str
            Market region code (e.g. 'jp', 'us', 'sg').
        top_n : int
            Maximum number of results to return.
        sector : str, optional
            Sector filter (e.g. 'Technology').
        theme : str, optional
            Theme filter key (e.g. 'ai', 'ev', 'defense').
        criteria_overrides : dict, optional
            Override preset criteria (e.g. max_market_cap for small-cap-growth).

        Returns
        -------
        list[dict]
            Screened stocks sorted by self.sort_by descending.
        """
        criteria = load_preset(self.preset)
        if criteria_overrides:
            criteria.update(criteria_overrides)

        # Step 1: EquityQuery for growth-filtered stocks (sorted by market cap)
        query = build_query(criteria, region=region, sector=sector, theme=theme)

        # Fetch enough candidates for detail enrichment
        fetch_size = max(top_n * 3, 60)
        raw_quotes = self.yahoo_client.screen_stocks(
            query,
            size=250,
            max_results=fetch_size,
            sort_field="intradaymarketcap",
            sort_asc=False,
        )

        if not raw_quotes:
            return []

        # Normalize quotes
        fundamentals: list[dict] = []
        for quote in raw_quotes:
            normalized = QueryScreener._normalize_quote(quote)
            fundamentals.append(normalized)

        # Step 2: Fetch stock detail for EPS growth, sort by growth
        results: list[dict] = []
        for stock in fundamentals:
            symbol = stock.get("symbol")
            if not symbol:
                continue

            detail = self.yahoo_client.get_stock_detail(symbol)
            if detail is None:
                continue

            eps_growth = detail.get("eps_growth")
            if self.require_positive_eps:
                if eps_growth is None or eps_growth <= 0:
                    continue

            rev_growth = stock.get("revenue_growth") or detail.get("revenue_growth")

            results.append({
                "symbol": symbol,
                "name": stock.get("name"),
                "sector": stock.get("sector"),
                "price": stock.get("price"),
                "per": stock.get("per"),
                "forward_per": stock.get("forward_per"),
                "pbr": stock.get("pbr"),
                "roe": stock.get("roe"),
                "eps_growth": eps_growth,
                "revenue_growth": rev_growth,
                "market_cap": stock.get("market_cap"),
            })

        # Sort by configured field descending
        results.sort(key=lambda r: r.get(self.sort_by, 0) or 0, reverse=True)
        return results[:top_n]
