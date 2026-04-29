"""Dry-run orchestrator (KIK-746).

Validates routing.yaml + agent definitions without invoking any LLM or
external API. Useful for:

- worktree clean-environment integration tests (no API keys required)
- routing.yaml change verification (intent dedup, header existence)
- Quick CI sanity check (target < 1s for the full scenario set)
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ROUTING_PATH = PROJECT_ROOT / ".claude/skills/stock-skills/routing.yaml"
AGENTS_DIR = PROJECT_ROOT / ".claude/agents"


@dataclass
class DryRunResult:
    """Routing-only verification result (no LLM/API calls)."""

    user_input: str
    matched_intent: Optional[str] = None
    pattern_id: Optional[str] = None  # A | B | C
    agents: list[str] = field(default_factory=list)
    header: Optional[str] = None
    expected_tools: list[str] = field(default_factory=list)
    flags: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


def _load_routing(routing_path: Path | str = ROUTING_PATH) -> dict:
    with Path(routing_path).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _agent_assets_exist(agent_name: str) -> tuple[bool, list[str]]:
    """Return (ok, missing_paths) for the agent's md/yaml files."""
    if agent_name in ("reviewer", "history-checker"):
        # 一部はSKILL.md内ロジックなので必ずしも .claude/agents/ 配下にない
        return True, []
    base = AGENTS_DIR / agent_name
    md = base / "agent.md"
    examples = base / "examples.yaml"
    missing = []
    if not md.exists():
        missing.append(str(md.relative_to(PROJECT_ROOT)))
    if not examples.exists():
        missing.append(str(examples.relative_to(PROJECT_ROOT)))
    return len(missing) == 0, missing


def _match_example(input_text: str, examples: list[dict]) -> Optional[dict]:
    """Find the routing example with the closest matching intent.

    Heuristic: prefer exact intent match, then substring match, then
    keyword overlap (Jaccard-ish on whitespace tokens).
    """
    if not input_text:
        return None
    s = input_text.strip()
    # 1) Exact
    for ex in examples:
        if ex.get("intent", "").strip() == s:
            return ex
    # 2) Substring
    for ex in examples:
        intent = ex.get("intent", "")
        if intent and (intent in s or s in intent):
            return ex
    # 3) Token overlap
    s_tokens = set(s)
    best = None
    best_overlap = 0
    for ex in examples:
        intent = ex.get("intent", "")
        overlap = len(s_tokens & set(intent))
        if overlap > best_overlap:
            best, best_overlap = ex, overlap
    return best if best_overlap >= 3 else None


def _expected_tools_for_agent(agent_name: str) -> list[str]:
    """Best-effort enumeration of tools the agent typically calls.

    We don't parse agent.md verbatim — instead, we use a stable mapping that
    mirrors the documented role of each agent in routing.yaml. This keeps the
    dry-run fast and deterministic.
    """
    # Stable mapping keyed by agent name. Add new entries as agents land.
    tool_map = {
        "screener": ["yahoo_finance.screen_stocks", "portfolio_io.load_portfolio"],
        "analyst": ["yahoo_finance.get_stock_info", "yahoo_finance.get_stock_detail",
                    "scoring.score_quality", "notes.load_notes"],
        "health-checker": ["portfolio_io.load_total_assets",
                           "yahoo_finance.get_stock_info", "morning_summary.detect_alerts"],
        "researcher": ["grok.search_market", "grok.search_x_sentiment", "llm.call_llm"],
        "strategist": ["portfolio_io.load_portfolio", "notes.load_notes",
                        "scoring.score_quality", "history_check.run"],
        "risk-assessor": ["yahoo_finance.get_stock_info"],
        "reviewer": ["llm.call_llm"],
    }
    return tool_map.get(agent_name, [])


def verify_routing(
    user_input: str,
    routing_path: Path | str = ROUTING_PATH,
) -> DryRunResult:
    """Routing-only validation. No LLM, no Yahoo Finance.

    Parameters
    ----------
    user_input : str
        Natural-language input as the user would type.
    routing_path : Path | str
        Override for tests.

    Returns
    -------
    DryRunResult
    """
    result = DryRunResult(user_input=user_input)
    try:
        data = _load_routing(routing_path)
    except (FileNotFoundError, yaml.YAMLError) as e:
        result.errors.append(f"failed to load routing.yaml: {e}")
        return result

    examples = data.get("examples", [])
    matched = _match_example(user_input, examples)
    if matched is None:
        result.errors.append(
            f"no matching example for input: {user_input!r}"
        )
        return result

    result.matched_intent = matched.get("intent")
    result.pattern_id = matched.get("pattern")
    result.header = matched.get("header")

    # agent or agents
    if "agent" in matched:
        agents = [matched["agent"]]
    elif "agents" in matched:
        agents = list(matched["agents"])
    elif "action" in matched:
        # direct action (note save / cash update etc.)
        result.flags["action"] = matched["action"]
        return result
    else:
        result.errors.append(
            f"matched intent {result.matched_intent!r} has no agent/agents/action"
        )
        return result
    result.agents = agents

    # Verify each agent's assets
    for ag in agents:
        ok, missing = _agent_assets_exist(ag)
        if not ok:
            result.errors.append(
                f"agent assets missing for {ag!r}: {missing}"
            )

    # Aggregate expected tools
    seen_tools = []
    for ag in agents:
        for tool in _expected_tools_for_agent(ag):
            if tool not in seen_tools:
                seen_tools.append(tool)
    result.expected_tools = seen_tools

    # Useful flags for downstream test/CI
    for flag in ("review", "history_check", "progressive", "mode"):
        if flag in matched:
            result.flags[flag] = matched[flag]

    # header missing for chain → warn (single-agent header is auto-generated)
    if len(agents) >= 2 and not result.header:
        result.warnings.append(
            f"chain pattern (agents={agents}) has no header field"
        )
    return result


def verify_routing_yaml_integrity(
    routing_path: Path | str = ROUTING_PATH,
) -> dict:
    """Static checks on routing.yaml (intent dup, agents dir existence, etc.)."""
    report = {"passed": True, "errors": [], "warnings": []}
    try:
        data = _load_routing(routing_path)
    except (FileNotFoundError, yaml.YAMLError) as e:
        report["passed"] = False
        report["errors"].append(f"load failed: {e}")
        return report

    examples = data.get("examples", [])

    # intent duplication
    intents = [ex.get("intent", "") for ex in examples if ex.get("intent")]
    counts = Counter(intents)
    dups = [i for i, c in counts.items() if c > 1]
    for d in dups:
        report["errors"].append(f"duplicate intent: {d!r}")

    # agents存在
    referenced_agents = set()
    for ex in examples:
        if "agent" in ex:
            referenced_agents.add(ex["agent"])
        elif "agents" in ex:
            referenced_agents.update(ex["agents"])
    for ag in referenced_agents:
        ok, missing = _agent_assets_exist(ag)
        if not ok:
            report["errors"].append(
                f"agent {ag!r} referenced but missing: {missing}"
            )

    # header missing for chain
    for ex in examples:
        agents = ex.get("agents")
        if agents and len(agents) >= 2 and not ex.get("header"):
            report["warnings"].append(
                f"chain intent {ex.get('intent')!r} missing header"
            )

    if report["errors"]:
        report["passed"] = False
    return report


__all__ = [
    "DryRunResult",
    "verify_routing",
    "verify_routing_yaml_integrity",
]
