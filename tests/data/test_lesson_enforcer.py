"""Tests for src.data.lesson_enforcer (KIK-736)."""

from __future__ import annotations

import pytest

from src.data.lesson_enforcer import (
    filter_relevant_lessons,
    verify_lesson_cited,
)


# ---------------------------------------------------------------------------
# filter_relevant_lessons
# ---------------------------------------------------------------------------


class TestFilterRelevantLessons:
    def test_matches_trigger_token(self):
        lessons = [
            {"id": "L1", "trigger": "PF全体レビュー / 徹底", "content": "..."},
            {"id": "L2", "trigger": "決算分析", "content": "..."},
        ]
        result = filter_relevant_lessons("ポートフォリオを徹底的に見直したい", lessons)
        assert any(l["id"] == "L1" for l in result)
        assert not any(l["id"] == "L2" for l in result)

    def test_empty_trigger_excluded(self):
        lessons = [
            {"id": "L1", "trigger": "", "content": "general"},
            {"id": "L2", "trigger": "AB", "content": "..."},  # 2文字、user 入力に含まれず
        ]
        result = filter_relevant_lessons("CDEどう？", lessons)
        assert result == []

    def test_no_user_input_returns_empty(self):
        lessons = [{"id": "L1", "trigger": "PF全体レビュー"}]
        assert filter_relevant_lessons("", lessons) == []

    def test_no_lessons_returns_empty(self):
        assert filter_relevant_lessons("徹底レビュー", []) == []

    def test_two_char_token_matches(self):
        # 2文字トークンは Japanese-friendly に許容（"PF"/"株" 等）
        lessons = [{"id": "L1", "trigger": "PF / 株"}]
        result = filter_relevant_lessons("PF株見直し", lessons)
        assert any(l["id"] == "L1" for l in result)

    def test_single_char_token_filtered(self):
        # 1文字トークンは無視
        lessons = [{"id": "L1", "trigger": "X / Y"}]
        assert filter_relevant_lessons("X Y", lessons) == []

    def test_punctuation_split(self):
        lessons = [{"id": "L1", "trigger": "ポートフォリオ・徹底レビュー"}]
        result = filter_relevant_lessons("ポートフォリオを見たい", lessons)
        assert any(l["id"] == "L1" for l in result)


# ---------------------------------------------------------------------------
# verify_lesson_cited
# ---------------------------------------------------------------------------


class TestVerifyLessonCited:
    def test_passes_when_keyphrase_present(self):
        lessons = [
            {"id": "L1",
             "expected_action": "assert_pf_complete を推奨生成前に通す",
             "key_kpis": ["Cash% = 15-20%"]},
        ]
        text = "推奨生成前に assert_pf_complete を通すこと"
        ok, missing = verify_lesson_cited(text, lessons)
        assert ok is True
        assert missing == []

    def test_fails_when_no_keyphrase(self):
        lessons = [
            {"id": "L1",
             "expected_action": "PFバランス normal: Cash 15-20% を維持する",
             "key_kpis": []},
        ]
        text = "完全に違うことを書いた"
        ok, missing = verify_lesson_cited(text, lessons)
        assert ok is False
        assert "L1" in missing

    def test_no_extractable_phrases_treated_as_cited(self):
        # expected_action が短い + key_kpis なし + content なし → 検証スキップ
        lessons = [
            {"id": "L1", "expected_action": "X", "key_kpis": [], "content": ""},
        ]
        ok, missing = verify_lesson_cited("anything", lessons)
        assert ok is True
        assert missing == []

    def test_falls_back_to_content_first_line(self):
        lessons = [
            {"id": "L1",
             "content": "【ホールド確定 4/25】キヤノンは売却しない\n以下続き..."},
        ]
        ok, _ = verify_lesson_cited(
            "【ホールド確定 4/25】キヤノンは売却しない を遵守", lessons
        )
        assert ok is True

    def test_partial_token_match(self):
        # 8文字以上のトークンならフォールバックで一致
        lessons = [
            {"id": "L1",
             "expected_action": "投資判断マルチエージェントシステム を活用"},
        ]
        text = "結果に 投資判断マルチエージェント を反映"
        ok, _ = verify_lesson_cited(text, lessons)
        assert ok is True

    def test_empty_lessons_passes(self):
        ok, missing = verify_lesson_cited("anything", [])
        assert ok is True
        assert missing == []
