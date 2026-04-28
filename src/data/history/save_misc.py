"""Save stress test and forecast results to history (KIK-578 split from save.py)."""

import json
from datetime import date, datetime

from src.data.history._helpers import (
    _safe_filename,
    _history_dir,
    _sanitize,
    _dual_write_graph,
    _unique_suffix,
)


def save_stress_test(
    scenario: str,
    symbols: list[str],
    portfolio_impact: float,
    per_stock_impacts: list[dict] | None = None,
    var_result: dict | None = None,
    high_correlation_pairs: list | None = None,
    concentration: dict | None = None,
    recommendations: list | None = None,
    base_dir: str = "data/history",
) -> str:
    """Save stress test results to JSON (KIK-428).

    Returns the absolute path of the saved file.
    """
    today = date.today().isoformat()
    now_dt = datetime.now()
    now = now_dt.isoformat(timespec="seconds")
    # KIK-744: HHMMSSffffff + uuid hex で完全一意化
    ts_suffix = _unique_suffix(now_dt)
    identifier = _safe_filename(scenario)
    filename = f"{today}_{identifier}_{ts_suffix}.json"

    payload = {
        "category": "stress_test",
        "date": today,
        "timestamp": now,
        "scenario": scenario,
        "symbols": symbols,
        "portfolio_impact": portfolio_impact,
        "per_stock_impacts": per_stock_impacts or [],
        "var_result": var_result or {},
        "high_correlation_pairs": high_correlation_pairs or [],
        "concentration": concentration or {},
        "recommendations": recommendations or [],
        "_saved_at": now,
    }

    d = _history_dir("stress_test", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-428) -- graceful degradation
    var = var_result or {}

    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_stress_test, merge_stock
        for sym in symbols:
            merge_stock(symbol=sym)
        merge_stress_test(
            test_date=today, scenario=scenario,
            portfolio_impact=portfolio_impact, symbols=symbols,
            var_95=var.get("var_95_daily", 0), var_99=var.get("var_99_daily", 0),
            semantic_summary=sem_summary, embedding=emb,
        )

    _dual_write_graph(
        _graph_write, "stress_test",
        dict(date=today, scenario=scenario,
             portfolio_impact=portfolio_impact, symbol_count=len(symbols)),
    )

    return str(path.resolve())


def save_forecast(
    positions: list[dict],
    total_value_jpy: float = 0,
    base_dir: str = "data/history",
) -> str:
    """Save forecast results to JSON (KIK-428).

    Parameters
    ----------
    positions : list[dict]
        Per-position forecast data with optimistic/base/pessimistic returns.
    total_value_jpy : float
        Total portfolio value in JPY.
    base_dir : str
        Root history directory.

    Returns the absolute path of the saved file.
    """
    today = date.today().isoformat()
    now_dt = datetime.now()
    now = now_dt.isoformat(timespec="seconds")
    # KIK-744: HHMMSSffffff + uuid hex で完全一意化
    ts_suffix = _unique_suffix(now_dt)
    filename = f"{today}_forecast_{ts_suffix}.json"

    # Extract portfolio-level 3-scenario returns from positions
    symbols = [p.get("symbol", "") for p in positions if p.get("symbol")]
    opt_returns = [p.get("optimistic", 0) for p in positions if p.get("symbol")]
    base_returns = [p.get("base", 0) for p in positions if p.get("symbol")]
    pess_returns = [p.get("pessimistic", 0) for p in positions if p.get("symbol")]
    avg_opt = sum(opt_returns) / len(opt_returns) if opt_returns else 0
    avg_base = sum(base_returns) / len(base_returns) if base_returns else 0
    avg_pess = sum(pess_returns) / len(pess_returns) if pess_returns else 0

    payload = {
        "category": "forecast",
        "date": today,
        "timestamp": now,
        "portfolio": {
            "optimistic": avg_opt,
            "base": avg_base,
            "pessimistic": avg_pess,
        },
        "positions": positions,
        "total_value_jpy": total_value_jpy,
        "_saved_at": now,
    }

    d = _history_dir("forecast", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-428) -- graceful degradation
    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_forecast, merge_stock
        for sym in symbols:
            merge_stock(symbol=sym)
        merge_forecast(
            forecast_date=today, optimistic=avg_opt, base=avg_base,
            pessimistic=avg_pess, symbols=symbols,
            total_value_jpy=total_value_jpy,
            semantic_summary=sem_summary, embedding=emb,
        )

    _dual_write_graph(
        _graph_write, "forecast",
        dict(date=today, optimistic=avg_opt, base=avg_base,
             pessimistic=avg_pess, symbol_count=len(symbols)),
    )

    return str(path.resolve())
