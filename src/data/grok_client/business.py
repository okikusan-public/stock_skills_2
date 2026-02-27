"""Business model analysis Grok API functions: search_business, synthesize_text.

Extracted from grok_client.py during KIK-508 submodule split.
"""

from src.data.grok_client._common import (
    EMPTY_BUSINESS,
    _call_grok_api,
    _get_api_key,
    _is_japanese_stock,
    _contains_japanese,
    _parse_json_response,
    reset_error_state,
)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_business_prompt(symbol: str, company_name: str = "", context: str = "") -> str:
    """Build the prompt for business model analysis."""
    name_part = f" ({company_name})" if company_name else ""
    context_block = f"{context}\n\n" if context else ""
    if _is_japanese_stock(symbol) or _contains_japanese(company_name):
        return (
            f"{context_block}"
            f"{symbol}{name_part} のビジネスモデルについて、WebとX（Twitter）の情報をもとに詳しく分析してください。\n\n"
            f"1. 事業概要（何で稼いでいるか）\n"
            f"2. 事業セグメント構成（セグメント名、売上比率、概要）\n"
            f"3. 収益モデル（ストック型/フロー型/サブスク/ライセンス等）\n"
            f"4. 競争優位性（参入障壁、ブランド、技術、ネットワーク効果等）\n"
            f"5. 重要KPI（投資家が注目すべき指標）\n"
            f"6. 成長戦略（中期経営計画、M&A、新規事業等）\n"
            f"7. ビジネスリスク（構造的リスク、依存度等）\n\n"
            f"JSON形式で回答:\n"
            f'{{\n'
            f'  "overview": "事業概要テキスト",\n'
            f'  "segments": [\n'
            f'    {{"name": "セグメント名", "revenue_share": "売上比率(例: 40%)", "description": "概要"}}\n'
            f'  ],\n'
            f'  "revenue_model": "収益モデルの説明",\n'
            f'  "competitive_advantages": ["優位性1", "優位性2"],\n'
            f'  "key_metrics": ["KPI1", "KPI2"],\n'
            f'  "growth_strategy": ["戦略1", "戦略2"],\n'
            f'  "risks": ["リスク1", "リスク2"]\n'
            f'}}'
        )
    return (
        f"{context_block}"
        f"Analyze the business model of {symbol}{name_part} using web and X (Twitter) sources. Provide:\n\n"
        f"1. Business overview (how the company makes money)\n"
        f"2. Business segments (name, revenue share, description)\n"
        f"3. Revenue model (recurring/transactional/subscription/licensing etc.)\n"
        f"4. Competitive advantages (moats, barriers to entry, brand, technology)\n"
        f"5. Key metrics (KPIs investors should watch)\n"
        f"6. Growth strategy (M&A, new markets, product roadmap)\n"
        f"7. Business risks (structural risks, dependencies)\n\n"
        f"Respond in JSON:\n"
        f'{{\n'
        f'  "overview": "business overview text",\n'
        f'  "segments": [\n'
        f'    {{"name": "Segment Name", "revenue_share": "e.g. 40%", "description": "overview"}}\n'
        f'  ],\n'
        f'  "revenue_model": "description of revenue model",\n'
        f'  "competitive_advantages": ["advantage1", "advantage2"],\n'
        f'  "key_metrics": ["KPI1", "KPI2"],\n'
        f'  "growth_strategy": ["strategy1", "strategy2"],\n'
        f'  "risks": ["risk1", "risk2"]\n'
        f'}}'
    )


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------

def synthesize_text(prompt: str, timeout: int = 20) -> str:
    """Pure text synthesis via Grok API (no search tools). KIK-452.

    Used for summarizing graph context data from the knowledge graph.
    Delegates to _call_grok_api with use_tools=False.
    Does NOT update _error_state -- this is an auxiliary call; resets
    any state change made by _call_grok_api before returning.

    Parameters
    ----------
    prompt : str
        Synthesis prompt (in Japanese or English).
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    str
        Generated text, or "" if unavailable/error.
    """
    if not _get_api_key():
        return ""
    try:
        result = _call_grok_api(prompt, timeout=timeout, use_tools=False)
        # Reset error state: this call is auxiliary and should not affect
        # the main error state used by other callers.
        reset_error_state()
        return result
    except Exception:
        return ""


def search_business(
    symbol: str,
    company_name: str = "",
    timeout: int = 60,
    context: str = "",
) -> dict:
    """Research a company's business model via X and web search.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. "7751.T", "AAPL").
    company_name : str
        Company name for prompt accuracy.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        See EMPTY_BUSINESS for the schema.
    """
    raw_text = _call_grok_api(_build_business_prompt(symbol, company_name, context=context), timeout)
    if not raw_text:
        return dict(EMPTY_BUSINESS)

    result = dict(EMPTY_BUSINESS)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("overview"), str):
        result["overview"] = parsed["overview"]

    segments = parsed.get("segments")
    if isinstance(segments, list):
        validated = []
        for seg in segments:
            if isinstance(seg, dict):
                validated.append({
                    "name": seg.get("name", "") if isinstance(seg.get("name"), str) else "",
                    "revenue_share": seg.get("revenue_share", "") if isinstance(seg.get("revenue_share"), str) else "",
                    "description": seg.get("description", "") if isinstance(seg.get("description"), str) else "",
                })
        result["segments"] = validated

    if isinstance(parsed.get("revenue_model"), str):
        result["revenue_model"] = parsed["revenue_model"]
    if isinstance(parsed.get("competitive_advantages"), list):
        result["competitive_advantages"] = parsed["competitive_advantages"]
    if isinstance(parsed.get("key_metrics"), list):
        result["key_metrics"] = parsed["key_metrics"]
    if isinstance(parsed.get("growth_strategy"), list):
        result["growth_strategy"] = parsed["growth_strategy"]
    if isinstance(parsed.get("risks"), list):
        result["risks"] = parsed["risks"]

    return result
