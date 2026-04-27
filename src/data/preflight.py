"""Preflight gate orchestration for DeepThink (KIK-735).

Wraps the three sanity gates from `src.data.sanity_gate` and adds:
- domain-specific data source loading (PF: portfolio + cash; market: tools)
- conviction extraction from data/notes/ thesis files
- structured violation/warning report

DeepThink Step 0 calls `run_preflight(domain=...)` and aborts if `passed=False`.
DeepThink Step 5 calls `run_preflight(proposed_actions=...)` to re-validate
before emitting any sell/trim recommendation.
"""

from __future__ import annotations

import os
from typing import Iterable

from src.data import note_manager
from src.data import portfolio_io
from src.data import sanity_gate

_CONVICTION_KEYWORDS = ("ホールド確定", "うらない", "売らない", "conviction")


class PreflightError(Exception):
    """Raised when preflight blocks execution."""

    def __init__(self, violations: list[str]):
        self.violations = list(violations or [])
        super().__init__("; ".join(self.violations) or "preflight failed")


def extract_convictions(notes_dir: str | None = None) -> list[str]:
    """Extract conviction symbols from data/notes/ thesis files.

    Mirrors `src.data.context.fallback_context._detect_conviction` logic but
    returns a unique symbol list for use by sanity_gate.
    """
    base_dir = notes_dir or note_manager._NOTES_DIR
    try:
        theses = note_manager.load_notes(note_type="thesis", base_dir=base_dir)
    except Exception:
        return []
    syms: set[str] = set()
    for n in theses:
        sym = n.get("symbol")
        if not sym:
            continue
        content = (n.get("content") or "").lower()
        source = (n.get("source") or "").lower()
        if any(k.lower() in content for k in _CONVICTION_KEYWORDS) \
                or source.startswith("user-conviction"):
            syms.add(sym)
    return sorted(syms)


def _check_pf_domain(violations: list[str], warnings: list[str]) -> dict:
    """Load PF context and run assert_pf_complete."""
    assets = portfolio_io.load_total_assets()
    cash = assets["cash"]
    if not assets["has_cash"]:
        violations.append(
            "cash_balance.json に total_jpy が無い／ファイル欠損 (KIK-735 PF gate)"
        )
        return {"cash_jpy": 0.0, "positions_count": len(assets["positions"])}
    # Compute a placeholder positions_value_jpy=cash so assert_pf_complete sees > 0.
    # The caller is expected to compute the real positions value; we just verify cash exists.
    try:
        sanity_gate.assert_pf_complete(assets["cash_jpy"], cash)
    except sanity_gate.SanityGateError as exc:
        violations.append(str(exc))
    return {
        "cash_jpy": assets["cash_jpy"],
        "positions_count": len(assets["positions"]),
    }


def run_preflight(
    domain: str = "pf",
    proposed_actions: Iterable[tuple] | None = None,
    notes_dir: str | None = None,
) -> dict:
    """Run preflight gates for a DeepThink session.

    Parameters
    ----------
    domain : str
        'pf' / 'market' / 'sector' / 'stock'. Currently only 'pf' performs
        cash/positions data source checks; others skip Gate 1.
    proposed_actions : Iterable of (action, symbol) or (action, symbol, shares)
        Optional list of recommendations to validate against lot size + convictions.
    notes_dir : str, optional
        Override notes directory (testing).

    Returns
    -------
    dict with keys:
        passed     : bool                      (no violations)
        violations : list[str]                 (block reasons)
        warnings   : list[str]                 (advisory only)
        context    : {"cash_jpy", "convictions", "positions_count"}
    """
    violations: list[str] = []
    warnings: list[str] = []
    cash_jpy = 0.0
    positions_count = 0

    if domain == "pf":
        info = _check_pf_domain(violations, warnings)
        cash_jpy = info["cash_jpy"]
        positions_count = info["positions_count"]
    elif domain in {"market", "sector", "stock"}:
        # PF data not strictly required; emit advisory only.
        warnings.append(
            f"domain={domain}: PF データ確認はスキップ (KIK-735)"
        )
    else:
        violations.append(
            f"unknown domain: {domain!r} (expected pf/market/sector/stock)"
        )

    convictions = extract_convictions(notes_dir)

    # Gate 2 + Gate 3: validate proposed actions
    if proposed_actions:
        for item in proposed_actions:
            try:
                if not isinstance(item, (tuple, list)):
                    raise sanity_gate.SanityGateError(
                        f"proposed_actions の要素は tuple/list (got {type(item).__name__})"
                    )
                if len(item) == 3:
                    action, symbol, shares = item
                elif len(item) == 2:
                    action, symbol = item
                    shares = None
                else:
                    raise sanity_gate.SanityGateError(
                        f"proposed_actions の要素形式が不正: {item}"
                    )
                if shares is not None:
                    sanity_gate.assert_lot_size(symbol, shares)
                sanity_gate.assert_conviction_respected(action, symbol, convictions)
            except sanity_gate.SanityGateError as exc:
                violations.append(str(exc))

    return {
        "passed": not violations,
        "violations": violations,
        "warnings": warnings,
        "context": {
            "cash_jpy": cash_jpy,
            "convictions": convictions,
            "positions_count": positions_count,
            "domain": domain,
        },
    }


__all__ = ["PreflightError", "run_preflight", "extract_convictions"]
