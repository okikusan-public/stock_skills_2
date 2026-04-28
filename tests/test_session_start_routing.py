"""Tests for session-start auto-invoke hard gate (KIK-741)."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTING_PATH = REPO_ROOT / ".claude/skills/stock-skills/routing.yaml"
SKILL_PATH = REPO_ROOT / ".claude/skills/stock-skills/SKILL.md"


def _load_routing():
    with ROUTING_PATH.open() as f:
        return yaml.safe_load(f)


def test_skill_description_mentions_session_start_keywords():
    """SKILL.md frontmatter description に session-start キーワードが明記されている."""
    text = SKILL_PATH.read_text()
    frontmatter_end = text.find("---", 3)
    frontmatter = text[:frontmatter_end]
    assert "description:" in frontmatter
    desc_line = [l for l in frontmatter.splitlines() if l.startswith("description:")][0]
    for keyword in ["おはよう", "朝", "現状", "PF"]:
        assert keyword in desc_line, f"keyword '{keyword}' missing from SKILL.md description"


def test_skill_description_mentions_reconcile_hard_gate():
    """SKILL.md frontmatter description に reconcile_session_state ハードゲート言及."""
    text = SKILL_PATH.read_text()
    frontmatter_end = text.find("---", 3)
    frontmatter = text[:frontmatter_end]
    desc_line = [l for l in frontmatter.splitlines() if l.startswith("description:")][0]
    assert "reconcile_session_state" in desc_line or "hard gate" in desc_line


def test_routing_morning_summary_has_pf_state_required():
    """morning-summary mode の全エントリに pf_state_required: true がある."""
    data = _load_routing()
    found = []
    for ex in data["examples"]:
        if ex.get("mode") == "morning-summary":
            assert ex.get("pf_state_required") is True, (
                f"pf_state_required missing on {ex.get('intent')}"
            )
            found.append(ex["intent"])
    assert len(found) >= 2, f"Expected ≥2 morning-summary entries, got {found}"


def test_routing_routine_daily_has_pf_state_required():
    """routine-daily mode の全エントリに pf_state_required: true がある."""
    data = _load_routing()
    found = []
    for ex in data["examples"]:
        if ex.get("mode") == "routine-daily":
            assert ex.get("pf_state_required") is True, (
                f"pf_state_required missing on {ex.get('intent')}"
            )
            found.append(ex["intent"])
    assert len(found) >= 3, f"Expected ≥3 routine-daily entries, got {found}"


def test_routing_routine_weekly_has_pf_state_required():
    """routine-weekly mode の全エントリに pf_state_required: true がある."""
    data = _load_routing()
    found = []
    for ex in data["examples"]:
        if ex.get("mode") == "routine-weekly":
            assert ex.get("pf_state_required") is True, (
                f"pf_state_required missing on {ex.get('intent')}"
            )
            found.append(ex["intent"])
    assert len(found) >= 3, f"Expected ≥3 routine-weekly entries, got {found}"


def test_routing_pf_health_check_has_pf_state_required():
    """PF / ヘルスチェック / ストレステスト系に pf_state_required: true がある."""
    data = _load_routing()
    targets = ["PF大丈夫？", "ストレステストして"]
    found = {i: False for i in targets}
    for ex in data["examples"]:
        if ex.get("intent") in targets:
            assert ex.get("pf_state_required") is True, (
                f"pf_state_required missing on {ex.get('intent')}"
            )
            found[ex["intent"]] = True
    assert all(found.values()), f"Some PF/HC intents missing: {found}"


def test_routing_strategist_pf_decisions_have_pf_state_required():
    """投資判断系（入替/PF改善/売却/損切り/利確/プラン）に pf_state_required: true がある."""
    data = _load_routing()
    targets = [
        "入替提案して",
        "PFを改善したい",
        "プランモードで",
        "この株売るべき？",
        "損切りすべき？",
        "利確すべき？",
        "リスク確認して代わりを探して",
    ]
    found = {i: False for i in targets}
    for ex in data["examples"]:
        if ex.get("intent") in targets:
            assert ex.get("pf_state_required") is True, (
                f"pf_state_required missing on {ex.get('intent')}"
            )
            found[ex["intent"]] = True
    assert all(found.values()), f"Some strategist/PF-decision intents missing: {found}"


def test_routing_pf_state_NOT_on_pure_info_queries():
    """純粋な情報照会（VIX/トヨタ分析/最新ニュース）には pf_state_required を付けない."""
    data = _load_routing()
    info_intents = ["VIXは？", "トヨタってどう？", "最新ニュース教えて", "半導体業界を調べて"]
    for ex in data["examples"]:
        if ex.get("intent") in info_intents:
            assert ex.get("pf_state_required") is not True, (
                f"pf_state_required should NOT be on info query: {ex.get('intent')}"
            )


def test_routing_yaml_pf_state_field_documented_in_header_comment():
    """routing.yaml の冒頭コメントに pf_state_required フィールドが説明されている."""
    text = ROUTING_PATH.read_text()
    header_end = text.find("agents:")
    header = text[:header_end]
    assert "pf_state_required" in header, "pf_state_required field not documented in header comment"
    assert "KIK-741" in header, "KIK-741 reference missing in header comment"


def test_skill_md_session_start_section_intact():
    """SKILL.md の Session Start State Reconcile セクションが残っている."""
    text = SKILL_PATH.read_text()
    assert "## Session Start State Reconcile" in text
    assert "reconcile_session_state" in text
    assert "pf_state_required" in text


def test_morning_intent_includes_extended_keywords():
    """新規追加された extended morning キーワード（今日の状況/現状どう？）が登録されている."""
    data = _load_routing()
    intents = [ex.get("intent") for ex in data["examples"]]
    assert "今日の状況" in intents
    assert "現状どう？" in intents
