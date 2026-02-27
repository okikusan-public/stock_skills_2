"""ActionItem graph queries (KIK-472).

Extracted from graph_query.py during KIK-508 submodule split.
"""

from src.data.graph_query import _common


# ---------------------------------------------------------------------------
# ActionItem history (KIK-472)
# ---------------------------------------------------------------------------

def get_action_item_history(symbol: str | None = None, limit: int = 10) -> list[dict]:
    """Get ActionItem nodes for graph-query skill.

    Returns list of {id, date, trigger_type, title, symbol, urgency, status,
    linear_identifier, linear_issue_url}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            if symbol:
                result = session.run(
                    "MATCH (a:ActionItem)-[:TARGETS]->(s:Stock {symbol: $symbol}) "
                    "RETURN a.id AS id, a.date AS date, "
                    "a.trigger_type AS trigger_type, a.title AS title, "
                    "a.symbol AS symbol, a.urgency AS urgency, "
                    "a.status AS status, "
                    "a.linear_identifier AS linear_identifier, "
                    "a.linear_issue_url AS linear_issue_url "
                    "ORDER BY a.date DESC LIMIT $limit",
                    symbol=symbol, limit=limit,
                )
            else:
                result = session.run(
                    "MATCH (a:ActionItem) "
                    "RETURN a.id AS id, a.date AS date, "
                    "a.trigger_type AS trigger_type, a.title AS title, "
                    "a.symbol AS symbol, a.urgency AS urgency, "
                    "a.status AS status, "
                    "a.linear_identifier AS linear_identifier, "
                    "a.linear_issue_url AS linear_issue_url "
                    "ORDER BY a.date DESC LIMIT $limit",
                    limit=limit,
                )
            return [dict(r) for r in result]
    except Exception:
        return []
