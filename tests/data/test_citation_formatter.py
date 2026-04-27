"""Tests for src.data.citation_formatter (KIK-739)."""

from __future__ import annotations

from datetime import date

import pytest

from src.data.citation_formatter import (
    compute_age_days,
    format_cited_line,
    format_cited_sources,
    freshness_marker,
)


_TODAY = date(2026, 4, 28)


# ---------------------------------------------------------------------------
# compute_age_days
# ---------------------------------------------------------------------------


class TestComputeAgeDays:
    def test_today(self):
        assert compute_age_days({"date": "2026-04-28"}, today=_TODAY) == 0

    def test_recent(self):
        assert compute_age_days({"date": "2026-04-24"}, today=_TODAY) == 4

    def test_old(self):
        assert compute_age_days({"date": "2026-02-28"}, today=_TODAY) == 59

    def test_iso_with_time(self):
        assert compute_age_days({"date": "2026-04-20T10:30:00+00:00"}, today=_TODAY) == 8

    def test_missing_date(self):
        assert compute_age_days({}, today=_TODAY) is None

    def test_invalid_date(self):
        assert compute_age_days({"date": "not-a-date"}, today=_TODAY) is None


# ---------------------------------------------------------------------------
# freshness_marker
# ---------------------------------------------------------------------------


class TestFreshnessMarker:
    def test_permanent_always_green_even_if_old(self):
        n = {"date": "2024-01-01", "persistence": "permanent"}
        assert freshness_marker(n, today=_TODAY) == "🟢"

    def test_seasonal_fresh(self):
        n = {"date": "2026-04-15", "persistence": "seasonal"}
        assert freshness_marker(n, today=_TODAY) == "🟢"

    def test_seasonal_warning(self):
        n = {"date": "2026-02-28", "persistence": "seasonal"}  # 59 days
        assert freshness_marker(n, today=_TODAY) == "🟡"

    def test_seasonal_red(self):
        n = {"date": "2025-12-01", "persistence": "seasonal"}
        assert freshness_marker(n, today=_TODAY) == "🔴"

    def test_expired_marker(self):
        n = {"date": "2026-04-28", "persistence": "expired"}
        assert freshness_marker(n, today=_TODAY) == "⛔"

    def test_thesis_with_conviction_override(self):
        n = {"date": "2025-01-01", "type": "thesis", "conviction_override": True}
        assert freshness_marker(n, today=_TODAY) == "🔒"

    def test_situational_uses_age(self):
        # situational without explicit override falls through to age-based
        n = {"date": "2026-04-25", "persistence": "situational"}
        assert freshness_marker(n, today=_TODAY) == "🟢"

    def test_unknown_persistence_age_based(self):
        n = {"date": "2026-04-15"}
        assert freshness_marker(n, today=_TODAY) == "🟢"

    def test_unknown_date_red(self):
        n = {"persistence": "seasonal"}
        assert freshness_marker(n, today=_TODAY) == "🔴"

    def test_custom_thresholds(self):
        n = {"date": "2026-04-21", "persistence": "seasonal"}  # 7 days
        # If fresh_days=3, age 7 falls into stale band
        assert freshness_marker(n, today=_TODAY, fresh_days=3, stale_days=10) == "🟡"

    def test_future_date_returns_green_by_age_logic(self):
        # Future-dated note: age becomes negative (-365), still <= fresh_days,
        # so falls into 🟢 band. This is a known edge case — clock-skew should
        # be caught upstream. Document via test rather than guard.
        n = {"date": "2027-04-28", "persistence": "seasonal"}
        assert freshness_marker(n, today=_TODAY) == "🟢"

    def test_future_date_age_is_negative(self):
        assert compute_age_days({"date": "2027-04-28"}, today=_TODAY) == -365


# ---------------------------------------------------------------------------
# format_cited_line
# ---------------------------------------------------------------------------


class TestFormatCitedLine:
    def test_permanent_line(self):
        n = {
            "id": "L1", "date": "2026-04-24", "persistence": "permanent",
            "trigger": "PFバランス normal 判定時",
        }
        line = format_cited_line(n, used_for="グロース判定", today=_TODAY)
        assert line.startswith("- 🟢")
        assert "permanent" in line
        assert "PFバランス normal 判定時" in line
        assert "グロース判定" in line
        assert "⚠" not in line

    def test_yellow_warning_appended(self):
        n = {
            "id": "L2", "date": "2026-02-28", "persistence": "seasonal",
            "trigger": "金利4%超 + VIX25超",
        }
        line = format_cited_line(n, today=_TODAY)
        assert line.startswith("- 🟡")
        # Both 警告 markers should be on the same line (no \n between them)
        assert "⚠" in line and "再確認" in line
        assert "\n" not in line

    def test_red_warning_appended(self):
        n = {"date": "2024-01-01", "persistence": "seasonal", "trigger": "原油急騰"}
        line = format_cited_line(n, today=_TODAY)
        assert line.startswith("- 🔴")
        assert "90日超" in line

    def test_falls_back_to_content(self):
        n = {"date": "2026-04-24", "persistence": "permanent",
             "content": "詳細な解説\n二行目"}
        line = format_cited_line(n, today=_TODAY)
        assert "詳細な解説" in line
        assert "二行目" not in line  # only first line


# ---------------------------------------------------------------------------
# format_cited_sources
# ---------------------------------------------------------------------------


class TestFormatCitedSources:
    def test_block_header(self):
        out = format_cited_sources([], today=_TODAY)
        assert out.startswith("## 📚 Cited Sources")

    def test_no_citations_warns(self):
        out = format_cited_sources([], today=_TODAY)
        assert "no lessons / theses cited" in out

    def test_renders_lessons_section(self):
        lessons = [
            {"id": "L1", "date": "2026-04-24", "persistence": "permanent",
             "trigger": "PFバランス"},
            {"id": "L2", "date": "2026-02-28", "persistence": "seasonal",
             "trigger": "原油急騰"},
        ]
        out = format_cited_sources(lessons, today=_TODAY)
        assert "### Lessons" in out
        assert "PFバランス" in out
        assert "原油急騰" in out

    def test_excludes_expired(self):
        lessons = [
            {"id": "L1", "date": "2026-04-24", "persistence": "permanent",
             "trigger": "active rule"},
            {"id": "L2", "date": "2026-04-24", "persistence": "expired",
             "trigger": "old garbage"},
        ]
        out = format_cited_sources(lessons, today=_TODAY)
        assert "active rule" in out
        assert "old garbage" not in out

    def test_renders_theses_section(self):
        theses = [{"id": "T1", "date": "2026-04-25", "type": "thesis",
                   "conviction_override": True, "content": "ホールド確定"}]
        out = format_cited_sources([], theses, today=_TODAY)
        assert "### Theses" in out
        assert "🔒" in out

    def test_used_for_annotation(self):
        lessons = [{"id": "L1", "date": "2026-04-24", "persistence": "permanent",
                    "trigger": "x"}]
        out = format_cited_sources(
            lessons, used_for_map={"L1": "売却対象除外"}, today=_TODAY,
        )
        assert "売却対象除外" in out

    def test_permanent_appears_before_seasonal(self):
        lessons = [
            {"id": "S", "date": "2026-04-26", "persistence": "seasonal",
             "trigger": "seasonal_one"},
            {"id": "P", "date": "2026-04-24", "persistence": "permanent",
             "trigger": "permanent_one"},
        ]
        out = format_cited_sources(lessons, today=_TODAY)
        # Restrict to the Lessons section to avoid false positives if other
        # sections happen to appear earlier
        lessons_section = out.split("### Lessons")[1].split("### ", 1)[0]
        permanent_idx = lessons_section.index("permanent_one")
        seasonal_idx = lessons_section.index("seasonal_one")
        assert permanent_idx < seasonal_idx

    def test_within_permanent_newer_first(self):
        # Both permanent — should be newer-first within group
        lessons = [
            {"id": "OLDER", "date": "2026-04-20", "persistence": "permanent",
             "trigger": "older_permanent"},
            {"id": "NEWER", "date": "2026-04-25", "persistence": "permanent",
             "trigger": "newer_permanent"},
        ]
        out = format_cited_sources(lessons, today=_TODAY)
        lessons_section = out.split("### Lessons")[1]
        newer_idx = lessons_section.index("newer_permanent")
        older_idx = lessons_section.index("older_permanent")
        assert newer_idx < older_idx, "newer permanent lesson must come first"

    def test_within_seasonal_newer_first(self):
        lessons = [
            {"id": "S_OLD", "date": "2026-04-20", "persistence": "seasonal",
             "trigger": "older_seasonal"},
            {"id": "S_NEW", "date": "2026-04-25", "persistence": "seasonal",
             "trigger": "newer_seasonal"},
        ]
        out = format_cited_sources(lessons, today=_TODAY)
        lessons_section = out.split("### Lessons")[1]
        newer_idx = lessons_section.index("newer_seasonal")
        older_idx = lessons_section.index("older_seasonal")
        assert newer_idx < older_idx
