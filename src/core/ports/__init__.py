"""ISP-compliant Protocol interfaces for external data clients (KIK-516).

Each Protocol defines a narrow, role-specific interface so that callers
only depend on the methods they actually use — not the full module surface.

Market data (yahoo_client):
  StockInfoProvider     — get_stock_info, get_stock_detail, get_multiple_stocks
  ScreeningProvider     — screen_stocks
  PriceHistoryProvider  — get_price_history, get_stock_news
  MacroDataProvider     — get_macro_indicators

Research data (grok_client):
  ResearchSearcher      — search_stock_deep, search_x_sentiment, search_industry,
                          search_market, search_business
  TrendingSearcher      — search_trending_stocks, get_trending_themes
  TextSynthesizer       — synthesize_text
  GrokAvailability      — is_available, get_error_status

Import:
  from src.core.ports import (
      StockInfoProvider, ScreeningProvider,
      PriceHistoryProvider, MacroDataProvider,
      ResearchSearcher, TrendingSearcher,
      TextSynthesizer, GrokAvailability,
  )
"""

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

__all__ = [
    # Yahoo-client protocols
    "StockInfoProvider",
    "ScreeningProvider",
    "PriceHistoryProvider",
    "MacroDataProvider",
    # Grok-client protocols
    "ResearchSearcher",
    "TrendingSearcher",
    "TextSynthesizer",
    "GrokAvailability",
]
