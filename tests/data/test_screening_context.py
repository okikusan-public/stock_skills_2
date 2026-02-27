"""Tests for src.data.screening_context (KIK-452).

Neo4j driver is mocked — no real database connection needed.
"""

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.no_auto_mock


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(autouse=True)
def reset_driver():
    """Reset global _driver before each test."""
    import src.data.graph_store as gs
    gs._driver = None
    yield
    gs._driver = None


@pytest.fixture
def mock_driver():
    """Provide a mock Neo4j driver with session context manager."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


@pytest.fixture
def ctx_with_driver(mock_driver):
    """Set up graph_store with a mock driver, return screening_context module."""
    import src.data.graph_store as gs
    import src.data.screening_context as sc
    driver, session = mock_driver
    gs._driver = driver
    return sc, driver, session


# ===================================================================
# get_screening_graph_context — graceful degradation
# ===================================================================

class TestGracefulDegradation:
    def test_returns_empty_when_neo4j_unavailable(self):
        """Neo4j unavailable (all graph_query helpers return empty) → has_data=False."""
        from src.data.screening_context import get_screening_graph_context
        # Simulate Neo4j unavailable: all graph_query helpers return empty results
        # (which is what each function does when driver is None)
        with (
            patch("src.data.graph_query.get_industry_research_for_sector", return_value=[]),
            patch("src.data.graph_query.get_sector_catalysts", return_value={}),
            patch("src.data.graph_query.get_notes_for_symbols_batch", return_value={}),
            patch("src.data.graph_query.get_themes_for_symbols_batch", return_value={}),
        ):
            result = get_screening_graph_context(["NVDA"], ["Technology"])
        assert result["has_data"] is False
        assert result["sector_research"] == {}
        assert result["symbol_notes"] == {}
        assert result["symbol_themes"] == {}

    def test_returns_empty_for_empty_inputs(self):
        """Empty symbols and sectors → has_data=False."""
        from src.data.screening_context import get_screening_graph_context
        with (
            patch("src.data.graph_query.get_industry_research_for_sector", return_value=[]),
            patch("src.data.graph_query.get_sector_catalysts", return_value={}),
            patch("src.data.graph_query.get_notes_for_symbols_batch", return_value={}),
            patch("src.data.graph_query.get_themes_for_symbols_batch", return_value={}),
        ):
            result = get_screening_graph_context([], [])
        assert result["has_data"] is False

    def test_returns_empty_when_graph_query_import_fails(self):
        """If graph_query cannot be imported → empty result."""
        import sys
        import src.data.screening_context as sc_mod
        original = sys.modules.pop("src.data.graph_query", None)
        try:
            # Reload screening_context without graph_query available
            import importlib
            with patch.dict("sys.modules", {"src.data.graph_query": None}):
                result = sc_mod.get_screening_graph_context(["NVDA"], ["Technology"])
            # With graph_query patched to None (ImportError), should return empty
        finally:
            if original is not None:
                sys.modules["src.data.graph_query"] = original
        assert result["has_data"] is False


# ===================================================================
# get_screening_graph_context — sector research
# ===================================================================

class TestSectorResearch:
    def test_sector_research_is_populated(self):
        """Sector with catalysts → sector_research entry and has_data=True."""
        from src.data.screening_context import get_screening_graph_context

        research_data = [{"summary": "AI需要拡大", "date": "2026-02-18"}]
        catalysts_data = {
            "positive": ["AI需要増", "設備投資"],
            "negative": ["地政学リスク"],
            "count_positive": 2,
            "count_negative": 1,
            "matched_sector": "Technology",
        }
        with (
            patch("src.data.graph_query.get_industry_research_for_sector", return_value=research_data),
            patch("src.data.graph_query.get_sector_catalysts", return_value=catalysts_data),
            patch("src.data.graph_query.get_notes_for_symbols_batch", return_value={}),
            patch("src.data.graph_query.get_themes_for_symbols_batch", return_value={}),
        ):
            result = get_screening_graph_context(["NVDA"], ["Technology"])

        assert result["has_data"] is True
        assert "Technology" in result["sector_research"]
        sr = result["sector_research"]["Technology"]
        assert "AI需要拡大" in sr["summaries"]
        assert "AI需要増" in sr["catalysts_pos"]
        assert "地政学リスク" in sr["catalysts_neg"]

    def test_empty_sector_is_skipped(self):
        """None or empty string sector is not queried."""
        from src.data.screening_context import get_screening_graph_context

        with (
            patch("src.data.graph_query.get_industry_research_for_sector", return_value=[]) as mock_research,
            patch("src.data.graph_query.get_sector_catalysts", return_value={}) as mock_cats,
            patch("src.data.graph_query.get_notes_for_symbols_batch", return_value={}),
            patch("src.data.graph_query.get_themes_for_symbols_batch", return_value={}),
        ):
            result = get_screening_graph_context(["NVDA"], [None, ""])

        mock_research.assert_not_called()
        mock_cats.assert_not_called()
        assert result["has_data"] is False

    def test_exception_in_sector_loop_is_ignored(self):
        """Exception for one sector does not abort; other sectors proceed."""
        from src.data.screening_context import get_screening_graph_context

        def side_effect_research(sector, days):
            if sector == "BadSector":
                raise RuntimeError("test error")
            return [{"summary": "ok", "date": "2026-02-01"}]

        with (
            patch("src.data.graph_query.get_industry_research_for_sector", side_effect=side_effect_research),
            patch("src.data.graph_query.get_sector_catalysts", return_value={"positive": ["x"], "negative": []}),
            patch("src.data.graph_query.get_notes_for_symbols_batch", return_value={}),
            patch("src.data.graph_query.get_themes_for_symbols_batch", return_value={}),
        ):
            result = get_screening_graph_context(
                ["NVDA", "AAPL"], ["BadSector", "Technology"]
            )

        assert result["has_data"] is True
        assert "BadSector" not in result["sector_research"]
        assert "Technology" in result["sector_research"]


# ===================================================================
# get_screening_graph_context — symbol notes
# ===================================================================

class TestSymbolNotes:
    def test_symbol_notes_are_populated(self):
        """Notes returned from graph_query → symbol_notes and has_data=True."""
        from src.data.screening_context import get_screening_graph_context

        notes_data = {
            "NVDA": [
                {"type": "thesis", "content": "AI長期成長", "date": "2026-01-15"},
                {"type": "concern", "content": "競合増加", "date": "2026-01-20"},
            ]
        }
        with (
            patch("src.data.graph_query.get_industry_research_for_sector", return_value=[]),
            patch("src.data.graph_query.get_sector_catalysts", return_value={}),
            patch("src.data.graph_query.get_notes_for_symbols_batch", return_value=notes_data),
            patch("src.data.graph_query.get_themes_for_symbols_batch", return_value={}),
        ):
            result = get_screening_graph_context(["NVDA"], ["Technology"])

        assert result["has_data"] is True
        assert "NVDA" in result["symbol_notes"]
        assert result["symbol_notes"]["NVDA"][0]["type"] == "thesis"

    def test_symbol_notes_exception_is_ignored(self):
        """Exception in notes lookup does not abort."""
        from src.data.screening_context import get_screening_graph_context

        with (
            patch("src.data.graph_query.get_industry_research_for_sector", return_value=[]),
            patch("src.data.graph_query.get_sector_catalysts", return_value={}),
            patch("src.data.graph_query.get_notes_for_symbols_batch", side_effect=RuntimeError("err")),
            patch("src.data.graph_query.get_themes_for_symbols_batch", return_value={}),
        ):
            result = get_screening_graph_context(["NVDA"], [])

        assert result["symbol_notes"] == {}


# ===================================================================
# get_screening_graph_context — symbol themes
# ===================================================================

class TestSymbolThemes:
    def test_symbol_themes_are_populated(self):
        """Themes returned → symbol_themes and has_data=True."""
        from src.data.screening_context import get_screening_graph_context

        themes_data = {"NVDA": ["AI", "半導体"]}
        with (
            patch("src.data.graph_query.get_industry_research_for_sector", return_value=[]),
            patch("src.data.graph_query.get_sector_catalysts", return_value={}),
            patch("src.data.graph_query.get_notes_for_symbols_batch", return_value={}),
            patch("src.data.graph_query.get_themes_for_symbols_batch", return_value=themes_data),
        ):
            result = get_screening_graph_context(["NVDA"], [])

        assert result["has_data"] is True
        assert result["symbol_themes"]["NVDA"] == ["AI", "半導体"]


# ===================================================================
# _get_themes_for_symbols — internal helper
# ===================================================================

class TestGetThemesForSymbolsBatch:
    """Tests for graph_query.get_themes_for_symbols_batch (KIK-452)."""

    def test_returns_empty_when_driver_none(self):
        import src.data.graph_store as gs
        gs._driver = None
        from src.data.graph_query import get_themes_for_symbols_batch
        assert get_themes_for_symbols_batch(["NVDA"]) == {}

    def test_returns_empty_for_empty_symbols(self):
        from src.data.graph_query import get_themes_for_symbols_batch
        assert get_themes_for_symbols_batch([]) == {}

    def test_returns_themes_from_neo4j(self, ctx_with_driver):
        sc, driver, session = ctx_with_driver
        from src.data.graph_query import get_themes_for_symbols_batch
        record1 = MagicMock()
        record1.__getitem__ = lambda self, k: {"symbol": "NVDA", "themes": ["AI", "半導体"]}[k]
        session.run.return_value = [record1]

        result = get_themes_for_symbols_batch(["NVDA"])
        assert result == {"NVDA": ["AI", "半導体"]}

    def test_exception_returns_empty(self, ctx_with_driver):
        sc, driver, session = ctx_with_driver
        from src.data.graph_query import get_themes_for_symbols_batch
        session.run.side_effect = RuntimeError("neo4j error")
        result = get_themes_for_symbols_batch(["NVDA"])
        assert result == {}
