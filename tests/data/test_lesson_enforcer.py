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


# ---------------------------------------------------------------------------
# KIK-738 hook integration scenarios
# Simulate the DeepThink Step 5 verification flow.
# ---------------------------------------------------------------------------


class TestStep5HookScenarios:
    """Simulate META-style mistakes — proposal references a stock that
    a lesson explicitly tells us to avoid, but never quotes the lesson's
    expected_action. verify_lesson_cited must catch this."""

    def test_meta_style_uncited_lesson_fails(self):
        lessons = [{
            "id": "L_DR_CHERRY_PICK",
            "trigger": "Deep Research 結果を踏まえた提案を作成する場面",
            "expected_action": "DR 不採用銘柄を plan に混入させない",
            "key_kpis": ["DR 不採用リスト", "cross-check"],
        }]
        # Plan mentions META but never quotes the lesson rule
        proposal = "推奨アクション: META +2株 を新規組入する。理由は割安"
        ok, missing = verify_lesson_cited(proposal, lessons)
        assert ok is False
        assert missing == ["L_DR_CHERRY_PICK"]

    def test_proper_citation_passes(self):
        lessons = [{
            "id": "L_ATH",
            "trigger": "新規買付候補を提案する場面",
            "expected_action": "52H からの距離を必ず確認",
            "key_kpis": ["52週高値からの距離"],
        }]
        proposal = (
            "推奨: AVGO は 52H からの距離 0.0% で ATH 接近。"
            "52H からの距離を必ず確認した結果、試し玉サイズに縮小"
        )
        ok, missing = verify_lesson_cited(proposal, lessons)
        assert ok is True

    def test_filter_then_verify_pipeline(self):
        """Simulates Step 1 (filter) → Step 5 (verify) full pipeline.

        trigger は filter 用にスラッシュ区切りで複数トークン化されている前提
        (KIK-738 backfill prompt はこの形式で抽出する)。
        """
        all_lessons = [
            {"id": "L1", "trigger": "新規買付 / 候補提案",
             "expected_action": "52Hからの距離を必ず確認"},
            {"id": "L2", "trigger": "売却 / タイミング検討",
             "expected_action": "ATH-40% から+30%ラリー時に利確"},
        ]
        user_input = "新規買付の候補提案を検討したい"
        relevant = filter_relevant_lessons(user_input, all_lessons)
        assert any(l["id"] == "L1" for l in relevant)
        assert all(l["id"] != "L2" for l in relevant)  # L2 is unrelated
        # Proposal must reference the lesson's expected_action keyphrase
        proposal = "新規候補X 52Hからの距離を必ず確認した結果、試し玉に縮小"
        ok, _ = verify_lesson_cited(proposal, relevant)
        assert ok is True
