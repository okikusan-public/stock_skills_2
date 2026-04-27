"""Tests for tools/deepthink_summary.py (KIK-732)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import deepthink_summary as ds


@pytest.fixture
def meta_log(monkeypatch, tmp_path):
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(ds, "_META_LOG_PATH", log)
    return log


def write_records(log: Path, records: list[dict]) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class TestLoadMetaRecords:
    def test_no_log_returns_empty(self, meta_log):
        assert ds.load_meta_records("2026-04") == []

    def test_filters_by_month(self, meta_log):
        write_records(meta_log, [
            {"ts": "2026-04-26T10:00:00+00:00", "tool": "gemini_deep_research", "cost_usd": 2.5},
            {"ts": "2026-03-15T10:00:00+00:00", "tool": "bulk_x_search", "cost_usd": 0.5},
            {"ts": "2026-04-01T10:00:00+00:00", "tool": "bulk_web_search", "cost_usd": 0.5},
        ])
        recs = ds.load_meta_records("2026-04")
        assert len(recs) == 2

    def test_handles_corrupt_lines(self, meta_log):
        meta_log.parent.mkdir(parents=True, exist_ok=True)
        meta_log.write_text(
            '{"ts": "2026-04-01T00:00:00+00:00", "tool": "x", "cost_usd": 1.0}\n'
            '{invalid json}\n'
            '\n'
            '{"ts": "2026-04-02T00:00:00+00:00", "tool": "y", "cost_usd": 2.0}\n',
            encoding="utf-8",
        )
        recs = ds.load_meta_records("2026-04")
        assert len(recs) == 2


class TestSummarize:
    def test_aggregates_by_tool(self):
        records = [
            {"tool": "gemini_deep_research", "cost_usd": 2.5, "status": "ok"},
            {"tool": "gemini_deep_research", "cost_usd": 2.5, "status": "ok"},
            {"tool": "bulk_x_search", "cost_usd": 0.5, "status": "ok"},
            {"tool": "bulk_x_search", "cost_usd": 0.0, "status": "http_429"},
        ]
        s = ds.summarize(records)
        assert s["total_cost_usd"] == 5.5
        assert s["by_tool"]["gemini_deep_research"]["count"] == 2
        assert s["by_tool"]["gemini_deep_research"]["cost_usd"] == 5.0
        assert s["by_tool"]["bulk_x_search"]["count"] == 2
        assert s["by_tool"]["bulk_x_search"]["errors"] == 1


class TestFormatSummary:
    def test_no_records(self):
        s = ds.summarize([])
        out = ds.format_summary("2026-04", s, 50.0)
        assert "実行記録なし" in out
        assert "$0.00" in out

    def test_warns_at_80_percent(self):
        s = ds.summarize([
            {"tool": "gemini_deep_research", "cost_usd": 42.0, "status": "ok"},
        ])
        out = ds.format_summary("2026-04", s, 50.0)
        assert "月予算 80% 到達" in out

    def test_includes_per_tool_lines(self):
        s = ds.summarize([
            {"tool": "gemini_deep_research", "cost_usd": 2.5, "status": "ok"},
            {"tool": "bulk_x_search", "cost_usd": 0.5, "status": "ok"},
        ])
        out = ds.format_summary("2026-04", s, 50.0)
        assert "gemini_deep_research" in out
        assert "bulk_x_search" in out


class TestActualCostDivergence:
    """KIK-737: estimate vs actual cost reporting."""

    def test_summarize_aggregates_actual_cost(self):
        records = [
            {"tool": "gemini_deep_research", "cost_usd": 2.5,
             "actual_cost_usd": 3.0, "status": "ok"},
            {"tool": "gemini_deep_research", "cost_usd": 2.5,
             "actual_cost_usd": 2.8, "status": "ok"},
        ]
        s = ds.summarize(records)
        assert s["total_actual_cost_usd"] == 5.8
        assert s["by_tool"]["gemini_deep_research"]["actual_cost_usd"] == 5.8

    def test_no_actual_cost_total_zero(self):
        records = [
            {"tool": "bulk_x_search", "cost_usd": 0.5, "status": "ok"},
        ]
        s = ds.summarize(records)
        assert s["total_actual_cost_usd"] == 0.0

    def test_warns_when_divergence_over_20pct(self):
        # Estimate $5.0 vs actual $7.0 → 40% divergence (under-estimate)
        s = ds.summarize([
            {"tool": "gemini_deep_research", "cost_usd": 5.0,
             "actual_cost_usd": 7.0, "status": "ok"},
        ])
        out = ds.format_summary("2026-04", s, 50.0)
        assert "再校正" in out
        assert "過小" in out

    def test_warns_when_estimate_too_high(self):
        # Estimate $10 vs actual $5 → 50% divergence (over-estimate)
        s = ds.summarize([
            {"tool": "gemini_deep_research", "cost_usd": 10.0,
             "actual_cost_usd": 5.0, "status": "ok"},
        ])
        out = ds.format_summary("2026-04", s, 50.0)
        assert "再校正" in out
        assert "過大" in out

    def test_no_warning_within_20pct(self):
        # Estimate $5.0 vs actual $5.5 → 10% divergence (acceptable)
        s = ds.summarize([
            {"tool": "gemini_deep_research", "cost_usd": 5.0,
             "actual_cost_usd": 5.5, "status": "ok"},
        ])
        out = ds.format_summary("2026-04", s, 50.0)
        assert "再校正" not in out
