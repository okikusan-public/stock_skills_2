"""Tests for src.data.gemini_client.deep_research (KIK-731 / KIK-733).

KIK-733: Mock schemas updated to match real /v1beta/interactions API.
- Submit: POST /v1beta/interactions returns {"id", "status": "in_progress"}
- Poll: GET /v1beta/interactions/{id} returns {"status": "completed", "outputs": [...]}
- Extraction: outputs[].content[].text + outputs[].annotations[].url
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.data.gemini_client.deep_research import (
    gemini_deep_research,
    is_available,
    is_deep_research_enabled,
)


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


class TestKillSwitch:
    def test_disabled_when_env_off(self, monkeypatch):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "off")
        assert is_deep_research_enabled() is False

    def test_enabled_default(self, monkeypatch):
        monkeypatch.delenv("DEEPTHINK_DR_ENABLED", raising=False)
        assert is_deep_research_enabled() is True

    def test_enabled_when_on(self, monkeypatch):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        assert is_deep_research_enabled() is True


class TestApiKeyCheck:
    def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert is_available() is False

    def test_with_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        assert is_available() is True


# ---------------------------------------------------------------------------
# Helpers for the new /v1beta/interactions schema
# ---------------------------------------------------------------------------


def _mock_submit_response(interaction_id: str = "v1_abc123",
                          status: str = "in_progress") -> MagicMock:
    """Build a /v1beta/interactions POST response (background=true)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"id": interaction_id, "status": status}
    return resp


def _mock_completed_response(text: str, urls: list[str]) -> MagicMock:
    """Build a GET /v1beta/interactions/{id} 'completed' response."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "id": "v1_abc123",
        "status": "completed",
        "outputs": [
            {
                "type": "text",
                "content": [{"text": text}],
                "annotations": [{"url": u, "title": f"src-{u}"} for u in urls],
            },
        ],
    }
    return resp


def _mock_in_progress_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"id": "v1_abc123", "status": "in_progress"}
    return resp


def _mock_failed_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "id": "v1_abc123",
        "status": "failed",
        "error": {"message": "internal", "code": 500},
    }
    return resp


# ---------------------------------------------------------------------------
# gemini_deep_research()
# ---------------------------------------------------------------------------


class TestGeminiDeepResearchGuards:
    """Pre-flight guards (no API call)."""

    def test_returns_disabled_when_kill_switch_off(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "off")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        r = gemini_deep_research("AI半導体")
        assert r["status"] == "disabled"
        assert r["text"] == ""
        assert r["sources"] == []
        assert r.get("interaction_id") is None

    def test_returns_no_api_key_without_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        r = gemini_deep_research("AI半導体")
        assert r["status"] == "no_api_key"

    def test_returns_budget_exceeded(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        r = gemini_deep_research("AI半導体", depth="heavy", budget_usd=1.0)
        assert r["status"] == "budget_exceeded"
        assert "estimate" in r["error_message"]


class TestGeminiDeepResearchFlow:
    """Full submit → poll → extract flow with /v1beta/interactions schema."""

    def test_inline_completed_response(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        inline = MagicMock()
        inline.status_code = 200
        inline.raise_for_status = MagicMock()
        inline.json.return_value = {
            "id": "v1_xyz",
            "status": "completed",
            "outputs": [
                {
                    "type": "text",
                    "content": [{"text": "AI半導体は2026年も成長"}],
                    "annotations": [{"url": "https://example.com/ai-2026"}],
                }
            ],
        }
        with patch(
            "src.data.gemini_client.deep_research.requests.post",
            return_value=inline,
        ):
            r = gemini_deep_research("AI半導体", depth="medium")

        assert r["status"] == "ok"
        assert "AI半導体" in r["text"]
        assert r["sources"] == ["https://example.com/ai-2026"]
        assert r["interaction_id"] == "v1_xyz"

    def test_polling_branch_returns_completed(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._POLL_INTERVAL_SEC", 0
        )
        submit = _mock_submit_response("v1_abc", "in_progress")
        completed = _mock_completed_response(
            "polled result", ["https://e.com", "https://f.com"]
        )
        with patch(
            "src.data.gemini_client.deep_research.requests.post",
            return_value=submit,
        ), patch(
            "src.data.gemini_client.deep_research.requests.get",
            return_value=completed,
        ):
            r = gemini_deep_research("AI", depth="medium")

        assert r["status"] == "ok"
        assert r["text"] == "polled result"
        assert r["sources"] == ["https://e.com", "https://f.com"]
        assert r["interaction_id"] == "v1_abc"

    def test_polling_dedups_repeated_urls(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._POLL_INTERVAL_SEC", 0
        )
        submit = _mock_submit_response()
        completed = MagicMock()
        completed.raise_for_status = MagicMock()
        completed.json.return_value = {
            "id": "v1_abc123",
            "status": "completed",
            "outputs": [
                {
                    "content": [{"text": "part A"}],
                    "annotations": [{"url": "https://a.com"}, {"url": "https://b.com"}],
                },
                {
                    "content": [{"text": "part B"}],
                    "annotations": [{"url": "https://a.com"}],
                },
            ],
        }
        with patch(
            "src.data.gemini_client.deep_research.requests.post",
            return_value=submit,
        ), patch(
            "src.data.gemini_client.deep_research.requests.get",
            return_value=completed,
        ):
            r = gemini_deep_research("AI", depth="light")
        assert r["status"] == "ok"
        assert r["text"] == "part A\npart B"
        assert r["sources"] == ["https://a.com", "https://b.com"]

    def test_timeout_when_polling_exceeds_deadline(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._POLL_INTERVAL_SEC", 0
        )
        submit = _mock_submit_response("v1_long")
        in_progress = _mock_in_progress_response()
        with patch(
            "src.data.gemini_client.deep_research.requests.post",
            return_value=submit,
        ), patch(
            "src.data.gemini_client.deep_research.requests.get",
            return_value=in_progress,
        ):
            r = gemini_deep_research("AI", depth="light", timeout_sec=0)

        assert r["status"] == "timeout"
        assert "wall_time exceeded" in r["error_message"]
        assert r["interaction_id"] == "v1_long"

    def test_failed_status_raises_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._POLL_INTERVAL_SEC", 0
        )
        submit = _mock_submit_response()
        failed = _mock_failed_response()
        with patch(
            "src.data.gemini_client.deep_research.requests.post",
            return_value=submit,
        ), patch(
            "src.data.gemini_client.deep_research.requests.get",
            return_value=failed,
        ):
            r = gemini_deep_research("AI", depth="light")
        assert r["status"] == "error"
        assert "interaction failed" in r["error_message"]

    def test_handles_request_exception(self, monkeypatch, tmp_path):
        import requests as req
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        with patch(
            "src.data.gemini_client.deep_research.requests.post",
            side_effect=req.RequestException("connection refused"),
        ):
            r = gemini_deep_research("AI", depth="light")
        assert r["status"] == "error"
        assert "RequestException" in r["error_message"]

    def test_submit_missing_id_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        bad_submit = MagicMock()
        bad_submit.status_code = 200
        bad_submit.raise_for_status = MagicMock()
        bad_submit.json.return_value = {"status": "in_progress"}
        with patch(
            "src.data.gemini_client.deep_research.requests.post",
            return_value=bad_submit,
        ):
            r = gemini_deep_research("AI", depth="light")
        assert r["status"] == "error"
        assert "missing 'id'" in r["error_message"]


class TestMetaLogging:
    def test_meta_log_appended_with_interaction_id(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "off")
        log = tmp_path / "log.jsonl"
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH", log
        )
        gemini_deep_research("AI半導体", depth="medium")
        rec = json.loads(log.read_text(encoding="utf-8").strip())
        assert rec["tool"] == "gemini_deep_research"
        assert rec["theme"] == "AI半導体"
        assert rec["depth"] == "medium"
        assert rec["status"] == "disabled"
        assert "interaction_id" in rec

    def test_meta_log_write_failure_does_not_crash(self, monkeypatch):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "off")
        bad_path = Path("/nonexistent/dir/that/cannot/be/created/log.jsonl")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH", bad_path
        )
        r = gemini_deep_research("AI")
        assert r["status"] == "disabled"
