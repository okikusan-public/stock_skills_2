"""Grok API (xAI) wrapper for X Search and sentiment analysis (KIK-359).

Uses the xAI Responses API to search X (Twitter) posts and analyze
market sentiment for individual stocks, industries, and markets.

API key is read from the XAI_API_KEY environment variable.
When the key is not set, is_available() returns False and
all search functions return empty results (graceful degradation).

Split into submodules in KIK-508.
"""

# Re-export `requests` at package level so that existing
# @patch("src.data.grok_client.requests.post") continues to work.
import requests  # noqa: F401

# --- Common: constants, helpers, error state ---
from src.data.grok_client._common import (  # noqa: F401
    EMPTY_STOCK_DEEP,
    EMPTY_INDUSTRY,
    EMPTY_MARKET,
    EMPTY_TRENDING,
    EMPTY_BUSINESS,
    EMPTY_TRENDING_THEMES,
    is_available,
    get_error_status,
    reset_error_state,
    # Private helpers re-exported for test compatibility
    _get_api_key,
    _is_japanese_stock,
    _contains_japanese,
    _call_grok_api,
    _parse_json_response,
    _parse_json_array_response,
    _error_warned,
    _error_state,
    _API_URL,
    _DEFAULT_MODEL,
)

# --- Stock functions ---
from src.data.grok_client.stock import (  # noqa: F401
    search_x_sentiment,
    search_stock_deep,
    _build_sentiment_prompt,
    _build_stock_deep_prompt,
)

# --- Market functions ---
from src.data.grok_client.market import (  # noqa: F401
    search_market,
    search_trending_stocks,
    get_trending_themes,
    _build_trending_prompt,
    _build_market_prompt,
    _build_trending_themes_prompt,
)

# --- Industry functions ---
from src.data.grok_client.industry import (  # noqa: F401
    search_industry,
    _build_industry_prompt,
)

# --- Business functions ---
from src.data.grok_client.business import (  # noqa: F401
    search_business,
    synthesize_text,
    _build_business_prompt,
)
