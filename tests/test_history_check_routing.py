"""Tests for History Check routing flag (KIK-740)."""

from pathlib import Path

import yaml


ROUTING_PATH = Path(__file__).resolve().parent.parent / ".claude/skills/stock-skills/routing.yaml"
SKILL_PATH = Path(__file__).resolve().parent.parent / ".claude/skills/stock-skills/SKILL.md"
ORCHESTRATION_PATH = Path(__file__).resolve().parent.parent / ".claude/skills/stock-skills/orchestration.yaml"


def _load_routing():
    with ROUTING_PATH.open() as f:
        return yaml.safe_load(f)


def test_routing_yaml_loads():
    """routing.yaml is valid YAML and has examples."""
    data = _load_routing()
    assert "examples" in data
    assert isinstance(data["examples"], list)
    assert len(data["examples"]) > 0


def test_history_check_added_to_sell_decisions():
    """売却判断系（売る/損切り/利確）に history_check: true が付与されている."""
    data = _load_routing()
    sell_intents = ["この株売るべき？", "損切りすべき？", "利確すべき？"]
    found = {i: False for i in sell_intents}
    for ex in data["examples"]:
        if ex.get("intent") in sell_intents:
            assert ex.get("history_check") is True, f"history_check missing on {ex.get('intent')}"
            found[ex["intent"]] = True
    assert all(found.values()), f"Some sell-decision intents missing: {found}"


def test_history_check_added_to_replacement():
    """入替・PF改善系に history_check: true が付与されている."""
    data = _load_routing()
    targets = ["入替提案して", "PFを改善したい", "プランモードで", "リスク確認して代わりを探して"]
    found = {i: False for i in targets}
    for ex in data["examples"]:
        if ex.get("intent") in targets:
            assert ex.get("history_check") is True, f"history_check missing on {ex.get('intent')}"
            found[ex["intent"]] = True
    assert all(found.values()), f"Some replacement intents missing: {found}"


def test_history_check_NOT_on_info_queries():
    """情報照会系（VIX/PF確認/単純分析）には history_check が付与されない."""
    data = _load_routing()
    info_intents = ["VIXは？", "PF大丈夫？", "トヨタってどう？", "TODO見せて", "おはよう", "朝サマリー"]
    for ex in data["examples"]:
        if ex.get("intent") in info_intents:
            assert ex.get("history_check") is not True, (
                f"history_check should NOT be on info query: {ex.get('intent')}"
            )


def test_history_check_NOT_on_routine():
    """routine-* mode には history_check が付与されない."""
    data = _load_routing()
    for ex in data["examples"]:
        mode = ex.get("mode", "")
        if mode.startswith("routine-") or mode == "morning-summary":
            assert ex.get("history_check") is not True, (
                f"history_check should NOT be on routine: {ex.get('intent')}"
            )


def test_skill_md_documents_history_check():
    """SKILL.md に History Check セクションが存在する."""
    text = SKILL_PATH.read_text()
    assert "### History Check" in text
    assert "KIK-740" in text
    assert "4LLM" in text or "4 LLM" in text


def test_skill_md_documents_graceful_degradation():
    """SKILL.md にgraceful degradationの仕様が記載されている."""
    text = SKILL_PATH.read_text()
    # APIキー未設定時のフォールバック挙動が言及されているか
    assert "graceful degradation" in text.lower() or "未設定" in text
    # 主要API_KEY名のいずれかが含まれる
    assert any(k in text for k in ["OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"])


def test_skill_md_documents_required_dual_view():
    """SKILL.md に「両論併記必須」「反証必須」のルールが記載されている."""
    text = SKILL_PATH.read_text()
    assert "両論併記" in text
    assert "反証" in text


def test_skill_md_differentiates_from_deepthink():
    """SKILL.md に DeepThink との差別化が記載されている."""
    text = SKILL_PATH.read_text()
    # History Check セクション内で DeepThink と比較されている
    history_section_start = text.find("### History Check")
    history_section_end = text.find("### Reviewer 起動方針", history_section_start)
    section = text[history_section_start:history_section_end]
    assert "DeepThink" in section
    # 起動条件・ラウンド数等の差別化記載
    assert "自動" in section
    assert "ラウンド" in section or "複数" in section


def test_orchestration_yaml_has_history_check():
    """orchestration.yaml に history_check の自動発動定義がある."""
    with ORCHESTRATION_PATH.open() as f:
        data = yaml.safe_load(f)
    assert "history_check" in data
    hc = data["history_check"]
    # 必須フィールド
    assert "trigger" in hc
    assert "llm_layout" in hc
    assert "skip_conditions" in hc
    assert "cost_guardrail" in hc


def test_orchestration_history_check_triggers():
    """history_check の trigger に投資判断キーワードと routing_flag が含まれる."""
    with ORCHESTRATION_PATH.open() as f:
        data = yaml.safe_load(f)
    triggers = data["history_check"]["trigger"]
    # routing_flag トリガー存在
    flag_triggers = [t for t in triggers if "routing_flag" in t]
    assert len(flag_triggers) >= 1
    # keyword_detect トリガー存在
    keyword_triggers = [t for t in triggers if "keyword_detect" in t]
    assert len(keyword_triggers) >= 1
    # 主要キーワード（売却・損切り・入替）が含まれる
    keywords = keyword_triggers[0]["keyword_detect"]
    for must in ["売却", "損切り", "入替"]:
        assert must in keywords, f"keyword '{must}' missing"


def test_orchestration_history_check_llm_layout():
    """llm_layout に Claude（必須）+ オプション3LLMが定義されている."""
    with ORCHESTRATION_PATH.open() as f:
        data = yaml.safe_load(f)
    layout = data["history_check"]["llm_layout"]
    llms = {item["llm"]: item for item in layout}
    # 4つのLLMが定義されている
    assert set(llms.keys()) == {"claude", "gpt", "gemini", "grok"}
    # Claudeは required: true（必須）
    assert llms["claude"].get("required") is True
    # オプション3LLMには env_key が指定されている
    for llm_name in ["gpt", "gemini", "grok"]:
        assert "env_key" in llms[llm_name]


def test_orchestration_history_check_skip_conditions():
    """routine_mode と morning_summary でスキップする設定がある."""
    with ORCHESTRATION_PATH.open() as f:
        data = yaml.safe_load(f)
    skip = data["history_check"]["skip_conditions"]
    contexts = [s.get("context") for s in skip if "context" in s]
    assert "routine_mode" in contexts
    assert "morning_summary" in contexts
    assert "history_check_already_executed" in contexts


def test_skill_md_documents_data_insufficient_fallback():
    """SKILL.md にデータ不足時のフォールバック仕様が記載されている."""
    text = SKILL_PATH.read_text()
    assert "データ不足" in text
    assert "該当事例なし" in text or "推測" in text
