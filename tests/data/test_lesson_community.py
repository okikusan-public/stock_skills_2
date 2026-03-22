"""Tests for KIK-571 lesson community classification."""

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.no_auto_mock


@pytest.fixture(autouse=True)
def reset_driver():
    import src.data.graph_store as gs
    gs._driver = None
    yield
    gs._driver = None


class TestClassifyLesson:
    def test_bias_classification(self):
        from src.data.lesson_community import classify_lesson
        assert classify_lesson("AIの保守バイアスを割り引く", "バイアス") == "判断バイアス"

    def test_trade_rule_classification(self):
        from src.data.lesson_community import classify_lesson
        assert classify_lesson("ファンダ良好でも-15%で損切り", "損切りルール") == "売買ルール"

    def test_macro_classification(self):
        from src.data.lesson_community import classify_lesson
        assert classify_lesson("原油高ヘッジとしてETFローテーション", "") == "マクロ戦略"

    def test_unknown_classification(self):
        from src.data.lesson_community import classify_lesson
        assert classify_lesson("完全に関係ないテキスト", "") == "その他"

    def test_empty_input(self):
        from src.data.lesson_community import classify_lesson
        assert classify_lesson("", "") == "その他"

    def test_mixed_keywords(self):
        from src.data.lesson_community import classify_lesson
        # RSI is a sell rule keyword
        result = classify_lesson("RSI高い時のエントリー条件", "エントリールール")
        assert result == "売買ルール"


class TestInferThemeFromInput:
    def test_market_query(self):
        from src.data.lesson_community import infer_theme_from_input
        assert infer_theme_from_input("市況チェック") == "マクロ戦略"

    def test_health_query(self):
        from src.data.lesson_community import infer_theme_from_input
        assert infer_theme_from_input("ヘルスチェック") == "売買ルール"

    def test_bias_query(self):
        from src.data.lesson_community import infer_theme_from_input
        assert infer_theme_from_input("判断バイアスに注意") == "判断バイアス"

    def test_no_match(self):
        from src.data.lesson_community import infer_theme_from_input
        assert infer_theme_from_input("こんにちは") is None

    def test_empty(self):
        from src.data.lesson_community import infer_theme_from_input
        assert infer_theme_from_input("") is None


class TestMergeLessonCommunity:
    def test_merge_creates_node(self):
        from src.data.lesson_community import merge_lesson_community
        import src.data.graph_store as gs

        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)
        gs._driver = driver

        with patch("src.data.graph_store._get_mode", return_value="full"):
            result = merge_lesson_community("note_001", "売買ルール")

        assert result is True
        assert session.run.call_count == 2  # MERGE node + MERGE rel

    def test_mode_off(self):
        from src.data.lesson_community import merge_lesson_community

        with patch("src.data.graph_store._get_mode", return_value="off"):
            assert merge_lesson_community("note_001", "test") is False


class TestGetLessonsByTheme:
    def test_returns_lessons(self):
        from src.data.lesson_community import get_lessons_by_theme
        import src.data.graph_store as gs

        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)

        r1 = MagicMock()
        r1.keys = lambda: ["id", "content", "trigger", "expected_action", "date"]
        r1.__getitem__ = lambda s, k: {
            "id": "n1", "content": "損切りルール",
            "trigger": "ファンダ良好でも", "expected_action": "-15%で損切り",
            "date": "2026-03-20",
        }[k]
        session.run.return_value = iter([r1])
        gs._driver = driver

        result = get_lessons_by_theme("売買ルール")
        assert len(result) == 1
        assert result[0]["trigger"] == "ファンダ良好でも"

    def test_no_driver(self):
        from src.data.lesson_community import get_lessons_by_theme
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert get_lessons_by_theme("test") == []


class TestSaveNoteIntegration:
    def test_lesson_gets_community(self, tmp_path):
        from src.data.note_manager import save_note

        with patch("src.data.lesson_community.merge_lesson_community", return_value=True) as mock_merge:
            note = save_note(
                note_type="lesson",
                content="損切りは-15%",
                trigger="ファンダ良好でも損切り",
                expected_action="-15%で撤退",
                base_dir=str(tmp_path),
            )

        assert note.get("_lesson_community") == "売買ルール"
        mock_merge.assert_called_once()
