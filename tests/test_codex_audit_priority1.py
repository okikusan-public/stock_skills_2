"""Tests for KIK-742 Codex Audit Priority 1 fixes."""

import json
import time
from datetime import date, datetime
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. save_trade.py — ファイル名一意化
# ---------------------------------------------------------------------------


def test_save_trade_filename_unique_for_same_day_same_symbol(tmp_path, monkeypatch):
    """同日同銘柄同タイプで2回呼んでもファイルが衝突しない."""
    from src.data.history.save_trade import save_trade

    base = tmp_path
    today = date.today().isoformat()
    p1 = save_trade(
        symbol="AAPL",
        trade_type="buy",
        shares=10,
        price=150.0,
        currency="USD",
        date_str=today,
        memo="first",
        base_dir=str(base / "history"),
    )
    # わずかに時刻ずらし（同秒回避）
    time.sleep(1.1)
    p2 = save_trade(
        symbol="AAPL",
        trade_type="buy",
        shares=5,
        price=151.0,
        currency="USD",
        date_str=today,
        memo="second",
        base_dir=str(base / "history"),
    )

    assert p1 != p2, "filenames must be unique"
    assert Path(p1).exists()
    assert Path(p2).exists()
    # 両ファイルとも残っている（上書きされない）
    rec1 = json.loads(Path(p1).read_text())
    rec2 = json.loads(Path(p2).read_text())
    assert rec1["memo"] == "first"
    assert rec2["memo"] == "second"


# ---------------------------------------------------------------------------
# 2. session_state.py — date キーフォールバック
# ---------------------------------------------------------------------------


def test_session_state_recognizes_date_key_from_save_trade(tmp_path):
    """save_trade で `date` キーで保存したファイルを recent_trades が拾う."""
    from src.data import session_state

    trade_dir = tmp_path / "data" / "history" / "trade"
    trade_dir.mkdir(parents=True)
    today = date.today().isoformat()
    rec = {
        "category": "trade",
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "symbol": "AAPL",
        "trade_type": "buy",
        "shares": 10,
        "price": 150.0,
        "currency": "USD",
        "memo": "test",
    }
    f = trade_dir / f"{today}_buy_AAPL_120000.json"
    f.write_text(json.dumps(rec))

    result = session_state.reconcile_session_state(
        base_dir=str(tmp_path), trade_window_days=7
    )
    assert f.name in result["recent_trades"]


def test_session_state_legacy_trade_date_still_works(tmp_path):
    """legacy `trade_date` キーでも認識される（後方互換）."""
    from src.data import session_state

    trade_dir = tmp_path / "data" / "history" / "trade"
    trade_dir.mkdir(parents=True)
    today = date.today().isoformat()
    rec = {
        "category": "trade",
        "trade_date": today,  # legacy
        "symbol": "AAPL",
    }
    f = trade_dir / "legacy_trade.json"
    f.write_text(json.dumps(rec))

    result = session_state.reconcile_session_state(
        base_dir=str(tmp_path), trade_window_days=7
    )
    assert f.name in result["recent_trades"]


# ---------------------------------------------------------------------------
# 3. cash_balance.py — 階層形式SSoT
# ---------------------------------------------------------------------------


def test_cash_balance_hierarchical_save_load_roundtrip(tmp_path):
    """階層形式で保存→読込でデータが保たれる."""
    from tools import cash_balance

    path = str(tmp_path / "cash.json")
    payload = {
        "date": "2026-04-29",
        "total_jpy": 1_000_000,
        "breakdown": {
            "USD": {
                "amount": 5934.21,
                "jpy_equivalent": 947634,
                "rate_jpy_per_usd": 159.69,
            },
            "JPY": {"amount": 233969},
        },
    }
    cash_balance.save_cash_balance(payload.copy(), path)
    loaded = cash_balance.load_cash_balance(path)
    assert loaded["total_jpy"] == 1_000_000
    assert loaded["breakdown"]["USD"]["amount"] == 5934.21
    assert "timestamp" in loaded  # save時に自動付与


def test_cash_balance_update_currency_hierarchical(tmp_path):
    """update_currency が階層形式の breakdown に書き込まれる."""
    from tools import cash_balance

    path = str(tmp_path / "cash.json")
    cash_balance.update_currency(
        "USD", 1000.0, path=path,
        jpy_equivalent=159000, rate_jpy_per_usd=159.0,
    )
    data = cash_balance.load_cash_balance(path)
    assert "breakdown" in data
    assert data["breakdown"]["USD"]["amount"] == 1000.0
    assert data["breakdown"]["USD"]["jpy_equivalent"] == 159000
    assert data["breakdown"]["USD"]["rate_jpy_per_usd"] == 159.0


# ---------------------------------------------------------------------------
# 4. portfolio_io.py — 入力バリデーション
# ---------------------------------------------------------------------------


def _empty_portfolio_csv(tmp_path):
    p = tmp_path / "portfolio.csv"
    p.write_text(
        "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
        "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
    )
    return str(p)


def test_add_position_rejects_zero_shares(tmp_path):
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    with pytest.raises(ValueError, match="shares"):
        add_position(csv_path, "AAPL", shares=0, cost_price=100)


def test_add_position_rejects_negative_shares(tmp_path):
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    with pytest.raises(ValueError, match="shares"):
        add_position(csv_path, "AAPL", shares=-5, cost_price=100)


def test_add_position_rejects_zero_cost_price(tmp_path):
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    with pytest.raises(ValueError, match="cost_price"):
        add_position(csv_path, "AAPL", shares=10, cost_price=0)


def test_add_position_rejects_negative_cost_price(tmp_path):
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    with pytest.raises(ValueError, match="cost_price"):
        add_position(csv_path, "AAPL", shares=10, cost_price=-10)


def test_sell_position_rejects_zero_shares(tmp_path):
    from src.data.portfolio_io import add_position, sell_position
    csv_path = _empty_portfolio_csv(tmp_path)
    add_position(csv_path, "AAPL", shares=10, cost_price=100)
    with pytest.raises(ValueError, match="shares"):
        sell_position(csv_path, "AAPL", shares=0)


def test_sell_position_rejects_negative_shares(tmp_path):
    from src.data.portfolio_io import add_position, sell_position
    csv_path = _empty_portfolio_csv(tmp_path)
    add_position(csv_path, "AAPL", shares=10, cost_price=100)
    with pytest.raises(ValueError, match="shares"):
        sell_position(csv_path, "AAPL", shares=-3)


def test_sell_position_rejects_negative_sell_price(tmp_path):
    from src.data.portfolio_io import add_position, sell_position
    csv_path = _empty_portfolio_csv(tmp_path)
    add_position(csv_path, "AAPL", shares=10, cost_price=100)
    with pytest.raises(ValueError, match="sell_price"):
        sell_position(csv_path, "AAPL", shares=5, sell_price=-50)


def test_add_position_normal_path_still_works(tmp_path):
    """正常系（既存テスト相当）."""
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    result = add_position(csv_path, "AAPL", shares=10, cost_price=150.5)
    assert result["shares"] == 10
    assert result["cost_price"] == 150.5
