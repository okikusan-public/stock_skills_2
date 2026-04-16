"""Portfolio health check orchestrator (KIK-576).

Runs health check on all portfolio holdings, combining trend analysis,
change quality, alert levels, and long-term suitability.
"""

from src.core.common import is_cash as _is_cash, is_etf as _is_etf
from src.core._thresholds import th
from src.core.screening.indicators import (
    calculate_shareholder_return,
    calculate_shareholder_return_history,
    assess_return_stability,
)
from src.core.health.trend import check_trend_health
from src.core.health.quality import check_change_quality
from src.core.health.alert import compute_alert_level, ALERT_NONE
from src.core.health.labels import check_long_term_suitability
from src.core.health.community import _compute_community_concentration
from src.core.health.theme import _compute_theme_exposure
from src.core.value_trap import detect_value_trap as _detect_value_trap


def run_health_check(csv_path: str, client) -> dict:
    """Run health check on all portfolio holdings.

    For each holding:
    1. Fetch 1-year price history -> trend health (SMA, RSI)
    2. Fetch stock detail -> change quality (alpha score)
    3. Compute alert level

    Parameters
    ----------
    csv_path : str
        Path to portfolio CSV.
    client
        yahoo_client module (get_price_history, get_stock_detail).

    Returns
    -------
    dict
        Keys: positions, alerts (non-none only), summary.
    """
    from src.core.portfolio.portfolio_manager import get_snapshot
    from src.core.portfolio.small_cap import classify_market_cap, check_small_cap_allocation
    from src.core.ticker_utils import infer_region_code

    snapshot = get_snapshot(csv_path, client)
    positions = snapshot.get("positions", [])

    empty_summary = {
        "total": 0,
        "healthy": 0,
        "early_warning": 0,
        "caution": 0,
        "exit": 0,
    }

    if not positions:
        return {"positions": [], "alerts": [], "summary": empty_summary}

    results: list[dict] = []
    alerts: list[dict] = []
    counts = {"healthy": 0, "early_warning": 0, "caution": 0, "exit": 0}

    for pos in positions:
        symbol = pos["symbol"]

        # Skip cash positions (e.g., JPY.CASH, USD.CASH)
        if _is_cash(symbol):
            continue

        # 0. Small-cap classification (KIK-438)
        region_code = infer_region_code(symbol)
        size_class = classify_market_cap(pos.get("market_cap"), region_code)
        is_small_cap = size_class == "小型"

        # 1. Trend analysis (small caps use shorter cross lookback)
        hist = client.get_price_history(symbol, period="1y")
        cross_lb = (
            th("health", "small_cap_cross_lookback", 30)
            if is_small_cap
            else None
        )
        trend_health = check_trend_health(hist, cross_lookback=cross_lb)

        # 2. Change quality
        stock_detail = client.get_stock_detail(symbol)
        if stock_detail is None:
            stock_detail = {}
        change_quality = check_change_quality(stock_detail)

        # 3. Shareholder return stability (KIK-403)
        sh_return = calculate_shareholder_return(stock_detail)
        sh_history = calculate_shareholder_return_history(stock_detail)
        sh_stability = assess_return_stability(sh_history)

        # 4. Alert level (small-cap escalation: KIK-438)
        alert = compute_alert_level(
            trend_health, change_quality,
            stock_detail=stock_detail,
            return_stability=sh_stability,
            is_small_cap=is_small_cap,
        )

        # 5. Long-term suitability (KIK-371, enhanced KIK-403)
        long_term = check_long_term_suitability(
            stock_detail, shareholder_return_data=sh_return,
        )

        # 6. Value trap detection (KIK-381)
        value_trap = _detect_value_trap(stock_detail)

        # 7. Contrarian score for alerted stocks (KIK-504)
        contrarian_data = None
        if alert["level"] != ALERT_NONE and not _is_etf(stock_detail):
            from src.core.screening.contrarian import compute_contrarian_score as _ct_score
            contrarian_data = _ct_score(hist, stock_detail)

        # 8. Exit-rule check (KIK-566)
        exit_rule_hit = None
        try:
            from src.data.note_manager import check_exit_rule
            exit_rule_hit = check_exit_rule(symbol, pos.get("pnl_pct", 0))
        except Exception:
            pass

        result = {
            "symbol": symbol,
            "name": pos.get("name") or pos.get("memo", ""),
            "pnl_pct": pos.get("pnl_pct", 0),
            "size_class": size_class,
            "is_small_cap": is_small_cap,
            "trend_health": trend_health,
            "change_quality": change_quality,
            "alert": alert,
            "long_term": long_term,
            "value_trap": value_trap,
            "shareholder_return": sh_return,
            "return_stability": sh_stability,
            "contrarian": contrarian_data,
            "exit_rule_hit": exit_rule_hit,
        }
        results.append(result)

        if alert["level"] != ALERT_NONE:
            alerts.append(result)
            counts[alert["level"]] = counts.get(alert["level"], 0) + 1
        else:
            counts["healthy"] += 1

    # Portfolio-level small-cap allocation (KIK-438)
    # Build symbol -> evaluation_jpy lookup from snapshot positions
    eval_by_symbol = {
        p["symbol"]: p.get("evaluation_jpy", 0)
        for p in positions
        if not _is_cash(p["symbol"])
    }
    total_value = sum(eval_by_symbol.values())
    small_cap_value = sum(
        eval_by_symbol.get(r["symbol"], 0)
        for r in results
        if r.get("is_small_cap")
    )
    small_cap_weight = small_cap_value / total_value if total_value > 0 else 0.0
    small_cap_alloc = check_small_cap_allocation(small_cap_weight)

    # KIK-549: Community concentration analysis
    community_concentration = _compute_community_concentration(
        results, eval_by_symbol, total_value,
    )

    # KIK-604: Theme exposure analysis
    theme_exposure = _compute_theme_exposure(
        results, eval_by_symbol, total_value,
    )

    # KIK-469 Phase 2: Partition positions into stocks and ETFs
    stock_positions = [
        r for r in results
        if not r.get("change_quality", {}).get("is_etf")
    ]
    etf_positions = [
        r for r in results
        if r.get("change_quality", {}).get("is_etf")
    ]

    return {
        "positions": results,
        "stock_positions": stock_positions,
        "etf_positions": etf_positions,
        "alerts": alerts,
        "summary": {
            "total": len(results),
            **counts,
        },
        "small_cap_allocation": small_cap_alloc,
        "community_concentration": community_concentration,
        "theme_exposure": theme_exposure,
    }
