"""Stock-related Grok API functions: search_stock_deep, search_x_sentiment.

Extracted from grok_client.py during KIK-508 submodule split.
"""

from src.data.grok_client._common import (
    EMPTY_STOCK_DEEP,
    _call_grok_api,
    _is_japanese_stock,
    _parse_json_response,
)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_sentiment_prompt(symbol: str, company_name: str = "", context: str = "") -> str:
    """Build the prompt for sentiment analysis."""
    name_part = f" ({company_name})" if company_name else ""
    context_block = f"{context}\n\n" if context else ""
    return (
        f"{context_block}"
        f"Search X for recent posts about {symbol}{name_part} stock. "
        f"Analyze the sentiment of the posts and provide:\n"
        f"1. A list of positive factors (bullish signals) mentioned\n"
        f"2. A list of negative factors (bearish signals) mentioned\n"
        f"3. An overall sentiment score from -1.0 (very bearish) to 1.0 (very bullish)\n\n"
        f"Respond in JSON format:\n"
        f'{{"positive": ["factor1", "factor2"], '
        f'"negative": ["factor1", "factor2"], '
        f'"sentiment_score": 0.0}}'
    )


def _build_stock_deep_prompt(symbol: str, company_name: str = "", context: str = "") -> str:
    """Build the prompt for deep stock research."""
    name_part = f" ({company_name})" if company_name else ""
    context_block = f"{context}\n\n" if context else ""
    if _is_japanese_stock(symbol):
        return (
            f"{context_block}"
            f"{symbol}{name_part} について、X（Twitter）とWebの最新情報をもとに以下を調査してください。\n\n"
            f"1. 最近の重要ニュース（直近1-2週間）\n"
            f"2. 業績に影響する材料（ポジティブ/ネガティブ）\n"
            f"3. 機関投資家・アナリストの見方\n"
            f"4. X上の投資家センチメント\n"
            f"5. 競合他社との比較での注目点\n\n"
            f"JSON形式で回答:\n"
            f'{{\n'
            f'  "recent_news": ["ニュース1", "ニュース2"],\n'
            f'  "catalysts": {{\n'
            f'    "positive": ["材料1", "材料2"],\n'
            f'    "negative": ["材料1", "材料2"]\n'
            f'  }},\n'
            f'  "analyst_views": ["見解1", "見解2"],\n'
            f'  "x_sentiment": {{\n'
            f'    "score": 0.0,\n'
            f'    "summary": "概要テキスト",\n'
            f'    "key_opinions": ["意見1", "意見2"]\n'
            f'  }},\n'
            f'  "competitive_notes": ["注目点1", "注目点2"]\n'
            f'}}'
        )
    return (
        f"{context_block}"
        f"Research {symbol}{name_part} using X (Twitter) and web sources. Provide:\n\n"
        f"1. Key recent news (last 1-2 weeks)\n"
        f"2. Catalysts affecting earnings (positive/negative)\n"
        f"3. Institutional/analyst perspectives\n"
        f"4. X investor sentiment\n"
        f"5. Notable competitive dynamics\n\n"
        f"Respond in JSON:\n"
        f'{{\n'
        f'  "recent_news": ["news1", "news2"],\n'
        f'  "catalysts": {{\n'
        f'    "positive": ["catalyst1", "catalyst2"],\n'
        f'    "negative": ["catalyst1", "catalyst2"]\n'
        f'  }},\n'
        f'  "analyst_views": ["view1", "view2"],\n'
        f'  "x_sentiment": {{\n'
        f'    "score": 0.0,\n'
        f'    "summary": "summary text",\n'
        f'    "key_opinions": ["opinion1", "opinion2"]\n'
        f'  }},\n'
        f'  "competitive_notes": ["note1", "note2"]\n'
        f'}}'
    )


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------

def search_x_sentiment(
    symbol: str,
    company_name: str = "",
    timeout: int = 30,
    context: str = "",
) -> dict:
    """Search X for stock sentiment using Grok API.

    Parameters
    ----------
    symbol : str
        Stock ticker symbol (e.g. "AAPL", "7203.T").
    company_name : str
        Company name for better search context.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        Keys: positive (list[str]), negative (list[str]),
              sentiment_score (float, -1 to 1),
              raw_response (str).
        Returns empty result on error or when API is unavailable.
    """
    empty_result = {
        "positive": [],
        "negative": [],
        "sentiment_score": 0.0,
        "raw_response": "",
    }

    raw_text = _call_grok_api(_build_sentiment_prompt(symbol, company_name, context=context), timeout)
    if not raw_text:
        return empty_result

    result = dict(empty_result)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if isinstance(parsed.get("positive"), list):
        result["positive"] = parsed["positive"]
    if isinstance(parsed.get("negative"), list):
        result["negative"] = parsed["negative"]
    score = parsed.get("sentiment_score")
    if isinstance(score, (int, float)):
        result["sentiment_score"] = max(-1.0, min(1.0, float(score)))

    return result


def search_stock_deep(
    symbol: str,
    company_name: str = "",
    timeout: int = 30,
    context: str = "",
) -> dict:
    """Deep research on a stock via X and web search.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. "7203.T", "AAPL").
    company_name : str
        Company name for prompt accuracy.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        See EMPTY_STOCK_DEEP for the schema.
    """
    raw_text = _call_grok_api(_build_stock_deep_prompt(symbol, company_name, context=context), timeout)
    if not raw_text:
        return dict(EMPTY_STOCK_DEEP)

    result = dict(EMPTY_STOCK_DEEP)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("recent_news"), list):
        result["recent_news"] = parsed["recent_news"]

    catalysts = parsed.get("catalysts")
    if isinstance(catalysts, dict):
        result["catalysts"] = {
            "positive": catalysts.get("positive", []) if isinstance(catalysts.get("positive"), list) else [],
            "negative": catalysts.get("negative", []) if isinstance(catalysts.get("negative"), list) else [],
        }

    if isinstance(parsed.get("analyst_views"), list):
        result["analyst_views"] = parsed["analyst_views"]

    x_sent = parsed.get("x_sentiment")
    if isinstance(x_sent, dict):
        score = x_sent.get("score", 0.0)
        result["x_sentiment"] = {
            "score": max(-1.0, min(1.0, float(score))) if isinstance(score, (int, float)) else 0.0,
            "summary": x_sent.get("summary", "") if isinstance(x_sent.get("summary"), str) else "",
            "key_opinions": x_sent.get("key_opinions", []) if isinstance(x_sent.get("key_opinions"), list) else [],
        }

    if isinstance(parsed.get("competitive_notes"), list):
        result["competitive_notes"] = parsed["competitive_notes"]

    return result
