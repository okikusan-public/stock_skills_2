"""Proactive intelligence helpers for graph queries (KIK-435).

Extracted from graph_query.py during KIK-508 submodule split.
"""

from typing import Optional

from src.data.graph_query import _common


# ---------------------------------------------------------------------------
# KIK-435: Proactive intelligence helpers
# ---------------------------------------------------------------------------

def get_last_health_check_date() -> Optional[str]:
    """Return ISO date string of the most recent HealthCheck, or None (KIK-435)."""
    driver = _common._get_driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (h:HealthCheck) RETURN h.date AS date ORDER BY h.date DESC LIMIT 1"
            )
            for r in result:
                return r["date"]
        return None
    except Exception:
        return None


def get_old_thesis_notes(older_than_days: int = 90) -> list[dict]:
    """Return thesis notes older than N days (KIK-435).

    Tries Neo4j first; falls back to JSON files via note_manager.
    Returns list of dicts: {symbol, days_old}
    """
    from datetime import date, timedelta
    driver = _common._get_driver()
    if driver is not None:
        try:
            since = (date.today() - timedelta(days=older_than_days)).isoformat()
            with driver.session() as session:
                result = session.run(
                    "MATCH (n:Note {type: 'thesis'}) WHERE n.date <= $since "
                    "RETURN n.symbol AS symbol, n.date AS note_date "
                    "ORDER BY n.date ASC LIMIT 3",
                    since=since,
                )
                out = []
                for r in result:
                    note_date = r["note_date"] or ""
                    days_old = (
                        (date.today() - date.fromisoformat(note_date)).days
                        if note_date else older_than_days
                    )
                    out.append({"symbol": r["symbol"], "days_old": days_old})
                if out:
                    return out
        except Exception:
            pass
    # JSON fallback
    try:
        from src.data.note_manager import load_notes
        notes = load_notes(note_type="thesis")
        cutoff = (date.today() - timedelta(days=older_than_days)).isoformat()
        out = []
        for n in notes:
            if n.get("date", "") <= cutoff:
                note_date = n.get("date", "")
                days_old = (
                    (date.today() - date.fromisoformat(note_date)).days
                    if note_date else older_than_days
                )
                out.append({"symbol": n.get("symbol", ""), "days_old": days_old})
        return out[:3]
    except Exception:
        return []


def get_concern_notes(limit: int = 1) -> list[dict]:
    """Return recent concern-type notes (KIK-435).

    Returns list of dicts: {symbol, days_old}
    """
    from datetime import date
    try:
        from src.data.note_manager import load_notes
        notes = load_notes(note_type="concern")
        out = []
        for n in notes[:limit]:
            note_date = n.get("date", "")
            days_old = (
                (date.today() - date.fromisoformat(note_date)).days
                if note_date else 0
            )
            out.append({"symbol": n.get("symbol", ""), "days_old": days_old})
        return out
    except Exception:
        return []
