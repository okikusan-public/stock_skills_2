"""Gemini Deep Research API wrapper (KIK-731 / KIK-733).

Single-shot DeepResearch task invocation with:
- Cost guards: estimated cost before execution
- Wall-time guard: 30 min hard cancel
- Hard cap: 1 task per call (no recursion)
- Meta logging: appends one record per call to data/logs/deepthink_meta.jsonl
- Disable switch: DEEPTHINK_DR_ENABLED=off bypasses execution

KIK-733: API contract corrected.
- Endpoint: POST /v1beta/interactions  (NOT generateContent — DR model only supports Interactions API)
- Required body: {"agent": "<dr-model>", "input": [{"role":"user","content":<theme>}], "background": true}
- Polling: GET /v1beta/interactions/{id}  (NOT operations/*)
- Response: outputs[].content[].text + outputs[].annotations[].url

Important: This is a tool, not an agent. The caller (DeepThink Step 3)
decides when to invoke based on config/tools.yaml `when`/`strength`/`not_for`.
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
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from src.data.deepthink_meta import META_LOG_PATH as _META_LOG_PATH

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "deep-research-preview-04-2026"

# Estimated cost per depth (USD). Used for pre-execution display + monthly tracking.
_DEPTH_COST_USD = {
    "light": 1.5,
    "medium": 2.5,
    "deep": 5.0,
}
# KIK-737: Gemini long-context tier pricing (USD per 1k tokens). 後で yaml 化可能。
_GEMINI_LONG_CONTEXT_PRICING_PER_1K = {
    "input_tokens": 0.00125,
    "output_tokens": 0.005,
    "thinking_tokens": 0.005,
    "tool_tokens": 0.0001,
}

# KIK-737: Hard wall-time. light/medium=15min, deep=30min。
_WALL_TIME_BY_DEPTH = {
    "light": 900,
    "medium": 900,
    "deep": 1800,
}
_DEFAULT_TIMEOUT_SEC = _WALL_TIME_BY_DEPTH["medium"]  # 後方互換
_POLL_INTERVAL_SEC = 10


def is_available() -> bool:
    """True if GEMINI_API_KEY is set."""
    return bool(os.environ.get("GEMINI_API_KEY"))


def is_deep_research_enabled() -> bool:
    """False if DEEPTHINK_DR_ENABLED=off (kill switch)."""
    return os.environ.get("DEEPTHINK_DR_ENABLED", "on").lower() != "off"


def is_dry_run() -> bool:
    """KIK-737: True if DEEPTHINK_DRY_RUN=1 (forces dry_run on every call)."""
    return os.environ.get("DEEPTHINK_DRY_RUN", "").lower() in ("1", "on", "true")


def calc_actual_cost_usd(usage_metadata: dict) -> float:
    """KIK-737: Compute actual cost from Gemini DR usage_metadata.

    Expected keys (Gemini /v1beta/interactions response):
      input_tokens, output_tokens, thinking_tokens, tool_tokens
    Missing keys are treated as 0.
    """
    if not isinstance(usage_metadata, dict):
        return 0.0
    total = 0.0
    for key, price_per_1k in _GEMINI_LONG_CONTEXT_PRICING_PER_1K.items():
        tokens = float(usage_metadata.get(key) or 0)
        total += (tokens / 1000.0) * price_per_1k
    return round(total, 4)


def gemini_deep_research(
    theme: str,
    depth: str = "medium",
    budget_usd: float = 3.0,
    timeout_sec: int | None = None,
    model: str = _DEFAULT_MODEL,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run a single Gemini Deep Research task via /v1beta/interactions.

    KIK-737:
      - timeout_sec=None で depth 連動デフォルト（light/medium=15min, deep=30min）
      - dry_run=True で API を呼ばず estimate のみ返す
      - DEEPTHINK_DRY_RUN=1 環境変数で全コール強制 dry_run

    Returns
    -------
    dict with keys:
        text             : str
        sources          : list[str]
        cost_usd         : float    # estimated cost (pre-execution)
        actual_cost_usd  : float    # 実トークン基準実コスト (KIK-737, status=ok のみ)
        duration_sec     : float
        status           : "ok" | "budget_exceeded" | "disabled" | "no_api_key" | "timeout" | "error" | "dry_run"
        error_message    : str | None
        interaction_id   : str | None
        usage_metadata   : dict | None   # KIK-737
    """
    started_at = time.time()
    estimate = _DEPTH_COST_USD.get(depth, _DEPTH_COST_USD["medium"])
    if timeout_sec is None:
        timeout_sec = _WALL_TIME_BY_DEPTH.get(depth, _WALL_TIME_BY_DEPTH["medium"])

    # KIK-737: dry_run（個別引数 OR 環境変数）→ API 不要
    if dry_run or is_dry_run():
        return _make_result(
            theme, depth, estimate, started_at,
            status="dry_run",
            error_message="dry_run=True (no API call)",
        )

    if not is_deep_research_enabled():
        return _make_result(
            theme, depth, estimate, started_at,
            status="disabled",
            error_message="DEEPTHINK_DR_ENABLED=off",
        )

    if estimate > budget_usd:
        return _make_result(
            theme, depth, estimate, started_at,
            status="budget_exceeded",
            error_message=f"estimate ${estimate:.2f} > budget ${budget_usd:.2f}",
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return _make_result(
            theme, depth, 0.0, started_at,
            status="no_api_key",
            error_message="GEMINI_API_KEY not set",
        )

    try:
        text, sources, interaction_id, usage_metadata = _run_deep_research(
            api_key, model, theme, timeout_sec,
        )
    except _DRTimeout as exc:
        return _make_result(
            theme, depth, estimate, started_at,
            status="timeout",
            error_message=f"wall_time exceeded {timeout_sec}s",
            interaction_id=getattr(exc, "interaction_id", None),
        )
    except (requests.RequestException, KeyError, ValueError) as exc:
        return _make_result(
            theme, depth, 0.0, started_at,
            status="error",
            error_message=f"{type(exc).__name__}: {exc}",
        )

    return _make_result(
        theme, depth, estimate, started_at,
        status="ok",
        text=text,
        sources=sources,
        interaction_id=interaction_id,
        usage_metadata=usage_metadata,
    )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


class _DRTimeout(Exception):
    """Raised when polling exceeds wall_time."""

    def __init__(self, message: str = "", interaction_id: str | None = None):
        super().__init__(message)
        self.interaction_id = interaction_id


def _run_deep_research(
    api_key: str, model: str, theme: str, timeout_sec: int,
) -> tuple[str, list[str], str | None, dict]:
    """Submit DR interaction and poll until done or wall-time exceed.

    KIK-733: Uses /v1beta/interactions (NOT generateContent).
    KIK-737: Returns usage_metadata as 4th tuple member.
    """
    submit_url = f"{_API_BASE}/interactions?key={api_key}"
    payload = {
        "agent": model,
        "input": [{"role": "user", "content": theme}],
        "background": True,
    }
    response = requests.post(submit_url, json=payload, timeout=60)
    response.raise_for_status()
    submit_body = response.json()

    interaction_id = submit_body.get("id")
    initial_status = submit_body.get("status")

    if initial_status == "completed":
        text, sources = _extract_text_and_sources(submit_body)
        usage = submit_body.get("usage_metadata") or {}
        return text, sources, interaction_id, usage

    if not interaction_id:
        raise ValueError(f"submit response missing 'id': {submit_body}")

    text, sources, usage = _poll_interaction(api_key, interaction_id, timeout_sec)
    return text, sources, interaction_id, usage


def _poll_interaction(
    api_key: str, interaction_id: str, timeout_sec: int,
) -> tuple[str, list[str], dict]:
    """Poll the long-running interaction until completed or deadline.

    KIK-733: Uses /v1beta/interactions/{id} (NOT operations/*).
    KIK-737: Returns usage_metadata.
    """
    deadline = time.time() + timeout_sec
    poll_url = f"{_API_BASE}/interactions/{interaction_id}?key={api_key}"
    while time.time() < deadline:
        time.sleep(_POLL_INTERVAL_SEC)
        r = requests.get(poll_url, timeout=30)
        r.raise_for_status()
        body = r.json()
        status = body.get("status")
        if status == "completed":
            text, sources = _extract_text_and_sources(body)
            usage = body.get("usage_metadata") or {}
            return text, sources, usage
        if status == "failed":
            raise ValueError(
                f"interaction failed: {body.get('error') or body.get('status')}"
            )
        # status == "in_progress" → keep polling
    raise _DRTimeout(interaction_id=interaction_id)


def _extract_text_and_sources(body: dict) -> tuple[str, list[str]]:
    """Extract text and citation URLs from Gemini DR /v1beta/interactions response.

    KIK-733: outputs[].content[].text  +  outputs[].annotations[].url

    Response shape:
      {
        "id": "v1_...",
        "status": "completed",
        "outputs": [
          {
            "type": "text",
            "content": [{"text": "..."}],
            "annotations": [{"url": "...", "title": "..."}]
          },
          ...
        ],
        "usage_metadata": {...}
      }
    """
    outputs = body.get("outputs") or []
    text_parts: list[str] = []
    sources: list[str] = []
    seen_urls: set[str] = set()

    for out in outputs:
        if not isinstance(out, dict):
            continue
        # Text content
        for c in out.get("content") or []:
            if isinstance(c, dict) and "text" in c:
                text_parts.append(c["text"])
        # Citation annotations
        for ann in out.get("annotations") or []:
            if isinstance(ann, dict):
                url = ann.get("url") or ann.get("uri")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    sources.append(url)

    text = "\n".join(text_parts)
    return text, sources


def _make_result(
    theme: str, depth: str, cost_usd: float, started_at: float,
    *,
    status: str,
    text: str = "",
    sources: list[str] | None = None,
    error_message: str | None = None,
    interaction_id: str | None = None,
    usage_metadata: dict | None = None,
) -> dict[str, Any]:
    """Build result dict and append to meta log (best-effort)."""
    duration = time.time() - started_at
    actual_cost = calc_actual_cost_usd(usage_metadata) if usage_metadata else 0.0
    result = {
        "text": text,
        "sources": sources or [],
        "cost_usd": cost_usd,
        "actual_cost_usd": actual_cost,
        "duration_sec": round(duration, 2),
        "status": status,
        "error_message": error_message,
        "interaction_id": interaction_id,
        "usage_metadata": usage_metadata,
    }
    _append_meta_log(theme, depth, result)
    return result


def _append_meta_log(theme: str, depth: str, result: dict) -> None:
    """Best-effort append to data/logs/deepthink_meta.jsonl."""
    try:
        _META_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": "gemini_deep_research",
            "theme": theme,
            "depth": depth,
            "status": result["status"],
            "cost_usd": result["cost_usd"],
            "actual_cost_usd": result.get("actual_cost_usd", 0.0),
            "sources_count": len(result["sources"]),
            "duration_sec": result["duration_sec"],
            "error_message": result.get("error_message"),
            "interaction_id": result.get("interaction_id"),
        }
        with open(_META_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[gemini_dr] meta log write failed: {exc}", file=sys.stderr)
