"""MarketContext/Indicator/UpcomingEvent graph queries.

Extracted from graph_query.py during KIK-508 submodule split.
"""

import json
from typing import Optional

from src.data.graph_query import _common


# ---------------------------------------------------------------------------
# 4. Recent market context
# ---------------------------------------------------------------------------

def get_recent_market_context() -> Optional[dict]:
    """Get the most recent MarketContext node.

    Returns dict with keys: date, indices (parsed from JSON).
    None if not found.
    """
    driver = _common._get_driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (m:MarketContext) "
                "RETURN m.date AS date, m.indices AS indices "
                "ORDER BY m.date DESC LIMIT 1",
            )
            record = result.single()
            if record is None:
                return None
            indices_raw = record["indices"]
            try:
                indices = json.loads(indices_raw) if indices_raw else []
            except (json.JSONDecodeError, TypeError):
                indices = []
            return {"date": record["date"], "indices": indices}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 11. Upcoming events (KIK-413)
# ---------------------------------------------------------------------------

def get_upcoming_events(limit: int = 10, within_days: int = None) -> list[dict]:
    """Get UpcomingEvent nodes from the most recent MarketContext.

    Parameters
    ----------
    limit : int
        Maximum number of events to return.
    within_days : int, optional
        If provided, filter events to those occurring within N days from today.

    Returns list of {date, text}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            if within_days is not None:
                from datetime import date, timedelta
                today = date.today().isoformat()
                until = (date.today() + timedelta(days=within_days)).isoformat()
                result = session.run(
                    "MATCH (m:MarketContext)-[:HAS_EVENT]->(e:UpcomingEvent) "
                    "WHERE e.date >= $today AND e.date <= $until "
                    "RETURN e.date AS date, e.text AS text "
                    "ORDER BY e.date LIMIT $limit",
                    today=today, until=until, limit=limit,
                )
            else:
                result = session.run(
                    "MATCH (m:MarketContext)-[:HAS_EVENT]->(e:UpcomingEvent) "
                    "RETURN e.date AS date, e.text AS text "
                    "ORDER BY m.date DESC, e.id LIMIT $limit",
                    limit=limit,
                )
            return [dict(r) for r in result]
    except Exception:
        return []
