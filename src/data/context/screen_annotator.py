"""Screen result annotator -- enrich screening results with sell/note context (KIK-418/419).

Adds annotation fields to each result dict:
  _note_markers : str  -- emoji markers (e.g. "⚠️📝")
  _note_summary : str  -- short text summary of notes
  _recently_sold: bool  -- True if sold within lookback window
  _sold_date    : str   -- ISO date of most recent sell

Sold stocks are excluded from results (KIK-418).
Note markers are displayed in formatter labels (KIK-419).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional


# Marker characters
MARKER_SOLD = "\U0001f504"      # 🔄 recently sold
MARKER_CONCERN = "\u26a0\ufe0f"  # ⚠️ concern
MARKER_LESSON = "\U0001f4dd"     # 📝 lesson
MARKER_WATCH = "\U0001f440"      # 👀 watch/skip

# Keywords in observation content that trigger the 👀 marker
_WATCH_KEYWORDS = {"見送り", "ステイ", "待ち", "様子見"}


# ---------------------------------------------------------------------------
# Data retrieval (Neo4j → JSON fallback)
# ---------------------------------------------------------------------------


def get_recent_sells(days: int = 90) -> dict[str, str]:
    """Get symbols sold within the last *days*.

    Returns {symbol: sell_date}. Empty dict on failure.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Try Neo4j first
    try:
        from src.data.graph_query import get_recent_sells_batch
        result = get_recent_sells_batch(cutoff)
        if result:
            return result
    except Exception:
        pass

    # Fallback: scan trade history JSON files
    return _load_sells_from_json(cutoff)


def _load_sells_from_json(cutoff: str) -> dict[str, str]:
    """Scan data/history/trade/*.json for sell records after cutoff."""
    trade_dir = Path("data/history/trade")
    if not trade_dir.exists():
        return {}

    sells: dict[str, str] = {}
    for fp in trade_dir.glob("*.json"):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = [data]
            for rec in data:
                if rec.get("trade_type") == "sell" and rec.get("date", "") >= cutoff:
                    sym = rec.get("symbol", "")
                    existing = sells.get(sym, "")
                    if sym and rec["date"] > existing:
                        sells[sym] = rec["date"]
        except (json.JSONDecodeError, OSError):
            continue
    return sells


def get_notes_for_symbols(
    symbols: list[str],
    note_types: Optional[list[str]] = None,
) -> dict[str, list[dict]]:
    """Get notes for symbols. Returns {symbol: [{type, content, date}]}.

    Falls back to note_manager JSON files when Neo4j is unavailable.
    """
    if not symbols:
        return {}

    target_types = note_types or ["concern", "lesson", "observation"]

    # Try Neo4j first
    try:
        from src.data.graph_query import get_notes_for_symbols_batch
        result = get_notes_for_symbols_batch(symbols, target_types)
        if result:
            return result
    except Exception:
        pass

    # Fallback: note_manager JSON
    return _load_notes_from_json(symbols, target_types)


def _load_notes_from_json(
    symbols: list[str],
    note_types: list[str],
) -> dict[str, list[dict]]:
    """Load notes from JSON files via note_manager."""
    try:
        from src.data.note_manager import load_notes
    except ImportError:
        return {}

    out: dict[str, list[dict]] = {}
    all_notes = load_notes()
    symbol_set = set(symbols)
    type_set = set(note_types)

    for note in all_notes:
        sym = note.get("symbol", "")
        ntype = note.get("type", "")
        if sym in symbol_set and ntype in type_set:
            if sym not in out:
                out[sym] = []
            out[sym].append({
                "type": ntype,
                "content": note.get("content", ""),
                "date": note.get("date", ""),
            })
    return out


# ---------------------------------------------------------------------------
# Annotation logic
# ---------------------------------------------------------------------------


def _build_markers(notes: list[dict]) -> str:
    """Build marker string from a list of notes for one symbol."""
    markers = []
    has_concern = False
    has_lesson = False
    has_watch = False

    for note in notes:
        ntype = note.get("type", "")
        content = note.get("content", "")

        if ntype == "concern" and not has_concern:
            markers.append(MARKER_CONCERN)
            has_concern = True
        elif ntype == "lesson" and not has_lesson:
            markers.append(MARKER_LESSON)
            has_lesson = True
        elif ntype == "observation" and not has_watch:
            if any(kw in content for kw in _WATCH_KEYWORDS):
                markers.append(MARKER_WATCH)
                has_watch = True

    return "".join(markers)


def _build_note_summary(notes: list[dict], max_notes: int = 2) -> str:
    """Build a short text summary from the most recent notes."""
    if not notes:
        return ""

    parts = []
    for note in notes[:max_notes]:
        ntype = note.get("type", "")
        content = note.get("content", "")
        if content:
            short = content[:40] + "..." if len(content) > 40 else content
            parts.append(f"[{ntype}] {short}")
    return " / ".join(parts)


def annotate_results(
    results: list[dict],
    sell_lookback_days: int = 90,
) -> tuple[list[dict], int]:
    """Annotate screening results with sell history and note markers.

    Parameters
    ----------
    results : list[dict]
        Screening result dicts (each must have "symbol" key).
    sell_lookback_days : int
        Number of days to look back for recent sells.

    Returns
    -------
    tuple[list[dict], int]
        (annotated_results_with_sold_excluded, excluded_count)
    """
    if not results:
        return results, 0

    symbols = [r.get("symbol", "") for r in results if r.get("symbol")]
    if not symbols:
        return results, 0

    # Batch fetch sell history and notes
    try:
        sells = get_recent_sells(days=sell_lookback_days)
    except Exception:
        sells = {}

    try:
        notes = get_notes_for_symbols(symbols)
    except Exception:
        notes = {}

    annotated = []
    excluded = 0

    for row in results:
        sym = row.get("symbol", "")

        # KIK-418: Exclude recently sold stocks
        if sym in sells:
            excluded += 1
            continue

        # KIK-419: Add note markers
        sym_notes = notes.get(sym, [])
        markers = _build_markers(sym_notes)
        summary = _build_note_summary(sym_notes)

        row["_note_markers"] = markers
        row["_note_summary"] = summary
        row["_recently_sold"] = False
        annotated.append(row)

    return annotated, excluded
