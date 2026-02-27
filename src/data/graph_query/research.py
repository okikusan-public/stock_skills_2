"""Research/News/Sentiment/Catalyst/AnalystView graph queries.

Extracted from graph_query.py during KIK-508 submodule split.
"""

from typing import Optional

from src.data.graph_query import _common


# ---------------------------------------------------------------------------
# 3. Research chain (SUPERSEDES)
# ---------------------------------------------------------------------------

def get_research_chain(
    research_type: str, target: str, limit: int = 5,
) -> list[dict]:
    """Get the SUPERSEDES chain for a research type+target, newest first.

    Returns list of {date, summary}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Research {research_type: $rtype, target: $target}) "
                "RETURN r.date AS date, r.summary AS summary "
                "ORDER BY r.date DESC LIMIT $limit",
                rtype=research_type, target=target, limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 7. Stock news history (KIK-413)
# ---------------------------------------------------------------------------

def get_stock_news_history(symbol: str, limit: int = 10) -> list[dict]:
    """Get News nodes linked to a stock via News->MENTIONS->Stock.

    Returns list of {date, title, source}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (n:News)-[:MENTIONS]->(s:Stock {symbol: $symbol}) "
                "RETURN n.date AS date, n.title AS title, n.source AS source "
                "ORDER BY n.date DESC LIMIT $limit",
                symbol=symbol, limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 8. Sentiment trend (KIK-413)
# ---------------------------------------------------------------------------

def get_sentiment_trend(symbol: str, limit: int = 5) -> list[dict]:
    """Get Sentiment nodes linked via Research->HAS_SENTIMENT for a stock.

    Returns list of {date, source, score, summary}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Research)-[:RESEARCHED]->(s:Stock {symbol: $symbol}) "
                "MATCH (r)-[:HAS_SENTIMENT]->(sent:Sentiment) "
                "RETURN sent.date AS date, sent.source AS source, "
                "sent.score AS score, sent.summary AS summary "
                "ORDER BY sent.date DESC LIMIT $limit",
                symbol=symbol, limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 9. Catalysts (KIK-413)
# ---------------------------------------------------------------------------

def get_catalysts(symbol: str) -> dict:
    """Get Catalyst nodes linked via Research->HAS_CATALYST for a stock.

    Returns {positive: [text], negative: [text]}.
    """
    empty = {"positive": [], "negative": []}
    driver = _common._get_driver()
    if driver is None:
        return empty
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Research)-[:RESEARCHED]->(s:Stock {symbol: $symbol}) "
                "MATCH (r)-[:HAS_CATALYST]->(c:Catalyst) "
                "RETURN c.type AS type, c.text AS text "
                "ORDER BY r.date DESC",
                symbol=symbol,
            )
            out = {"positive": [], "negative": []}
            for rec in result:
                polarity = rec["type"]
                if polarity in out:
                    out[polarity].append(rec["text"])
            return out
    except Exception:
        return empty


# ---------------------------------------------------------------------------
# 10. Sector Catalysts (KIK-433)
# ---------------------------------------------------------------------------

def get_sector_catalysts(sector: str, days: int = 30) -> dict:
    """Get Catalyst nodes from recent industry Research matching the sector.

    Matches Research.target vs sector using case-insensitive CONTAINS.
    Falls back to all recent industry catalysts if no sector match found.

    Returns
    -------
    dict
        {positive: [str], negative: [str], count_positive: int,
         count_negative: int, matched_sector: bool}
    """
    from datetime import date, timedelta
    empty = {"positive": [], "negative": [], "count_positive": 0, "count_negative": 0, "matched_sector": False}
    driver = _common._get_driver()
    if driver is None:
        return empty
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        with driver.session() as session:
            # Try sector-matched query first
            result = session.run(
                "MATCH (r:Research {research_type: 'industry'})-[:HAS_CATALYST]->(c:Catalyst) "
                "WHERE r.date >= $since "
                "  AND (toLower(r.target) CONTAINS toLower($sector) "
                "       OR toLower($sector) CONTAINS toLower(r.target)) "
                "RETURN c.type AS type, c.text AS text "
                "ORDER BY r.date DESC LIMIT 50",
                since=since, sector=sector,
            )
            records = list(result)
            matched = len(records) > 0
            if not matched:
                # Fallback: all recent industry catalysts
                result = session.run(
                    "MATCH (r:Research {research_type: 'industry'})-[:HAS_CATALYST]->(c:Catalyst) "
                    "WHERE r.date >= $since "
                    "RETURN c.type AS type, c.text AS text "
                    "ORDER BY r.date DESC LIMIT 30",
                    since=since,
                )
                records = list(result)
            positive = []
            negative = []
            for rec in records:
                ctype = rec["type"]
                text = rec["text"]
                if ctype == "growth_driver":
                    positive.append(text)
                elif ctype == "risk":
                    negative.append(text)
            return {
                "positive": positive,
                "negative": negative,
                "count_positive": len(positive),
                "count_negative": len(negative),
                "matched_sector": matched,
            }
    except Exception:
        return empty


def get_industry_research_for_sector(sector: str, days: int = 30) -> list:
    """Get recent industry Research summaries matching the sector.

    Matches Research.target vs sector using case-insensitive CONTAINS.

    Returns
    -------
    list[dict]
        [{date, target, summary, catalysts: [{type, text}]}]
    """
    from datetime import date, timedelta
    driver = _common._get_driver()
    if driver is None:
        return []
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Research {research_type: 'industry'}) "
                "WHERE r.date >= $since "
                "  AND (toLower(r.target) CONTAINS toLower($sector) "
                "       OR toLower($sector) CONTAINS toLower(r.target)) "
                "OPTIONAL MATCH (r)-[:HAS_CATALYST]->(c:Catalyst) "
                "RETURN r.date AS date, r.target AS target, r.summary AS summary, "
                "       collect({type: c.type, text: c.text}) AS catalysts "
                "ORDER BY r.date DESC LIMIT 5",
                since=since, sector=sector,
            )
            out = []
            for rec in result:
                cats = [c for c in rec["catalysts"] if c.get("type") is not None]
                out.append({
                    "date": rec["date"],
                    "target": rec["target"],
                    "summary": rec["summary"] or "",
                    "catalysts": cats,
                })
            return out
    except Exception:
        return []


# ---------------------------------------------------------------------------
# KIK-434: Candidate node queries for AI graph linking
# ---------------------------------------------------------------------------

def get_nodes_for_symbol(
    symbol: str,
    include_notes: bool = False,
    limit: int = 6,
) -> list[dict]:
    """Return recent Report and HealthCheck nodes for a symbol (AI linking).

    When include_notes=True, also includes Note nodes.
    Returns list of dicts: {id, type, summary}
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    results = []
    try:
        with driver.session() as session:
            # Most recent Report
            rec = session.run(
                "MATCH (r:Report)-[:ANALYZED]->(s:Stock {symbol: $symbol}) "
                "RETURN r.id AS id, 'Report' AS type, "
                "('score=' + toString(coalesce(r.score, 0)) + ' ' + coalesce(r.verdict, '')) AS summary "
                "ORDER BY r.date DESC LIMIT 1",
                symbol=symbol,
            )
            results.extend([dict(r) for r in rec])

            # Recent HealthChecks (up to 2)
            rec2 = session.run(
                "MATCH (h:HealthCheck)-[:CHECKED]->(s:Stock {symbol: $symbol}) "
                "RETURN h.id AS id, 'HealthCheck' AS type, "
                "coalesce(h.summary, '') AS summary "
                "ORDER BY h.date DESC LIMIT 2",
                symbol=symbol,
            )
            results.extend([dict(r) for r in rec2])

            if include_notes:
                rec3 = session.run(
                    "MATCH (n:Note)-[:ABOUT]->(s:Stock {symbol: $symbol}) "
                    "RETURN n.id AS id, 'Note' AS type, "
                    "coalesce(n.content, '') AS summary "
                    "ORDER BY n.date DESC LIMIT 3",
                    symbol=symbol,
                )
                results.extend([dict(r) for r in rec3])
    except Exception:
        pass
    return results[:limit]


def get_industry_research_for_linking(
    sector: str,
    days: int = 30,
    limit: int = 3,
) -> list[dict]:
    """Return recent industry Research nodes matching a sector (AI linking).

    Returns list of dicts: {id, type, target, summary}
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    from datetime import date, timedelta
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Research {research_type: 'industry'}) "
                "WHERE r.date >= $since "
                "  AND (toLower(r.target) CONTAINS toLower($sector) "
                "       OR toLower($sector) CONTAINS toLower(r.target)) "
                "RETURN r.id AS id, 'Research' AS type, "
                "r.target AS target, coalesce(r.summary, '') AS summary "
                "ORDER BY r.date DESC LIMIT $limit",
                since=since, sector=sector, limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []
