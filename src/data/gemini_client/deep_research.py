"""Gemini Deep Research API wrapper (KIK-731).

Provides single-shot DeepResearch task invocation with:
- Cost guards: estimated cost before execution, monthly budget check
- Wall-time guard: 30 min hard cancel
- Hard cap: 1 task per call (no recursion)
- Meta logging: appends one record per call to data/logs/deepthink_meta.jsonl
- Disable switch: DEEPTHINK_DR_ENABLED=off bypasses execution

Important: This is a tool, not an agent. The caller (DeepThink Step 3)
decides when to invoke based on config/tools.yaml `when`/`strength`/`not_for`.

API: POST https://generativelanguage.googleapis.com/v1beta/{model}:generateContent
Model: deep-research-preview-04-2026 (Google Deep Research)
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
# Hard wall-time per call. Gemini DR API allows up to 60 min; we cap at 30 min.
_DEFAULT_TIMEOUT_SEC = 1800
_POLL_INTERVAL_SEC = 10


def is_available() -> bool:
    """True if GEMINI_API_KEY is set."""
    return bool(os.environ.get("GEMINI_API_KEY"))


def is_deep_research_enabled() -> bool:
    """False if DEEPTHINK_DR_ENABLED=off (kill switch)."""
    return os.environ.get("DEEPTHINK_DR_ENABLED", "on").lower() != "off"


def gemini_deep_research(
    theme: str,
    depth: str = "medium",
    budget_usd: float = 3.0,
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
    model: str = _DEFAULT_MODEL,
) -> dict[str, Any]:
    """Run a single Gemini Deep Research task.

    Parameters
    ----------
    theme : str
        Research theme (e.g. "AI半導体 2026 市場動向").
    depth : str
        "light" / "medium" / "deep". Affects estimated cost only; DR API
        decides actual search depth internally.
    budget_usd : float
        Per-call hard cap. Returned status="budget_exceeded" if estimate > budget_usd.
    timeout_sec : int
        Wall-time hard cancel (default 1800s = 30 min).
    model : str
        DR model name (default deep-research-preview-04-2026).

    Returns
    -------
    dict with keys:
        text          : str
        sources       : list[str]   # citation URLs
        cost_usd      : float       # estimated cost
        duration_sec  : float
        status        : "ok" | "budget_exceeded" | "disabled" | "no_api_key" | "timeout" | "error"
        error_message : str | None
    """
    started_at = time.time()
    estimate = _DEPTH_COST_USD.get(depth, _DEPTH_COST_USD["medium"])

    # Kill-switch
    if not is_deep_research_enabled():
        return _make_result(
            theme, depth, estimate, started_at,
            status="disabled",
            error_message="DEEPTHINK_DR_ENABLED=off",
        )

    # Per-call budget guard
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

    # Submit DR task and poll until done or wall-time exceeded.
    try:
        text, sources = _run_deep_research(api_key, model, theme, depth, timeout_sec)
    except _DRTimeout:
        return _make_result(
            theme, depth, estimate, started_at,
            status="timeout",
            error_message=f"wall_time exceeded {timeout_sec}s",
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
    )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


class _DRTimeout(Exception):
    pass


def _run_deep_research(
    api_key: str, model: str, theme: str, depth: str, timeout_sec: int,
) -> tuple[str, list[str]]:
    """Submit DR task and poll for completion. Raises _DRTimeout on wall-time exceed."""
    url = f"{_API_BASE}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": theme}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"depth": depth},
    }
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    body = response.json()

    # If response has operation name (background task), poll. Otherwise return inline.
    op_name = body.get("name")
    if op_name:
        return _poll_operation(api_key, op_name, timeout_sec)

    return _extract_text_and_sources(body)


def _poll_operation(api_key: str, op_name: str, timeout_sec: int) -> tuple[str, list[str]]:
    """Poll the long-running operation until done or wall-time exceed."""
    deadline = time.time() + timeout_sec
    poll_url = f"{_API_BASE}/{op_name}?key={api_key}"
    while time.time() < deadline:
        time.sleep(_POLL_INTERVAL_SEC)
        r = requests.get(poll_url, timeout=30)
        r.raise_for_status()
        body = r.json()
        if body.get("done"):
            return _extract_text_and_sources(body.get("response", body))
    raise _DRTimeout()


def _extract_text_and_sources(body: dict) -> tuple[str, list[str]]:
    """Extract text and citation URLs from Gemini response body."""
    candidates = body.get("candidates", [])
    if not candidates:
        return "", []
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(p.get("text", "") for p in parts if "text" in p)
    grounding = candidates[0].get("groundingMetadata", {})
    chunks = grounding.get("groundingChunks", []) or []
    sources = []
    for c in chunks:
        web = c.get("web", {})
        uri = web.get("uri")
        if uri:
            sources.append(uri)
    return text, sources


def _make_result(
    theme: str, depth: str, cost_usd: float, started_at: float,
    *,
    status: str,
    text: str = "",
    sources: list[str] | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Build result dict and append to meta log (best-effort)."""
    duration = time.time() - started_at
    result = {
        "text": text,
        "sources": sources or [],
        "cost_usd": cost_usd,
        "duration_sec": round(duration, 2),
        "status": status,
        "error_message": error_message,
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
            "sources_count": len(result["sources"]),
            "duration_sec": result["duration_sec"],
            "error_message": result.get("error_message"),
        }
        with open(_META_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        # Don't fail the call on log write failure.
        print(f"[gemini_dr] meta log write failed: {exc}", file=sys.stderr)
