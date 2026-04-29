"""Tests for KIK-746 dry-run orchestrator."""

import os
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. verify_routing
# ---------------------------------------------------------------------------


def test_verify_routing_known_intent():
    from src.orchestrator import verify_routing
    r = verify_routing("いい株ある？")
    assert r.passed
    assert "screener" in r.agents
    # 期待ツールに screen_stocks が含まれる
    assert any("screen" in t for t in r.expected_tools)


def test_verify_routing_chain_intent():
    from src.orchestrator import verify_routing
    r = verify_routing("この株売るべき？")
    assert r.passed
    # 連鎖: risk-assessor → health-checker → strategist
    assert len(r.agents) >= 2
    assert "strategist" in r.agents


def test_verify_routing_unknown_intent_fails():
    from src.orchestrator import verify_routing
    r = verify_routing("@@@unknownXYZ123@@@")
    assert not r.passed
    assert any("no matching" in e for e in r.errors)


def test_verify_routing_returns_header_for_chain():
    from src.orchestrator import verify_routing
    r = verify_routing("この株売るべき？")
    # routing.yaml にheaderが書かれている
    assert r.header is not None and "→" in r.header


def test_verify_routing_no_llm_calls(monkeypatch):
    """LLM API key を全削除しても dry-run は動く（API呼んでない証拠）."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    from src.orchestrator import verify_routing
    r = verify_routing("いい株ある？")
    assert r.passed  # 通る = LLM/Web呼んでいない


def test_verify_routing_action_direct():
    """action: direct パターンも適切に処理される."""
    from src.orchestrator import verify_routing
    r = verify_routing("メモして")
    assert r.passed
    # actionフラグが立つ
    assert r.flags.get("action") == "direct"


# ---------------------------------------------------------------------------
# 2. verify_routing_yaml_integrity
# ---------------------------------------------------------------------------


def test_routing_yaml_integrity_passes_currently():
    """現状の routing.yaml は重複/欠損なくPASS."""
    from src.orchestrator import verify_routing_yaml_integrity
    report = verify_routing_yaml_integrity()
    assert report["passed"], (
        f"routing.yaml integrity FAILED: {report['errors']}"
    )


def test_routing_yaml_integrity_detects_intent_dup(tmp_path):
    """意図的に重複intentを入れると FAIL する."""
    from src.orchestrator import verify_routing_yaml_integrity

    bad = tmp_path / "routing.yaml"
    bad.write_text(yaml.safe_dump({
        "agents": {
            "screener": {"role": "test", "triggers": []},
        },
        "examples": [
            {"intent": "test_intent", "agent": "screener"},
            {"intent": "test_intent", "agent": "screener"},  # ← 重複
        ],
    }))
    report = verify_routing_yaml_integrity(routing_path=bad)
    assert not report["passed"]
    assert any("duplicate" in e for e in report["errors"])


def test_routing_yaml_integrity_detects_missing_agent(tmp_path):
    """存在しない agent を参照していたら FAIL する."""
    from src.orchestrator import verify_routing_yaml_integrity

    bad = tmp_path / "routing.yaml"
    bad.write_text(yaml.safe_dump({
        "agents": {},
        "examples": [
            {"intent": "test", "agent": "nonexistent-agent-xyz"},
        ],
    }))
    report = verify_routing_yaml_integrity(routing_path=bad)
    assert not report["passed"]
    assert any("nonexistent-agent-xyz" in e for e in report["errors"])


# ---------------------------------------------------------------------------
# 3. run_e2e.py --dry-run CLI
# ---------------------------------------------------------------------------


def test_run_e2e_dry_run_cli(monkeypatch):
    """run_e2e.py --dry-run が import + 実行できる."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    import sys
    sys.path.insert(0, str(REPO_ROOT))
    # 直接 import & 関数呼び出し
    from tests.e2e.run_e2e import run_dry_run
    success = run_dry_run()
    assert success, "dry-run must pass with current routing.yaml"
