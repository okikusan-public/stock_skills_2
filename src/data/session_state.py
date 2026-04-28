"""Session-start state reconcile (KIK-738 後追い).

Purpose
-------
Before the AI makes any claim about PF / cash / holdings / pending trades, it
must read the disk state (portfolio.csv / cash_balance.json / recent notes /
recent trade JSONs). The 2026-04-29 morning-greeting bug was a regression
where the AI relied on memory and surfaced stale plans.

Pattern: same as `src/data/preflight.py` — a thin pure function returning a
structured dict. SKILL.md only carries the call site (`reconcile_session_state()`),
not the implementation.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_iso_date(value: object) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value:
        return None
    s = value.strip().split("T", 1)[0]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _load_portfolio(base_dir: Path) -> list[dict]:
    """Parse `<base_dir>/data/portfolio.csv` directly (respects base_dir)."""
    import csv

    path = base_dir / "data" / "portfolio.csv"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _load_cash_balance(base_dir: Path) -> Optional[dict]:
    path = base_dir / "data" / "cash_balance.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_recent_notes(base_dir: Path, window_days: int) -> list[dict]:
    """Return notes whose `date` is within `window_days` of today."""
    notes_dir = base_dir / "data" / "notes"
    if not notes_dir.exists():
        return []
    cutoff = _today() - timedelta(days=window_days)
    recent: list[dict] = []
    for fp in sorted(notes_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        notes = data if isinstance(data, list) else [data]
        for n in notes:
            if not isinstance(n, dict):
                continue
            d = _parse_iso_date(n.get("date"))
            if d is not None and d >= cutoff:
                recent.append(n)
    # Newer first
    recent.sort(key=lambda n: n.get("date", ""), reverse=True)
    return recent


def _load_recent_trades(base_dir: Path, window_days: int) -> list[str]:
    """Return trade JSON filenames whose `date` (or legacy `trade_date`) is within window_days.

    KIK-742: save_trade.py は `"date"` キーで保存するが、過去には `trade_date` も
    使われていた。両方をフォールバックして読む。
    """
    trade_dir = base_dir / "data" / "history" / "trade"
    if not trade_dir.exists():
        return []
    cutoff = _today() - timedelta(days=window_days)
    recent: list[str] = []
    for fp in sorted(trade_dir.glob("*.json"), reverse=True):
        try:
            rec = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # KIK-742: date が正、trade_date は legacy フォールバック
        d = _parse_iso_date(rec.get("date") or rec.get("trade_date"))
        if d is not None and d >= cutoff:
            recent.append(fp.name)
    return recent


def reconcile_session_state(
    notes_window_days: int = 7,
    trade_window_days: int = 7,
    cash_stale_days: int = 3,
    base_dir: str = ".",
) -> dict[str, Any]:
    """Read all disk state required before talking about PF / cash / holdings.

    See tools/session_state.py for the public facade and SKILL.md hook.
    """
    root = Path(base_dir).resolve()
    portfolio = _load_portfolio(root)
    cash = _load_cash_balance(root)
    recent_notes = _load_recent_notes(root, notes_window_days)
    recent_trades = _load_recent_trades(root, trade_window_days)

    warnings: list[str] = []
    cash_stale = False
    cash_missing = cash is None
    if cash_missing:
        warnings.append("cash_balance.json が見つかりません")
    else:
        cash_date = _parse_iso_date(cash.get("date"))
        if cash_date is None:
            warnings.append("cash_balance.json の date が解釈できません")
            # 年月日が読めない時は stale 扱い（保守側）
            cash_stale = True
        else:
            age_days = (_today() - cash_date).days
            if age_days > cash_stale_days:
                cash_stale = True
                warnings.append(
                    f"cash_balance.json は {cash['date']} 時点 "
                    f"({age_days}日前) — 直近取引と乖離の可能性"
                )

    if not recent_notes:
        warnings.append(
            f"直近 {notes_window_days} 日に新規 note なし — "
            "前回 session 以降の判断記録が無い可能性"
        )

    return {
        "portfolio": portfolio,
        "cash_balance": cash,
        "cash_missing": cash_missing,
        "cash_stale": cash_stale,
        "recent_notes": recent_notes,
        "recent_trades": recent_trades,
        "warnings": warnings,
        "checked_at": _today().isoformat(),
    }


__all__ = ["reconcile_session_state"]
