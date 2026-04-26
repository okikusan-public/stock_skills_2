"""Tests for src.data.gemini_client.deep_research (KIK-731)."""

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
# gemini_deep_research()
# ---------------------------------------------------------------------------


class TestGeminiDeepResearch:
    def test_returns_disabled_when_kill_switch_off(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "off")
        # Redirect log to tmp
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        r = gemini_deep_research("AI半導体")
        assert r["status"] == "disabled"
        assert r["text"] == ""
        assert r["sources"] == []

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
        # depth=heavy estimate $5.0 > budget $1.0
        r = gemini_deep_research("AI半導体", depth="heavy", budget_usd=1.0)
        assert r["status"] == "budget_exceeded"
        assert "estimate" in r["error_message"]

    def test_appends_meta_log(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "off")  # avoids real API call
        log_path = tmp_path / "log.jsonl"
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH", log_path
        )
        gemini_deep_research("AI半導体", depth="medium")
        assert log_path.exists()
        line = log_path.read_text(encoding="utf-8").strip()
        rec = json.loads(line)
        assert rec["tool"] == "gemini_deep_research"
        assert rec["theme"] == "AI半導体"
        assert rec["depth"] == "medium"
        assert rec["status"] == "disabled"

    def test_successful_call_with_mocked_api(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": "AI半導体は2026年も成長"}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"uri": "https://example.com/ai-2026"}},
                        {"web": {"uri": "https://example.com/sec-filing"}},
                    ]
                },
            }]
        }
        with patch(
            "src.data.gemini_client.deep_research.requests.post",
            return_value=mock_response,
        ):
            r = gemini_deep_research("AI半導体", depth="medium")

        assert r["status"] == "ok"
        assert "AI半導体" in r["text"]
        assert len(r["sources"]) == 2
        assert r["sources"][0] == "https://example.com/ai-2026"

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

    def test_polling_branch_returns_done_response(self, monkeypatch, tmp_path):
        """op_name 付きレスポンス → polling → done で結果取得 (KIK-731)."""
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._POLL_INTERVAL_SEC", 0
        )

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.raise_for_status = MagicMock()
        post_resp.json.return_value = {"name": "operations/abc123"}

        get_resp = MagicMock()
        get_resp.raise_for_status = MagicMock()
        get_resp.json.return_value = {
            "done": True,
            "response": {
                "candidates": [{
                    "content": {"parts": [{"text": "polled result"}]},
                    "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://e.com"}}]},
                }],
            },
        }
        with patch(
            "src.data.gemini_client.deep_research.requests.post",
            return_value=post_resp,
        ), patch(
            "src.data.gemini_client.deep_research.requests.get",
            return_value=get_resp,
        ):
            r = gemini_deep_research("AI", depth="medium")

        assert r["status"] == "ok"
        assert r["text"] == "polled result"
        assert r["sources"] == ["https://e.com"]

    def test_timeout_when_polling_exceeds_deadline(self, monkeypatch, tmp_path):
        """polling 中に wall_time 超過 → status='timeout' (KIK-731)."""
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "on")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH",
            tmp_path / "log.jsonl",
        )
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._POLL_INTERVAL_SEC", 0
        )

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.raise_for_status = MagicMock()
        post_resp.json.return_value = {"name": "operations/longrunning"}

        # done=False を返し続けることで deadline 超過させる
        get_resp = MagicMock()
        get_resp.raise_for_status = MagicMock()
        get_resp.json.return_value = {"done": False}

        with patch(
            "src.data.gemini_client.deep_research.requests.post",
            return_value=post_resp,
        ), patch(
            "src.data.gemini_client.deep_research.requests.get",
            return_value=get_resp,
        ):
            r = gemini_deep_research("AI", depth="light", timeout_sec=0)

        assert r["status"] == "timeout"
        assert "wall_time exceeded" in r["error_message"]

    def test_meta_log_write_failure_does_not_crash(self, monkeypatch):
        """log 書き込み失敗時も呼出は完了する (graceful degradation)."""
        monkeypatch.setenv("DEEPTHINK_DR_ENABLED", "off")
        # 存在しない深いパスを指定（OSError を発生させる）
        from pathlib import Path
        bad_path = Path("/nonexistent/dir/that/cannot/be/created/log.jsonl")
        monkeypatch.setattr(
            "src.data.gemini_client.deep_research._META_LOG_PATH", bad_path
        )
        # 例外発生せず status="disabled" を返す
        r = gemini_deep_research("AI")
        assert r["status"] == "disabled"
