"""Tests for KIK-566 exit-rule note type."""

import pytest
from unittest.mock import patch


class TestParseThreshold:
    def test_percentage(self):
        from src.data.note_manager import _parse_threshold
        assert _parse_threshold("-15%") == -15.0
        assert _parse_threshold("+20%") == 20.0

    def test_full_width(self):
        from src.data.note_manager import _parse_threshold
        assert _parse_threshold("-15％") == -15.0

    def test_plain_number(self):
        from src.data.note_manager import _parse_threshold
        assert _parse_threshold("4100") == 4100.0

    def test_empty(self):
        from src.data.note_manager import _parse_threshold
        assert _parse_threshold("") is None
        assert _parse_threshold(None) is None

    def test_invalid(self):
        from src.data.note_manager import _parse_threshold
        assert _parse_threshold("abc") is None


class TestSaveExitRule:
    def test_saves_with_thresholds(self, tmp_path):
        from src.data.note_manager import save_note

        result = save_note(
            symbol="7751.T",
            note_type="exit-rule",
            content="バリュー株なので-15%損切り、+20%利確",
            stop_loss="-15%",
            take_profit="+20%",
            base_dir=str(tmp_path),
        )
        assert result["type"] == "exit-rule"
        assert result["stop_loss"] == "-15%"
        assert result["take_profit"] == "+20%"
        assert result["symbol"] == "7751.T"

    def test_saves_stop_loss_only(self, tmp_path):
        from src.data.note_manager import save_note

        result = save_note(
            symbol="NFLX",
            note_type="exit-rule",
            content="配当ETFなので利確不要",
            stop_loss="-10%",
            base_dir=str(tmp_path),
        )
        assert result["stop_loss"] == "-10%"
        assert "take_profit" not in result

    def test_exit_rule_category_is_stock(self, tmp_path):
        from src.data.note_manager import save_note

        result = save_note(
            symbol="AAPL",
            note_type="exit-rule",
            content="test",
            stop_loss="-15%",
            base_dir=str(tmp_path),
        )
        assert result["category"] == "stock"


class TestGetExitRules:
    def test_loads_exit_rules(self, tmp_path):
        from src.data.note_manager import save_note, get_exit_rules

        save_note(
            symbol="7751.T", note_type="exit-rule",
            content="test", stop_loss="-15%", take_profit="+20%",
            base_dir=str(tmp_path),
        )
        rules = get_exit_rules(symbol="7751.T", base_dir=str(tmp_path))
        assert len(rules) == 1
        assert rules[0]["stop_loss"] == "-15%"

    def test_empty_when_no_rules(self, tmp_path):
        from src.data.note_manager import get_exit_rules
        assert get_exit_rules(symbol="NONE", base_dir=str(tmp_path)) == []


class TestCheckExitRule:
    def test_stop_loss_hit(self, tmp_path):
        from src.data.note_manager import save_note, check_exit_rule

        save_note(
            symbol="7751.T", note_type="exit-rule",
            content="バリュー株損切り", stop_loss="-15%",
            base_dir=str(tmp_path),
        )
        result = check_exit_rule("7751.T", pnl_pct=-16.0, base_dir=str(tmp_path))
        assert result is not None
        assert result["type"] == "stop_loss"
        assert result["threshold"] == "-15%"

    def test_take_profit_hit(self, tmp_path):
        from src.data.note_manager import save_note, check_exit_rule

        save_note(
            symbol="7751.T", note_type="exit-rule",
            content="利確", take_profit="+20%",
            base_dir=str(tmp_path),
        )
        result = check_exit_rule("7751.T", pnl_pct=25.0, base_dir=str(tmp_path))
        assert result is not None
        assert result["type"] == "take_profit"

    def test_no_hit(self, tmp_path):
        from src.data.note_manager import save_note, check_exit_rule

        save_note(
            symbol="7751.T", note_type="exit-rule",
            content="test", stop_loss="-15%", take_profit="+20%",
            base_dir=str(tmp_path),
        )
        result = check_exit_rule("7751.T", pnl_pct=5.0, base_dir=str(tmp_path))
        assert result is None

    def test_no_rule(self, tmp_path):
        from src.data.note_manager import check_exit_rule
        assert check_exit_rule("NONE", pnl_pct=-50.0, base_dir=str(tmp_path)) is None

    def test_stop_loss_exact_boundary(self, tmp_path):
        from src.data.note_manager import save_note, check_exit_rule

        save_note(
            symbol="X", note_type="exit-rule",
            content="test", stop_loss="-15%",
            base_dir=str(tmp_path),
        )
        # Exactly at boundary → should trigger
        result = check_exit_rule("X", pnl_pct=-15.0, base_dir=str(tmp_path))
        assert result is not None
        assert result["type"] == "stop_loss"


class TestHealthCheckExitRule:
    def test_check_exit_rule_integrates(self, tmp_path):
        """check_exit_rule works as called from health_check."""
        from src.data.note_manager import save_note, check_exit_rule

        save_note(
            symbol="TEST.T", note_type="exit-rule",
            content="test rule", stop_loss="-10%",
            base_dir=str(tmp_path),
        )
        hit = check_exit_rule("TEST.T", pnl_pct=-12.0, base_dir=str(tmp_path))
        assert hit is not None
        assert hit["type"] == "stop_loss"


class TestHealthFormatterExitRule:
    def test_stop_loss_alert_displayed(self):
        from src.output.health_formatter import format_health_check

        pos = {
            "symbol": "7751.T", "name": "Canon", "pnl_pct": -16.5,
            "trend_health": {}, "change_quality": {"quality_label": "-"},
            "alert": {"level": "none", "emoji": "", "label": "なし", "reasons": []},
            "long_term": {"label": "適格", "emoji": "✅"}, "value_trap": {},
            "shareholder_return": {}, "return_stability": {}, "contrarian": None,
            "is_small_cap": False, "size_class": "大型",
            "exit_rule_hit": {
                "type": "stop_loss",
                "threshold": "-15%",
                "reason": "バリュー株損切り",
            },
        }
        health_data = {
            "positions": [pos], "stock_positions": [pos], "etf_positions": [],
            "alerts": [], "summary": {"total": 1, "healthy": 1, "early_warning": 0, "caution": 0, "exit": 0},
            "small_cap_allocation": None, "community_concentration": None,
        }
        output = format_health_check(health_data)
        assert "損切りライン到達" in output
        assert "-15%" in output
        assert "バリュー株損切り" in output

    def test_no_exit_rule_no_section(self):
        from src.output.health_formatter import format_health_check

        pos = {
            "symbol": "A", "name": "A", "pnl_pct": 5,
            "trend_health": {}, "change_quality": {"quality_label": "-"},
            "alert": {"level": "none", "emoji": "", "label": "なし", "reasons": []},
            "long_term": {"label": "適格", "emoji": "✅"}, "value_trap": {},
            "shareholder_return": {}, "return_stability": {}, "contrarian": None,
            "is_small_cap": False, "size_class": "大型",
            "exit_rule_hit": None,
        }
        health_data = {
            "positions": [pos], "stock_positions": [pos], "etf_positions": [],
            "alerts": [], "summary": {"total": 1, "healthy": 1, "early_warning": 0, "caution": 0, "exit": 0},
            "small_cap_allocation": None, "community_concentration": None,
        }
        output = format_health_check(health_data)
        assert "損切りライン" not in output
        assert "利確ライン" not in output
