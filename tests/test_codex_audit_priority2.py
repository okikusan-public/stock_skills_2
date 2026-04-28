"""Tests for KIK-743 Codex Audit Priority 2 fixes."""

import json
import time
from datetime import date
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. yahoo_client/detail.py — try ブロック内変数の未定義参照回避
# ---------------------------------------------------------------------------


def test_yahoo_detail_init_outside_try_blocks():
    """KIK-743: try 外で dividend_paid_history 等が初期化されているソース確認.

    実 API モックは複雑なので、ソース静的検査で初期化位置を担保する。
    """
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src/data/yahoo_client/detail.py"
    text = src.read_text()
    # cashflow ブロックの初期化が try より前にあること
    cf_init = text.find("dividend_paid_history: list[float] = []")
    cf_try = text.find("cf = ticker.cashflow")
    assert 0 < cf_init < cf_try, "dividend_paid_history must be initialized BEFORE cashflow try"
    # ETF 系: expense_ratio = None 初期化と、その後の代入
    etf_init = text.find('expense_ratio: Optional[float] = None')
    # 代入 (型注釈なし) は init より後にある
    etf_assign = text.find('expense_ratio = _safe_get(info, "annualReportExpenseRatio")')
    assert 0 < etf_init < etf_assign, (
        "expense_ratio must be initialized to None BEFORE its try-block assignment"
    )


def test_yahoo_detail_no_remaining_try_only_init():
    """try ブロック内のみで `expense_ratio: Optional` 型注釈付き再代入がないこと."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src/data/yahoo_client/detail.py"
    text = src.read_text()
    # `expense_ratio: Optional[float] = _safe_get` パターンが残っていれば NG
    # (try外初期化 + try内代入 のパターンに変わっていることを確認)
    assert "expense_ratio: Optional[float] = _safe_get" not in text, (
        "expense_ratio should be re-assigned inside try without type annotation"
    )


# ---------------------------------------------------------------------------
# 2. save_report / save_screen / save_research / save_health の同日上書き防止
# ---------------------------------------------------------------------------


def test_save_report_unique_filename(tmp_path):
    from src.data.history.save_report import save_report

    p1 = save_report(
        "AAPL", {"x": 1}, score=0.5, verdict="hold",
        base_dir=str(tmp_path),
    )
    time.sleep(1.1)
    p2 = save_report(
        "AAPL", {"x": 2}, score=0.6, verdict="buy",
        base_dir=str(tmp_path),
    )
    assert p1 != p2
    assert Path(p1).exists() and Path(p2).exists()


def test_save_screening_unique_filename(tmp_path):
    from src.data.history.save_screen import save_screening

    p1 = save_screening(
        "alpha", "us", [{"symbol": "AAPL"}], base_dir=str(tmp_path),
    )
    time.sleep(1.1)
    p2 = save_screening(
        "alpha", "us", [{"symbol": "MSFT"}], base_dir=str(tmp_path),
    )
    assert p1 != p2
    assert Path(p1).exists() and Path(p2).exists()


def test_save_health_unique_filename(tmp_path):
    from src.data.history.save_health import save_health

    health_data = {"summary": {"total": 0, "healthy": 0}, "positions": []}
    p1 = save_health(health_data, base_dir=str(tmp_path))
    time.sleep(1.1)
    p2 = save_health(health_data, base_dir=str(tmp_path))
    assert p1 != p2
    assert Path(p1).exists() and Path(p2).exists()


# ---------------------------------------------------------------------------
# 3. watchlist 形式不整合: list 形式と dict 形式の両方が読める
# ---------------------------------------------------------------------------


def test_fallback_context_reads_list_format_watchlist(tmp_path, monkeypatch):
    """tools/watchlist.py が保存する list 形式 ["AAPL", "MSFT"] を読める."""
    from src.data.context import fallback_context as fc

    wl_dir = tmp_path / "watchlists"
    wl_dir.mkdir()
    (wl_dir / "default.json").write_text(json.dumps(["AAPL", "MSFT"]))

    monkeypatch.setattr(fc, "_WATCHLIST_DIR", str(wl_dir))
    assert fc._is_bookmarked_local("AAPL") is True
    assert fc._is_bookmarked_local("MSFT") is True
    assert fc._is_bookmarked_local("GOOGL") is False


def test_fallback_context_reads_legacy_dict_format(tmp_path, monkeypatch):
    """legacy {"symbols": [...]} 形式も読める（後方互換）."""
    from src.data.context import fallback_context as fc

    wl_dir = tmp_path / "watchlists"
    wl_dir.mkdir()
    (wl_dir / "legacy.json").write_text(
        json.dumps({"symbols": ["AAPL", "MSFT"]})
    )

    monkeypatch.setattr(fc, "_WATCHLIST_DIR", str(wl_dir))
    assert fc._is_bookmarked_local("AAPL") is True
    assert fc._is_bookmarked_local("GOOGL") is False


# ---------------------------------------------------------------------------
# 4. graph_store mode cache reset
# ---------------------------------------------------------------------------


def test_reset_mode_cache_function_exists():
    from src.data.graph_store._common import reset_mode_cache, _mode_cache  # noqa: F401
    # 呼べることを確認
    reset_mode_cache()


def test_mode_cache_reset_clears_cached_value(monkeypatch):
    from src.data.graph_store import _common as gc

    # 一旦 full に設定
    gc._mode_cache = ("full", time.time())
    assert gc._mode_cache[0] == "full"

    gc.reset_mode_cache()
    assert gc._mode_cache == ("", 0.0)
