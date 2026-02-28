"""MomentumScreener: momentum surge / breakout screening (KIK-506, KIK-530: parallel)."""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.core.screening.query_builder import build_query
from src.core.screening.query_screener import QueryScreener
from src.core.screening.technicals import detect_momentum_surge

_MAX_WORKERS = int(os.environ.get("SCREEN_MAX_WORKERS", "5"))


class MomentumScreener:
    """Screen for momentum surge / breakout stocks.

    Sub-modes:
      - stable: steady uptrend (50MA deviation +10-15%, low beta, near high)
      - surge: strong breakout (50MA deviation +15%+, high volume)

    Three-step pipeline:
      Step 1: EquityQuery (momentum criteria + liquidity + market cap)
      Step 2: Technical analysis (detect_momentum_surge) — parallel
      Step 3: Filter + rank by surge_score
    """

    STABLE_CRITERIA = {
        "min_52wk_change": 0.15,
        "max_beta": 1.2,
        "min_market_cap": 50_000_000_000,
    }

    SURGE_CRITERIA = {
        "min_52wk_change": 0.20,
        "min_market_cap": 50_000_000_000,
        "min_avg_volume_3m": 500_000,
    }

    def __init__(self, yahoo_client):
        self.yahoo_client = yahoo_client

    def _score_one_stock(self, quote: dict, submode: str) -> Optional[dict]:
        """Evaluate a single stock for momentum signals.

        Returns the enriched stock dict if it passes, else None.
        """
        normalized = QueryScreener._normalize_quote(quote)
        symbol = normalized.get("symbol")
        if not symbol:
            return None

        fifty_day_avg_change = quote.get("fiftyDayAverageChangePercent")
        fifty_two_wk_high_change = quote.get("fiftyTwoWeekHighChangePercent")

        hist = self.yahoo_client.get_price_history(symbol)
        if hist is None or hist.empty:
            return None

        surge_result = detect_momentum_surge(
            hist,
            fifty_day_avg_change_pct=fifty_day_avg_change,
            fifty_two_week_high_change_pct=fifty_two_wk_high_change,
        )

        level = surge_result["surge_level"]

        if submode == "stable":
            if level != "accelerating":
                return None
        else:  # surge
            if level == "none":
                return None

        normalized["ma50_deviation"] = surge_result["ma50_deviation"]
        normalized["ma200_deviation"] = surge_result["ma200_deviation"]
        normalized["volume_ratio"] = surge_result["volume_ratio"]
        normalized["rsi"] = surge_result["rsi"]
        normalized["surge_level"] = level
        normalized["surge_score"] = surge_result["surge_score"]
        normalized["near_high"] = surge_result["near_high"]
        normalized["new_high"] = surge_result["new_high"]
        normalized["high_change_pct"] = fifty_two_wk_high_change
        return normalized

    def screen(
        self,
        region: str = "jp",
        top_n: int = 20,
        submode: str = "surge",
        sector: Optional[str] = None,
        theme: Optional[str] = None,
    ) -> list[dict]:
        """Run the momentum screening pipeline.

        Parameters
        ----------
        region : str
            Market region code (e.g. 'jp', 'us').
        top_n : int
            Maximum number of results to return.
        submode : str
            'stable' for steady uptrend, 'surge' for breakout.
        sector : str, optional
            Sector filter.
        theme : str, optional
            Theme filter.

        Returns
        -------
        list[dict]
            Screened stocks sorted by surge_score descending.
        """
        criteria = dict(self.STABLE_CRITERIA if submode == "stable" else self.SURGE_CRITERIA)

        # Step 1: EquityQuery
        query = build_query(criteria, region=region, sector=sector, theme=theme)

        raw_quotes = self.yahoo_client.screen_stocks(
            query,
            size=250,
            max_results=max(top_n * 5, 250),
            sort_field="intradaymarketcap",
            sort_asc=False,
        )

        if not raw_quotes:
            return []

        # Step 2: Technical analysis + filtering (parallel)
        scored: list[dict] = []

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._score_one_stock, quote, submode): quote
                for quote in raw_quotes
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result is not None:
                        scored.append(result)
                except Exception:
                    pass  # skip failed stocks

        if not scored:
            return []

        # Step 3: Sort by surge_score descending
        scored.sort(key=lambda r: r.get("surge_score", 0), reverse=True)
        return scored[:top_n]
