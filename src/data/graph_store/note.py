"""Note and ActionItem node operations (KIK-507).

Handles merge_note, merge_action_item, update_action_item_linear,
get_open_action_items.
"""

from typing import Optional

from src.data.graph_store import _common


# ---------------------------------------------------------------------------
# Note node
# ---------------------------------------------------------------------------

def merge_note(
    note_id: str, note_date: str, note_type: str, content: str,
    symbol: Optional[str] = None, source: str = "",
    category: str = "",
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a Note node and ABOUT relationship (KIK-491).

    Links to Stock (if symbol), Portfolio (if category=portfolio),
    or MarketContext (if category=market).
    """
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            session.run(
                "MERGE (n:Note {id: $id}) "
                "SET n.date = $date, n.type = $type, "
                "n.content = $content, n.source = $source, "
                "n.category = $category",
                id=note_id, date=note_date, type=note_type,
                content=content, source=source, category=category,
            )
            if symbol:
                session.run(
                    "MATCH (n:Note {id: $note_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (n)-[:ABOUT]->(s)",
                    note_id=note_id, symbol=symbol,
                )
            elif category == "portfolio":
                session.run(
                    "MATCH (n:Note {id: $note_id}) "
                    "MERGE (p:Portfolio {name: 'default'}) "
                    "MERGE (n)-[:ABOUT]->(p)",
                    note_id=note_id,
                )
            elif category == "market":
                session.run(
                    "MATCH (n:Note {id: $note_id}) "
                    "WITH n "
                    "OPTIONAL MATCH (mc:MarketContext) "
                    "WITH n, mc ORDER BY mc.date DESC LIMIT 1 "
                    "WHERE mc IS NOT NULL "
                    "MERGE (n)-[:ABOUT]->(mc)",
                    note_id=note_id,
                )
            _common._set_embedding(session, "Note", note_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# ActionItem node (KIK-472)
# ---------------------------------------------------------------------------

def merge_action_item(
    action_id: str,
    action_date: str,
    trigger_type: str,
    title: str,
    symbol: str | None = None,
    urgency: str = "medium",
    linear_issue_id: str | None = None,
    linear_issue_url: str | None = None,
    linear_identifier: str | None = None,
    source_node_id: str | None = None,
) -> bool:
    """Create/update ActionItem node + TARGETS->Stock + optional source relationship."""
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            session.run(
                "MERGE (a:ActionItem {id: $id}) "
                "SET a.date = $date, a.trigger_type = $trigger_type, "
                "a.title = $title, a.symbol = $symbol, "
                "a.urgency = $urgency, a.status = coalesce(a.status, 'open'), "
                "a.linear_issue_id = $linear_id, "
                "a.linear_issue_url = $linear_url, "
                "a.linear_identifier = $linear_ident",
                id=action_id, date=action_date,
                trigger_type=trigger_type, title=title,
                symbol=symbol or "", urgency=urgency,
                linear_id=linear_issue_id or "",
                linear_url=linear_issue_url or "",
                linear_ident=linear_identifier or "",
            )
            if symbol:
                session.run(
                    "MATCH (a:ActionItem {id: $action_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (a)-[:TARGETS]->(s)",
                    action_id=action_id, symbol=symbol,
                )
            if source_node_id:
                session.run(
                    "MATCH (a:ActionItem {id: $action_id}) "
                    "MATCH (src {id: $source_id}) "
                    "MERGE (src)-[:TRIGGERED]->(a)",
                    action_id=action_id, source_id=source_node_id,
                )
        return True
    except Exception:
        return False


def update_action_item_linear(
    action_id: str,
    linear_issue_id: str,
    linear_issue_url: str,
    linear_identifier: str,
) -> bool:
    """Link ActionItem to Linear issue after creation."""
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            session.run(
                "MATCH (a:ActionItem {id: $id}) "
                "SET a.linear_issue_id = $lid, "
                "a.linear_issue_url = $lurl, "
                "a.linear_identifier = $lident",
                id=action_id,
                lid=linear_issue_id,
                lurl=linear_issue_url,
                lident=linear_identifier,
            )
        return True
    except Exception:
        return False


def get_open_action_items(symbol: str | None = None) -> list[dict]:
    """Query open ActionItem nodes for dedup check."""
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            if symbol:
                result = session.run(
                    "MATCH (a:ActionItem {status: 'open'}) "
                    "WHERE a.symbol = $symbol "
                    "RETURN a.id AS id, a.date AS date, "
                    "a.trigger_type AS trigger_type, a.title AS title, "
                    "a.symbol AS symbol, a.urgency AS urgency "
                    "ORDER BY a.date DESC",
                    symbol=symbol,
                )
            else:
                result = session.run(
                    "MATCH (a:ActionItem {status: 'open'}) "
                    "RETURN a.id AS id, a.date AS date, "
                    "a.trigger_type AS trigger_type, a.title AS title, "
                    "a.symbol AS symbol, a.urgency AS urgency "
                    "ORDER BY a.date DESC",
                )
            return [dict(r) for r in result]
    except Exception:
        return []
