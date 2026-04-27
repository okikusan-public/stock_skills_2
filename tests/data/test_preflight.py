"""Tests for src.data.preflight (KIK-735)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data.preflight import (
    PreflightError,
    extract_convictions,
    run_preflight,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    header = (
        "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
        "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
    )
    body = "\n".join(
        f"{r['symbol']},{r['shares']},{r['cost_price']},{r.get('cost_currency','JPY')},"
        f",{r.get('memo','')},,,,,,"
        for r in rows
    )
    path.write_text(header + body + "\n", encoding="utf-8")


def _write_cash(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_thesis(notes_dir: Path, symbol: str, content: str,
                  source: str = "manual", date: str = "2026-04-25") -> None:
    fp = notes_dir / f"{date}_{symbol.replace('.', '_')}_thesis.json"
    fp.write_text(
        json.dumps([{
            "id": f"note_{date}_{symbol}",
            "date": date,
            "symbol": symbol,
            "type": "thesis",
            "content": content,
            "source": source,
        }], ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    notes_dir = data_dir / "notes"
    notes_dir.mkdir(parents=True)
    csv_path = data_dir / "portfolio.csv"
    cash_path = data_dir / "cash_balance.json"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "src.data.portfolio_io.DEFAULT_CSV_PATH", str(csv_path),
    )
    monkeypatch.setattr(
        "src.data.portfolio_io.DEFAULT_CASH_PATH", str(cash_path),
    )

    return {
        "notes_dir": notes_dir,
        "csv_path": csv_path,
        "cash_path": cash_path,
    }


# ---------------------------------------------------------------------------
# extract_convictions
# ---------------------------------------------------------------------------


class TestExtractConvictions:
    def test_detects_hold_kakutei(self, env):
        _write_thesis(env["notes_dir"], "7751.T", "【ホールド確定 4/25】売らない")
        convs = extract_convictions(notes_dir=str(env["notes_dir"]))
        assert convs == ["7751.T"]

    def test_detects_user_conviction_source(self, env):
        _write_thesis(
            env["notes_dir"], "AMZN", "強気維持",
            source="user-conviction+3llm",
        )
        convs = extract_convictions(notes_dir=str(env["notes_dir"]))
        assert convs == ["AMZN"]

    def test_no_conviction_returns_empty(self, env):
        _write_thesis(env["notes_dir"], "AAPL", "標準的な thesis")
        assert extract_convictions(notes_dir=str(env["notes_dir"])) == []

    def test_dedupe_multiple_thesis_same_symbol(self, env):
        _write_thesis(
            env["notes_dir"], "7751.T", "ホールド確定 1", date="2026-04-20",
        )
        _write_thesis(
            env["notes_dir"], "7751.T", "ホールド確定 2", date="2026-04-25",
        )
        convs = extract_convictions(notes_dir=str(env["notes_dir"]))
        assert convs == ["7751.T"]


# ---------------------------------------------------------------------------
# run_preflight (PF domain)
# ---------------------------------------------------------------------------


class TestRunPreflightPf:
    def test_valid_pf_passes(self, env):
        _write_csv(env["csv_path"], [
            {"symbol": "7751.T", "shares": 100, "cost_price": 4784.45},
        ])
        _write_cash(env["cash_path"], {"total_jpy": 870_969})
        result = run_preflight(domain="pf", notes_dir=str(env["notes_dir"]))
        assert result["passed"] is True
        assert result["violations"] == []
        assert result["context"]["cash_jpy"] == 870_969
        assert result["context"]["positions_count"] == 1

    def test_missing_cash_total_jpy_fails(self, env):
        _write_csv(env["csv_path"], [
            {"symbol": "AAPL", "shares": 1, "cost_price": 200, "cost_currency": "USD"},
        ])
        _write_cash(env["cash_path"], {"breakdown": {}})
        result = run_preflight(domain="pf", notes_dir=str(env["notes_dir"]))
        assert result["passed"] is False
        assert any("total_jpy" in v for v in result["violations"])

    def test_no_cash_file_fails(self, env):
        _write_csv(env["csv_path"], [
            {"symbol": "AAPL", "shares": 1, "cost_price": 200, "cost_currency": "USD"},
        ])
        # cash_path does not exist
        result = run_preflight(domain="pf", notes_dir=str(env["notes_dir"]))
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# run_preflight (proposed_actions)
# ---------------------------------------------------------------------------


class TestRunPreflightProposedActions:
    def test_lot_size_violation_blocks(self, env):
        _write_csv(env["csv_path"], [])
        _write_cash(env["cash_path"], {"total_jpy": 1_000_000})
        result = run_preflight(
            domain="pf",
            proposed_actions=[("sell", "7203.T", 50)],
            notes_dir=str(env["notes_dir"]),
        )
        assert result["passed"] is False
        assert any("100株単位" in v for v in result["violations"])

    def test_conviction_violation_blocks(self, env):
        _write_csv(env["csv_path"], [])
        _write_cash(env["cash_path"], {"total_jpy": 1_000_000})
        _write_thesis(env["notes_dir"], "7751.T", "【ホールド確定】売らない")
        result = run_preflight(
            domain="pf",
            proposed_actions=[("trim", "7751.T", 100)],
            notes_dir=str(env["notes_dir"]),
        )
        assert result["passed"] is False
        assert any("conviction" in v for v in result["violations"])

    def test_valid_actions_pass(self, env):
        _write_csv(env["csv_path"], [])
        _write_cash(env["cash_path"], {"total_jpy": 1_000_000})
        result = run_preflight(
            domain="pf",
            proposed_actions=[("sell", "AMZN", 5), ("buy", "7203.T", 100)],
            notes_dir=str(env["notes_dir"]),
        )
        assert result["passed"] is True

    def test_invalid_action_format(self, env):
        _write_csv(env["csv_path"], [])
        _write_cash(env["cash_path"], {"total_jpy": 1_000_000})
        result = run_preflight(
            domain="pf",
            proposed_actions=["not-a-tuple"],
            notes_dir=str(env["notes_dir"]),
        )
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# run_preflight (market/sector/stock domains)
# ---------------------------------------------------------------------------


class TestRunPreflightOtherDomains:
    def test_market_domain_emits_warning_only(self, env):
        result = run_preflight(domain="market", notes_dir=str(env["notes_dir"]))
        assert result["passed"] is True
        assert len(result["warnings"]) >= 1

    def test_unknown_domain_fails(self, env):
        result = run_preflight(domain="zzz", notes_dir=str(env["notes_dir"]))
        assert result["passed"] is False
        assert any("unknown domain" in v for v in result["violations"])


# ---------------------------------------------------------------------------
# PreflightError
# ---------------------------------------------------------------------------


class TestPreflightError:
    def test_raises_with_violations(self):
        with pytest.raises(PreflightError) as exc_info:
            raise PreflightError(["v1", "v2"])
        assert exc_info.value.violations == ["v1", "v2"]
        assert "v1" in str(exc_info.value)
