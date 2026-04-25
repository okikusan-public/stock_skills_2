"""Tests for KIK-719: Local data/ fallback in get_context() when Neo4j is offline.

Verifies that conviction notes (e.g. 7751.T thesis) and PF context can be
constructed from local files only.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data.context.auto_context import get_context
from src.data.context.fallback_context import (
    build_portfolio_context_local,
    build_symbol_context_local,
)


@pytest.fixture
def tmp_data_env(tmp_path, monkeypatch):
    """Set up a temporary data/ structure with notes and portfolio.

    note_manager._NOTES_DIR は "data/notes" 相対パスで、cwd を tmp_path に
    変更して resolve させる。portfolio_io.load_portfolio は明示的にパスを
    受け取らないと DEFAULT_CSV_PATH を使うので、それも tmp_path 配下にセット。
    """
    data_dir = tmp_path / "data"
    notes_dir = data_dir / "notes"
    notes_dir.mkdir(parents=True)
    portfolio_csv = data_dir / "portfolio.csv"
    watchlists_dir = data_dir / "watchlists"
    watchlists_dir.mkdir()
    screening_dir = data_dir / "screening_results"
    screening_dir.mkdir()

    # cwd を切り替えて relative path "data/notes" を resolve させる
    monkeypatch.chdir(tmp_path)
    # portfolio_io / fallback_context の絶対パス参照を上書き
    monkeypatch.setattr(
        "src.data.portfolio_io.DEFAULT_CSV_PATH", str(portfolio_csv),
    )
    monkeypatch.setattr(
        "src.data.context.fallback_context._SCREENING_DIR", str(screening_dir),
    )

    return {
        "notes_dir": notes_dir,
        "portfolio_csv": portfolio_csv,
        "watchlists_dir": watchlists_dir,
        "screening_dir": screening_dir,
    }


def _write_note(notes_dir: Path, symbol: str, ntype: str, content: str,
                date: str = "2026-04-25", source: str = "manual"):
    fp = notes_dir / f"{date}_{symbol.replace('.', '_')}_{ntype}.json"
    fp.write_text(
        json.dumps([{
            "id": f"note_{date}_{symbol}",
            "date": date,
            "symbol": symbol,
            "type": ntype,
            "content": content,
            "source": source,
        }], ensure_ascii=False),
        encoding="utf-8",
    )


def _write_portfolio(csv_path: Path, symbols: list[str]):
    header = (
        "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
        "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
    )
    rows = "\n".join(
        f"{s},100,1000,JPY,2026-01-01,,,,,,," for s in symbols
    )
    csv_path.write_text(header + rows + "\n", encoding="utf-8")


# ===================================================================
# build_symbol_context_local
# ===================================================================

class TestBuildSymbolContextLocal:
    def test_conviction_thesis_detected(self, tmp_data_env):
        """7751.T の thesis に「ホールド確定」 → conviction フラグ立つ."""
        _write_note(
            tmp_data_env["notes_dir"], "7751.T", "thesis",
            "【ホールド確定 4/25】キヤノンは売却しない",
            source="user-conviction+3llm-review",
        )
        _write_portfolio(tmp_data_env["portfolio_csv"], ["7751.T"])

        result = build_symbol_context_local("7751.T")
        assert result is not None
        md = result["context_markdown"]
        assert "conviction" in md.lower() or "ホールド確定" in md
        assert "保有中" in md
        assert result["relationship"] == "保有(conviction)"

    def test_unknown_symbol_returns_none(self, tmp_data_env):
        """notes/portfolio/watchlist/screening にない銘柄 → None."""
        result = build_symbol_context_local("UNKNOWN")
        assert result is None

    def test_held_no_conviction(self, tmp_data_env):
        """保有中だが conviction なし → 通常の保有 relationship."""
        _write_portfolio(tmp_data_env["portfolio_csv"], ["AAPL"])
        result = build_symbol_context_local("AAPL")
        assert result is not None
        assert result["relationship"] == "保有"
        assert result["recommended_skill"] == "health"

    def test_concern_note_detected(self, tmp_data_env):
        """concern メモあり、非保有 → relationship='懸念あり'."""
        _write_note(
            tmp_data_env["notes_dir"], "TSLA", "concern", "需要鈍化",
        )
        result = build_symbol_context_local("TSLA")
        assert result is not None
        assert result["relationship"] == "懸念あり"
        assert "concern" in result["context_markdown"]

    def test_screening_history_detected(self, tmp_data_env):
        """screening_results に 3 回以上出現 → 注目銘柄."""
        for i in range(3):
            fp = tmp_data_env["screening_dir"] / f"trending_us_2026{i:02d}.json"
            fp.write_text(
                json.dumps({"results": [{"symbol": "NVDA", "score": 90}]}),
                encoding="utf-8",
            )
        result = build_symbol_context_local("NVDA")
        assert result is not None
        assert result["relationship"] == "注目銘柄"
        assert "スクリーニング履歴: 3件" in result["context_markdown"]

    def test_screening_below_threshold_returns_unknown(self, tmp_data_env):
        """screening_results 1-2 件 → threshold 未満で未知扱い."""
        for i in range(2):
            fp = tmp_data_env["screening_dir"] / f"x_{i}.json"
            fp.write_text(
                json.dumps({"results": [{"symbol": "TSLA", "score": 80}]}),
                encoding="utf-8",
            )
        result = build_symbol_context_local("TSLA")
        # 2 件のみで他に signal なし → relationship は「未知」（screen_countは含まれる）
        assert result is not None
        assert result["relationship"] == "未知"

    def test_conviction_keyword_uppercase(self, tmp_data_env):
        """大文字 'CONVICTION' でも検出される（case-insensitive）."""
        _write_note(
            tmp_data_env["notes_dir"], "AAPL", "thesis",
            "Strong CONVICTION buy thesis",
        )
        _write_portfolio(tmp_data_env["portfolio_csv"], ["AAPL"])
        result = build_symbol_context_local("AAPL")
        assert result is not None
        assert result["relationship"] == "保有(conviction)"

    def test_screening_with_broken_json(self, tmp_data_env):
        """screening_results に JSON 破損ファイル → skip して続行."""
        (tmp_data_env["screening_dir"] / "broken.json").write_text(
            "{invalid json", encoding="utf-8",
        )
        # Should not crash, just skip the broken file
        _write_portfolio(tmp_data_env["portfolio_csv"], ["NVDA"])
        result = build_symbol_context_local("NVDA")
        assert result is not None  # found via portfolio


# ===================================================================
# build_portfolio_context_local
# ===================================================================

class TestBuildPortfolioContextLocal:
    def test_empty_portfolio(self, tmp_data_env):
        """portfolio.csv が空 → 空のコンテキスト返す."""
        _write_portfolio(tmp_data_env["portfolio_csv"], [])
        result = build_portfolio_context_local()
        assert result["recommended_skill"] == "health"
        assert "保有銘柄" not in result["context_markdown"]

    def test_with_holdings(self, tmp_data_env):
        """保有銘柄数 + 重要メモが含まれる."""
        _write_portfolio(tmp_data_env["portfolio_csv"], ["7751.T", "NFLX"])
        _write_note(
            tmp_data_env["notes_dir"], "7751.T", "thesis",
            "ホールド確定",
        )
        result = build_portfolio_context_local()
        md = result["context_markdown"]
        assert "保有銘柄: 2件" in md
        assert "[7751.T] thesis" in md


# ===================================================================
# get_context() integration with fallback
# ===================================================================

class TestGetContextLocalFallback:
    @patch("src.data.context.auto_context._vector_search", return_value=[])
    @patch("src.data.context.auto_context.graph_store")
    def test_symbol_falls_back_to_local(self, mock_gs, mock_vs, tmp_data_env):
        """Neo4j 未接続 → ローカル data/ から conviction 銘柄を読む."""
        mock_gs._get_driver.return_value = None
        mock_gs.is_available.return_value = False

        _write_note(
            tmp_data_env["notes_dir"], "7751.T", "thesis",
            "【ホールド確定】売らない",
            source="user-conviction",
        )
        _write_portfolio(tmp_data_env["portfolio_csv"], ["7751.T"])

        result = get_context("7751.T")
        assert result is not None
        assert "ホールド確定" in result["context_markdown"]

    @patch("src.data.context.auto_context._load_lessons", return_value=[])
    @patch("src.data.context.auto_context._vector_search", return_value=[])
    @patch("src.data.context.auto_context.graph_store")
    def test_pf_query_falls_back_to_local(self, mock_gs, mock_vs, mock_les,
                                            tmp_data_env):
        """Neo4j 未接続 → ローカル data/ から PF コンテキストを組み立てる."""
        mock_gs._get_driver.return_value = None
        mock_gs.is_available.return_value = False

        _write_portfolio(
            tmp_data_env["portfolio_csv"], ["AAPL", "MSFT"],
        )
        _write_note(
            tmp_data_env["notes_dir"], "AAPL", "thesis", "AI需要継続",
        )

        result = get_context("PF大丈夫？")
        assert result is not None
        md = result["context_markdown"]
        assert "保有銘柄: 2件" in md
        assert "[AAPL]" in md
