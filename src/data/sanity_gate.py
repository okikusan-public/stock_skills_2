"""Sanity gate for recommendation generation (KIK-734).

Hard assertions that must pass before any agent emits a sell/trim/buy
recommendation. Self-violation must be impossible: the gate raises and
prevents the recommendation from reaching the user.

Three gates:
1. assert_pf_complete  — cash_balance.json must be loaded; total > 0
2. assert_lot_size     — JP/SG/JKT stocks are 100-share lots
3. assert_conviction_respected — conviction symbols cannot receive sell/trim
"""

from __future__ import annotations

from typing import Iterable, Mapping


class SanityGateError(AssertionError):
    """Raised when a sanity gate refuses to let a recommendation through."""


# ---------------------------------------------------------------------------
# Gate 1: PF total assets completeness
# ---------------------------------------------------------------------------


def assert_pf_complete(
    positions_value_jpy: float,
    cash: Mapping | None,
) -> None:
    """Assert PF total assets calculation includes both positions and cash.

    Parameters
    ----------
    positions_value_jpy : float
        株式保有評価額（JPY換算）
    cash : Mapping | None
        cash_balance.json のロード結果。None ならゲート失敗。

    Raises
    ------
    SanityGateError
        cash 未参照、または PF総資産が 0 以下
    """
    if cash is None:
        raise SanityGateError(
            "cash_balance.json が未参照。HC/Risk 起動時の必須入力 (KIK-734)"
        )
    if not isinstance(cash, Mapping) or "total_jpy" not in cash:
        raise SanityGateError(
            "cash 構造が不正: total_jpy が必要 (KIK-734)"
        )
    cash_jpy = float(cash.get("total_jpy") or 0)
    if cash_jpy < 0:
        raise SanityGateError(f"cash 残高が負: {cash_jpy}")
    total = float(positions_value_jpy or 0) + cash_jpy
    if total <= 0:
        raise SanityGateError(f"PF総資産が 0 以下: {total}")


# ---------------------------------------------------------------------------
# Gate 2: Lot size enforcement for non-US stocks
# ---------------------------------------------------------------------------


_LOT_100_SUFFIXES = (".T", ".S", ".SI", ".JK", ".HK", ".KS")


def assert_lot_size(symbol: str, shares: int) -> None:
    """Assert lot size compliance.

    Japan/Singapore/Indonesia/HongKong/Korea stocks: 100-share lots.
    US stocks: 1-share allowed.
    """
    if not symbol:
        raise SanityGateError("symbol が空")
    # KIK-734 review: integer required (float が通り抜けてた)
    if isinstance(shares, bool) or not isinstance(shares, int):
        raise SanityGateError(
            f"{symbol}: shares は int 必須 (got {type(shares).__name__}={shares})"
        )
    if shares <= 0:
        raise SanityGateError(f"{symbol}: shares は正の整数 (got {shares})")
    sym_upper = symbol.upper()
    if any(sym_upper.endswith(s) for s in _LOT_100_SUFFIXES):
        if shares % 100 != 0:
            raise SanityGateError(
                f"{symbol} は 100株単位 (got {shares}). 楽天証券では一部売却不可"
            )


# ---------------------------------------------------------------------------
# Gate 3: Conviction symbol protection
# ---------------------------------------------------------------------------


_SELL_LIKE_ACTIONS = frozenset({"sell", "trim", "exit", "close", "売却", "トリム", "全売却"})


def assert_conviction_respected(
    action: str,
    symbol: str,
    convictions: Iterable[str],
) -> None:
    """Assert conviction symbols never receive sell/trim recommendations.

    Parameters
    ----------
    action : str
        One of buy/hold/sell/trim/exit/close (or 日本語同等)
    symbol : str
        Target ticker
    convictions : Iterable[str]
        Conviction symbol list (loaded from data/notes thesis with conviction marker)
    """
    if not action or not symbol:
        return
    if action.lower() in _SELL_LIKE_ACTIONS or action in _SELL_LIKE_ACTIONS:
        if symbol in set(convictions):
            raise SanityGateError(
                f"{symbol} は conviction 銘柄。{action} 提案禁止 (KIK-734)"
            )


# ---------------------------------------------------------------------------
# Aggregate convenience
# ---------------------------------------------------------------------------


def run_all_gates(
    *,
    positions_value_jpy: float,
    cash: Mapping | None,
    proposed_actions: Iterable[tuple[str, str, int | None]] | None = None,
    convictions: Iterable[str] | None = None,
) -> None:
    """Run all relevant gates.

    Parameters
    ----------
    positions_value_jpy, cash : see assert_pf_complete
    proposed_actions : Iterable of (action, symbol, shares|None)
        Each proposal is checked for lot size and conviction respect.
    convictions : Iterable[str]
        Conviction symbol list.
    """
    assert_pf_complete(positions_value_jpy, cash)
    if proposed_actions:
        conv = list(convictions or [])
        for item in proposed_actions:
            if len(item) == 3:
                action, symbol, shares = item
            elif len(item) == 2:
                action, symbol = item
                shares = None
            else:
                raise SanityGateError(f"proposed_actions の要素形式が不正: {item}")
            if shares is not None:
                assert_lot_size(symbol, shares)
            assert_conviction_respected(action, symbol, conv)


__all__ = [
    "SanityGateError",
    "assert_pf_complete",
    "assert_lot_size",
    "assert_conviction_respected",
    "run_all_gates",
]
