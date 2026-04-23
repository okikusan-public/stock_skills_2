"""Yahoo Finance API wrapper with JSON file-based caching (KIK-449).

This package was split from a single yahoo_client.py module into submodules
for maintainability.  All public and internal symbols are re-exported here
so that existing imports (``from src.data import yahoo_client``,
``from src.data.yahoo_client import get_stock_info``, etc.) continue to work
without changes.
"""

# -- Re-export submodules so that patch paths like
#    "src.data.yahoo_client.time.sleep" and "src.data.yahoo_client.yf.screen"
#    resolve correctly against this package namespace. --
import time  # noqa: F401  (used by test patches)
import yfinance as yf  # noqa: F401  (used by test patches)

# -- Cache helpers (internal, but imported by tests) --
from src.data.yahoo_client._cache import (  # noqa: F401
    CACHE_DIR,
    CACHE_TTL_HOURS,
    _cache_path,
    _read_cache,
    _write_cache,
    _detail_cache_path,
    _read_detail_cache,
    _write_detail_cache,
)

# -- Normalization utilities (internal, but imported by tests) --
from src.data.yahoo_client._normalize import (  # noqa: F401
    _normalize_ratio,
    _safe_get,
    _sanitize_anomalies,
)

# -- Detail / stock info --
from src.data.yahoo_client.detail import (  # noqa: F401
    _try_get_field,
    _try_get_history,
    _build_dividend_history_from_actions,
    get_stock_info,
    get_multiple_stocks,
    get_stock_detail,
)

# -- Screening --
from src.data.yahoo_client.screen import screen_stocks  # noqa: F401

# -- Price history & news --
from src.data.yahoo_client.history import (  # noqa: F401
    get_price_history,
    get_stock_news,
)

# -- In-memory cache management (KIK-531) --
from src.data.yahoo_client._memory_cache import clear_memory_cache  # noqa: F401

# -- Macro indicators --
from src.data.yahoo_client.macro import (  # noqa: F401
    MACRO_TICKERS,
    _POINT_DIFF_TICKERS,
    get_macro_indicators,
)

# -- Sector relative strength (KIK-702) --
from src.data.yahoo_client.sector_rs import (  # noqa: F401
    SECTOR_ETFS,
    BENCHMARK,
    get_sector_rs,
)

__all__ = [
    # Constants
    "CACHE_DIR",
    "CACHE_TTL_HOURS",
    "MACRO_TICKERS",
    # Public functions
    "get_stock_info",
    "get_multiple_stocks",
    "get_stock_detail",
    "screen_stocks",
    "get_price_history",
    "get_stock_news",
    "get_macro_indicators",
    "clear_memory_cache",
    # Sector RS (KIK-702)
    "SECTOR_ETFS",
    "get_sector_rs",
]
