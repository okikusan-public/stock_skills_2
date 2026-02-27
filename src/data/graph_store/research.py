"""Research node operations (KIK-507).

Handles merge_research, merge_research_full, link_research_supersedes,
and all sub-node creation (News, Sentiment, Catalyst, AnalystView).
"""

from src.data.graph_store import _common


# ---------------------------------------------------------------------------
# Research node (KIK-398)
# ---------------------------------------------------------------------------

def merge_research(
    research_date: str, research_type: str, target: str,
    summary: str = "",
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a Research node with context-appropriate relationship (KIK-491).

    For stock/business types, links to Stock via RESEARCHED.
    For industry type, links to Sector via ANALYZES.
    For market type, links to latest MarketContext via COMPLEMENTS.
    """
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    research_id = f"research_{research_date}_{research_type}_{_common._safe_id(target)}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (r:Research {id: $id}) "
                "SET r.date = $date, r.research_type = $rtype, "
                "r.target = $target, r.summary = $summary",
                id=research_id, date=research_date, rtype=research_type,
                target=target, summary=summary,
            )
            if research_type in ("stock", "business"):
                session.run(
                    "MATCH (r:Research {id: $research_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (r)-[:RESEARCHED]->(s)",
                    research_id=research_id, symbol=target,
                )
            elif research_type == "industry":
                session.run(
                    "MATCH (r:Research {id: $research_id}) "
                    "MERGE (sec:Sector {name: $sector}) "
                    "MERGE (r)-[:ANALYZES]->(sec)",
                    research_id=research_id, sector=target,
                )
            elif research_type == "market":
                session.run(
                    "MATCH (r:Research {id: $research_id}) "
                    "WITH r "
                    "OPTIONAL MATCH (mc:MarketContext) "
                    "WITH r, mc ORDER BY mc.date DESC LIMIT 1 "
                    "WHERE mc IS NOT NULL "
                    "MERGE (r)-[:COMPLEMENTS]->(mc)",
                    research_id=research_id,
                )
            _common._set_embedding(session, "Research", research_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Research SUPERSEDES chain (KIK-398)
# ---------------------------------------------------------------------------

def link_research_supersedes(research_type: str, target: str) -> bool:
    """Link Research nodes of same type+target in date order with SUPERSEDES."""
    if _common._get_mode() == "off":
        return False
    driver = _common._get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            session.run(
                "MATCH (r:Research {research_type: $rtype, target: $target}) "
                "WITH r ORDER BY r.date ASC "
                "WITH collect(r) AS nodes "
                "UNWIND range(0, size(nodes)-2) AS i "
                "WITH nodes[i] AS a, nodes[i+1] AS b "
                "MERGE (a)-[:SUPERSEDES]->(b)",
                rtype=research_type, target=target,
            )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Research full (KIK-413)
# ---------------------------------------------------------------------------

def merge_research_full(
    research_date: str, research_type: str, target: str,
    summary: str = "",
    grok_research: dict | None = None,
    x_sentiment: dict | None = None,
    news: list | None = None,
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create Research node with semantic sub-nodes (KIK-413).

    Expands grok_research data into News, Sentiment, Catalyst, AnalystView
    nodes connected to the Research node via relationships.
    Only creates sub-nodes in 'full' mode.
    """
    if _common._get_mode() != "full":
        return merge_research(research_date, research_type, target, summary,
                              semantic_summary=semantic_summary, embedding=embedding)
    # Ensure base Research + Stock nodes exist
    merge_research(research_date, research_type, target, summary,
                   semantic_summary=semantic_summary, embedding=embedding)
    driver = _common._get_driver()
    if driver is None:
        return False
    research_id = f"research_{research_date}_{research_type}_{_common._safe_id(target)}"
    try:
        with driver.session() as session:
            # --- News nodes (from grok recent_news + yahoo news) ---
            news_items: list[dict | str] = []
            if grok_research and isinstance(grok_research.get("recent_news"), list):
                for item in grok_research["recent_news"][:5]:
                    if isinstance(item, str):
                        news_items.append({"title": item, "source": "grok"})
                    elif isinstance(item, dict):
                        news_items.append({**item, "source": "grok"})
            if isinstance(news, list):
                for item in news[:5]:
                    if isinstance(item, dict):
                        news_items.append({
                            "title": item.get("title", ""),
                            "source": item.get("publisher", "yahoo"),
                            "link": item.get("link", ""),
                        })
            for i, nitem in enumerate(news_items[:10]):
                nid = f"{research_id}_news_{i}"
                title = _common._truncate(nitem.get("title", ""), 500)
                source = nitem.get("source", "")[:50]
                link = nitem.get("link", "")[:500]
                session.run(
                    "MERGE (n:News {id: $id}) "
                    "SET n.date = $date, n.title = $title, "
                    "n.source = $source, n.link = $link "
                    "WITH n "
                    "MATCH (r:Research {id: $rid}) "
                    "MERGE (r)-[:HAS_NEWS]->(n)",
                    id=nid, date=research_date, title=title,
                    source=source, link=link, rid=research_id,
                )
                # MENTIONS->Stock for stock/business research
                if research_type in ("stock", "business"):
                    session.run(
                        "MATCH (n:News {id: $nid}) "
                        "MERGE (s:Stock {symbol: $symbol}) "
                        "MERGE (n)-[:MENTIONS]->(s)",
                        nid=nid, symbol=target,
                    )

            # --- Sentiment nodes ---
            # From grok x_sentiment
            if grok_research and isinstance(grok_research.get("x_sentiment"), dict):
                xs = grok_research["x_sentiment"]
                sid = f"{research_id}_sent_grok"
                session.run(
                    "MERGE (s:Sentiment {id: $id}) "
                    "SET s.date = $date, s.source = 'grok_x', "
                    "s.score = $score, s.summary = $summary "
                    "WITH s "
                    "MATCH (r:Research {id: $rid}) "
                    "MERGE (r)-[:HAS_SENTIMENT]->(s)",
                    id=sid, date=research_date,
                    score=float(xs.get("score", 0)),
                    summary=_common._truncate(xs.get("summary", ""), 500),
                    rid=research_id,
                )
            # From top-level x_sentiment (yahoo/yfinance)
            if isinstance(x_sentiment, dict) and x_sentiment:
                sid2 = f"{research_id}_sent_yahoo"
                pos = x_sentiment.get("positive", [])
                neg = x_sentiment.get("negative", [])
                pos_text = _common._truncate("; ".join(pos[:3]) if isinstance(pos, list) else str(pos), 500)
                neg_text = _common._truncate("; ".join(neg[:3]) if isinstance(neg, list) else str(neg), 500)
                session.run(
                    "MERGE (s:Sentiment {id: $id}) "
                    "SET s.date = $date, s.source = 'yahoo_x', "
                    "s.positive = $pos, s.negative = $neg "
                    "WITH s "
                    "MATCH (r:Research {id: $rid}) "
                    "MERGE (r)-[:HAS_SENTIMENT]->(s)",
                    id=sid2, date=research_date,
                    pos=pos_text, neg=neg_text, rid=research_id,
                )

            # --- Catalyst nodes ---
            if grok_research and isinstance(grok_research.get("catalysts"), dict):
                cats = grok_research["catalysts"]
                for polarity in ("positive", "negative"):
                    items = cats.get(polarity, [])
                    if isinstance(items, list):
                        for j, txt in enumerate(items[:5]):
                            cid = f"{research_id}_cat_{polarity[0]}_{j}"
                            session.run(
                                "MERGE (c:Catalyst {id: $id}) "
                                "SET c.date = $date, c.type = $polarity, "
                                "c.text = $text "
                                "WITH c "
                                "MATCH (r:Research {id: $rid}) "
                                "MERGE (r)-[:HAS_CATALYST]->(c)",
                                id=cid, date=research_date, polarity=polarity,
                                text=_common._truncate(str(txt), 500), rid=research_id,
                            )

            # --- AnalystView nodes ---
            if grok_research and isinstance(grok_research.get("analyst_views"), list):
                for k, view_text in enumerate(grok_research["analyst_views"][:5]):
                    avid = f"{research_id}_av_{k}"
                    session.run(
                        "MERGE (a:AnalystView {id: $id}) "
                        "SET a.date = $date, a.text = $text "
                        "WITH a "
                        "MATCH (r:Research {id: $rid}) "
                        "MERGE (r)-[:HAS_ANALYST_VIEW]->(a)",
                        id=avid, date=research_date,
                        text=_common._truncate(str(view_text), 500),
                        rid=research_id,
                    )

            # --- Market research sub-nodes (KIK-430) ---
            if research_type == "market" and grok_research:
                # Sentiment (market-level)
                mkt_sent = grok_research.get("sentiment")
                if isinstance(mkt_sent, dict):
                    sid = f"{research_id}_sent_market"
                    session.run(
                        "MERGE (s:Sentiment {id: $id}) "
                        "SET s.date = $date, s.source = 'market_research', "
                        "s.score = $score, s.summary = $summary "
                        "WITH s "
                        "MATCH (r:Research {id: $rid}) "
                        "MERGE (r)-[:HAS_SENTIMENT]->(s)",
                        id=sid, date=research_date,
                        score=float(mkt_sent.get("score", 0)),
                        summary=_common._truncate(mkt_sent.get("summary", ""), 500),
                        rid=research_id,
                    )
                # UpcomingEvent
                events = grok_research.get("upcoming_events", [])
                if isinstance(events, list):
                    for j, ev in enumerate(events[:5]):
                        eid = f"{research_id}_event_{j}"
                        session.run(
                            "MERGE (e:UpcomingEvent {id: $id}) "
                            "SET e.date = $date, e.text = $text "
                            "WITH e "
                            "MATCH (r:Research {id: $rid}) "
                            "MERGE (r)-[:HAS_EVENT]->(e)",
                            id=eid, date=research_date,
                            text=_common._truncate(str(ev), 500), rid=research_id,
                        )
                # SectorRotation
                rotations = grok_research.get("sector_rotation", [])
                if isinstance(rotations, list):
                    for k, rot in enumerate(rotations[:3]):
                        srid = f"{research_id}_rot_{k}"
                        session.run(
                            "MERGE (sr:SectorRotation {id: $id}) "
                            "SET sr.date = $date, sr.text = $text "
                            "WITH sr "
                            "MATCH (r:Research {id: $rid}) "
                            "MERGE (r)-[:HAS_ROTATION]->(sr)",
                            id=srid, date=research_date,
                            text=_common._truncate(str(rot), 500), rid=research_id,
                        )
                # Indicator (macro_factors)
                macros = grok_research.get("macro_factors", [])
                if isinstance(macros, list):
                    for m, factor in enumerate(macros[:10]):
                        iid = f"{research_id}_macro_{m}"
                        session.run(
                            "MERGE (ind:Indicator {id: $id}) "
                            "SET ind.date = $date, ind.name = $name "
                            "WITH ind "
                            "MATCH (r:Research {id: $rid}) "
                            "MERGE (r)-[:INCLUDES]->(ind)",
                            id=iid, date=research_date,
                            name=_common._truncate(str(factor), 200),
                            rid=research_id,
                        )

            # --- Industry research sub-nodes (KIK-430) ---
            if research_type == "industry" and grok_research:
                # Catalyst nodes (trends, growth_drivers, risks, regulatory)
                _catalyst_keys = [
                    ("trends", "trend"),
                    ("growth_drivers", "growth_driver"),
                    ("risks", "risk"),
                    ("regulatory", "regulatory"),
                ]
                cat_idx = 0
                for grok_key, cat_type in _catalyst_keys:
                    items = grok_research.get(grok_key, [])
                    if isinstance(items, list):
                        for txt in items[:5]:
                            cid = f"{research_id}_cat_{cat_type}_{cat_idx}"
                            session.run(
                                "MERGE (c:Catalyst {id: $id}) "
                                "SET c.date = $date, c.type = $ctype, "
                                "c.text = $text "
                                "WITH c "
                                "MATCH (r:Research {id: $rid}) "
                                "MERGE (r)-[:HAS_CATALYST]->(c)",
                                id=cid, date=research_date,
                                ctype=cat_type,
                                text=_common._truncate(str(txt), 500),
                                rid=research_id,
                            )
                            cat_idx += 1
                # key_players -> Stock MENTIONS
                players = grok_research.get("key_players", [])
                if isinstance(players, list):
                    for player in players[:10]:
                        name = ""
                        symbol = ""
                        if isinstance(player, dict):
                            name = player.get("name", "")
                            symbol = player.get("symbol", player.get("ticker", ""))
                        elif isinstance(player, str):
                            name = player
                        if not name and not symbol:
                            continue
                        if symbol:
                            session.run(
                                "MERGE (s:Stock {symbol: $symbol}) "
                                "ON CREATE SET s.name = $name "
                                "WITH s "
                                "MATCH (r:Research {id: $rid}) "
                                "MERGE (r)-[:MENTIONS]->(s)",
                                symbol=symbol, name=name[:100],
                                rid=research_id,
                            )
                        elif name:
                            session.run(
                                "MERGE (s:Stock {name: $name}) "
                                "WITH s "
                                "MATCH (r:Research {id: $rid}) "
                                "MERGE (r)-[:MENTIONS]->(s)",
                                name=name[:100], rid=research_id,
                            )

        return True
    except Exception:
        return False
