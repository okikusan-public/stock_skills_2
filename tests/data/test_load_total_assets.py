"""Tests for portfolio_io.load_total_assets / load_cash_balance (KIK-734)."""

from __future__ import annotations

import json

import pytest

from src.data.portfolio_io import (
    load_cash_balance,
    load_total_assets,
)


def _write_csv(path, rows: list[dict]) -> None:
    header = (
        "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
        "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
    )
    body = "\n".join(
        f"{r['symbol']},{r['shares']},{r['cost_price']},{r.get('cost_currency','JPY')},"
        f",{r.get('memo','')},{r.get('next_earnings','')},,,,,{r.get('role','')}"
        for r in rows
    )
    path.write_text(header + body + "\n", encoding="utf-8")


def _write_cash(path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestLoadCashBalance:
    def test_returns_empty_when_missing(self, tmp_path):
        result = load_cash_balance(str(tmp_path / "missing.json"))
        assert result == {}

    def test_returns_dict_when_exists(self, tmp_path):
        cash_path = tmp_path / "cash.json"
        _write_cash(cash_path, {
            "total_jpy": 870_969,
            "breakdown": {"USD": {"amount": 4435.32}, "JPY": {"amount": 233969}},
        })
        result = load_cash_balance(str(cash_path))
        assert result["total_jpy"] == 870_969
        assert result["breakdown"]["USD"]["amount"] == 4435.32


class TestLoadTotalAssets:
    def test_returns_both_positions_and_cash(self, tmp_path):
        csv_path = tmp_path / "portfolio.csv"
        cash_path = tmp_path / "cash.json"
        _write_csv(csv_path, [
            {"symbol": "7751.T", "shares": 100, "cost_price": 4784.45, "role": "長期インカム"},
            {"symbol": "AAPL", "shares": 5, "cost_price": 200.0, "cost_currency": "USD", "role": "グロース"},
        ])
        _write_cash(cash_path, {"total_jpy": 870_969, "breakdown": {}})

        result = load_total_assets(str(csv_path), str(cash_path))
        assert len(result["positions"]) == 2
        assert result["cash"]["total_jpy"] == 870_969
        assert result["cash_jpy"] == 870_969
        assert result["has_cash"] is True

    def test_has_cash_false_when_missing(self, tmp_path):
        csv_path = tmp_path / "portfolio.csv"
        _write_csv(csv_path, [
            {"symbol": "AAPL", "shares": 1, "cost_price": 200.0, "cost_currency": "USD"},
        ])
        result = load_total_assets(str(csv_path), str(tmp_path / "missing.json"))
        assert result["has_cash"] is False
        assert result["cash_jpy"] == 0.0

    def test_empty_portfolio(self, tmp_path):
        csv_path = tmp_path / "portfolio.csv"
        cash_path = tmp_path / "cash.json"
        _write_csv(csv_path, [])
        _write_cash(cash_path, {"total_jpy": 1_000_000})

        result = load_total_assets(str(csv_path), str(cash_path))
        assert result["positions"] == []
        assert result["cash_jpy"] == 1_000_000

    def test_cash_total_jpy_missing_marks_has_cash_false(self, tmp_path):
        """KIK-734 review: cash_balance.json が壊れて total_jpy 欠損の場合、
        has_cash=False で扱う（cash_jpy=0 と整合性を保つ）。"""
        csv_path = tmp_path / "portfolio.csv"
        cash_path = tmp_path / "cash.json"
        _write_csv(csv_path, [])
        _write_cash(cash_path, {"breakdown": {"USD": {"amount": 100}}})

        result = load_total_assets(str(csv_path), str(cash_path))
        assert result["cash_jpy"] == 0.0
        assert result["has_cash"] is False  # total_jpy 欠損 → False
        assert "breakdown" in result["cash"]  # 元 cash dict は保持
