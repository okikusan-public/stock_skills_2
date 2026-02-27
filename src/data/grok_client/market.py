"""Market-related Grok API functions: search_market, search_trending_stocks, get_trending_themes.

Extracted from grok_client.py during KIK-508 submodule split.
"""

from typing import Optional

from src.data.grok_client._common import (
    EMPTY_MARKET,
    EMPTY_TRENDING,
    EMPTY_TRENDING_THEMES,
    _call_grok_api,
    _parse_json_response,
    _parse_json_array_response,
)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_trending_prompt(region: str = "japan", theme: Optional[str] = None) -> str:
    """Build the prompt for discovering trending stocks on X."""
    _REGION_DESC = {
        "japan": ("日本株", "Tokyo Stock Exchange", ".T"),
        "jp": ("日本株", "Tokyo Stock Exchange", ".T"),
        "us": ("米国株", "US stock exchanges (NYSE/NASDAQ)", ""),
        "asean": ("ASEAN株", "Singapore/Thailand/Malaysia/Indonesia/Philippines exchanges",
                  ".SI/.BK/.KL/.JK/.PS"),
        "sg": ("シンガポール株", "Singapore Exchange", ".SI"),
        "th": ("タイ株", "Stock Exchange of Thailand", ".BK"),
        "hk": ("香港株", "Hong Kong Stock Exchange", ".HK"),
        "kr": ("韓国株", "Korea Exchange", ".KS"),
        "tw": ("台湾株", "Taiwan Stock Exchange", ".TW"),
    }
    label, exchange, suffix = _REGION_DESC.get(region, _REGION_DESC["japan"])

    theme_part = f"\nFocus specifically on the theme/sector: {theme}" if theme else ""

    if suffix:
        suffix_inst = (
            f"Use Yahoo Finance ticker format with suffix '{suffix}' "
            f"(e.g., 7203{suffix.split('/')[0]} for Toyota)."
        )
    else:
        suffix_inst = "Use standard Yahoo Finance ticker symbols (e.g., AAPL, MSFT)."

    if region in ("japan", "jp"):
        return (
            f"X（Twitter）上で今、投資家の間で話題になっている{label}を検索してください。"
            f"{theme_part}\n\n"
            f"決算サプライズ、新製品発表、規制変更、業界トレンドなどで注目されている"
            f"銘柄を10〜20件見つけてください。\n"
            f"各銘柄について、ティッカーシンボルと話題の理由を提供してください。\n\n"
            f"重要: {suffix_inst}\n"
            f"Yahoo Finance で検索可能な実在のティッカーのみを返してください。\n\n"
            f"JSON形式で回答:\n"
            f'{{\n'
            f'  "stocks": [\n'
            f'    {{"ticker": "シンボル", "name": "企業名", "reason": "話題の理由"}}\n'
            f'  ],\n'
            f'  "market_context": "X上の市場センチメント概要"\n'
            f'}}'
        )
    return (
        f"Search X (Twitter) for stocks that are currently trending or heavily discussed "
        f"among investors in the {label} ({exchange}) market.{theme_part}\n\n"
        f"Find 10-20 stocks getting significant attention on X right now. "
        f"For each stock, provide the ticker symbol and a brief reason WHY it is trending.\n\n"
        f"IMPORTANT: {suffix_inst}\n"
        f"Return ONLY valid, real ticker symbols that can be looked up on Yahoo Finance.\n\n"
        f"Respond in JSON format:\n"
        f'{{\n'
        f'  "stocks": [\n'
        f'    {{"ticker": "SYMBOL", "name": "Company Name", "reason": "Why it is trending"}}\n'
        f'  ],\n'
        f'  "market_context": "Brief summary of the current market mood on X"\n'
        f'}}'
    )


def _build_market_prompt(market_or_index: str, context: str = "") -> str:
    """Build the prompt for market research."""
    context_block = f"{context}\n\n" if context else ""
    return (
        f"{context_block}"
        f"「{market_or_index}」の最新マーケット概況を、X（Twitter）とWebの情報をもとに調査してください。\n\n"
        f"1. 直近の値動きと要因\n"
        f"2. マクロ経済の影響（金利・為替・商品）\n"
        f"3. センチメント（強気/弱気のバランス）\n"
        f"4. 注目イベント・経済指標の予定\n"
        f"5. セクターローテーションの兆候\n\n"
        f"JSON形式で回答:\n"
        f'{{\n'
        f'  "price_action": "直近の値動きサマリー",\n'
        f'  "macro_factors": ["要因1", "要因2"],\n'
        f'  "sentiment": {{\n'
        f'    "score": 0.0,\n'
        f'    "summary": "概要"\n'
        f'  }},\n'
        f'  "upcoming_events": ["イベント1", "イベント2"],\n'
        f'  "sector_rotation": ["兆候1", "兆候2"]\n'
        f'}}'
    )


def _build_trending_themes_prompt(region: str = "global") -> str:
    """Build prompt for discovering trending investment themes (KIK-440)."""
    region_desc = {"japan": "日本市場", "jp": "日本市場", "us": "米国市場", "global": "グローバル市場"}
    label = region_desc.get(region, f"{region.upper()}市場")
    valid_keys = "ai, ev, cloud-saas, cybersecurity, biotech, renewable-energy, fintech, defense, healthcare"

    return (
        f"X（Twitter）とWebの情報をもとに、今{label}で投資家が注目している"
        f"セクター・投資テーマを調査してください。\n\n"
        f"勢いのあるテーマを3〜5つ特定し、各テーマについて:\n"
        f"- なぜ今注目されているか（簡潔な理由）\n"
        f"- 信頼度（0.0〜1.0）\n"
        f"を提供してください。\n\n"
        f"重要: theme は以下のキーのいずれかで返してください:\n"
        f"{valid_keys}\n\n"
        f"JSON形式で回答:\n"
        f"[\n"
        f'  {{"theme": "テーマキー", "reason": "注目理由（日本語）", "confidence": 0.85}}\n'
        f"]"
    )


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------

def search_market(
    market_or_index: str,
    timeout: int = 30,
    context: str = "",
) -> dict:
    """Research a market or index via X and web search.

    Parameters
    ----------
    market_or_index : str
        Market name or index (e.g. "日経平均", "S&P500").
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        See EMPTY_MARKET for the schema.
    """
    raw_text = _call_grok_api(_build_market_prompt(market_or_index, context=context), timeout)
    if not raw_text:
        return dict(EMPTY_MARKET)

    result = dict(EMPTY_MARKET)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("price_action"), str):
        result["price_action"] = parsed["price_action"]
    if isinstance(parsed.get("macro_factors"), list):
        result["macro_factors"] = parsed["macro_factors"]

    sentiment = parsed.get("sentiment")
    if isinstance(sentiment, dict):
        score = sentiment.get("score", 0.0)
        result["sentiment"] = {
            "score": max(-1.0, min(1.0, float(score))) if isinstance(score, (int, float)) else 0.0,
            "summary": sentiment.get("summary", "") if isinstance(sentiment.get("summary"), str) else "",
        }

    if isinstance(parsed.get("upcoming_events"), list):
        result["upcoming_events"] = parsed["upcoming_events"]
    if isinstance(parsed.get("sector_rotation"), list):
        result["sector_rotation"] = parsed["sector_rotation"]

    return result


def search_trending_stocks(
    region: str = "japan",
    theme: Optional[str] = None,
    timeout: int = 60,
) -> dict:
    """Search X for currently trending stocks in a specific market region.

    Parameters
    ----------
    region : str
        Market region (japan/us/asean/sg/hk/kr/tw).
    theme : str | None
        Optional theme/sector filter (AI/semiconductor/EV/etc).
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        Keys: stocks (list of {ticker, name, reason}),
              market_context (str), raw_response (str).
    """
    raw_text = _call_grok_api(_build_trending_prompt(region, theme), timeout)
    if not raw_text:
        return dict(EMPTY_TRENDING)

    result = dict(EMPTY_TRENDING)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    stocks_raw = parsed.get("stocks")
    if isinstance(stocks_raw, list):
        validated = []
        for item in stocks_raw:
            if isinstance(item, dict) and isinstance(item.get("ticker"), str):
                validated.append({
                    "ticker": item["ticker"].strip(),
                    "name": item.get("name", "") if isinstance(item.get("name"), str) else "",
                    "reason": item.get("reason", "") if isinstance(item.get("reason"), str) else "",
                })
        result["stocks"] = validated

    if isinstance(parsed.get("market_context"), str):
        result["market_context"] = parsed["market_context"]

    return result


def get_trending_themes(
    region: str = "global",
    timeout: int = 30,
) -> dict:
    """Discover trending investment themes via Grok X/Web search (KIK-440).

    Parameters
    ----------
    region : str
        Market region for theme discovery (japan/us/global).
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        Keys: themes (list of {theme, reason, confidence}),
              raw_response (str).
    """
    raw_text = _call_grok_api(_build_trending_themes_prompt(region), timeout)
    if not raw_text:
        return dict(EMPTY_TRENDING_THEMES)

    result = dict(EMPTY_TRENDING_THEMES)
    result["raw_response"] = raw_text

    # Try array first (expected format), then object with "themes" key
    parsed = _parse_json_array_response(raw_text)
    if not parsed:
        obj = _parse_json_response(raw_text)
        parsed = obj.get("themes", []) if isinstance(obj.get("themes"), list) else []

    validated = []
    for item in parsed:
        if isinstance(item, dict) and isinstance(item.get("theme"), str):
            validated.append({
                "theme": item["theme"].strip().lower(),
                "reason": item.get("reason", "") if isinstance(item.get("reason"), str) else "",
                "confidence": float(item.get("confidence", 0.5)) if isinstance(item.get("confidence"), (int, float)) else 0.5,
            })
    validated.sort(key=lambda x: x["confidence"], reverse=True)
    result["themes"] = validated
    return result
