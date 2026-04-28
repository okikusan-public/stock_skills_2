"""Local data/ fallback for get_context() when Neo4j is unavailable (KIK-719).

When Neo4j is not connected, build context_markdown from local files:
- data/notes/*.json (thesis/observation/concern via note_manager.load_notes)
- data/portfolio.csv (holding status via portfolio_io.load_portfolio)
- data/screening_results/*.json (past screening surfaces)

This module supports the conviction-violation detection pathway by ensuring
thesis notes (e.g. "ホールド確定") are always readable without Neo4j.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from src.data import note_manager
from src.data import portfolio_io


_SCREENING_DIR = "data/screening_results"  # relative; resolved at call time


def _is_held_local(symbol: str) -> bool:
    """Check holding status from data/portfolio.csv (Neo4j-free)."""
    try:
        portfolio = portfolio_io.load_portfolio(portfolio_io.DEFAULT_CSV_PATH)
    except Exception:
        return False
    sym_upper = symbol.upper()
    return any(
        (p.get("symbol") or "").upper() == sym_upper for p in portfolio
    )


_WATCHLIST_DIR = "data/watchlists"  # relative; resolved at call time


def _is_bookmarked_local(symbol: str) -> bool:
    """Check watchlist membership from data/watchlists/*.json (Neo4j-free).

    KIK-743: tools/watchlist.py:save_watchlist は list 形式（["AAPL", ...]）で
    保存するため、list / dict {symbols: [...]} 両形式に対応する。
    """
    wl_dir = Path(_WATCHLIST_DIR)
    if not wl_dir.exists():
        return False
    sym_upper = symbol.upper()
    for fp in wl_dir.glob("*.json"):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        # KIK-743: list 直保存形式（tools/watchlist.py の標準形式）
        if isinstance(data, list):
            symbols = data
        elif isinstance(data, dict):
            # legacy: {"symbols": [...]} 形式
            symbols = data.get("symbols")
        else:
            symbols = None
        if symbols and any(
            (s or "").upper() == sym_upper for s in symbols if isinstance(s, str)
        ):
            return True
    return False


def _count_screening_appearances(symbol: str) -> int:
    """Count how many past screening_results contain this symbol."""
    sd = Path(_SCREENING_DIR)
    if not sd.exists():
        return 0
    sym_upper = symbol.upper()
    count = 0
    for fp in sd.glob("*.json"):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        # Common shapes: {"results": [{"symbol": ...}]} or [{"symbol": ...}]
        items = data.get("results") if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if (item.get("symbol") or "").upper() == sym_upper:
                count += 1
                break  # one count per file
    return count


def _detect_conviction(notes: list[dict]) -> Optional[str]:
    """Return conviction snippet if any note signals 'hold confirmed'.

    Case-insensitive match for English keywords; Japanese keywords are
    inherently case-stable.
    """
    keywords = ("ホールド確定", "うらない", "売らない", "conviction")
    for n in notes:
        content = (n.get("content") or "")
        content_lower = content.lower()
        source = (n.get("source") or "").lower()
        if any(k in content_lower for k in keywords) \
                or source.startswith("user-conviction"):
            return content[:120]
    return None


def _format_notes_section(notes: list[dict], limit: int = 5) -> list[str]:
    """Format thesis/observation/concern notes into markdown lines."""
    lines: list[str] = []
    if not notes:
        return lines
    lines.append("## 投資メモ")
    for n in notes[:limit]:
        ntype = n.get("type", "?")
        date = n.get("date", "")
        content = (n.get("content") or "")[:140]
        date_part = f" ({date})" if date else ""
        lines.append(f"- [{ntype}]{date_part} {content}")
    return lines


def build_symbol_context_local(symbol: str) -> Optional[dict]:
    """Build symbol context from local data/ when Neo4j is unavailable.

    Returns a dict matching get_context()'s shape, or None if no signals exist.
    """
    notes = note_manager.load_notes(symbol=symbol)
    is_held = _is_held_local(symbol)
    is_bookmarked = _is_bookmarked_local(symbol)
    screen_count = _count_screening_appearances(symbol)
    conviction = _detect_conviction(notes)

    # If we have nothing meaningful, return None (graceful degradation)
    if not notes and not is_held and not is_bookmarked and screen_count == 0:
        return None

    # Skill recommendation (simplified, Neo4j-free)
    if is_held:
        if conviction:
            skill, reason, relationship = (
                "health", "保有 + conviction銘柄 → ヘルスチェック", "保有(conviction)",
            )
        else:
            skill, reason, relationship = (
                "health", "保有銘柄 → ヘルスチェック優先", "保有",
            )
    elif notes and any(n.get("type") == "concern" for n in notes):
        skill, reason, relationship = (
            "report", "懸念メモあり → 再検証", "懸念あり",
        )
    elif is_bookmarked:
        skill, reason, relationship = (
            "report", "ウォッチリスト登録済 → レポート", "監視中",
        )
    elif screen_count >= 3:
        # Threshold aligned with Neo4j path's _recommend_skill (3+ screenings)
        skill, reason, relationship = (
            "report", f"スクリーニング {screen_count}回出現 → レポート", "注目銘柄",
        )
    elif notes:
        skill, reason, relationship = (
            "report", "過去メモあり → レポート", "既知",
        )
    else:
        skill, reason, relationship = (
            "report", "未知の銘柄 → ゼロから調査", "未知",
        )

    # Compose markdown
    lines = [f"## 過去の経緯: {symbol} ({relationship})"]
    if conviction:
        lines.append(f"- ⚠ conviction銘柄: {conviction}")
    if is_held:
        lines.append("- 保有中（portfolio.csv）")
    if is_bookmarked:
        lines.append("- ウォッチリスト登録")
    if screen_count > 0:
        lines.append(f"- スクリーニング履歴: {screen_count}件")
    lines.extend(_format_notes_section(notes))
    lines.append(f"\n**推奨**: {skill} ({reason})")

    return {
        "symbol": symbol,
        "context_markdown": "\n".join(lines),
        "recommended_skill": skill,
        "recommendation_reason": reason,
        "relationship": relationship,
    }


def build_portfolio_context_local() -> dict:
    """Build portfolio context from data/portfolio.csv + data/notes (Neo4j-free)."""
    try:
        portfolio = portfolio_io.load_portfolio(portfolio_io.DEFAULT_CSV_PATH)
    except Exception:
        portfolio = []

    lines = ["## ポートフォリオコンテキスト"]
    if portfolio:
        lines.append(f"- 保有銘柄: {len(portfolio)}件")

    # Collect notes for held symbols (top 1 per symbol)
    held_notes_lines: list[str] = []
    for entry in portfolio:
        sym = entry.get("symbol")
        if not sym:
            continue
        notes = note_manager.load_notes(symbol=sym)
        # Prioritize thesis/concern over observation
        priority = {"thesis": 0, "concern": 1, "observation": 2, "review": 3}
        notes_sorted = sorted(
            notes, key=lambda n: priority.get(n.get("type", ""), 99),
        )
        for n in notes_sorted[:1]:
            ntype = n.get("type", "?")
            content = (n.get("content") or "")[:60]
            ndate = n.get("date", "")
            date_part = f" ({ndate})" if ndate else ""
            held_notes_lines.append(f"- [{sym}] {ntype}: {content}{date_part}")

    if held_notes_lines:
        lines.append("")
        lines.append("## 保有銘柄の重要メモ")
        lines.extend(held_notes_lines)

    lines.append("\n**推奨**: health (ポートフォリオ診断)")

    return {
        "symbol": "",
        "context_markdown": "\n".join(lines),
        "recommended_skill": "health",
        "recommendation_reason": "ポートフォリオ照会",
        "relationship": "PF",
    }
