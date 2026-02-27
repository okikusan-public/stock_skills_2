"""AI-driven knowledge graph linking (KIK-434).

When nodes are saved (Research, Report, Note), an LLM reads the content,
evaluates existing graph nodes, and assigns semantic relationships:
INFLUENCES, CONTRADICTS, CONTEXT_OF, INFORMS, SUPPORTS.

Requires ANTHROPIC_API_KEY environment variable.
Graceful degradation: no-op when API key is unset, Neo4j is unreachable,
or any exception occurs.
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5-20251001"
_SUPPORTED_REL_TYPES = {"INFLUENCES", "CONTRADICTS", "CONTEXT_OF", "INFORMS", "SUPPORTS"}
_CONFIDENCE_THRESHOLD = 0.6
_MAX_CANDIDATES = 10
_LLM_TIMEOUT = 20  # seconds


from src.data.graph_store._common import _safe_id  # noqa: E402 (KIK-507: dedup)


# ---------------------------------------------------------------------------
# AIGraphLinker
# ---------------------------------------------------------------------------

class AIGraphLinker:
    """LLM-driven semantic relationship engine (KIK-434).

    Calls the Anthropic Messages API (claude-haiku) to determine
    which relationships should exist between a new node and existing nodes.
    """

    def is_available(self) -> bool:
        """Return True if ANTHROPIC_API_KEY is set."""
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def link_on_save(self, new_node: dict, candidates: list[dict]) -> list[dict]:
        """Determine semantic relationships via LLM.

        Parameters
        ----------
        new_node : dict
            Keys: id, type, target/symbol, summary/content
        candidates : list[dict]
            Each: id, type, summary  (max _MAX_CANDIDATES used)

        Returns
        -------
        list[dict]
            Each: {rel_type, to_id, confidence, reason}
            Empty when unavailable or no relationships found.
        """
        if not self.is_available() or not candidates:
            return []
        prompt = self._build_prompt(new_node, candidates[:_MAX_CANDIDATES])
        raw = self._call_llm(prompt)
        if not raw:
            return []
        return self._parse_relationships(raw, candidates[:_MAX_CANDIDATES])

    def _build_prompt(self, new_node: dict, candidates: list[dict]) -> str:
        """Build the relationship detection prompt."""
        node_type = new_node.get("type", "Node")
        target = new_node.get("target") or new_node.get("symbol") or ""
        description = (new_node.get("summary") or new_node.get("content") or "")[:300]
        node_desc = f"種別: {node_type}\n対象: {target}\n内容要約: {description}"

        cand_lines = []
        for i, c in enumerate(candidates):
            ctype = c.get("type", "?")
            cid = c.get("id", "?")
            csummary = str(c.get("summary") or c.get("content") or c.get("verdict") or "")[:200]
            cand_lines.append(f"[candidate_{i}] {ctype} ({cid}): {csummary}")
        cands_text = "\n".join(cand_lines)

        return (
            "あなたは投資知識グラフのリレーション判定エンジンです。\n\n"
            f"## 新ノード\n{node_desc}\n\n"
            f"## 既存ノード候補\n{cands_text}\n\n"
            "## タスク\n"
            "新ノードと各候補の意味的関係を判定してください。\n"
            f"confidence が {_CONFIDENCE_THRESHOLD} 未満の関係は含めない。"
            "関係がない場合は [] を返す。\n\n"
            "## 関係種別\n"
            "- INFLUENCES: 新ノードが既存ノードの価値・見通しに直接影響する\n"
            "- CONTRADICTS: 新ノードが既存ノードの投資テーゼと矛盾する\n"
            "- CONTEXT_OF: 新ノードが既存ノードを解釈するコンテキストになる\n"
            "- INFORMS: 新ノードが既存ノードの判断材料を提供する\n"
            "- SUPPORTS: 新ノードが既存ノードの投資テーゼを支持する\n\n"
            "## 出力形式（JSON配列のみ、説明・コードブロック不要）\n"
            '[{"rel_type":"INFLUENCES","to_id":"candidate_0","confidence":0.85,"reason":"理由"}]'
        )

    def _call_llm(self, prompt: str, timeout: int = _LLM_TIMEOUT) -> str:
        """Call Anthropic Messages API.  Returns text or '' on failure."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return ""
        try:
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": _MODEL,
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = requests.post(_API_URL, headers=headers, json=payload, timeout=timeout)
            if resp.status_code != 200:
                return ""
            data = resp.json()
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block.get("text", "")
            return ""
        except Exception:
            return ""

    def _parse_relationships(self, raw: str, candidates: list[dict]) -> list[dict]:
        """Parse LLM response into relationship dicts, filtering invalid entries."""
        # Extract JSON array from raw text (may contain markdown fences)
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1 or end < start:
            return []
        try:
            items = json.loads(raw[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(items, list):
            return []

        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rel_type = item.get("rel_type", "")
            candidate_ref = str(item.get("to_id", ""))
            try:
                confidence = float(item.get("confidence", 0))
            except (TypeError, ValueError):
                continue
            reason = str(item.get("reason", ""))

            if rel_type not in _SUPPORTED_REL_TYPES:
                continue
            if confidence < _CONFIDENCE_THRESHOLD:
                continue

            # Map "candidate_N" → actual node id
            to_id = None
            if candidate_ref.startswith("candidate_"):
                idx_str = candidate_ref[len("candidate_"):]
                if idx_str.isdigit():
                    idx = int(idx_str)
                    if 0 <= idx < len(candidates):
                        to_id = candidates[idx].get("id")
            if not to_id:
                continue

            result.append({
                "rel_type": rel_type,
                "to_id": to_id,
                "confidence": confidence,
                "reason": reason,
            })
        return result


# ---------------------------------------------------------------------------
# Public helper functions (called from history_store / note_manager)
# ---------------------------------------------------------------------------

def link_research(
    research_id: str,
    research_type: str,
    target: str,
    summary: str,
) -> int:
    """Link a newly saved Research node to portfolio holdings via LLM (KIK-434).

    Fetches portfolio holdings as candidates, calls the LLM, and writes
    INFLUENCES / INFORMS / CONTEXT_OF etc. relationships to Neo4j.

    Returns number of relationships created (0 on any failure).
    """
    linker = AIGraphLinker()
    if not linker.is_available():
        return 0
    try:
        from src.data.graph_query import get_portfolio_holdings_for_linking
        from src.data.graph_store import create_ai_relationship
        candidates = get_portfolio_holdings_for_linking()
        if not candidates:
            return 0
        new_node = {
            "id": research_id,
            "type": "Research",
            "target": target,
            "summary": summary,
        }
        relationships = linker.link_on_save(new_node, candidates)
        count = 0
        for rel in relationships:
            if create_ai_relationship(
                research_id, rel["to_id"], rel["rel_type"],
                rel["confidence"], rel["reason"],
            ):
                count += 1
        return count
    except Exception:
        return 0


def link_note(
    note_id: str,
    symbol: Optional[str],
    note_type: str,
    content: str,
) -> int:
    """Link a newly saved Note node to related nodes for the same symbol (KIK-434).

    Fetches Report + HealthCheck for the same symbol as candidates.
    Returns number of relationships created (0 on any failure).
    """
    linker = AIGraphLinker()
    if not linker.is_available() or not symbol:
        return 0
    try:
        from src.data.graph_query import get_nodes_for_symbol
        from src.data.graph_store import create_ai_relationship
        candidates = get_nodes_for_symbol(symbol)
        if not candidates:
            return 0
        new_node = {
            "id": note_id,
            "type": "Note",
            "symbol": symbol,
            "target": symbol,
            "summary": content,
        }
        relationships = linker.link_on_save(new_node, candidates)
        count = 0
        for rel in relationships:
            if create_ai_relationship(
                note_id, rel["to_id"], rel["rel_type"],
                rel["confidence"], rel["reason"],
            ):
                count += 1
        return count
    except Exception:
        return 0


def link_report(
    report_id: str,
    symbol: str,
    sector: str,
    score: float,
    verdict: str,
) -> int:
    """Link a newly saved Report node to Notes and same-sector Research (KIK-434).

    Returns number of relationships created (0 on any failure).
    """
    linker = AIGraphLinker()
    if not linker.is_available():
        return 0
    try:
        from src.data.graph_query import get_nodes_for_symbol, get_industry_research_for_linking
        from src.data.graph_store import create_ai_relationship
        candidates = get_nodes_for_symbol(symbol, include_notes=True)
        if sector:
            candidates += get_industry_research_for_linking(sector)
        candidates = candidates[:_MAX_CANDIDATES]
        if not candidates:
            return 0
        new_node = {
            "id": report_id,
            "type": "Report",
            "symbol": symbol,
            "target": symbol,
            "summary": f"score={score:.1f} {verdict}",
        }
        relationships = linker.link_on_save(new_node, candidates)
        count = 0
        for rel in relationships:
            if create_ai_relationship(
                report_id, rel["to_id"], rel["rel_type"],
                rel["confidence"], rel["reason"],
            ):
                count += 1
        return count
    except Exception:
        return 0
