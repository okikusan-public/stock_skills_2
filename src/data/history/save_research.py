"""Save research and market context results to history (KIK-578 split from save.py)."""

import json
import re as _re
from datetime import date, datetime

from src.data.history._helpers import (
    _safe_filename,
    _history_dir,
    _sanitize,
    _dual_write_graph,
    _unique_suffix,
)


def _build_research_summary(research_type: str, result: dict) -> str:
    """Build a summary string from research result for Neo4j storage (KIK-416).

    Extracts key information from grok_research and other fields to create
    a concise summary (max 200 chars) for GraphRAG queries.
    """
    grok = result.get("grok_research")
    if grok is None or not isinstance(grok, dict):
        grok = {}

    parts: list[str] = []

    if research_type == "stock":
        # Name + first news headline + sentiment score + value_score
        name = result.get("name", "")
        if name:
            parts.append(name)
        news = grok.get("recent_news") or result.get("news") or []
        if news and isinstance(news, list) and isinstance(news[0], (str, dict)):
            headline = news[0] if isinstance(news[0], str) else news[0].get("title", "")
            headline = headline.split("<")[0].strip()  # strip grok citation tags
            if headline:
                parts.append(headline[:80])
        xs = grok.get("x_sentiment") or result.get("x_sentiment") or {}
        if isinstance(xs, dict) and xs.get("score") is not None:
            parts.append(f"Xセンチメント{xs['score']}")
        vs = result.get("value_score")
        if vs is not None:
            parts.append(f"スコア{vs}")

    elif research_type == "market":
        # price_action + sentiment score
        pa = grok.get("price_action", "")
        if pa:
            if isinstance(pa, list):
                pa = "\n".join(pa)
            pa_clean = pa.split("<")[0].strip()
            parts.append(pa_clean[:120])
        sent = grok.get("sentiment") or {}
        if isinstance(sent, dict) and sent.get("score") is not None:
            parts.append(f"センチメント{sent['score']}")

    elif research_type == "industry":
        # trends
        trends = grok.get("trends", "")
        if trends:
            if isinstance(trends, list):
                trends = "\n".join(trends)
            trends_clean = trends.split("<")[0].strip()
            parts.append(trends_clean[:120])

    elif research_type == "business":
        # name + overview
        name = result.get("name", "")
        if name:
            parts.append(name)
        overview = grok.get("overview", "")
        if overview:
            if isinstance(overview, list):
                overview = "\n".join(overview)
            overview_clean = overview.split("<")[0].strip()
            parts.append(overview_clean[:120])

    summary = ". ".join(parts)
    if len(summary) > 200:
        summary = summary[:197] + "..."
    return summary


def save_research(
    research_type: str,
    target: str,
    result: dict,
    base_dir: str = "data/history",
) -> str:
    """Save research results to JSON (KIK-405).

    Parameters
    ----------
    research_type : str
        "stock", "industry", "market", or "business".
    target : str
        Symbol (e.g. "7203.T") or theme name (e.g. "半導体").
    result : dict
        Return value from researcher.research_*() functions.
    base_dir : str
        Root history directory.

    Returns
    -------
    str
        Absolute path of the saved file.
    """
    today = date.today().isoformat()
    now_dt = datetime.now()
    now = now_dt.isoformat(timespec="seconds")
    # KIK-744: HHMMSSffffff + uuid hex で完全一意化
    ts_suffix = _unique_suffix(now_dt)
    identifier = f"{_safe_filename(research_type)}_{_safe_filename(target)}"
    filename = f"{today}_{identifier}_{ts_suffix}.json"

    payload = {
        "category": "research",
        "date": today,
        "timestamp": now,
        "research_type": research_type,
        "target": target,
        **{k: v for k, v in result.items() if k != "type"},
        "_saved_at": now,
    }

    d = _history_dir("research", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-399/413/416/420) -- graceful degradation
    summary = result.get("summary", "") or _build_research_summary(research_type, result)

    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_research_full, merge_stock, link_research_supersedes
        if research_type in ("stock", "business"):
            _fundamentals = result.get("fundamentals") or {}
            merge_stock(
                symbol=target,
                name=result.get("name", ""),
                sector=_fundamentals.get("sector", "") or "",
            )
        merge_research_full(
            research_date=today, research_type=research_type,
            target=target, summary=summary,
            grok_research=result.get("grok_research"),
            x_sentiment=result.get("x_sentiment"),
            news=result.get("news"),
            semantic_summary=sem_summary, embedding=emb,
        )
        link_research_supersedes(research_type, target)

    _dual_write_graph(
        _graph_write, "research",
        dict(research_type=research_type, target=target, result=result),
    )

    # KIK-434: AI graph linking (graceful degradation)
    try:
        from src.data.graph_store.linker import link_research
        _rid = f"research_{today}_{research_type}_{_re.sub(r'[^a-zA-Z0-9]', '_', target)}"
        link_research(_rid, research_type, target, summary)
    except Exception:
        pass

    return str(path.resolve())


def save_market_context(
    context: dict,
    base_dir: str = "data/history",
) -> str:
    """Save market context snapshot to JSON (KIK-405).

    Parameters
    ----------
    context : dict
        Market context data. Expected key: "indices" (list of dicts from
        get_macro_indicators) or a flat dict with indicator values.
    base_dir : str
        Root history directory.

    Returns
    -------
    str
        Absolute path of the saved file.
    """
    today = date.today().isoformat()
    now_dt = datetime.now()
    now = now_dt.isoformat(timespec="seconds")
    # KIK-744: HHMMSSffffff + uuid hex で完全一意化
    ts_suffix = _unique_suffix(now_dt)
    filename = f"{today}_context_{ts_suffix}.json"

    payload = {
        "category": "market_context",
        "date": today,
        "timestamp": now,
        **context,
        "_saved_at": now,
    }

    d = _history_dir("market_context", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-399/413/420) -- graceful degradation
    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_market_context_full
        merge_market_context_full(
            context_date=today, indices=context.get("indices", []),
            grok_research=context.get("grok_research"),
            semantic_summary=sem_summary, embedding=emb,
        )

    _dual_write_graph(
        _graph_write, "market_context",
        dict(date=today, indices=context.get("indices", []),
             grok_research=context.get("grok_research")),
    )

    return str(path.resolve())
