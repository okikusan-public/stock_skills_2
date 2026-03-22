"""Change quality evaluation for portfolio health checks (KIK-576).

Reuses alpha.py's compute_change_score() to assess whether the
original investment thesis (fundamental improvement) is still valid.
"""

from src.core.common import is_etf as _is_etf
from src.core.health.etf import check_etf_health

# Value trap detection extracted to src/core/value_trap.py (KIK-392)
from src.core.value_trap import detect_value_trap as _detect_value_trap  # noqa: F401


def check_change_quality(stock_detail: dict) -> dict:
    """Evaluate change quality (alpha signal) of a holding.

    Reuses alpha.py's compute_change_score() to assess whether the
    original investment thesis (fundamental improvement) is still valid.

    Parameters
    ----------
    stock_detail : dict
        From yahoo_client.get_stock_detail().

    Returns
    -------
    dict
        Keys: change_score, quality_pass, passed_count, indicators,
        earnings_penalty, quality_label.
    """
    if _is_etf(stock_detail):
        etf_health = check_etf_health(stock_detail)
        return {
            "change_score": 0,
            "quality_pass": False,
            "passed_count": 0,
            "indicators": {},
            "earnings_penalty": 0,
            "quality_label": "対象外",
            "is_etf": True,
            "etf_health": etf_health,
        }

    from src.core.screening.alpha import compute_change_score

    result = compute_change_score(stock_detail)

    passed_count = result["passed_count"]

    if passed_count >= 3:
        quality_label = "良好"
    elif passed_count == 2:
        quality_label = "1指標↓"
    else:
        quality_label = "複数悪化"

    return {
        "change_score": result["change_score"],
        "quality_pass": result["quality_pass"],
        "passed_count": passed_count,
        "indicators": {
            "accruals": result["accruals"],
            "revenue_acceleration": result["revenue_acceleration"],
            "fcf_yield": result["fcf_yield"],
            "roe_trend": result["roe_trend"],
        },
        "earnings_penalty": result.get("earnings_penalty", 0),
        "quality_label": quality_label,
        "is_etf": False,
    }
