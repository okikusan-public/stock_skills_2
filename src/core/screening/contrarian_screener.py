"""ContrarianScreener: oversold-but-solid screening pipeline (KIK-504, KIK-533, KIK-530)."""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.core.screening.contrarian import compute_contrarian_score
from src.core.screening.indicators import calculate_value_score
from src.core.screening.query_builder import build_query
from src.core.screening.query_screener import QueryScreener

_MAX_WORKERS = int(os.environ.get("SCREEN_MAX_WORKERS", "5"))


class ContrarianScreener:
    """Screen for oversold stocks with solid fundamentals.

    Three-step pipeline:
      Step 1: EquityQuery for fundamental filtering (low PER/PBR, min ROE)
      Step 2: Contrarian score calculation (technical + valuation + fundamental) — parallel
      Step 3: Filter (score >= 30) and rank by contrarian_score
    """

    DEFAULT_CRITERIA = {
        "max_per": 15,
        "max_pbr": 1.5,
        "min_roe": 0.03,
    }

    _MIN_CONTRARIAN_SCORE = 30.0

    def __init__(self, yahoo_client):
        self.yahoo_client = yahoo_client

    def _score_one_stock(self, stock: dict) -> Optional[dict]:
        """Score a single stock for contrarian signals.

        Returns the enriched stock dict if score >= threshold, else None.
        """
        symbol = stock.get("symbol")
        if not symbol:
            return None

        hist = self.yahoo_client.get_price_history(symbol)

        detail = self.yahoo_client.get_stock_detail(symbol)
        if detail is None:
            detail = {}

        merged = {**stock, **detail}

        ct_result = compute_contrarian_score(hist, merged)

        if ct_result["contrarian_score"] < self._MIN_CONTRARIAN_SCORE:
            return None

        stock["contrarian_score"] = ct_result["contrarian_score"]
        stock["contrarian_grade"] = ct_result["grade"]
        stock["is_contrarian"] = ct_result["is_contrarian"]
        stock["tech_score"] = ct_result["technical"]["score"]
        stock["val_score"] = ct_result["valuation"]["score"]
        stock["fund_score"] = ct_result["fundamental"]["score"]
        stock["rsi"] = ct_result["technical"].get("rsi")
        stock["sma200_deviation"] = ct_result["technical"].get("sma200_deviation")
        stock["bb_position"] = ct_result["technical"].get("bb_position")
        stock["volume_surge"] = ct_result["technical"].get("volume_surge")
        return stock

    def screen(
        self,
        region: str = "jp",
        top_n: int = 20,
        sector: Optional[str] = None,
        theme: Optional[str] = None,
    ) -> list[dict]:
        """Run the contrarian screening pipeline.

        Parameters
        ----------
        region : str
            Market region code (e.g. 'jp', 'us').
        top_n : int
            Maximum number of results to return.
        sector : str, optional
            Sector filter.
        theme : str, optional
            Theme filter.

        Returns
        -------
        list[dict]
            Screened stocks sorted by contrarian_score descending.
        """
        criteria = dict(self.DEFAULT_CRITERIA)

        # Step 1: EquityQuery for fundamental filtering
        query = build_query(criteria, region=region, sector=sector, theme=theme)

        raw_quotes = self.yahoo_client.screen_stocks(
            query,
            size=250,
            max_results=max(top_n * 3, 30),
            sort_field="intradaymarketcap",
            sort_asc=False,
        )

        if not raw_quotes:
            return []

        # Normalize
        fundamentals: list[dict] = []
        for quote in raw_quotes:
            normalized = QueryScreener._normalize_quote(quote)
            normalized["value_score"] = calculate_value_score(normalized)
            fundamentals.append(normalized)

        # Step 2: Contrarian score calculation (parallel)
        scored: list[dict] = []

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._score_one_stock, stock): stock
                for stock in fundamentals
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

        # Step 3: Sort by contrarian_score descending
        scored.sort(key=lambda r: r.get("contrarian_score", 0), reverse=True)
        return scored[:top_n]
