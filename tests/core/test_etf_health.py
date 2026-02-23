"""Tests for check_etf_health() in health_check.py (KIK-469)."""

import pytest

from src.core.health_check import check_etf_health


class TestExpenseRatioEvaluation:
    """Test expense ratio classification."""

    def test_ultra_low_cost(self):
        """Expense ratio <= 0.1% should be ultra low cost."""
        result = check_etf_health({"expense_ratio": 0.0009, "total_assets_fund": 1e10})
        assert result["expense_label"] == "超低コスト"
        assert len(result["alerts"]) == 0

    def test_low_cost(self):
        """Expense ratio 0.1-0.5% should be low cost."""
        result = check_etf_health({"expense_ratio": 0.003, "total_assets_fund": 1e10})
        assert result["expense_label"] == "低コスト"
        assert len(result["alerts"]) == 0

    def test_somewhat_high(self):
        """Expense ratio 0.5-1.0% should be somewhat high."""
        result = check_etf_health({"expense_ratio": 0.007, "total_assets_fund": 1e10})
        assert result["expense_label"] == "やや高め"
        assert any("やや高め" in a for a in result["alerts"])

    def test_high_cost(self):
        """Expense ratio > 1.0% should be high cost."""
        result = check_etf_health({"expense_ratio": 0.015, "total_assets_fund": 1e10})
        assert result["expense_label"] == "高コスト"
        assert any("高コスト" in a for a in result["alerts"])

    def test_none_expense_ratio(self):
        """None expense ratio should return '-'."""
        result = check_etf_health({"expense_ratio": None, "total_assets_fund": 1e10})
        assert result["expense_label"] == "-"

    def test_boundary_0001(self):
        """Expense ratio exactly 0.1% should be ultra low cost."""
        result = check_etf_health({"expense_ratio": 0.001, "total_assets_fund": 1e10})
        assert result["expense_label"] == "超低コスト"

    def test_boundary_0005(self):
        """Expense ratio exactly 0.5% should be low cost."""
        result = check_etf_health({"expense_ratio": 0.005, "total_assets_fund": 1e10})
        assert result["expense_label"] == "低コスト"

    def test_boundary_001(self):
        """Expense ratio exactly 1.0% should be somewhat high."""
        result = check_etf_health({"expense_ratio": 0.01, "total_assets_fund": 1e10})
        assert result["expense_label"] == "やや高め"


class TestAUMEvaluation:
    """Test AUM (total assets fund) classification."""

    def test_large_aum(self):
        """AUM >= $1B should be sufficient."""
        result = check_etf_health({"expense_ratio": 0.001, "total_assets_fund": 5e9})
        assert result["aum_label"] == "十分"
        assert not any("AUM" in a for a in result["alerts"])

    def test_small_aum(self):
        """AUM $100M-$1B should be small."""
        result = check_etf_health({"expense_ratio": 0.001, "total_assets_fund": 5e8})
        assert result["aum_label"] == "小規模"
        assert any("AUM小規模" in a for a in result["alerts"])

    def test_tiny_aum(self):
        """AUM < $100M should be extremely small."""
        result = check_etf_health({"expense_ratio": 0.001, "total_assets_fund": 5e7})
        assert result["aum_label"] == "極小"
        assert any("AUM極小" in a for a in result["alerts"])

    def test_none_aum(self):
        """None AUM should return '-'."""
        result = check_etf_health({"expense_ratio": 0.001, "total_assets_fund": None})
        assert result["aum_label"] == "-"


class TestETFScore:
    """Test ETF score calculation."""

    def test_perfect_score(self):
        """Ultra low cost + large AUM = 100."""
        result = check_etf_health({"expense_ratio": 0.0005, "total_assets_fund": 20e9})
        assert result["score"] == 100  # 50 + 25 + 25

    def test_good_score(self):
        """Low cost + large AUM = 90."""
        result = check_etf_health({"expense_ratio": 0.003, "total_assets_fund": 20e9})
        assert result["score"] == 90  # 50 + 15 + 25

    def test_medium_score(self):
        """Low cost + medium AUM = 80."""
        result = check_etf_health({"expense_ratio": 0.003, "total_assets_fund": 5e9})
        assert result["score"] == 80  # 50 + 15 + 15

    def test_baseline_score(self):
        """Somewhat high cost + medium AUM = 65."""
        result = check_etf_health({"expense_ratio": 0.007, "total_assets_fund": 5e9})
        assert result["score"] == 65  # 50 + 0 + 15

    def test_poor_score(self):
        """High cost + tiny AUM = 20."""
        result = check_etf_health({"expense_ratio": 0.02, "total_assets_fund": 5e7})
        assert result["score"] == 20  # 50 - 15 - 15

    def test_score_clamped_at_0(self):
        """Score should not go below 0."""
        result = check_etf_health({"expense_ratio": 0.05, "total_assets_fund": 1e6})
        assert result["score"] >= 0

    def test_score_clamped_at_100(self):
        """Score should not go above 100."""
        result = check_etf_health({"expense_ratio": 0.0001, "total_assets_fund": 100e9})
        assert result["score"] <= 100

    def test_no_data_score(self):
        """No expense ratio and no AUM = baseline 50."""
        result = check_etf_health({})
        assert result["score"] == 50


class TestETFHealthMetadata:
    """Test metadata fields in ETF health."""

    def test_fund_category_returned(self):
        """fund_category from input should be returned."""
        result = check_etf_health({"fund_category": "Europe Stock"})
        assert result["fund_category"] == "Europe Stock"

    def test_fund_family_returned(self):
        """fund_family from input should be returned."""
        result = check_etf_health({"fund_family": "Vanguard"})
        assert result["fund_family"] == "Vanguard"

    def test_expense_ratio_passthrough(self):
        """Raw expense_ratio should be returned."""
        result = check_etf_health({"expense_ratio": 0.0009})
        assert result["expense_ratio"] == 0.0009

    def test_aum_passthrough(self):
        """Raw AUM should be returned."""
        result = check_etf_health({"total_assets_fund": 20e9})
        assert result["aum"] == 20e9

    def test_info_nested_access(self):
        """Should also work when data is nested under 'info' key."""
        data = {"info": {"expense_ratio": 0.001, "total_assets_fund": 5e9, "fund_category": "Bond"}}
        result = check_etf_health(data)
        assert result["expense_label"] == "超低コスト"
        assert result["fund_category"] == "Bond"


class TestETFHealthIntegration:
    """Test check_etf_health integration with check_change_quality and check_long_term_suitability."""

    def test_change_quality_etf_has_etf_health(self, etf_detail_data):
        """check_change_quality should include etf_health for ETFs."""
        from src.core.health_check import check_change_quality

        result = check_change_quality(etf_detail_data)
        assert result["is_etf"] is True
        assert result["quality_label"] == "対象外"
        assert "etf_health" in result
        assert result["etf_health"]["expense_label"] == "超低コスト"

    def test_long_term_suitability_etf_has_etf_health(self, etf_detail_data):
        """check_long_term_suitability should include etf_health for ETFs."""
        from src.core.health_check import check_long_term_suitability

        result = check_long_term_suitability(etf_detail_data)
        assert result["label"] == "対象外"
        assert result["summary"] == "ETF"
        assert "etf_health" in result
        assert result["etf_health"]["score"] == 100  # ultra low cost + large AUM

    def test_long_term_suitability_etf_score_reflects_etf_health(self, etf_detail_data):
        """ETF long-term score should use etf_health score instead of 0."""
        from src.core.health_check import check_long_term_suitability

        result = check_long_term_suitability(etf_detail_data)
        # VGK: expense_ratio=0.0009 (ultra low: +25) + AUM=20B (large: +25) = 100
        assert result["score"] == 100

    def test_change_quality_stock_no_etf_health(self, stock_detail_data):
        """check_change_quality should NOT include etf_health for regular stocks."""
        from src.core.health_check import check_change_quality

        result = check_change_quality(stock_detail_data)
        assert result["is_etf"] is False
        assert "etf_health" not in result
