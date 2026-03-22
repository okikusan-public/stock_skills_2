"""Trend health analysis for portfolio health checks (KIK-576).

Analyzes SMA50/SMA200 crossovers, RSI, and trend direction from price history.
"""

import numpy as np
import pandas as pd
from typing import Optional

from src.core._thresholds import th

# Technical thresholds (from config/thresholds.yaml, KIK-446)
SMA_APPROACHING_GAP = th("health", "sma_approaching_gap", 0.02)
RSI_PREV_THRESHOLD = th("health", "rsi_prev_threshold", 50)
RSI_DROP_THRESHOLD = th("health", "rsi_drop_threshold", 40)


def check_trend_health(
    hist: Optional[pd.DataFrame],
    cross_lookback: int | None = None,
) -> dict:
    """Analyze trend health from price history.

    Parameters
    ----------
    hist : pd.DataFrame or None
        DataFrame with Close and Volume columns.
    cross_lookback : int or None
        Override cross event lookback window (KIK-438: 30 for small caps).
        Defaults to th("health", "cross_lookback", 60).

    Returns
    -------
    dict
        Trend analysis with keys: trend, price_above_sma50,
        price_above_sma200, sma50_above_sma200, dead_cross,
        sma50_approaching_sma200, rsi, rsi_drop, current_price,
        sma50, sma200.
    """
    default = {
        "trend": "不明",
        "price_above_sma50": False,
        "price_above_sma200": False,
        "sma50_above_sma200": False,
        "dead_cross": False,
        "sma50_approaching_sma200": False,
        "rsi": float("nan"),
        "rsi_drop": False,
        "current_price": float("nan"),
        "sma50": float("nan"),
        "sma200": float("nan"),
        "cross_signal": "none",
        "days_since_cross": None,
        "cross_date": None,
    }

    if hist is None or not isinstance(hist, pd.DataFrame):
        return default
    if "Close" not in hist.columns or len(hist) < 200:
        return default

    close = hist["Close"]

    from src.core.screening.technicals import compute_rsi

    sma50 = close.rolling(window=50).mean()
    sma200 = close.rolling(window=200).mean()
    rsi_series = compute_rsi(close, period=14)

    current_price = float(close.iloc[-1])
    current_sma50 = float(sma50.iloc[-1])
    current_sma200 = float(sma200.iloc[-1])
    current_rsi = float(rsi_series.iloc[-1])

    price_above_sma50 = current_price > current_sma50
    price_above_sma200 = current_price > current_sma200
    sma50_above_sma200 = current_sma50 > current_sma200
    dead_cross = not sma50_above_sma200

    # --- Cross event detection (lookback N trading days) ---
    _CROSS_LOOKBACK = cross_lookback if cross_lookback is not None else th("health", "cross_lookback", 60)
    cross_signal = "none"
    days_since_cross = None
    cross_date = None

    max_scan = min(_CROSS_LOOKBACK, len(sma50) - 201)
    for i in range(max(0, max_scan)):
        idx = -1 - i
        prev_idx = idx - 1
        cur_above = sma50.iloc[idx] > sma200.iloc[idx]
        prev_above = sma50.iloc[prev_idx] > sma200.iloc[prev_idx]

        if cur_above and not prev_above:
            cross_signal = "golden_cross"
            days_since_cross = i
            idx_val = hist.index[idx]
            cross_date = str(idx_val.date()) if hasattr(idx_val, "date") else str(idx_val)
            break
        elif not cur_above and prev_above:
            cross_signal = "death_cross"
            days_since_cross = i
            idx_val = hist.index[idx]
            cross_date = str(idx_val.date()) if hasattr(idx_val, "date") else str(idx_val)
            break

    # SMA50 approaching SMA200 (gap < 2%)
    sma_gap = (
        abs(current_sma50 - current_sma200) / current_sma200
        if current_sma200 > 0
        else 0
    )
    sma50_approaching = sma_gap < SMA_APPROACHING_GAP

    # RSI drop: was > 50 five days ago and now < 40
    rsi_drop = False
    if len(rsi_series) >= 6:
        prev_rsi = float(rsi_series.iloc[-6])
        if not np.isnan(prev_rsi) and prev_rsi > RSI_PREV_THRESHOLD and current_rsi < RSI_DROP_THRESHOLD:
            rsi_drop = True

    # Trend determination
    if price_above_sma50 and sma50_above_sma200:
        trend = "上昇"
    elif sma50_approaching or (not price_above_sma50 and price_above_sma200):
        trend = "横ばい"
    else:
        trend = "下降"

    return {
        "trend": trend,
        "price_above_sma50": price_above_sma50,
        "price_above_sma200": price_above_sma200,
        "sma50_above_sma200": sma50_above_sma200,
        "dead_cross": dead_cross,
        "sma50_approaching_sma200": sma50_approaching,
        "rsi": round(current_rsi, 2),
        "rsi_drop": rsi_drop,
        "current_price": round(current_price, 2),
        "sma50": round(current_sma50, 2),
        "sma200": round(current_sma200, 2),
        "cross_signal": cross_signal,
        "days_since_cross": days_since_cross,
        "cross_date": cross_date,
    }
