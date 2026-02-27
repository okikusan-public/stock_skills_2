"""Stock/Screen/Report related graph queries.

Extracted from graph_query.py during KIK-508 submodule split.
"""

import json
from typing import Optional

from src.data.graph_query import _common


# ---------------------------------------------------------------------------
# 1. Prior report lookup
# ---------------------------------------------------------------------------

def get_prior_report(symbol: str) -> Optional[dict]:
    """Get the most recent Report for a symbol.

    Returns dict with keys: date, score, verdict. None if not found.
    """
    driver = _common._get_driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Report)-[:ANALYZED]->(s:Stock {symbol: $symbol}) "
                "RETURN r.date AS date, r.score AS score, r.verdict AS verdict "
                "ORDER BY r.date DESC LIMIT 1",
                symbol=symbol,
            )
            record = result.single()
            if record is None:
                return None
            return dict(record)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 2. Screening frequency
# ---------------------------------------------------------------------------

def get_screening_frequency(symbols: list[str]) -> dict[str, int]:
    """Count how many times each symbol appeared in past Screen results.

    Returns {symbol: count} for symbols with count >= 1.
    """
    driver = _common._get_driver()
    if driver is None:
        return {}
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (sc:Screen)-[:SURFACED]->(s:Stock) "
                "WHERE s.symbol IN $symbols "
                "RETURN s.symbol AS symbol, count(sc) AS cnt",
                symbols=symbols,
            )
            return {r["symbol"]: r["cnt"] for r in result if r["cnt"] >= 1}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# 5. Trade context (trades + notes for a symbol)
# ---------------------------------------------------------------------------

def get_trade_context(symbol: str) -> dict:
    """Get trade history and notes for a symbol.

    Returns {trades: [{date, type, shares, price}], notes: [{date, type, content}]}.
    """
    empty = {"trades": [], "notes": []}
    driver = _common._get_driver()
    if driver is None:
        return empty
    try:
        with driver.session() as session:
            trades = session.run(
                "MATCH (t:Trade)-[:BOUGHT|SOLD]->(s:Stock {symbol: $symbol}) "
                "RETURN t.date AS date, t.type AS type, "
                "t.shares AS shares, t.price AS price "
                "ORDER BY t.date DESC",
                symbol=symbol,
            )
            notes = session.run(
                "MATCH (n:Note)-[:ABOUT]->(s:Stock {symbol: $symbol}) "
                "RETURN n.date AS date, n.type AS type, n.content AS content "
                "ORDER BY n.date DESC",
                symbol=symbol,
            )
            return {
                "trades": [dict(r) for r in trades],
                "notes": [dict(r) for r in notes],
            }
    except Exception:
        return empty


# ---------------------------------------------------------------------------
# 6. Recurring picks (frequently screened but not bought)
# ---------------------------------------------------------------------------

def get_recurring_picks(min_count: int = 2) -> list[dict]:
    """Find stocks that appear in multiple screens but have no BOUGHT trade.

    Returns list of {symbol, count, last_date}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (sc:Screen)-[:SURFACED]->(s:Stock) "
                "WHERE NOT exists { MATCH (:Trade)-[:BOUGHT]->(s) } "
                "WITH s.symbol AS symbol, count(sc) AS cnt, "
                "max(sc.date) AS last_date "
                "WHERE cnt >= $min_count "
                "RETURN symbol, cnt AS count, last_date "
                "ORDER BY cnt DESC, last_date DESC",
                min_count=min_count,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 11. Report trend (KIK-413)
# ---------------------------------------------------------------------------

def get_report_trend(symbol: str, limit: int = 10) -> list[dict]:
    """Get Report nodes with extended properties for a stock, newest first.

    Returns list of {date, score, verdict, price, per, pbr}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Report)-[:ANALYZED]->(s:Stock {symbol: $symbol}) "
                "RETURN r.date AS date, r.score AS score, r.verdict AS verdict, "
                "r.price AS price, r.per AS per, r.pbr AS pbr "
                "ORDER BY r.date DESC LIMIT $limit",
                symbol=symbol, limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Batch helpers for screen annotator (KIK-418/419)
# ---------------------------------------------------------------------------

def get_recent_sells_batch(cutoff_date: str) -> dict[str, str]:
    """Get symbols sold on or after cutoff_date (KIK-418).

    Parameters
    ----------
    cutoff_date : str
        ISO date string (e.g. "2025-01-01"). Only sells on or after this date are returned.

    Returns
    -------
    dict[str, str]
        {symbol: sell_date} for recently sold stocks. Empty dict if Neo4j unavailable.
    """
    driver = _common._get_driver()
    if driver is None:
        return {}
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (t:Trade)-[:SOLD]->(s:Stock) "
                "WHERE t.date >= $cutoff "
                "RETURN s.symbol AS symbol, max(t.date) AS sell_date",
                cutoff=cutoff_date,
            )
            return {r["symbol"]: r["sell_date"] for r in result}
    except Exception:
        return {}


def get_notes_for_symbols_batch(
    symbols: list[str],
    note_types: list[str] | None = None,
) -> dict[str, list[dict]]:
    """Get notes for multiple symbols in one query (KIK-419).

    Parameters
    ----------
    symbols : list[str]
        Ticker symbols to look up.
    note_types : list[str] | None
        Filter to specific note types (e.g. ["concern", "lesson"]).
        None means all types.

    Returns
    -------
    dict[str, list[dict]]
        {symbol: [{type, content, date}]}. Empty dict if Neo4j unavailable.
    """
    driver = _common._get_driver()
    if driver is None:
        return {}
    try:
        with driver.session() as session:
            if note_types:
                result = session.run(
                    "MATCH (n:Note)-[:ABOUT]->(s:Stock) "
                    "WHERE s.symbol IN $symbols AND n.type IN $types "
                    "RETURN s.symbol AS symbol, n.type AS type, "
                    "n.content AS content, n.date AS date "
                    "ORDER BY n.date DESC",
                    symbols=symbols, types=note_types,
                )
            else:
                result = session.run(
                    "MATCH (n:Note)-[:ABOUT]->(s:Stock) "
                    "WHERE s.symbol IN $symbols "
                    "RETURN s.symbol AS symbol, n.type AS type, "
                    "n.content AS content, n.date AS date "
                    "ORDER BY n.date DESC",
                    symbols=symbols,
                )
            out: dict[str, list[dict]] = {}
            for r in result:
                sym = r["symbol"]
                if sym not in out:
                    out[sym] = []
                out[sym].append({"type": r["type"], "content": r["content"], "date": r["date"]})
            return out
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Theme query (KIK-452)
# ---------------------------------------------------------------------------

def get_themes_for_symbols_batch(symbols: list[str]) -> dict[str, list[str]]:
    """Multi-hop query: Stock -[:HAS_THEME]-> Theme for multiple symbols.

    Returns {symbol: [theme_name, ...]} for symbols that have associated themes.
    Returns {} when Neo4j is unavailable or on error.
    """
    if not symbols:
        return {}
    driver = _common._get_driver()
    if driver is None:
        return {}
    try:
        with driver.session() as session:
            result = session.run(
                "UNWIND $symbols AS sym "
                "MATCH (s:Stock {symbol: sym})-[:HAS_THEME]->(t:Theme) "
                "RETURN sym AS symbol, collect(t.name) AS themes",
                symbols=symbols,
            )
            return {record["symbol"]: record["themes"] for record in result}
    except Exception:
        return {}
