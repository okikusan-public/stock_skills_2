"""MarketContext node operations (KIK-507).

Handles merge_market_context, merge_market_context_full,
and sub-nodes (Indicator, UpcomingEvent, SectorRotation, Sentiment).
Also handles ThemeTrend nodes (KIK-603).
"""

import json as _json

from src.data.graph_store import _common


# ---------------------------------------------------------------------------
# MarketContext node (KIK-399)
# ---------------------------------------------------------------------------

def merge_market_context(context_date: str, indices: list[dict],
                         semantic_summary: str = "",
                         embedding: list[float] | None = None,
                         ) -> bool:
    """Create/update a MarketContext node with index snapshots.

    indices is stored as a JSON string (Neo4j can't store list-of-maps).
    """
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    context_id = f"market_context_{context_date}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (m:MarketContext {id: $id}) "
                "SET m.date = $date, m.indices = $indices",
                id=context_id,
                date=context_date,
                indices=_json.dumps(indices, ensure_ascii=False),
            )
            _common._set_embedding(session, "MarketContext", context_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


def merge_market_context_full(
    context_date: str, indices: list[dict],
    grok_research: dict | None = None,
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create MarketContext with semantic sub-nodes (KIK-413).

    Expands indices into Indicator nodes, and grok_research into
    UpcomingEvent, SectorRotation, and Sentiment nodes.
    Only creates sub-nodes in 'full' mode.
    """
    if _common._get_mode() != "full":
        return merge_market_context(context_date, indices,
                                     semantic_summary=semantic_summary,
                                     embedding=embedding)
    # Ensure base MarketContext node exists
    merge_market_context(context_date, indices,
                         semantic_summary=semantic_summary, embedding=embedding)
    driver = _common._get_driver()
    if driver is None:
        return False
    context_id = f"market_context_{context_date}"
    try:
        with driver.session() as session:
            # --- Indicator nodes (from indices) ---
            for i, idx in enumerate(indices[:20]):
                iid = f"{context_id}_ind_{i}"
                session.run(
                    "MERGE (ind:Indicator {id: $id}) "
                    "SET ind.date = $date, ind.name = $name, "
                    "ind.symbol = $symbol, ind.price = $price, "
                    "ind.daily_change = $dchange, ind.weekly_change = $wchange "
                    "WITH ind "
                    "MATCH (m:MarketContext {id: $mid}) "
                    "MERGE (m)-[:INCLUDES]->(ind)",
                    id=iid, date=context_date,
                    name=str(idx.get("name", ""))[:100],
                    symbol=str(idx.get("symbol", ""))[:20],
                    price=float(idx.get("price", 0) or 0),
                    dchange=float(idx.get("daily_change", 0) or 0),
                    wchange=float(idx.get("weekly_change", 0) or 0),
                    mid=context_id,
                )

            if not grok_research:
                return True

            # --- UpcomingEvent nodes ---
            events = grok_research.get("upcoming_events", [])
            if isinstance(events, list):
                for j, ev in enumerate(events[:5]):
                    eid = f"{context_id}_event_{j}"
                    session.run(
                        "MERGE (e:UpcomingEvent {id: $id}) "
                        "SET e.date = $date, e.text = $text "
                        "WITH e "
                        "MATCH (m:MarketContext {id: $mid}) "
                        "MERGE (m)-[:HAS_EVENT]->(e)",
                        id=eid, date=context_date,
                        text=_common._truncate(str(ev), 500), mid=context_id,
                    )

            # --- SectorRotation nodes ---
            rotations = grok_research.get("sector_rotation", [])
            if isinstance(rotations, list):
                for k, rot in enumerate(rotations[:3]):
                    rid = f"{context_id}_rot_{k}"
                    session.run(
                        "MERGE (sr:SectorRotation {id: $id}) "
                        "SET sr.date = $date, sr.text = $text "
                        "WITH sr "
                        "MATCH (m:MarketContext {id: $mid}) "
                        "MERGE (m)-[:HAS_ROTATION]->(sr)",
                        id=rid, date=context_date,
                        text=_common._truncate(str(rot), 500), mid=context_id,
                    )

            # --- Sentiment node (market-level) ---
            sentiment = grok_research.get("sentiment")
            if isinstance(sentiment, dict):
                sid = f"{context_id}_sent"
                session.run(
                    "MERGE (s:Sentiment {id: $id}) "
                    "SET s.date = $date, s.source = 'market', "
                    "s.score = $score, s.summary = $summary "
                    "WITH s "
                    "MATCH (m:MarketContext {id: $mid}) "
                    "MERGE (m)-[:HAS_SENTIMENT]->(s)",
                    id=sid, date=context_date,
                    score=float(sentiment.get("score", 0)),
                    summary=_common._truncate(sentiment.get("summary", ""), 500),
                    mid=context_id,
                )

        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# ThemeTrend node (KIK-603)
# ---------------------------------------------------------------------------

def merge_theme_trend(
    theme: str,
    date: str,
    confidence: float = 0.0,
    reason: str = "",
    rank: int = 0,
    region: str = "",
) -> bool:
    """Save a theme trend detection to Neo4j.

    Creates a ThemeTrend node and links it to the corresponding Theme node
    via a FOR_THEME relationship.

    Parameters
    ----------
    theme : str
        Theme key (e.g. "ai", "ev", "cybersecurity").
    date : str
        Detection date (YYYY-MM-DD).
    confidence : float
        Grok confidence score (0.0-1.0).
    reason : str
        Why the theme is trending.
    rank : int
        Rank within the detection batch (1 = highest confidence).
    region : str
        Market region used for detection (e.g. "japan", "us").

    Returns
    -------
    bool
        True on success, False on any failure.
    """
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    trend_id = f"theme_trend_{date}_{theme}_{region}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (tt:ThemeTrend {id: $id}) "
                "SET tt.date = $date, tt.theme = $theme, "
                "    tt.confidence = $confidence, tt.reason = $reason, "
                "    tt.rank = $rank, tt.region = $region "
                "MERGE (t:Theme {name: $theme}) "
                "MERGE (tt)-[:FOR_THEME]->(t)",
                id=trend_id,
                date=date,
                theme=_common._truncate(theme, 100),
                confidence=float(confidence),
                reason=_common._truncate(reason, 500),
                rank=int(rank),
                region=_common._truncate(region, 50),
            )
        return True
    except Exception:
        return False
