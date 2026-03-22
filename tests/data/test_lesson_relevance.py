"""Tests for KIK-569 lesson relevance selection and community lessons."""

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.no_auto_mock


@pytest.fixture(autouse=True)
def reset_driver():
    import src.data.graph_store as gs
    gs._driver = None
    yield
    gs._driver = None


# ===================================================================
# Phase 1: _select_relevant_lessons
# ===================================================================


class TestSelectRelevantLessons:
    def test_symbol_match_boosts_relevance(self):
        from src.data.context.auto_context import _select_relevant_lessons

        lessons = [
            {"trigger": "金利上昇", "expected_action": "債券売り", "symbol": "", "content": "金利注意"},
            {"trigger": "高値掴み", "expected_action": "RSI確認", "symbol": "NVDA", "content": ""},
            {"trigger": "パニック売り", "expected_action": "冷静に", "symbol": "", "content": ""},
        ]
        result = _select_relevant_lessons(lessons, "NVDAどう？")
        # NVDA lesson should be first due to symbol match
        assert result[0]["symbol"] == "NVDA"

    def test_trigger_keyword_match(self):
        from src.data.context.auto_context import _select_relevant_lessons

        lessons = [
            {"trigger": "金利上昇時", "expected_action": "債券比率下げ", "symbol": "", "content": ""},
            {"trigger": "RSI高値掴み", "expected_action": "買わない", "symbol": "", "content": ""},
        ]
        result = _select_relevant_lessons(lessons, "金利が上がってきたけど")
        assert "金利" in result[0]["trigger"]

    def test_limits_to_max_results(self):
        from src.data.context.auto_context import _select_relevant_lessons

        lessons = [{"trigger": f"trigger{i}", "expected_action": f"act{i}",
                     "symbol": "", "content": ""} for i in range(20)]
        result = _select_relevant_lessons(lessons, "test", max_results=5)
        assert len(result) == 5

    def test_empty_input_returns_top_n(self):
        from src.data.context.auto_context import _select_relevant_lessons

        lessons = [
            {"trigger": "a", "expected_action": "b", "symbol": "", "content": ""},
            {"trigger": "c", "expected_action": "d", "symbol": "", "content": ""},
        ]
        result = _select_relevant_lessons(lessons, "")
        assert len(result) == 2

    def test_empty_lessons(self):
        from src.data.context.auto_context import _select_relevant_lessons

        result = _select_relevant_lessons([], "test")
        assert result == []

    def test_no_trigger_still_works(self):
        from src.data.context.auto_context import _select_relevant_lessons

        lessons = [
            {"trigger": "", "expected_action": "", "symbol": "", "content": "NVDA関連の学び"},
        ]
        result = _select_relevant_lessons(lessons, "NVDAを調べて")
        assert len(result) == 1


# ===================================================================
# Phase 2: get_community_lessons
# ===================================================================


class TestGetCommunityLessons:
    def test_returns_empty_no_driver(self):
        from src.data.graph_query.community import get_community_lessons

        with patch("src.data.graph_store._get_driver", return_value=None):
            assert get_community_lessons("NVDA") == []

    def test_returns_lessons_with_source(self):
        from src.data.graph_query.community import get_community_lessons
        import src.data.graph_store as gs

        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)

        r1 = MagicMock()
        r1.__getitem__ = lambda s, k: {
            "content": "セクター固定観念バイアスの教訓",
            "trigger": "セクター平均PERで判断",
            "expected_action": "個別企業を見る",
            "date": "2026-02-28",
            "id": "note_001",
            "source_symbol": "CEG",
            "community_name": "Technology",
        }[k]
        session.run.return_value = iter([r1])
        gs._driver = driver

        result = get_community_lessons("NVDA")
        assert len(result) == 1
        assert result[0]["_source_symbol"] == "CEG"
        assert result[0]["_community"] == "Technology"
        assert "CEG" in result[0]["symbol"]

    def test_graceful_on_error(self):
        from src.data.graph_query.community import get_community_lessons
        import src.data.graph_store as gs

        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)
        session.run.side_effect = Exception("db error")
        gs._driver = driver

        result = get_community_lessons("NVDA")
        assert result == []


# ===================================================================
# Integration: _append_lessons with user_input
# ===================================================================


class TestAppendLessonsWithInput:
    def test_relevant_lesson_selected(self):
        """Lessons related to user input should be prioritized."""
        from src.data.context.auto_context import _select_relevant_lessons

        lessons = [
            {"id": "a", "trigger": "VIX上昇", "expected_action": "様子見", "symbol": "", "content": "", "date": "2026-03-01"},
            {"id": "b", "trigger": "高値掴み", "expected_action": "RSI確認", "symbol": "", "content": "", "date": "2026-03-15"},
            {"id": "c", "trigger": "金利上昇", "expected_action": "債券比率下げ", "symbol": "", "content": "", "date": "2026-03-10"},
        ]
        result = _select_relevant_lessons(lessons, "VIXが上がってきた")
        # VIX lesson should be first
        assert result[0]["trigger"] == "VIX上昇"

    @patch("src.data.auto_context._load_lessons")
    @patch("src.data.auto_context._load_community_lessons")
    @patch("src.data.auto_context._check_bookmarked")
    @patch("src.data.auto_context.graph_store")
    def test_community_lesson_included(self, mock_gs, mock_bm, mock_comm, mock_load):
        from src.data.context.auto_context import get_context

        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = {}
        mock_gs.is_held.return_value = False
        mock_bm.return_value = False
        mock_load.return_value = []
        mock_comm.return_value = [{
            "id": "comm1",
            "trigger": "セクター固定観念",
            "expected_action": "個別企業を見る",
            "symbol": "CEG→Technology",
            "content": "peer lesson",
            "date": "2026-02-28",
            "_source_symbol": "CEG",
            "_community": "Technology",
        }]

        result = get_context("NVDAどう？")
        assert result is not None
        md = result["context_markdown"]
        if "## 投資lesson" in md:
            assert "CEG" in md
