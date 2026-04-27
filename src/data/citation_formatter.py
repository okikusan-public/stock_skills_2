"""Cited Sources formatter for DeepThink Step 5 reports (KIK-739).

Generates a human-readable Layer 5 (Cited Sources) section for reports,
respecting persistence tags so that permanent rules are not flagged as
stale, and surfacing seasonal lessons that have aged past warning thresholds.

Used by DeepThink Step 5 after `verify_lesson_cited()` confirms which
lessons were actually referenced.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime, timezone
from typing import Iterable, Optional


# Freshness thresholds (days). Configurable via `freshness_days` if needed.
_FRESH_DAYS = 30
_STALE_DAYS = 90


def _today() -> _date:
    """Return today's date in UTC. Wrapper for testability."""
    return datetime.now(timezone.utc).date()


def _parse_date(value: object) -> Optional[_date]:
    """Best-effort ISO-8601 parser. Returns None if unparseable."""
    if isinstance(value, _date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value:
        return None
    s = value.strip().split("T", 1)[0]
    try:
        return _date.fromisoformat(s)
    except ValueError:
        return None


def compute_age_days(note: dict, today: Optional[_date] = None) -> Optional[int]:
    """Days between note['date'] and today. None if date is missing/invalid."""
    d = _parse_date(note.get("date"))
    if d is None:
        return None
    return ((today or _today()) - d).days


def freshness_marker(
    note: dict,
    today: Optional[_date] = None,
    fresh_days: int = _FRESH_DAYS,
    stale_days: int = _STALE_DAYS,
) -> str:
    """Return a single-character emoji freshness marker for a note.

    Rules (KIK-739):
      - persistence=permanent → 🟢 (always fresh; permanent rules never stale)
      - persistence=expired   → ⛔
      - thesis with conviction_override=true → 🔒 (永続)
      - otherwise: by age
        - 0..fresh_days  → 🟢
        - ..stale_days   → 🟡
        - older / unknown → 🔴
    """
    persistence = (note.get("persistence") or "").lower()
    if persistence == "permanent":
        return "🟢"
    if persistence == "expired":
        return "⛔"
    if note.get("type") == "thesis" and note.get("conviction_override"):
        return "🔒"
    age = compute_age_days(note, today=today)
    if age is None:
        return "🔴"
    if age <= fresh_days:
        return "🟢"
    if age <= stale_days:
        return "🟡"
    return "🔴"


def _short_label(note: dict) -> str:
    """Pick the most informative one-line label for the note."""
    for k in ("trigger", "expected_action"):
        v = note.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().split("\n", 1)[0][:80]
    content = (note.get("content") or "").strip().splitlines()
    return content[0][:80] if content else "(no description)"


def format_cited_line(
    note: dict,
    used_for: Optional[str] = None,
    today: Optional[_date] = None,
) -> str:
    """Render a single bullet line for a cited note."""
    marker = freshness_marker(note, today=today)
    persistence = (note.get("persistence") or "unspecified").lower()
    age = compute_age_days(note, today=today)
    age_part = f"/{age}日" if age is not None else ""
    date_str = note.get("date") or "(unknown)"
    label = _short_label(note)
    line = f"- {marker} [{persistence}{age_part}] {date_str} {label}"
    if used_for:
        line += f" — {used_for}"
    if marker == "🟡":
        line += " ⚠ 古い: 環境変化あれば再確認"
    elif marker == "🔴":
        line += " ⚠ 90日超: 環境変化で無効の可能性"
    return line


def format_cited_sources(
    cited_lessons: Iterable[dict],
    cited_theses: Iterable[dict] = (),
    used_for_map: Optional[dict] = None,
    today: Optional[_date] = None,
) -> str:
    """Build the full Layer 5 markdown block.

    Parameters
    ----------
    cited_lessons : iterable of lesson note dicts
    cited_theses : iterable of thesis note dicts
    used_for_map : optional {note_id: "purpose string"} for "— used for ..." text
    """
    used_for_map = used_for_map or {}
    today = today or _today()

    def _line(n: dict) -> str:
        return format_cited_line(n, used_for=used_for_map.get(n.get("id")), today=today)

    lessons = [n for n in cited_lessons if (n.get("persistence") or "").lower() != "expired"]
    theses = list(cited_theses)

    blocks: list[str] = ["## 📚 Cited Sources"]
    if lessons:
        blocks.append("\n### Lessons")
        # Sort: permanent first, then by date desc
        lessons.sort(
            key=lambda n: (
                0 if (n.get("persistence") or "").lower() == "permanent" else 1,
                # newer-first → invert by negative ordinal
                -(_parse_date(n.get("date")) or _date.min).toordinal(),
            )
        )
        blocks.extend(_line(n) for n in lessons)
    if theses:
        blocks.append("\n### Theses")
        blocks.extend(_line(n) for n in theses)
    if not lessons and not theses:
        blocks.append("\n_(no lessons / theses cited — review whether this is intentional)_")
    return "\n".join(blocks)


__all__ = [
    "compute_age_days",
    "freshness_marker",
    "format_cited_line",
    "format_cited_sources",
]
