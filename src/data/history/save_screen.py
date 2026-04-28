"""Save screening results to history (KIK-578 split from save.py)."""

import json
from datetime import date, datetime

from src.data.history._helpers import (
    _safe_filename,
    _history_dir,
    _sanitize,
    _dual_write_graph,
)


def save_screening(
    preset: str,
    region: str,
    results: list[dict],
    sector: str | None = None,
    theme: str | None = None,
    base_dir: str = "data/history",
) -> str:
    """Save screening results to JSON.

    Returns the absolute path of the saved file.
    """
    today = date.today().isoformat()
    now_dt = datetime.now()
    now = now_dt.isoformat(timespec="seconds")
    # KIK-743: HHMMSS で一意化（同日同region/preset の上書き防止）
    ts_suffix = now_dt.strftime("%H%M%S")
    identifier = f"{_safe_filename(region)}_{_safe_filename(preset)}"
    filename = f"{today}_{identifier}_{ts_suffix}.json"

    payload = {
        "category": "screen",
        "date": today,
        "timestamp": now,
        "preset": preset,
        "region": region,
        "sector": sector,
        "theme": theme,
        "count": len(results),
        "results": results,
        "_saved_at": now,
    }

    d = _history_dir("screen", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-399/420/487) -- graceful degradation
    symbols = [r.get("symbol") for r in results if r.get("symbol")]

    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_screen, merge_stock, tag_theme
        for r in results:
            sym = r.get("symbol")
            if sym:
                merge_stock(symbol=sym, name=r.get("name", ""), sector=r.get("sector", ""))
                if theme:
                    tag_theme(sym, theme)
        merge_screen(today, preset, region, len(results), symbols,
                     semantic_summary=sem_summary, embedding=emb)

    _dual_write_graph(
        _graph_write, "screen",
        dict(date=today, preset=preset, region=region, top_symbols=symbols[:5]),
    )

    return str(path.resolve())
