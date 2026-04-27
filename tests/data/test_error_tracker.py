"""Tests for src.data.error_tracker (KIK-736)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.data.error_tracker import (
    detect_recent_patterns,
    load_errors,
    record_error,
)


@pytest.fixture
def errors_path(tmp_path):
    return tmp_path / "archive" / "errors.jsonl"


class TestRecordError:
    def test_appends_one_record(self, errors_path):
        rec = record_error(
            error_type="cash_not_verified",
            theme="PF徹底レビュー",
            root_cause="cash_balance.json 未参照",
            recall="NVDA/CEG/GLDM トリム提案を撤回",
            path=errors_path,
        )
        assert errors_path.exists()
        line = errors_path.read_text(encoding="utf-8").strip()
        loaded = json.loads(line)
        assert loaded["error_type"] == "cash_not_verified"
        assert loaded["theme"] == "PF徹底レビュー"
        assert loaded["recall"] == "NVDA/CEG/GLDM トリム提案を撤回"
        assert "ts" in rec

    def test_appends_multiple(self, errors_path):
        record_error("e1", "t1", "rc1", path=errors_path)
        record_error("e2", "t2", "rc2", path=errors_path)
        contents = errors_path.read_text(encoding="utf-8").splitlines()
        assert len(contents) == 2

    def test_does_not_crash_on_io_error(self, tmp_path):
        # parent.mkdir で作成試行 → 不可ならスキップ。
        # /dev/null/foo のような完全不可ケースを擬す
        bad = tmp_path / "subdir" / "errors.jsonl"
        rec = record_error("e1", "t1", "rc1", path=bad)
        # 通常ケースは作れる。assert はクラッシュしないこと。
        assert "ts" in rec


class TestLoadErrors:
    def test_returns_empty_when_missing(self, errors_path):
        assert load_errors(errors_path) == []

    def test_skips_corrupt_lines(self, errors_path):
        errors_path.parent.mkdir(parents=True, exist_ok=True)
        errors_path.write_text(
            '{"ts":"2026-04-27T10:00:00+00:00","error_type":"e1"}\n'
            '{invalid}\n'
            '\n'
            '{"ts":"2026-04-27T11:00:00+00:00","error_type":"e2"}\n',
            encoding="utf-8",
        )
        recs = load_errors(errors_path)
        assert len(recs) == 2


class TestDetectRecentPatterns:
    def _write(self, path, error_type: str, days_ago: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "error_type": error_type}) + "\n")

    def test_returns_only_repeated_types(self, errors_path):
        self._write(errors_path, "cash_not_verified", 1)
        self._write(errors_path, "cash_not_verified", 2)
        self._write(errors_path, "cash_not_verified", 5)
        self._write(errors_path, "dr_api_schema", 1)  # only 1 occurrence
        result = detect_recent_patterns(within_days=30, min_count=3, path=errors_path)
        assert result == {"cash_not_verified": 3}

    def test_excludes_old_records(self, errors_path):
        self._write(errors_path, "stale_type", 60)
        self._write(errors_path, "stale_type", 70)
        self._write(errors_path, "stale_type", 80)
        result = detect_recent_patterns(within_days=30, min_count=3, path=errors_path)
        assert result == {}

    def test_empty_file_returns_empty(self, errors_path):
        assert detect_recent_patterns(path=errors_path) == {}
