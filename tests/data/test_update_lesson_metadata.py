"""Tests for src.data.note_manager.update_lesson_metadata (KIK-738)."""

from __future__ import annotations

import json

import pytest

from src.data.note_manager import save_note, update_lesson_metadata


@pytest.fixture
def lesson_dir(tmp_path):
    """A temporary notes/ dir with one lesson saved."""
    rec = save_note(
        note_type="lesson",
        content="本文 content (テスト)",
        source="test",
        category="general",
        base_dir=str(tmp_path),
    )
    return tmp_path, rec["id"]


class TestUpdateLessonMetadata:
    def test_updates_all_fields(self, lesson_dir):
        d, nid = lesson_dir
        out = update_lesson_metadata(
            nid,
            trigger="テストトリガー",
            expected_action="テスト動作",
            key_kpis=["KPI1", "KPI2"],
            base_dir=str(d),
        )
        assert out is not None
        assert out["trigger"] == "テストトリガー"
        assert out["expected_action"] == "テスト動作"
        assert out["key_kpis"] == ["KPI1", "KPI2"]

    def test_persists_to_disk(self, lesson_dir):
        d, nid = lesson_dir
        update_lesson_metadata(nid, trigger="永続テスト", base_dir=str(d))
        # Re-read raw JSON
        files = list(d.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        notes = data if isinstance(data, list) else [data]
        target = next(n for n in notes if n.get("id") == nid)
        assert target["trigger"] == "永続テスト"

    def test_partial_update_preserves_other_fields(self, lesson_dir):
        d, nid = lesson_dir
        update_lesson_metadata(nid, trigger="A", base_dir=str(d))
        update_lesson_metadata(nid, expected_action="B", base_dir=str(d))
        files = list(d.glob("*.json"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        target = next(n for n in (data if isinstance(data, list) else [data])
                      if n.get("id") == nid)
        assert target["trigger"] == "A"  # preserved
        assert target["expected_action"] == "B"

    def test_preserves_content_and_date(self, lesson_dir):
        d, nid = lesson_dir
        out = update_lesson_metadata(nid, trigger="x", base_dir=str(d))
        assert out["content"] == "本文 content (テスト)"
        assert "date" in out

    def test_unknown_id_returns_none(self, lesson_dir):
        d, _ = lesson_dir
        assert update_lesson_metadata("does-not-exist", trigger="x", base_dir=str(d)) is None

    def test_non_lesson_note_returns_none(self, tmp_path):
        rec = save_note(
            note_type="thesis",
            content="not a lesson",
            base_dir=str(tmp_path),
        )
        assert update_lesson_metadata(rec["id"], trigger="x", base_dir=str(tmp_path)) is None

    def test_missing_dir_returns_none(self, tmp_path):
        assert update_lesson_metadata("any", trigger="x", base_dir=str(tmp_path / "nope")) is None

    def test_passing_none_leaves_field_unchanged(self, lesson_dir):
        d, nid = lesson_dir
        update_lesson_metadata(nid, trigger="initial", base_dir=str(d))
        # Pass trigger=None: should not clear it
        update_lesson_metadata(nid, expected_action="action only", base_dir=str(d))
        files = list(d.glob("*.json"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        target = next(n for n in (data if isinstance(data, list) else [data])
                      if n.get("id") == nid)
        assert target["trigger"] == "initial"  # untouched
        assert target["expected_action"] == "action only"

    def test_key_kpis_replaces_list(self, lesson_dir):
        d, nid = lesson_dir
        update_lesson_metadata(nid, key_kpis=["A", "B"], base_dir=str(d))
        update_lesson_metadata(nid, key_kpis=["C"], base_dir=str(d))
        out = update_lesson_metadata(nid, base_dir=str(d))  # no-op read; returns None unless update?
        # update with no fields should be a no-op but still find the note? Currently returns None
        # because no field updates → no modification path. So re-read directly:
        files = list(d.glob("*.json"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        target = next(n for n in (data if isinstance(data, list) else [data])
                      if n.get("id") == nid)
        assert target["key_kpis"] == ["C"]
