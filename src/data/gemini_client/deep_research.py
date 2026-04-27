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
    """Run a single Gemini Deep Research task via /v1beta/interactions.

    Returns
    -------
    dict with keys:
        text          : str
        sources       : list[str]   # citation URLs
        cost_usd      : float       # estimated cost
        duration_sec  : float
        status        : "ok" | "budget_exceeded" | "disabled" | "no_api_key" | "timeout" | "error"
        error_message : str | None
        interaction_id : str | None  # KIK-733: the long-running interaction id
    """
    started_at = time.time()
    estimate = _DEPTH_COST_USD.get(depth, _DEPTH_COST_USD["medium"])

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
        text, sources, interaction_id = _run_deep_research(
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
) -> tuple[str, list[str], str | None]:
    """Submit DR interaction and poll until done or wall-time exceed.

    KIK-733: Uses /v1beta/interactions (NOT generateContent).
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

    # If already complete inline (rare), extract immediately.
    if initial_status == "completed":
        text, sources = _extract_text_and_sources(submit_body)
        return text, sources, interaction_id

    if not interaction_id:
        raise ValueError(f"submit response missing 'id': {submit_body}")

    text, sources = _poll_interaction(api_key, interaction_id, timeout_sec)
    return text, sources, interaction_id


def _poll_interaction(
    api_key: str, interaction_id: str, timeout_sec: int,
) -> tuple[str, list[str]]:
    """Poll the long-running interaction until completed or deadline.

    KIK-733: Uses /v1beta/interactions/{id} (NOT operations/*).
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
            return _extract_text_and_sources(body)
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
        "interaction_id": interaction_id,
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
            "interaction_id": result.get("interaction_id"),
        }
        with open(_META_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[gemini_dr] meta log write failed: {exc}", file=sys.stderr)
