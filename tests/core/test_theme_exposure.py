"""Tests for KIK-604 theme exposure analysis.

Covers: _compute_theme_exposure(), health_formatter theme section,
and graceful degradation when Neo4j is unavailable.
"""

import pytest
from unittest.mock import patch


# ===================================================================
# 1. _compute_theme_exposure basic tests
# ===================================================================


class TestComputeThemeExposure:
    def test_basic_overlap_and_gap(self):
        from src.core.health.theme import _compute_theme_exposure

        positions = [
            {"symbol": "NVDA"},
            {"symbol": "AAPL"},
            {"symbol": "4540.T"},
        ]
        eval_by_symbol = {"NVDA": 5000, "AAPL": 3000, "4540.T": 2000}
        total_value = 10000

        mock_symbol_themes = {
            "NVDA": ["AI", "Semiconductor"],
            "AAPL": ["AI", "Consumer Tech"],
        }
        mock_trending = [
            {"theme": "AI", "stock_count": 15},
            {"theme": "Defense", "stock_count": 8},
            {"theme": "Semiconductor", "stock_count": 6},
            {"theme": "Healthcare", "stock_count": 5},
        ]

        with patch(
            "src.data.graph_query.stock.get_themes_for_symbols_batch",
            return_value=mock_symbol_themes,
        ), patch(
            "src.data.graph_query.market.get_theme_trends",
            return_value=mock_trending,
        ):
            result = _compute_theme_exposure(positions, eval_by_symbol, total_value)

        assert result is not None
        # PF themes
        assert "AI" in result["pf_themes"]
        assert "Semiconductor" in result["pf_themes"]
        assert "Consumer Tech" in result["pf_themes"]
        # AI: NVDA(5000) + AAPL(3000) = 8000 / 10000 = 0.8
        assert result["pf_themes"]["AI"]["weight"] == 0.8
        assert set(result["pf_themes"]["AI"]["symbols"]) == {"NVDA", "AAPL"}
        # Overlap: AI and Semiconductor are both in PF and trending
        assert "AI" in result["overlap"]
        assert "Semiconductor" in result["overlap"]
        # Gap: Defense and Healthcare are trending but not in PF
        gap_themes = [g["theme"] for g in result["gap"]]
        assert "Defense" in gap_themes
        assert "Healthcare" in gap_themes
        assert "AI" not in gap_themes

    def test_no_gap_when_all_covered(self):
        from src.core.health.theme import _compute_theme_exposure

        positions = [{"symbol": "A"}]
        eval_by_symbol = {"A": 10000}

        mock_symbol_themes = {"A": ["AI", "Semiconductor"]}
        mock_trending = [
            {"theme": "AI", "stock_count": 10},
            {"theme": "Semiconductor", "stock_count": 5},
        ]

        with patch(
            "src.data.graph_query.stock.get_themes_for_symbols_batch",
            return_value=mock_symbol_themes,
        ), patch(
            "src.data.graph_query.market.get_theme_trends",
            return_value=mock_trending,
        ):
            result = _compute_theme_exposure(positions, eval_by_symbol, 10000)

        assert result is not None
        assert len(result["gap"]) == 0
        assert sorted(result["overlap"]) == ["AI", "Semiconductor"]

    def test_returns_none_when_no_symbol_themes(self):
        from src.core.health.theme import _compute_theme_exposure

        positions = [{"symbol": "X"}]
        eval_by_symbol = {"X": 1000}

        with patch(
            "src.data.graph_query.stock.get_themes_for_symbols_batch",
            return_value={},
        ), patch(
            "src.data.graph_query.market.get_theme_trends",
            return_value=[],
        ):
            result = _compute_theme_exposure(positions, eval_by_symbol, 1000)

        assert result is None

    def test_returns_none_when_empty_positions(self):
        from src.core.health.theme import _compute_theme_exposure

        with patch(
            "src.data.graph_query.stock.get_themes_for_symbols_batch",
            return_value={},
        ), patch(
            "src.data.graph_query.market.get_theme_trends",
            return_value=[],
        ):
            result = _compute_theme_exposure([], {}, 0)

        assert result is None

    def test_graceful_degradation_on_batch_error(self):
        from src.core.health.theme import _compute_theme_exposure

        positions = [{"symbol": "A"}]

        with patch(
            "src.data.graph_query.stock.get_themes_for_symbols_batch",
            side_effect=Exception("Neo4j error"),
        ):
            result = _compute_theme_exposure(positions, {"A": 1000}, 1000)

        assert result is None

    def test_trending_error_returns_empty_gap(self):
        from src.core.health.theme import _compute_theme_exposure

        positions = [{"symbol": "A"}]
        mock_symbol_themes = {"A": ["AI"]}

        with patch(
            "src.data.graph_query.stock.get_themes_for_symbols_batch",
            return_value=mock_symbol_themes,
        ), patch(
            "src.data.graph_query.market.get_theme_trends",
            side_effect=Exception("Neo4j error"),
        ):
            result = _compute_theme_exposure(positions, {"A": 1000}, 1000)

        assert result is not None
        assert result["gap"] == []
        assert result["trending_themes"] == []

    def test_weight_calculation_with_zero_total(self):
        from src.core.health.theme import _compute_theme_exposure

        positions = [{"symbol": "A"}]
        mock_symbol_themes = {"A": ["AI"]}

        with patch(
            "src.data.graph_query.stock.get_themes_for_symbols_batch",
            return_value=mock_symbol_themes,
        ), patch(
            "src.data.graph_query.market.get_theme_trends",
            return_value=[],
        ):
            result = _compute_theme_exposure(positions, {"A": 0}, 0)

        assert result is not None
        assert result["pf_themes"]["AI"]["weight"] == 0.0

    def test_themes_sorted_by_weight_descending(self):
        from src.core.health.theme import _compute_theme_exposure

        positions = [{"symbol": "A"}, {"symbol": "B"}]
        eval_by_symbol = {"A": 8000, "B": 2000}
        mock_symbol_themes = {
            "A": ["Healthcare"],
            "B": ["AI"],
        }

        with patch(
            "src.data.graph_query.stock.get_themes_for_symbols_batch",
            return_value=mock_symbol_themes,
        ), patch(
            "src.data.graph_query.market.get_theme_trends",
            return_value=[],
        ):
            result = _compute_theme_exposure(positions, eval_by_symbol, 10000)

        theme_names = list(result["pf_themes"].keys())
        # Healthcare (0.8) should come before AI (0.2)
        assert theme_names[0] == "Healthcare"
        assert theme_names[1] == "AI"


# ===================================================================
# 2. Health formatter theme section tests
# ===================================================================


class TestHealthFormatterThemeSection:
    def _make_health_data(self, theme_exposure=None):
        pos = {
            "symbol": "NVDA",
            "name": "NVIDIA",
            "pnl_pct": 10,
            "trend_health": {"trend": "up", "rsi": 55},
            "change_quality": {
                "quality": "good",
                "score": 70,
                "quality_label": "良好",
            },
            "alert": {
                "level": "none",
                "emoji": "",
                "label": "なし",
                "reasons": [],
            },
            "long_term": {"label": "適格", "emoji": ""},
            "value_trap": {},
            "shareholder_return": {},
            "return_stability": {},
            "contrarian": None,
            "is_small_cap": False,
            "size_class": "大型",
        }
        return {
            "positions": [pos],
            "stock_positions": [pos],
            "etf_positions": [],
            "alerts": [],
            "summary": {
                "total": 1,
                "healthy": 1,
                "early_warning": 0,
                "caution": 0,
                "exit": 0,
            },
            "small_cap_allocation": None,
            "community_concentration": None,
            "theme_exposure": theme_exposure,
        }

    def test_theme_section_rendered(self):
        from src.output.health_formatter import format_health_check

        theme_exposure = {
            "pf_themes": {
                "AI": {"symbols": ["NVDA"], "weight": 0.5},
                "Semiconductor": {"symbols": ["NVDA"], "weight": 0.5},
            },
            "trending_themes": [
                {"theme": "AI", "stock_count": 15},
                {"theme": "Defense", "stock_count": 8},
            ],
            "overlap": ["AI"],
            "gap": [{"theme": "Defense", "stock_count": 8}],
        }
        output = format_health_check(self._make_health_data(theme_exposure))
        assert "テーマ構成分析" in output
        assert "PFテーマ構成" in output
        assert "AI" in output
        assert "50.0%" in output
        assert "テーマギャップ" in output
        assert "Defense" in output
        assert "PFに該当銘柄なし" in output

    def test_no_theme_section_when_none(self):
        from src.output.health_formatter import format_health_check

        output = format_health_check(self._make_health_data(None))
        assert "テーマ構成分析" not in output

    def test_no_theme_section_when_empty(self):
        from src.output.health_formatter import format_health_check

        theme_exposure = {
            "pf_themes": {},
            "trending_themes": [],
            "overlap": [],
            "gap": [],
        }
        output = format_health_check(self._make_health_data(theme_exposure))
        assert "テーマ構成分析" not in output

    def test_no_gap_section_when_no_gap(self):
        from src.output.health_formatter import format_health_check

        theme_exposure = {
            "pf_themes": {"AI": {"symbols": ["NVDA"], "weight": 0.5}},
            "trending_themes": [{"theme": "AI", "stock_count": 10}],
            "overlap": ["AI"],
            "gap": [],
        }
        output = format_health_check(self._make_health_data(theme_exposure))
        assert "PFテーマ構成" in output
        assert "テーマギャップ" not in output


# ===================================================================
# 3. get_theme_trends graph query test
# ===================================================================


class TestGetThemeTrends:
    def test_returns_empty_when_no_driver(self):
        from src.data.graph_query.market import get_theme_trends

        with patch("src.data.graph_query._common._get_driver", return_value=None):
            result = get_theme_trends()

        assert result == []

    def test_returns_empty_on_exception(self):
        from src.data.graph_query.market import get_theme_trends

        mock_driver = type("MockDriver", (), {
            "session": lambda self: (_ for _ in ()).throw(Exception("fail")),
        })()

        with patch("src.data.graph_query._common._get_driver", return_value=mock_driver):
            result = get_theme_trends()

        assert result == []
