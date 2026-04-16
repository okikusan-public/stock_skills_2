"""Theme exposure analysis for portfolio health checks (KIK-604).

Computes PF theme exposure and detects gaps with trending themes.
"""


def _compute_theme_exposure(
    positions: list[dict],
    eval_by_symbol: dict[str, float],
    total_value: float,
) -> dict | None:
    """Compute PF theme exposure and detect gaps with trending themes.

    Parameters
    ----------
    positions : list[dict]
        Health check result dicts (each must have "symbol" key).
    eval_by_symbol : dict[str, float]
        Mapping from symbol to evaluation value in JPY.
    total_value : float
        Total portfolio value (sum of eval_by_symbol values).

    Returns
    -------
    dict or None
        Keys:
        - pf_themes: {theme_name: {symbols: [...], weight: float}}
        - trending_themes: [{theme, stock_count}]
        - overlap: list of theme names covered by PF that are also trending
        - gap: list of {theme, stock_count} for trending themes not in PF
        Returns None if graph unavailable or no theme data.
    """
    try:
        from src.data.graph_query.stock import get_themes_for_symbols_batch
        from src.data.graph_query.market import get_theme_trends
    except ImportError:
        return None

    symbols = [r["symbol"] for r in positions]
    if not symbols:
        return None

    # 1. Get themes for PF symbols
    try:
        symbol_themes = get_themes_for_symbols_batch(symbols)
    except Exception:
        return None

    if not symbol_themes:
        return None

    # 2. Compute PF theme weights
    pf_themes: dict[str, dict] = {}
    for sym, themes in symbol_themes.items():
        weight = eval_by_symbol.get(sym, 0) / total_value if total_value > 0 else 0
        for theme in themes:
            if theme not in pf_themes:
                pf_themes[theme] = {"symbols": [], "weight": 0.0}
            pf_themes[theme]["symbols"].append(sym)
            pf_themes[theme]["weight"] += weight

    # Round weights
    for theme_data in pf_themes.values():
        theme_data["weight"] = round(theme_data["weight"], 4)

    # 3. Get trending themes
    try:
        trending_themes = get_theme_trends(limit=10)
    except Exception:
        trending_themes = []

    # 4. Compute overlap and gap
    pf_theme_names = set(pf_themes.keys())
    trending_names = {t["theme"] for t in trending_themes}

    overlap = sorted(pf_theme_names & trending_names)
    gap = [t for t in trending_themes if t["theme"] not in pf_theme_names]

    return {
        "pf_themes": dict(
            sorted(pf_themes.items(), key=lambda x: -x[1]["weight"])
        ),
        "trending_themes": trending_themes,
        "overlap": overlap,
        "gap": gap,
    }
