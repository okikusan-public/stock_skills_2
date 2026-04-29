"""Mocked E2E tests (KIK-747).

LLM API / Yahoo Finance / Grok を全て stub化し、決定論的に
agent.md / examples.yaml / orchestrator の挙動を検証する。

利用方針:
- agent.md / examples.yaml / routing.yaml は実物を使う
- 外部I/Oだけstub（tools/llm.py, tools/grok.py, tools/yahoo_finance.py）
- 個人PFは触らない（tests/fixtures/sample_portfolio.csv を利用、KIK-745）
- 全シナリオ10秒以内、API key 全削除環境でも PASS
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_PORTFOLIO = REPO_ROOT / "tests/fixtures/sample_portfolio.csv"
SAMPLE_CASH = REPO_ROOT / "tests/fixtures/sample_cash_balance.json"
STOCK_INFO_FIXTURE = REPO_ROOT / "tests/fixtures/stock_info.json"
STOCK_DETAIL_FIXTURE = REPO_ROOT / "tests/fixtures/stock_detail.json"


# ---------------------------------------------------------------------------
# Mock fixtures (autouse for this module)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mocked_e2e_env(monkeypatch, tmp_path):
    """Stub LLM / Yahoo Finance / Grok and disable real API keys.

    既存の `_block_external_io` (conftest.py) は Neo4j/TEI/Grok を扱うため、
    ここでは追加で LLM と Yahoo Finance を stub する。
    """
    # 1) API keys 削除（実呼び出しを物理的に防ぐ最終防衛線）
    for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    # 2) LLM stub
    def _stub_call_llm(provider, model, prompt, **kwargs):
        return f"[mock:{provider}] {prompt[:50]}... → 推奨: 7203.T (PER 10.5)"

    monkeypatch.setattr("tools.llm.call_llm", _stub_call_llm)

    # 3) Yahoo Finance stub: fixturesから返す
    stock_info = json.loads(STOCK_INFO_FIXTURE.read_text())
    stock_detail = json.loads(STOCK_DETAIL_FIXTURE.read_text())

    def _stub_get_stock_info(symbol):
        d = dict(stock_info)
        d["symbol"] = symbol
        return d

    def _stub_get_stock_detail(symbol):
        d = dict(stock_detail)
        d["symbol"] = symbol
        return d

    def _stub_screen_stocks(query=None, max_results=10):
        return [
            {"symbol": "7203.T", "shortName": "Toyota Motor",
             "trailingPE": 10.5, "exchange": "JPX"},
            {"symbol": "6758.T", "shortName": "Sony Group",
             "trailingPE": 18.2, "exchange": "JPX"},
        ][:max_results]

    def _stub_get_price_history(symbol, period="3mo"):
        import pandas as pd
        # 簡易な上昇トレンド系列
        prices = [2500 + i * 5 for i in range(60)]
        return pd.DataFrame({
            "Open": prices,
            "High": [p + 10 for p in prices],
            "Low": [p - 10 for p in prices],
            "Close": prices,
            "Volume": [1_000_000] * 60,
        })

    def _stub_get_macro_indicators():
        return {"VIX": 18.5, "USDJPY": 159.0, "BTC": 95000}

    monkeypatch.setattr("tools.yahoo_finance.get_stock_info", _stub_get_stock_info)
    monkeypatch.setattr("tools.yahoo_finance.get_stock_detail", _stub_get_stock_detail)
    monkeypatch.setattr("tools.yahoo_finance.screen_stocks", _stub_screen_stocks)
    monkeypatch.setattr("tools.yahoo_finance.get_price_history", _stub_get_price_history)
    monkeypatch.setattr("tools.yahoo_finance.get_macro_indicators", _stub_get_macro_indicators)

    # 4) Grok stub
    def _stub_search_market(query):
        return {
            "summary": f"[mock] {query} の市況: 中立",
            "macro_factors": ["金利据え置き", "VIX 18.5"],
            "sentiment": {"score": 0.0, "summary": "neutral"},
        }

    def _stub_search_x_sentiment(symbol, name):
        return {
            "score": 0.3,
            "summary": f"[mock] {symbol} centiment: 強気優勢",
            "positive": ["EPS成長"],
            "negative": ["高PER"],
        }

    monkeypatch.setattr("tools.grok.search_market", _stub_search_market, raising=False)
    monkeypatch.setattr("tools.grok.search_x_sentiment", _stub_search_x_sentiment, raising=False)

    # 5) sample fixtures を data/ にコピー（agent が直接 data/ を読むケース対策）
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "portfolio.csv").write_text(SAMPLE_PORTFOLIO.read_text())
    (data_dir / "cash_balance.json").write_text(SAMPLE_CASH.read_text())
    monkeypatch.setenv("STOCK_SKILLS_DATA_DIR", str(data_dir))


# ---------------------------------------------------------------------------
# Scenario tests (シナリオ単位の挙動検証)
# ---------------------------------------------------------------------------


def test_scenario_screener_routing():
    """e2e_001: 「いい日本株ある？」 → screener にルーティングし期待ツールが出る."""
    from src.orchestrator import verify_routing
    r = verify_routing("いい日本株ある？")
    assert r.passed
    assert r.agents == ["screener"]
    assert any("screen" in t for t in r.expected_tools)


def test_scenario_screener_yahoo_call_returns_mocked_data():
    """screener が呼ぶ screen_stocks が mock 応答を返すこと."""
    from tools.yahoo_finance import screen_stocks
    result = screen_stocks(max_results=5)
    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0]["symbol"] == "7203.T"


def test_scenario_analyst_routing_and_data():
    """e2e_002: 「トヨタってどう？」 → analyst + stock_info取得."""
    from src.orchestrator import verify_routing
    from tools.yahoo_finance import get_stock_info, get_stock_detail

    r = verify_routing("トヨタってどう？")
    assert r.passed
    assert r.agents == ["analyst"]

    info = get_stock_info("7203.T")
    detail = get_stock_detail("7203.T")
    assert info["symbol"] == "7203.T"
    # PER等の主要指標が含まれる（fixture経由）
    assert "per" in info or "trailingPE" in info


def test_scenario_health_checker_uses_sample_portfolio():
    """e2e_003: PF確認系で sample_portfolio が読み込まれる."""
    from src.data.portfolio_io import load_portfolio
    positions = load_portfolio(str(SAMPLE_PORTFOLIO))
    assert len(positions) >= 5
    symbols = [p["symbol"] for p in positions]
    assert "AAPL" in symbols  # sample fixture の銘柄
    # 個人PF銘柄は含まれない
    assert all(s not in symbols for s in ("9856.T",))  # ケーユーHD等は sample に無し


def test_scenario_researcher_grok_returns_mock():
    """e2e_004: researcher の grok 呼び出しが mock 応答を返す."""
    from tools.grok import search_market

    result = search_market("日本株市況")
    assert "[mock]" in result["summary"]
    assert "sentiment" in result


def test_scenario_strategist_chain_routing():
    """e2e_006: 「PFを改善したい」が連鎖（HC→strategist）にルーティング."""
    from src.orchestrator import verify_routing
    r = verify_routing("PFを改善したい")
    assert r.passed
    assert "health-checker" in r.agents
    assert "strategist" in r.agents
    # history_check フラグが立つ（KIK-740）
    assert r.flags.get("history_check") is True


def test_scenario_sell_decision_with_history_check():
    """e2e_007: 「この株売るべき？」で history_check + review が立つ."""
    from src.orchestrator import verify_routing
    r = verify_routing("この株売るべき？")
    assert r.passed
    assert r.flags.get("history_check") is True
    assert r.flags.get("review") is True
    # 3エージェント連鎖（risk-assessor → HC → strategist）
    assert len(r.agents) == 3


# ---------------------------------------------------------------------------
# Smoke tests (即時 PASS でCIの sanity check として使える)
# ---------------------------------------------------------------------------


def test_no_api_keys_present():
    """API keys が削除されていること（fixture の効力確認）."""
    for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY"):
        assert os.environ.get(k) is None, f"{k} should be removed by fixture"


def test_llm_stub_returns_mock_string():
    """tools.llm.call_llm が stub 応答を返す."""
    from tools.llm import call_llm
    result = call_llm("gpt", "gpt-5.5", "test prompt")
    assert "[mock:gpt]" in result
