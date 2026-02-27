"""Industry-related Grok API functions: search_industry.

Extracted from grok_client.py during KIK-508 submodule split.
"""

from src.data.grok_client._common import (
    EMPTY_INDUSTRY,
    _call_grok_api,
    _contains_japanese,
    _parse_json_response,
)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_industry_prompt(industry_or_theme: str, context: str = "") -> str:
    """Build the prompt for industry research."""
    context_block = f"{context}\n\n" if context else ""
    if _contains_japanese(industry_or_theme):
        return (
            f"{context_block}"
            f"「{industry_or_theme}」業界・テーマについて、X（Twitter）とWebの最新情報をもとに以下を調査してください。\n\n"
            f"1. 業界の現状と最近のトレンド\n"
            f"2. 主要プレイヤーと注目企業\n"
            f"3. 成長ドライバーとリスク要因\n"
            f"4. 規制・政策の動向\n"
            f"5. 投資家の注目ポイント\n\n"
            f"JSON形式で回答:\n"
            f'{{\n'
            f'  "trends": ["トレンド1", "トレンド2"],\n'
            f'  "key_players": [\n'
            f'    {{"name": "企業名", "ticker": "シンボル", "note": "注目理由"}}\n'
            f'  ],\n'
            f'  "growth_drivers": ["ドライバー1", "ドライバー2"],\n'
            f'  "risks": ["リスク1", "リスク2"],\n'
            f'  "regulatory": ["規制動向1", "規制動向2"],\n'
            f'  "investor_focus": ["注目点1", "注目点2"]\n'
            f'}}'
        )
    return (
        f"{context_block}"
        f"Research the \"{industry_or_theme}\" industry/theme using X (Twitter) and web sources. Provide:\n\n"
        f"1. Current trends\n"
        f"2. Key players and notable companies\n"
        f"3. Growth drivers and risk factors\n"
        f"4. Regulatory/policy developments\n"
        f"5. Investor focus points\n\n"
        f"Respond in JSON:\n"
        f'{{\n'
        f'  "trends": ["trend1", "trend2"],\n'
        f'  "key_players": [\n'
        f'    {{"name": "company", "ticker": "SYMBOL", "note": "reason"}}\n'
        f'  ],\n'
        f'  "growth_drivers": ["driver1", "driver2"],\n'
        f'  "risks": ["risk1", "risk2"],\n'
        f'  "regulatory": ["development1", "development2"],\n'
        f'  "investor_focus": ["point1", "point2"]\n'
        f'}}'
    )


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------

def search_industry(
    industry_or_theme: str,
    timeout: int = 30,
    context: str = "",
) -> dict:
    """Research an industry or theme via X and web search.

    Parameters
    ----------
    industry_or_theme : str
        Industry name or theme (e.g. "半導体", "EV", "AI").
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        See EMPTY_INDUSTRY for the schema.
    """
    raw_text = _call_grok_api(_build_industry_prompt(industry_or_theme, context=context), timeout)
    if not raw_text:
        return dict(EMPTY_INDUSTRY)

    result = dict(EMPTY_INDUSTRY)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("trends"), list):
        result["trends"] = parsed["trends"]
    if isinstance(parsed.get("key_players"), list):
        result["key_players"] = parsed["key_players"]
    if isinstance(parsed.get("growth_drivers"), list):
        result["growth_drivers"] = parsed["growth_drivers"]
    if isinstance(parsed.get("risks"), list):
        result["risks"] = parsed["risks"]
    if isinstance(parsed.get("regulatory"), list):
        result["regulatory"] = parsed["regulatory"]
    if isinstance(parsed.get("investor_focus"), list):
        result["investor_focus"] = parsed["investor_focus"]

    return result
