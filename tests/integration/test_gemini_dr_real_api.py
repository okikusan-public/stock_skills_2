"""Real-API contract tests for Gemini Deep Research (KIK-733).

These tests **call the actual Gemini DR API** to validate that our wrapper's
schema assumptions match the live service. They cost money ($1.5–3 per run)
and take 5–15 minutes per call, so they are gated behind environment
variables and a pytest marker.

Activation
----------
1. `GEMINI_API_KEY` must be set
2. `DEEPTHINK_REAL_API_TEST=on` must be set explicitly
3. Run: ``pytest -m real_api tests/integration/test_gemini_dr_real_api.py``

Skipped by default in normal `pytest tests/` runs.

Why these exist
---------------
KIK-731 shipped with mock tests that did not match the real API schema.
The bug (wrong endpoint, wrong fields, wrong response parsing) was only
found when a $4.9 production call failed. KIK-733 introduces this real-API
test as a one-time contract check to prevent recurrence.

Budget guard: monthly cap is enforced by deepthink_limits.yaml. These tests
should be invoked at most a few times per month.
"""

from __future__ import annotations

import json
import os

import pytest

from src.data.gemini_client.deep_research import gemini_deep_research

pytestmark = pytest.mark.real_api


def _real_api_enabled() -> bool:
    return (
        os.environ.get("DEEPTHINK_REAL_API_TEST") == "on"
        and bool(os.environ.get("GEMINI_API_KEY"))
    )


REASON_SKIP = (
    "Real API test disabled. Set DEEPTHINK_REAL_API_TEST=on and GEMINI_API_KEY "
    "to run. Cost: $1.5–3 per call."
)


# ---------------------------------------------------------------------------
# Real-API contract tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _real_api_enabled(), reason=REASON_SKIP)
def test_real_api_light_depth_returns_sources(tmp_path, monkeypatch):
    """Light depth call should complete and return at least 1 source."""
    monkeypatch.setattr(
        "src.data.gemini_client.deep_research._META_LOG_PATH",
        tmp_path / "log.jsonl",
    )
    result = gemini_deep_research(
        theme="AI semiconductor 2026 outlook (KIK-733 contract test)",
        depth="light",
        budget_usd=3.0,
        timeout_sec=900,  # 15min cap for tests
    )
    assert result["status"] == "ok", (
        f"expected ok, got {result['status']!r}: {result.get('error_message')}"
    )
    assert isinstance(result["text"], str) and len(result["text"]) > 0
    assert isinstance(result["sources"], list) and len(result["sources"]) > 0
    assert isinstance(result["interaction_id"], str)
    assert result["interaction_id"].startswith(("v1_", "interactions/"))


@pytest.mark.skipif(not _real_api_enabled(), reason=REASON_SKIP)
def test_real_api_response_schema_matches_extraction(tmp_path, monkeypatch):
    """outputs[].content[].text + outputs[].annotations[].url が抽出される。"""
    monkeypatch.setattr(
        "src.data.gemini_client.deep_research._META_LOG_PATH",
        tmp_path / "log.jsonl",
    )
    result = gemini_deep_research(
        theme="Test query — Bitcoin price 2026 (KIK-733)",
        depth="light",
        budget_usd=3.0,
        timeout_sec=900,
    )
    assert result["status"] == "ok"
    # All sources should be valid http(s) URLs
    for src in result["sources"]:
        assert src.startswith(("http://", "https://")), f"non-URL source: {src!r}"
    # Text should be substantial (>200 chars for a real DR response)
    assert len(result["text"]) > 200, f"text suspiciously short: {len(result['text'])}"


@pytest.mark.skipif(not _real_api_enabled(), reason=REASON_SKIP)
def test_real_api_meta_log_written(tmp_path, monkeypatch):
    """meta.jsonl auto-append after a real call."""
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(
        "src.data.gemini_client.deep_research._META_LOG_PATH", log,
    )
    result = gemini_deep_research(
        theme="Test query — TSMC capex 2026 (KIK-733)",
        depth="light",
        budget_usd=3.0,
        timeout_sec=900,
    )
    assert result["status"] == "ok"
    assert log.exists()
    rec = json.loads(log.read_text(encoding="utf-8").strip())
    assert rec["tool"] == "gemini_deep_research"
    assert rec["status"] == "ok"
    assert rec["sources_count"] == len(result["sources"])
    assert rec["interaction_id"] == result["interaction_id"]


@pytest.mark.skipif(not _real_api_enabled(), reason=REASON_SKIP)
def test_real_api_polling_completes_within_timeout(tmp_path, monkeypatch):
    """background=true → poll → completed の経路が15分以内に完了する。"""
    monkeypatch.setattr(
        "src.data.gemini_client.deep_research._META_LOG_PATH",
        tmp_path / "log.jsonl",
    )
    result = gemini_deep_research(
        theme="Test query — short macro check (KIK-733)",
        depth="light",
        budget_usd=3.0,
        timeout_sec=900,
    )
    assert result["status"] == "ok"
    assert result["duration_sec"] < 900
