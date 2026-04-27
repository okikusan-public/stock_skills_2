"""Tests for src.data.sanity_gate (KIK-734)."""

from __future__ import annotations

import pytest

from src.data.sanity_gate import (
    SanityGateError,
    assert_pf_complete,
    assert_lot_size,
    assert_conviction_respected,
    run_all_gates,
)


# ---------------------------------------------------------------------------
# Gate 1: assert_pf_complete
# ---------------------------------------------------------------------------


class TestAssertPfComplete:
    def test_passes_with_valid_cash(self):
        assert_pf_complete(5_900_000.0, {"total_jpy": 870_969})

    def test_raises_when_cash_is_none(self):
        with pytest.raises(SanityGateError, match="cash_balance.json が未参照"):
            assert_pf_complete(5_900_000.0, None)

    def test_raises_when_cash_missing_total_jpy(self):
        with pytest.raises(SanityGateError, match="total_jpy が必要"):
            assert_pf_complete(5_900_000.0, {"breakdown": {}})

    def test_raises_when_cash_negative(self):
        with pytest.raises(SanityGateError, match="cash 残高が負"):
            assert_pf_complete(5_900_000.0, {"total_jpy": -100})

    def test_raises_when_total_zero_or_negative(self):
        with pytest.raises(SanityGateError, match="PF総資産が 0 以下"):
            assert_pf_complete(0, {"total_jpy": 0})

    def test_passes_with_only_cash(self):
        # 株式ゼロでも現金あれば PASS
        assert_pf_complete(0.0, {"total_jpy": 1_000_000})


# ---------------------------------------------------------------------------
# Gate 2: assert_lot_size
# ---------------------------------------------------------------------------


class TestAssertLotSize:
    def test_jp_100_share_lot_passes(self):
        assert_lot_size("7203.T", 100)
        assert_lot_size("7203.T", 200)

    def test_jp_partial_lot_fails(self):
        with pytest.raises(SanityGateError, match="100株単位"):
            assert_lot_size("7203.T", 50)

    def test_sg_partial_lot_fails(self):
        with pytest.raises(SanityGateError, match="100株単位"):
            assert_lot_size("Z74.SI", 250)

    def test_jkt_partial_lot_fails(self):
        with pytest.raises(SanityGateError, match="100株単位"):
            assert_lot_size("AUTO.JK", 12_750)

    def test_us_single_share_passes(self):
        assert_lot_size("AAPL", 1)
        assert_lot_size("NVDA", 7)

    def test_zero_or_negative_fails(self):
        with pytest.raises(SanityGateError):
            assert_lot_size("AAPL", 0)
        with pytest.raises(SanityGateError):
            assert_lot_size("AAPL", -5)

    def test_empty_symbol_fails(self):
        with pytest.raises(SanityGateError):
            assert_lot_size("", 100)

    def test_float_shares_rejected(self):
        # KIK-734 review: integer 必須
        with pytest.raises(SanityGateError, match="int 必須"):
            assert_lot_size("AAPL", 1.5)
        with pytest.raises(SanityGateError, match="int 必須"):
            assert_lot_size("7203.T", 100.0)

    def test_bool_shares_rejected(self):
        # bool は int の subclass だが shares ではない
        with pytest.raises(SanityGateError, match="int 必須"):
            assert_lot_size("AAPL", True)

    def test_korean_hk_suffix_lots(self):
        # KIK-734 review: .S / .KS / .HK の境界も明示テスト
        with pytest.raises(SanityGateError, match="100株単位"):
            assert_lot_size("005930.KS", 50)
        with pytest.raises(SanityGateError, match="100株単位"):
            assert_lot_size("0700.HK", 250)
        assert_lot_size("005930.KS", 100)
        assert_lot_size("0700.HK", 200)


# ---------------------------------------------------------------------------
# Gate 3: assert_conviction_respected
# ---------------------------------------------------------------------------


class TestAssertConvictionRespected:
    def test_buy_passes_for_conviction(self):
        # buy は conviction 銘柄でも問題なし
        assert_conviction_respected("buy", "7751.T", ["7751.T", "AMZN"])

    def test_hold_passes(self):
        assert_conviction_respected("hold", "7751.T", ["7751.T"])

    def test_sell_conviction_fails(self):
        with pytest.raises(SanityGateError, match="conviction 銘柄"):
            assert_conviction_respected("sell", "7751.T", ["7751.T"])

    def test_trim_conviction_fails(self):
        with pytest.raises(SanityGateError, match="conviction 銘柄"):
            assert_conviction_respected("trim", "7751.T", ["7751.T"])

    def test_jp_action_keyword_blocked(self):
        with pytest.raises(SanityGateError, match="conviction 銘柄"):
            assert_conviction_respected("売却", "7751.T", ["7751.T"])

    def test_non_conviction_sell_passes(self):
        assert_conviction_respected("sell", "AMZN", ["7751.T"])

    def test_empty_convictions_passes(self):
        assert_conviction_respected("sell", "7751.T", [])


# ---------------------------------------------------------------------------
# Aggregate: run_all_gates
# ---------------------------------------------------------------------------


class TestRunAllGates:
    def test_all_pass(self):
        run_all_gates(
            positions_value_jpy=5_900_000,
            cash={"total_jpy": 870_969},
            proposed_actions=[("sell", "AMZN", 10), ("buy", "7203.T", 100)],
            convictions=["7751.T"],
        )

    def test_pf_complete_failure_aborts(self):
        with pytest.raises(SanityGateError):
            run_all_gates(
                positions_value_jpy=5_900_000,
                cash=None,
                proposed_actions=[("sell", "AMZN", 10)],
                convictions=[],
            )

    def test_conviction_violation_aborts(self):
        with pytest.raises(SanityGateError, match="conviction"):
            run_all_gates(
                positions_value_jpy=5_900_000,
                cash={"total_jpy": 870_969},
                proposed_actions=[("trim", "7751.T", 100)],
                convictions=["7751.T"],
            )

    def test_lot_size_violation_aborts(self):
        with pytest.raises(SanityGateError, match="100株単位"):
            run_all_gates(
                positions_value_jpy=5_900_000,
                cash={"total_jpy": 870_969},
                proposed_actions=[("sell", "7203.T", 50)],
                convictions=[],
            )

    def test_no_actions_passes(self):
        # actions=None でも cash check は通る
        run_all_gates(
            positions_value_jpy=5_900_000,
            cash={"total_jpy": 870_969},
        )
