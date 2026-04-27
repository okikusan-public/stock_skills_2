"""Error / mis-recommendation tracker (KIK-736).

Append-only log of past recommendation errors so we can detect repeated
patterns (e.g. "cash_not_verified" happening 3 times in 30 days).

Storage: data/archive/errors.jsonl  (each line is one error event).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


_ERRORS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "archive" / "errors.jsonl"
)


def _resolve_path(path: str | os.PathLike | None) -> Path:
    if path is None:
        return _ERRORS_PATH
    return Path(path)


def record_error(
    error_type: str,
    theme: str,
    root_cause: str,
    *,
    recall: Optional[str] = None,
    extra: Optional[dict] = None,
    path: str | os.PathLike | None = None,
) -> dict:
    """Append one error event to errors.jsonl (best-effort).

    Parameters
    ----------
    error_type : str
        Stable category, e.g. "cash_not_verified", "dr_api_schema_mismatch",
        "conviction_violation_emitted".
    theme : str
        Short description of the failed task.
    root_cause : str
        One-line root cause analysis.
    recall : str, optional
        What was recalled / undone, if any.
    extra : dict, optional
        Additional structured fields (linked KIK ids, recommendations made).
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "error_type": error_type,
        "theme": theme,
        "root_cause": root_cause,
        "recall": recall,
        "extra": extra or {},
    }
    out = _resolve_path(path)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        # Best-effort: do not crash the caller
        pass
    return record


def load_errors(
    path: str | os.PathLike | None = None,
) -> list[dict]:
    """Load all errors. Skips corrupt/blank lines."""
    p = _resolve_path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def detect_recent_patterns(
    within_days: int = 30,
    min_count: int = 3,
    path: str | os.PathLike | None = None,
) -> dict[str, int]:
    """Return error_type → count for the last N days, only types ≥ min_count.

    Used by `tools/deepthink_summary.py` (or DeepThink Step 0) to warn about
    recurring failure patterns.
    """
    p = _resolve_path(path)
    if not p.exists():
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    counts: dict[str, int] = {}
    for rec in load_errors(p):
        ts_str = rec.get("ts", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        # Ensure tz-aware for comparison
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            continue
        et = rec.get("error_type") or "unknown"
        counts[et] = counts.get(et, 0) + 1
    return {k: v for k, v in counts.items() if v >= min_count}


__all__ = [
    "record_error",
    "load_errors",
    "detect_recent_patterns",
]
