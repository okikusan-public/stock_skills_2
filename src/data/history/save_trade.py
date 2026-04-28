"""Save trade records to history (KIK-578 split from save.py)."""

import json
from datetime import date, datetime
from typing import Optional

from src.data.history._helpers import (
    _safe_filename,
    _history_dir,
    _sanitize,
    _dual_write_graph,
    _unique_suffix,
)


def save_trade(
    symbol: str,
    trade_type: str,
    shares: int,
    price: float,
    currency: str,
    date_str: str,
    memo: str = "",
    base_dir: str = "data/history",
    sell_price: Optional[float] = None,
    realized_pnl: Optional[float] = None,
    pnl_rate: Optional[float] = None,
    hold_days: Optional[int] = None,
    cost_price: Optional[float] = None,
    stock_info: Optional[dict] = None,
) -> str:
    """Save a trade record to JSON.

    Returns the absolute path of the saved file.

    Parameters
    ----------
    sell_price : float, optional
        売却単価（KIK-441）。sell 時のみ。
    realized_pnl : float, optional
        実現損益（KIK-441）。
    pnl_rate : float, optional
        損益率（KIK-441）。
    hold_days : int, optional
        保有日数（KIK-441）。
    cost_price : float, optional
        取得単価（KIK-441）。sell 時に保存。
    """
    today = date.today().isoformat()
    now_dt = datetime.now()
    now = now_dt.isoformat(timespec="seconds")
    # KIK-744: HHMMSSffffff + uuid hex で完全一意化（同秒2回呼びでも衝突しない）
    ts_suffix = _unique_suffix(now_dt)
    identifier = f"{trade_type}_{_safe_filename(symbol)}"
    filename = f"{today}_{identifier}_{ts_suffix}.json"

    payload: dict = {
        "category": "trade",
        "date": date_str,
        "timestamp": now,
        "symbol": symbol,
        "trade_type": trade_type,
        "shares": shares,
        "price": price,
        "currency": currency,
        "memo": memo,
        "_saved_at": now,
    }

    # KIK-441: sell P&L フィールド
    if sell_price is not None:
        payload["sell_price"] = sell_price
    if realized_pnl is not None:
        payload["realized_pnl"] = realized_pnl
    if pnl_rate is not None:
        payload["pnl_rate"] = pnl_rate
    if hold_days is not None:
        payload["hold_days"] = hold_days
    if cost_price is not None:
        payload["cost_price"] = cost_price

    d = _history_dir("trade", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-399/420/555) -- graceful degradation
    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_trade, merge_stock
        # KIK-555: Enrich Stock metadata from stock_info or yfinance
        _si = stock_info
        if not _si:
            try:
                from src.data import yahoo_client
                _si = yahoo_client.get_stock_info(symbol) or {}
            except Exception:
                _si = {}
        merge_stock(
            symbol=symbol,
            name=_si.get("name", ""),
            sector=_si.get("sector", ""),
            country=_si.get("country", ""),
        )
        merge_trade(
            trade_date=date_str, trade_type=trade_type, symbol=symbol,
            shares=shares, price=price, currency=currency, memo=memo,
            semantic_summary=sem_summary, embedding=emb,
            sell_price=sell_price, realized_pnl=realized_pnl,
            hold_days=hold_days,
        )

    _dual_write_graph(
        _graph_write, "trade",
        dict(date=date_str, trade_type=trade_type,
             symbol=symbol, shares=shares, memo=memo),
    )

    return str(path.resolve())
