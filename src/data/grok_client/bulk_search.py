"""Grok bulk search wrappers (KIK-732).

Run multiple Grok searches sequentially with rate-limit-friendly pacing.
Two flavors:
- bulk_x_search: X firehose 並列（投資家センチメント・$cashtag・特定 handle）
- bulk_web_search: Grok web 並列（速報重視）

Sequential execution with sleep(0.5) between calls keeps us within Grok's
default rate limits without needing asyncio. Each call returns sources
when available and respects max_sources_per_call to cap source-billing.

Meta logging appends to data/logs/deepthink_meta.jsonl (KIK-731 共有).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.data.deepthink_meta import META_LOG_PATH as _META_LOG_PATH
from src.data.grok_client._common import (
    _API_URL,
    _DEFAULT_MODEL,
    _get_api_key,
    is_available,
)
_DEFAULT_PARALLEL_INTERVAL_SEC = 0.5
_DEFAULT_TIMEOUT_PER_CALL = 30
# 1 call ≈ ~$0.50 (10 sources × $0.025 + tokens). Used for meta logging.
_COST_PER_CALL_USD = 0.5


def is_dry_run() -> bool:
    """KIK-737: True if DEEPTHINK_DRY_RUN=1."""
    import os
    return os.environ.get("DEEPTHINK_DRY_RUN", "").lower() in ("1", "on", "true")


def bulk_x_search(
    queries: list[str],
    max_sources_per_call: int = 10,
    timeout_sec: int = _DEFAULT_TIMEOUT_PER_CALL,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run multiple Grok x_search queries sequentially.

    Parameters
    ----------
    queries : list[str]
        Each query is a free-text search string (e.g. "$NVDA earnings reaction").
    max_sources_per_call : int
        Cap on Grok source citations per call to control source-based billing.
    timeout_sec : int
        Per-call timeout.

    Returns
    -------
    dict with keys:
        results          : list[{"query", "text", "sources", "status"}]
        total_cost_usd   : float
        total_calls      : int
        successful_calls : int
    """
    return _bulk_search(
        queries,
        tools=[{"type": "x_search"}],
        tool_label="bulk_x_search",
        max_sources_per_call=max_sources_per_call,
        timeout_sec=timeout_sec,
        dry_run=dry_run,
    )


def bulk_web_search(
    queries: list[str],
    allowed_domains: list[str] | None = None,
    max_sources_per_call: int = 10,
    timeout_sec: int = _DEFAULT_TIMEOUT_PER_CALL,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run multiple Grok web_search queries sequentially.

    Parameters
    ----------
    queries : list[str]
        Each query is a free-text search string.
    allowed_domains : list[str], optional
        Restrict results to these domains (e.g. ["sec.gov", "reuters.com"]).
    max_sources_per_call : int
        Cap on Grok source citations per call.
    timeout_sec : int
        Per-call timeout.
    """
    web_tool: dict[str, Any] = {"type": "web_search"}
    if allowed_domains:
        web_tool["allowed_domains"] = allowed_domains[:5]  # API limit: 5
    return _bulk_search(
        queries,
        tools=[web_tool],
        tool_label="bulk_web_search",
        max_sources_per_call=max_sources_per_call,
        timeout_sec=timeout_sec,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _bulk_search(
    queries: list[str],
    *,
    tools: list[dict],
    tool_label: str,
    max_sources_per_call: int,
    dry_run: bool = False,
    timeout_sec: int,
) -> dict[str, Any]:
    started_at = time.time()

    # KIK-737: dry_run（個別引数 OR 環境変数）→ API 不要、estimate のみ返す
    if dry_run or is_dry_run():
        dry_results = [
            {"query": q, "text": "", "sources": [], "status": "dry_run"}
            for q in queries
        ]
        return _make_bulk_result(
            queries, dry_results, tool_label, started_at,
            successful=0, error="dry_run=True (no API call)",
            dry_run=True,
        )

    api_key = _get_api_key()
    if not api_key:
        return _make_bulk_result(
            queries, [], tool_label, started_at,
            error="XAI_API_KEY not set",
        )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    results = []
    successful = 0
    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(_DEFAULT_PARALLEL_INTERVAL_SEC)
        result = _call_one(headers, query, tools, max_sources_per_call, timeout_sec)
        if result["status"] == "ok":
            successful += 1
        results.append(result)

    return _make_bulk_result(queries, results, tool_label, started_at, successful=successful)


def _call_one(
    headers: dict, query: str, tools: list[dict],
    max_sources_per_call: int, timeout_sec: int,
) -> dict[str, Any]:
    payload = {
        "model": _DEFAULT_MODEL,
        "input": query,
        "tools": tools,
    }
    try:
        r = requests.post(_API_URL, headers=headers, json=payload, timeout=timeout_sec)
        if r.status_code != 200:
            return {
                "query": query, "text": "", "sources": [],
                "status": f"http_{r.status_code}",
            }
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        return {
            "query": query, "text": "", "sources": [],
            "status": f"error:{type(exc).__name__}",
        }

    text = _extract_text(body)
    sources = _extract_sources(body)[:max_sources_per_call]
    return {"query": query, "text": text, "sources": sources, "status": "ok"}


def _extract_text(body: dict) -> str:
    """Best-effort text extraction from Grok responses API output."""
    out = body.get("output")
    if isinstance(out, list):
        chunks = []
        for item in out:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                for c in item.get("content", []) or []:
                    if isinstance(c, dict) and "text" in c:
                        chunks.append(c["text"])
        if chunks:
            return "\n".join(chunks)
    text = body.get("output_text") or body.get("text")
    if isinstance(text, str):
        return text
    return ""


def _extract_sources(body: dict) -> list[str]:
    """Best-effort source URL extraction (citations array)."""
    citations = body.get("citations") or []
    urls = []
    for c in citations:
        if isinstance(c, str):
            urls.append(c)
        elif isinstance(c, dict):
            uri = c.get("url") or c.get("uri")
            if uri:
                urls.append(uri)
    return urls


def _make_bulk_result(
    queries: list[str], results: list[dict], tool_label: str, started_at: float,
    *, successful: int = 0, error: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    duration = time.time() - started_at
    total_cost = round(_COST_PER_CALL_USD * successful, 3)
    # KIK-737: estimate_cost_usd はクエリ数 × per-call で計算（dry_run でも返す）
    estimate_cost = round(_COST_PER_CALL_USD * len(queries), 3)
    out = {
        "results": results,
        "total_cost_usd": total_cost,
        "estimate_cost_usd": estimate_cost,
        "total_calls": len(queries),
        "successful_calls": successful,
        "duration_sec": round(duration, 2),
        "error": error,
        "dry_run": dry_run,
    }
    _append_meta_log(tool_label, queries, out)
    return out


def _append_meta_log(tool: str, queries: list[str], result: dict) -> None:
    """Best-effort append to data/logs/deepthink_meta.jsonl."""
    try:
        _META_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "query_count": len(queries),
            "successful_calls": result.get("successful_calls", 0),
            "cost_usd": result.get("total_cost_usd", 0.0),
            "duration_sec": result.get("duration_sec", 0.0),
            "error": result.get("error"),
        }
        with open(_META_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[grok_bulk] meta log write failed: {exc}", file=sys.stderr)


__all__ = ["bulk_x_search", "bulk_web_search", "is_available"]
