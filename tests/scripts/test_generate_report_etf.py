"""Tests for ETF report output in generate_report.py (KIK-469)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"


def _load_etf_detail():
    with open(FIXTURES_DIR / "etf_detail.json", "r") as f:
        return json.load(f)


def _load_stock_detail():
    with open(FIXTURES_DIR / "stock_detail.json", "r") as f:
        return json.load(f)


@pytest.fixture
def etf_data():
    return _load_etf_detail()


@pytest.fixture
def stock_data():
    return _load_stock_detail()


class TestETFDetection:
    """Test that ETF detection routes to _print_etf_report."""

    def test_etf_detected_by_quote_type(self, etf_data):
        """ETF with quoteType='ETF' should be detected."""
        from src.core.common import is_etf
        assert is_etf(etf_data) is True

    def test_stock_not_detected_as_etf(self, stock_data):
        """Regular stock should not be detected as ETF."""
        from src.core.common import is_etf
        assert is_etf(stock_data) is False


class TestPrintETFReport:
    """Test _print_etf_report output."""

    def test_etf_report_header(self, etf_data, capsys):
        """ETF report should show [ETF] in header."""
        sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "stock-report" / "scripts"))

        with patch("scripts.common.print_context", return_value=None), \
             patch("scripts.common.print_suggestions"):
            from generate_report import _print_etf_report
            _print_etf_report("VGK", etf_data)

        output = capsys.readouterr().out
        assert "[ETF]" in output
        assert "VGK" in output

    def test_etf_report_fund_overview(self, etf_data, capsys):
        """ETF report should have fund overview section."""
        sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "stock-report" / "scripts"))

        with patch("scripts.common.print_context", return_value=None), \
             patch("scripts.common.print_suggestions"):
            from generate_report import _print_etf_report
            _print_etf_report("VGK", etf_data)

        output = capsys.readouterr().out
        assert "ファンド概要" in output
        assert "Europe Stock" in output
        assert "Vanguard" in output

    def test_etf_report_expense_ratio(self, etf_data, capsys):
        """ETF report should show expense ratio evaluation."""
        sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "stock-report" / "scripts"))

        with patch("scripts.common.print_context", return_value=None), \
             patch("scripts.common.print_suggestions"):
            from generate_report import _print_etf_report
            _print_etf_report("VGK", etf_data)

        output = capsys.readouterr().out
        assert "経費率評価" in output
        assert "超低コスト" in output

    def test_etf_report_performance(self, etf_data, capsys):
        """ETF report should have performance section."""
        sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "stock-report" / "scripts"))

        with patch("scripts.common.print_context", return_value=None), \
             patch("scripts.common.print_suggestions"):
            from generate_report import _print_etf_report
            _print_etf_report("VGK", etf_data)

        output = capsys.readouterr().out
        assert "パフォーマンス" in output
        assert "配当利回り" in output

    def test_etf_report_aum_evaluation(self, etf_data, capsys):
        """ETF report should show AUM evaluation."""
        sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "stock-report" / "scripts"))

        with patch("scripts.common.print_context", return_value=None), \
             patch("scripts.common.print_suggestions"):
            from generate_report import _print_etf_report
            _print_etf_report("VGK", etf_data)

        output = capsys.readouterr().out
        assert "ファンド規模" in output
        assert "大規模" in output

    def test_etf_report_high_expense(self, capsys):
        """ETF with high expense ratio should show warning."""
        sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "stock-report" / "scripts"))
        data = _load_etf_detail()
        data["expense_ratio"] = 0.015

        with patch("scripts.common.print_context", return_value=None), \
             patch("scripts.common.print_suggestions"):
            from generate_report import _print_etf_report
            _print_etf_report("ARKK", data)

        output = capsys.readouterr().out
        assert "高コスト" in output

    def test_etf_report_small_aum(self, capsys):
        """ETF with small AUM should show warning."""
        sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "stock-report" / "scripts"))
        data = _load_etf_detail()
        data["total_assets_fund"] = 50_000_000  # $50M

        with patch("scripts.common.print_context", return_value=None), \
             patch("scripts.common.print_suggestions"):
            from generate_report import _print_etf_report
            _print_etf_report("TINY", data)

        output = capsys.readouterr().out
        assert "極小" in output

    def test_etf_report_no_valuation_section(self, etf_data, capsys):
        """ETF report should NOT have PER/PBR valuation section."""
        sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "stock-report" / "scripts"))

        with patch("scripts.common.print_context", return_value=None), \
             patch("scripts.common.print_suggestions"):
            from generate_report import _print_etf_report
            _print_etf_report("VGK", etf_data)

        output = capsys.readouterr().out
        assert "バリュエーション" not in output
        assert "割安度判定" not in output

    def test_etf_report_no_roe(self, etf_data, capsys):
        """ETF report should NOT show ROE."""
        sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "stock-report" / "scripts"))

        with patch("scripts.common.print_context", return_value=None), \
             patch("scripts.common.print_suggestions"):
            from generate_report import _print_etf_report
            _print_etf_report("VGK", etf_data)

        output = capsys.readouterr().out
        assert "ROE" not in output
