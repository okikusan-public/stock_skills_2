"""Port interfaces for SOLID compliance (KIK-513 DIP, KIK-516 ISP).

Protocol-based interfaces that decouple Core from Data layer.
Existing modules satisfy these protocols structurally — no modification needed.

Market data (yahoo_client) — ISP-split (KIK-516):
  StockInfoProvider     — get_stock_info, get_stock_detail, get_multiple_stocks
  ScreeningProvider     — screen_stocks
  PriceHistoryProvider  — get_price_history, get_stock_news
  MacroDataProvider     — get_macro_indicators

Research data (grok_client) — ISP-split (KIK-516):
  ResearchSearcher      — search_stock_deep, search_x_sentiment, search_industry,
                          search_market, search_business
  TrendingSearcher      — search_trending_stocks, get_trending_themes
  TextSynthesizer       — synthesize_text
  GrokAvailability      — is_available, get_error_status

Research data (grok_client) — DIP composite (KIK-513):
  ResearchClient        — is_available + get_error_status + all search methods

Graph store — DIP (KIK-513):
  GraphReader           — read-only queries against Neo4j
  GraphWriter           — write operations to Neo4j

Storage — DIP (KIK-513):
  HistoryStore          — screening/report/research history
  NoteStore             — investment notes
"""

from src.core.ports.graph import GraphReader, GraphWriter
from src.core.ports.market_data import (
    MacroDataProvider,
    PriceHistoryProvider,
    ScreeningProvider,
    StockInfoProvider,
)
from src.core.ports.research import (
    GrokAvailability,
    ResearchClient,
    ResearchSearcher,
    TextSynthesizer,
    TrendingSearcher,
)
from src.core.ports.storage import HistoryStore, NoteStore

__all__ = [
    # Graph store protocols (KIK-513)
    "GraphReader",
    "GraphWriter",
    # Yahoo-client protocols — ISP (KIK-516)
    "StockInfoProvider",
    "ScreeningProvider",
    "PriceHistoryProvider",
    "MacroDataProvider",
    # Grok-client protocols — ISP (KIK-516)
    "ResearchSearcher",
    "TrendingSearcher",
    "TextSynthesizer",
    "GrokAvailability",
    # Grok-client — DIP composite (KIK-513)
    "ResearchClient",
    # Storage protocols (KIK-513)
    "HistoryStore",
    "NoteStore",
]
