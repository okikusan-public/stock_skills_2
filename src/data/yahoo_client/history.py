"""Price history and news fetching (KIK-449, KIK-531)."""

import socket
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

from src.data.yahoo_client._memory_cache import price_history_cache


def get_price_history(symbol: str, period: str = "1y") -> Optional[pd.DataFrame]:
    """Fetch price history for technical analysis.

    Returns a pandas DataFrame with columns: Open, High, Low, Close, Volume.
    Returns None on error.

    Uses in-memory cache (default 5 min TTL) to avoid redundant API calls
    within a screening session (KIK-531).
    """
    cache_key = f"{symbol}:{period}"
    cached = price_history_cache.get(cache_key)
    if cached is not None:
        return cached.copy()

    try:
        time.sleep(1)  # rate-limit
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist is None or hist.empty:
            print(f"[yahoo_client] No price history for {symbol}")
            return None
        # Keep only the standard OHLCV columns
        expected_cols = ["Open", "High", "Low", "Close", "Volume"]
        available_cols = [c for c in expected_cols if c in hist.columns]
        if "Close" not in available_cols:
            print(f"[yahoo_client] No 'Close' column in history for {symbol}")
            return None
        result = hist[available_cols]
        price_history_cache.set(cache_key, result)
        return result
    except (TimeoutError, socket.timeout) as e:
        print(
            f"⚠️  Yahoo Financeへの接続がタイムアウトしました ({symbol})\n"
            "    原因: ネットワーク接続が不安定、またはYahoo Financeが一時的に応答していません\n"
            "    対処: ネットワーク接続を確認し、再試行してください"
        )
        return None
    except Exception as e:
        if "timed out" in str(e).lower() or "timeout" in str(e).lower():
            print(
                f"⚠️  Yahoo Financeへの接続がタイムアウトしました ({symbol})\n"
                "    原因: ネットワーク接続が不安定、またはYahoo Financeが一時的に応答していません\n"
                "    対処: ネットワーク接続を確認し、再試行してください"
            )
        else:
            print(f"[yahoo_client] Error fetching price history for {symbol}: {e}")
        return None


def get_stock_news(symbol: str, count: int = 10) -> list[dict]:
    """Fetch recent news for a stock symbol.

    Returns a list of news items with title, publisher, link, and publish time.
    No caching is applied because news freshness is important.

    Parameters
    ----------
    symbol : str
        Stock ticker symbol (e.g. "AAPL", "7203.T").
    count : int
        Maximum number of news items to return (default 10).

    Returns
    -------
    list[dict]
        Each dict contains: title, publisher, link, publish_time (ISO format str).
        Returns an empty list on error.
    """
    try:
        ticker = yf.Ticker(symbol)
        raw_news = ticker.news
        if not raw_news:
            return []

        results = []
        for item in raw_news[:count]:
            content = item.get("content", item)  # yfinance wraps in "content" sometimes
            if isinstance(content, dict):
                publish_time = content.get("pubDate") or content.get("providerPublishTime")
            else:
                publish_time = item.get("providerPublishTime")

            # Handle providerPublishTime as unix timestamp
            if isinstance(publish_time, (int, float)):
                publish_time = datetime.fromtimestamp(publish_time).isoformat()

            news_item = {
                "title": content.get("title", "") if isinstance(content, dict) else item.get("title", ""),
                "publisher": content.get("provider", {}).get("displayName", "") if isinstance(content, dict) else item.get("publisher", ""),
                "link": content.get("canonicalUrl", {}).get("url", "") if isinstance(content, dict) else item.get("link", ""),
                "publish_time": str(publish_time) if publish_time else "",
            }
            results.append(news_item)
        return results
    except Exception as e:
        print(f"[yahoo_client] Error fetching news for {symbol}: {e}")
        return []
