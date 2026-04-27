"""Unit tests for scripts.backfill_lesson_fields helpers (KIK-738).

Only tests the pure helpers (`_extract_json`, `_validate_extracted`) —
LLM-calling paths are not exercised here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


# Load the script as a module without invoking its CLI
_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "backfill_lesson_fields.py"
_spec = importlib.util.spec_from_file_location("backfill_lesson_fields", _SCRIPT_PATH)
_module = importlib.util.module_from_spec(_spec)
sys.modules["backfill_lesson_fields"] = _module
_spec.loader.exec_module(_module)

_extract_json = _module._extract_json
_validate_extracted = _module._validate_extracted


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_markdown_fenced_json(self):
        assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_fenced_no_lang(self):
        assert _extract_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_text_with_surrounding_prose(self):
        text = 'ここに JSON: {"trigger": "x"} です'
        assert _extract_json(text) == {"trigger": "x"}

    def test_empty_text_returns_none(self):
        assert _extract_json("") is None

    def test_none_text_returns_none(self):
        assert _extract_json(None) is None

    def test_no_json_returns_none(self):
        assert _extract_json("just plain text") is None

    def test_malformed_json_returns_none(self):
        # missing closing brace; brace search finds {...{... but parse fails
        assert _extract_json('{"a": 1') is None

    def test_array_at_top_level_returns_none(self):
        # function expects a dict, not a list
        assert _extract_json("[1, 2, 3]") is None


# ---------------------------------------------------------------------------
# _validate_extracted
# ---------------------------------------------------------------------------


class TestValidateExtracted:
    def test_all_fields_ok(self):
        warns = _validate_extracted({
            "trigger": "X / Y / Z",
            "expected_action": "確認する",
            "key_kpis": ["A", "B"],
        })
        assert warns == []

    def test_empty_trigger_warns(self):
        warns = _validate_extracted({"trigger": "", "expected_action": "OK", "key_kpis": []})
        assert any("trigger" in w for w in warns)

    def test_empty_action_warns(self):
        warns = _validate_extracted({"trigger": "x", "expected_action": "", "key_kpis": []})
        assert any("expected_action" in w for w in warns)

    def test_too_long_trigger_warns(self):
        warns = _validate_extracted({
            "trigger": "x" * 100,
            "expected_action": "OK",
            "key_kpis": [],
        })
        assert any("too long" in w for w in warns)

    def test_too_long_action_warns(self):
        warns = _validate_extracted({
            "trigger": "x",
            "expected_action": "y" * 100,
            "key_kpis": [],
        })
        assert any("too long" in w for w in warns)

    def test_kpis_not_list_warns(self):
        warns = _validate_extracted({
            "trigger": "x",
            "expected_action": "y",
            "key_kpis": "not a list",
        })
        assert any("key_kpis" in w for w in warns)
