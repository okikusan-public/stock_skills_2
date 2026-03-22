"""Tests for unified lesson conflict engine (KIK-570)."""

import pytest


class TestTokenize:
    def test_english(self):
        from src.data.lesson_conflict import tokenize
        assert tokenize("hello world") == ["hello", "world"]

    def test_japanese(self):
        from src.data.lesson_conflict import tokenize
        tokens = tokenize("高値掴みRSI確認")
        assert "高値掴み" in tokens
        assert "rsi" in tokens
        assert "確認" in tokens

    def test_mixed(self):
        from src.data.lesson_conflict import tokenize
        tokens = tokenize("VIX上昇 → 様子見")
        assert "vix" in tokens
        assert "上昇" in tokens
        assert "様子見" in tokens

    def test_empty(self):
        from src.data.lesson_conflict import tokenize
        assert tokenize("") == []


class TestKeywordSimilarityCJK:
    def test_japanese_identical(self):
        from src.data.lesson_conflict import keyword_similarity
        assert keyword_similarity("高値掴み", "高値掴み") == pytest.approx(1.0)

    def test_japanese_partial(self):
        from src.data.lesson_conflict import keyword_similarity
        sim = keyword_similarity("高値掴みRSI高い", "高値掴みRSI確認")
        assert sim > 0.3  # Shared: 高値掴み, RSI

    def test_japanese_disjoint(self):
        from src.data.lesson_conflict import keyword_similarity
        sim = keyword_similarity("金利上昇", "半導体需要")
        assert sim == 0.0

    def test_old_split_would_fail(self):
        """Old .split() would return 0.0 for Japanese without spaces."""
        from src.data.lesson_conflict import keyword_similarity
        # Without CJK tokenization, "高値掴み" and "高値掴みRSI" are single tokens
        sim = keyword_similarity("高値掴み", "高値掴みRSI")
        assert sim > 0  # CJK tokenizer should find overlap


class TestExtractTriggerAction:
    def test_structured_fields(self):
        from src.data.lesson_conflict import extract_trigger, extract_action
        les = {"trigger": "VIX上昇", "expected_action": "様子見"}
        assert extract_trigger(les) == "VIX上昇"
        assert extract_action(les) == "様子見"

    def test_content_fallback(self):
        from src.data.lesson_conflict import extract_trigger, extract_action
        les = {
            "content": "■trigger: 高値掴み\n■expected_action: RSI確認してから買う",
            "trigger": "",
            "expected_action": "",
        }
        assert extract_trigger(les) == "高値掴み"
        assert extract_action(les) == "RSI確認してから買う"

    def test_content_with_japanese_labels(self):
        from src.data.lesson_conflict import extract_trigger, extract_action
        les = {
            "content": "トリガー: パニック売り\n次回アクション: 冷静に待つ",
            "trigger": "",
            "expected_action": "",
        }
        assert extract_trigger(les) == "パニック売り"
        assert extract_action(les) == "冷静に待つ"

    def test_no_trigger(self):
        from src.data.lesson_conflict import extract_trigger
        les = {"content": "一般的な学び"}
        assert extract_trigger(les) == ""


class TestFindConflicts:
    def test_contradicting_action(self):
        from src.data.lesson_conflict import find_conflicts

        new = {"id": "new", "trigger": "高値掴みRSI高い", "expected_action": "買う", "content": ""}
        existing = [
            {"id": "old", "trigger": "高値掴みRSI高い", "expected_action": "買わない", "content": ""},
        ]
        conflicts = find_conflicts(new, existing, similarity_threshold=0.3)
        assert len(conflicts) >= 1
        assert conflicts[0]["conflict_type"] == "contradicting_action"

    def test_no_conflict_same_action(self):
        from src.data.lesson_conflict import find_conflicts

        new = {"id": "new", "trigger": "VIX上昇", "expected_action": "様子見", "content": ""}
        existing = [
            {"id": "old", "trigger": "VIX上昇", "expected_action": "様子見", "content": ""},
        ]
        conflicts = find_conflicts(new, existing, similarity_threshold=0.3)
        for c in conflicts:
            assert c["conflict_type"] != "contradicting_action"

    def test_content_only_lessons(self):
        """Legacy lessons with trigger in content should be detected."""
        from src.data.lesson_conflict import find_conflicts

        new = {"id": "new", "trigger": "高値掴み", "expected_action": "RSI確認", "content": ""}
        existing = [
            {"id": "old", "trigger": "", "expected_action": "",
             "content": "■trigger: 高値掴み\n■expected_action: 買わない"},
        ]
        conflicts = find_conflicts(new, existing, similarity_threshold=0.3)
        assert len(conflicts) >= 1

    def test_skips_self(self):
        from src.data.lesson_conflict import find_conflicts

        les = {"id": "same", "trigger": "x", "expected_action": "y", "content": "z"}
        conflicts = find_conflicts(les, [les], similarity_threshold=0.0)
        assert len(conflicts) == 0

    def test_empty_existing(self):
        from src.data.lesson_conflict import find_conflicts
        assert find_conflicts({"trigger": "x"}, []) == []


class TestFindConflictPairs:
    def test_returns_map_with_details(self):
        from src.data.lesson_conflict import find_conflict_pairs

        lessons = [
            {"id": "a", "trigger": "高値掴みRSI", "expected_action": "買わない"},
            {"id": "b", "trigger": "高値掴みRSI", "expected_action": "買う"},
        ]
        result = find_conflict_pairs(lessons)
        assert "a" in result
        assert "b" in result
        assert "買う" in result["a"]  # detail shows the other lesson's action

    def test_no_conflict(self):
        from src.data.lesson_conflict import find_conflict_pairs

        lessons = [
            {"id": "a", "trigger": "VIX", "expected_action": "様子見"},
            {"id": "b", "trigger": "金利", "expected_action": "債券売り"},
        ]
        result = find_conflict_pairs(lessons)
        assert len(result) == 0
