"""Tests for src.data.grok_client.bulk_search (KIK-732)."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from src.data.grok_client.bulk_search import bulk_x_search, bulk_web_search


@pytest.fixture
def patch_meta_log(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.data.grok_client.bulk_search._META_LOG_PATH", tmp_path / "log.jsonl"
    )
    # Skip the inter-call sleep
    monkeypatch.setattr(
        "src.data.grok_client.bulk_search._DEFAULT_PARALLEL_INTERVAL_SEC", 0.0
    )
    return tmp_path / "log.jsonl"


def _mock_grok_response(text: str, sources: list[str]):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "output": [
            {"type": "message", "content": [{"text": text}]},
        ],
        "citations": [{"url": s} for s in sources],
    }
    return resp


class TestBulkXSearch:
    def test_no_api_key_returns_error(self, monkeypatch, patch_meta_log):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("DEEPTHINK_DRY_RUN", raising=False)
        out = bulk_x_search(["$NVDA", "$AAPL"])
        assert out["error"] == "XAI_API_KEY not set"
        assert out["successful_calls"] == 0
        assert out["total_calls"] == 2

    def test_successful_calls(self, monkeypatch, patch_meta_log):
        monkeypatch.setenv("XAI_API_KEY", "test")
        with patch(
            "src.data.grok_client.bulk_search.requests.post",
            return_value=_mock_grok_response("strong buy", ["https://x.com/post/1"]),
        ):
            out = bulk_x_search(["$NVDA", "$AAPL"])
        assert out["successful_calls"] == 2
        assert out["total_calls"] == 2
        assert out["total_cost_usd"] == 1.0  # 2 × 0.5
        assert all(r["status"] == "ok" for r in out["results"])
        assert out["results"][0]["text"] == "strong buy"

    def test_max_sources_per_call_caps_sources(self, monkeypatch, patch_meta_log):
        monkeypatch.setenv("XAI_API_KEY", "test")
        with patch(
            "src.data.grok_client.bulk_search.requests.post",
            return_value=_mock_grok_response("ok", [f"u{i}" for i in range(50)]),
        ):
            out = bulk_x_search(["q1"], max_sources_per_call=10)
        assert len(out["results"][0]["sources"]) == 10

    def test_http_error_marks_failure(self, monkeypatch, patch_meta_log):
        monkeypatch.setenv("XAI_API_KEY", "test")
        bad = MagicMock()
        bad.status_code = 429
        with patch(
            "src.data.grok_client.bulk_search.requests.post", return_value=bad
        ):
            out = bulk_x_search(["q1"])
        assert out["successful_calls"] == 0
        assert out["results"][0]["status"] == "http_429"

    def test_meta_log_appended(self, monkeypatch, patch_meta_log):
        monkeypatch.setenv("XAI_API_KEY", "test")
        with patch(
            "src.data.grok_client.bulk_search.requests.post",
            return_value=_mock_grok_response("ok", []),
        ):
            bulk_x_search(["q1"])
        assert patch_meta_log.exists()
        rec = json.loads(patch_meta_log.read_text().strip())
        assert rec["tool"] == "bulk_x_search"
        assert rec["query_count"] == 1
        assert rec["successful_calls"] == 1


class TestBulkWebSearch:
    def test_allowed_domains_passed(self, monkeypatch, patch_meta_log):
        monkeypatch.setenv("XAI_API_KEY", "test")
        captured: dict = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["payload"] = json
            return _mock_grok_response("ok", [])

        with patch(
            "src.data.grok_client.bulk_search.requests.post", side_effect=fake_post
        ):
            bulk_web_search(["earnings"], allowed_domains=["sec.gov", "reuters.com"])

        tools = captured["payload"]["tools"]
        assert tools[0]["type"] == "web_search"
        assert tools[0]["allowed_domains"] == ["sec.gov", "reuters.com"]

    def test_caps_allowed_domains_at_5(self, monkeypatch, patch_meta_log):
        monkeypatch.setenv("XAI_API_KEY", "test")
        captured: dict = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["payload"] = json
            return _mock_grok_response("ok", [])

        with patch(
            "src.data.grok_client.bulk_search.requests.post", side_effect=fake_post
        ):
            bulk_web_search(["q"], allowed_domains=[f"d{i}.com" for i in range(10)])
        assert len(captured["payload"]["tools"][0]["allowed_domains"]) == 5


class TestBulkDryRun:
    """KIK-737: dry_run for bulk searches."""

    def test_dry_run_arg_skips_api(self, monkeypatch, patch_meta_log):
        monkeypatch.setenv("XAI_API_KEY", "test")
        with patch(
            "src.data.grok_client.bulk_search.requests.post"
        ) as p:
            out = bulk_x_search(["$NVDA", "$AAPL"], dry_run=True)
        assert p.call_count == 0
        assert out["dry_run"] is True
        assert out["successful_calls"] == 0
        assert out["estimate_cost_usd"] == 1.0  # 0.5 × 2
        assert all(r["status"] == "dry_run" for r in out["results"])

    def test_env_var_forces_dry_run(self, monkeypatch, patch_meta_log):
        monkeypatch.setenv("XAI_API_KEY", "test")
        monkeypatch.setenv("DEEPTHINK_DRY_RUN", "1")
        with patch(
            "src.data.grok_client.bulk_search.requests.post"
        ) as p:
            out = bulk_web_search(["earnings"])
        assert p.call_count == 0
        assert out["dry_run"] is True
        assert out["estimate_cost_usd"] == 0.5
