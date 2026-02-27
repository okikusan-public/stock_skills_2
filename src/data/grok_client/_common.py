"""Shared API calling helpers, constants, and utilities for grok_client package.

Extracted from grok_client.py during KIK-508 submodule split.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parents[3] / ".env")


_API_URL = "https://api.x.ai/v1/responses"
_DEFAULT_MODEL = "grok-4-1-fast-non-reasoning"
_error_warned = [False]

# ---------------------------------------------------------------------------
# Error state tracking (KIK-431)
# ---------------------------------------------------------------------------

_error_state: dict = {
    "status": "ok",       # not_configured | ok | auth_error | rate_limited | timeout | other_error
    "status_code": None,  # int | None
    "message": "",
}


def get_error_status() -> dict:
    """Return the current Grok API error state (KIK-431)."""
    return dict(_error_state)


def reset_error_state() -> None:
    """Reset the error state to 'ok' (KIK-431)."""
    _error_state["status"] = "ok"
    _error_state["status_code"] = None
    _error_state["message"] = ""


# ---------------------------------------------------------------------------
# Empty result constants
# ---------------------------------------------------------------------------

EMPTY_STOCK_DEEP = {
    "recent_news": [],
    "catalysts": {"positive": [], "negative": []},
    "analyst_views": [],
    "x_sentiment": {"score": 0.0, "summary": "", "key_opinions": []},
    "competitive_notes": [],
    "raw_response": "",
}

EMPTY_INDUSTRY = {
    "trends": [],
    "key_players": [],
    "growth_drivers": [],
    "risks": [],
    "regulatory": [],
    "investor_focus": [],
    "raw_response": "",
}

EMPTY_MARKET = {
    "price_action": "",
    "macro_factors": [],
    "sentiment": {"score": 0.0, "summary": ""},
    "upcoming_events": [],
    "sector_rotation": [],
    "raw_response": "",
}

EMPTY_TRENDING = {
    "stocks": [],
    "market_context": "",
    "raw_response": "",
}

EMPTY_BUSINESS = {
    "overview": "",
    "segments": [],
    "revenue_model": "",
    "competitive_advantages": [],
    "key_metrics": [],
    "growth_strategy": [],
    "risks": [],
    "raw_response": "",
}

EMPTY_TRENDING_THEMES = {
    "themes": [],
    "raw_response": "",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """Check if Grok API is available (XAI_API_KEY is set)."""
    return bool(os.environ.get("XAI_API_KEY"))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_api_key() -> Optional[str]:
    """Return the API key or None."""
    return os.environ.get("XAI_API_KEY")


def _is_japanese_stock(symbol: str) -> bool:
    """Return True if *symbol* looks like a JPX ticker (.T or .S suffix)."""
    return symbol.upper().endswith((".T", ".S"))


def _contains_japanese(text: str) -> bool:
    """Return True if *text* contains Japanese characters."""
    return any(0x3000 <= ord(c) <= 0x9FFF for c in text)


def _call_grok_api(prompt: str, timeout: int = 30, use_tools: bool = True) -> str:
    """Common request helper for the Grok API.

    Parameters
    ----------
    prompt : str
        Prompt to send to the API.
    timeout : int
        Request timeout in seconds.
    use_tools : bool
        If True (default), attaches x_search and web_search tools.
        Set to False for pure text synthesis without live search (KIK-452).

    Returns
    -------
    str
        Text portion of the API response.  Empty string on error.
    """
    api_key = _get_api_key()
    if not api_key:
        if not _error_warned[0]:
            print(
                "\u26a0\ufe0f  Grok API\u30ad\u30fc\u304c\u8a2d\u5b9a\u3055\u308c\u3066\u3044\u307e\u305b\u3093\n"
                "    \u539f\u56e0: XAI_API_KEY \u74b0\u5883\u5909\u6570\u304c\u672a\u8a2d\u5b9a\u3067\u3059\n"
                "    \u5bfe\u51e6: export XAI_API_KEY=your_key \u3092\u8a2d\u5b9a\u3057\u3066\u304f\u3060\u3055\u3044\n"
                "    \u2192 yfinance\u30c7\u30fc\u30bf\u306e\u307f\u3067\u5b9f\u884c\u3057\u307e\u3059",
                file=sys.stderr,
            )
            _error_warned[0] = True
        _error_state["status"] = "not_configured"
        _error_state["status_code"] = None
        _error_state["message"] = "XAI_API_KEY is not set"
        return ""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": _DEFAULT_MODEL,
            "input": prompt,
        }
        if use_tools:
            payload["tools"] = [{"type": "x_search"}, {"type": "web_search"}]

        response = requests.post(
            _API_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )

        if response.status_code != 200:
            if not _error_warned[0]:
                if response.status_code == 401:
                    print(
                        "\u26a0\ufe0f  Grok API\u8a8d\u8a3c\u30a8\u30e9\u30fc\n"
                        "    \u539f\u56e0: API\u30ad\u30fc\u304c\u7121\u52b9\u307e\u305f\u306f\u671f\u9650\u5207\u308c\u306e\u53ef\u80fd\u6027\u304c\u3042\u308a\u307e\u3059\n"
                        "    \u5bfe\u51e6: xai.com \u3067API\u30ad\u30fc\u3092\u78ba\u8a8d\u30fb\u518d\u767a\u884c\u3057\u3066\u304f\u3060\u3055\u3044\n"
                        "    \u2192 yfinance\u30c7\u30fc\u30bf\u306e\u307f\u3067\u5b9f\u884c\u3057\u307e\u3059",
                        file=sys.stderr,
                    )
                elif response.status_code == 429:
                    print(
                        "\u26a0\ufe0f  Grok API\u306e\u30ec\u30fc\u30c8\u5236\u9650\u306b\u9054\u3057\u307e\u3057\u305f\n"
                        "    \u539f\u56e0: \u77ed\u6642\u9593\u306b\u591a\u304f\u306e\u30ea\u30af\u30a8\u30b9\u30c8\u304c\u9001\u4fe1\u3055\u308c\u307e\u3057\u305f\n"
                        "    \u5bfe\u51e6: \u3057\u3070\u3089\u304f\u5f85\u3063\u3066\u304b\u3089\u518d\u8a66\u884c\u3057\u3066\u304f\u3060\u3055\u3044\uff08\u901a\u5e381\u301c2\u5206\uff09\n"
                        "    \u2192 yfinance\u30c7\u30fc\u30bf\u306e\u307f\u3067\u5b9f\u884c\u3057\u307e\u3059",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"\u26a0\ufe0f  Grok API\u30a8\u30e9\u30fc (HTTP {response.status_code})\n"
                        "    \u5bfe\u51e6: \u3057\u3070\u3089\u304f\u5f85\u3063\u3066\u304b\u3089\u518d\u8a66\u884c\u3057\u3066\u304f\u3060\u3055\u3044\n"
                        "    \u2192 yfinance\u30c7\u30fc\u30bf\u306e\u307f\u3067\u5b9f\u884c\u3057\u307e\u3059",
                        file=sys.stderr,
                    )
                _error_warned[0] = True
            # KIK-431: track error type by status code
            if response.status_code == 401:
                _error_state["status"] = "auth_error"
            elif response.status_code == 429:
                _error_state["status"] = "rate_limited"
            else:
                _error_state["status"] = "other_error"
            _error_state["status_code"] = response.status_code
            _error_state["message"] = f"HTTP {response.status_code}"
            return ""

        data = response.json()

        # Extract text content from the response
        raw_text = ""
        output_items = data.get("output", [])
        for item in output_items:
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        raw_text = content.get("text", "")
                        break

        _error_state["status"] = "ok"
        _error_state["status_code"] = 200
        _error_state["message"] = ""
        return raw_text

    except requests.exceptions.Timeout:
        if not _error_warned[0]:
            print(
                "\u26a0\ufe0f  Grok API\u3078\u306e\u63a5\u7d9a\u304c\u30bf\u30a4\u30e0\u30a2\u30a6\u30c8\u3057\u307e\u3057\u305f\n"
                "    \u539f\u56e0: \u30cd\u30c3\u30c8\u30ef\u30fc\u30af\u63a5\u7d9a\u304c\u4e0d\u5b89\u5b9a\u3001\u307e\u305f\u306fAPI\u304c\u4e00\u6642\u7684\u306b\u5fdc\u7b54\u3057\u3066\u3044\u307e\u305b\u3093\n"
                "    \u5bfe\u51e6: \u30cd\u30c3\u30c8\u30ef\u30fc\u30af\u63a5\u7d9a\u3092\u78ba\u8a8d\u3057\u3001\u518d\u8a66\u884c\u3057\u3066\u304f\u3060\u3055\u3044\n"
                "    \u2192 yfinance\u30c7\u30fc\u30bf\u306e\u307f\u3067\u5b9f\u884c\u3057\u307e\u3059",
                file=sys.stderr,
            )
            _error_warned[0] = True
        _error_state["status"] = "timeout"
        _error_state["status_code"] = None
        _error_state["message"] = "Request timed out"
        return ""
    except requests.exceptions.RequestException as e:
        if not _error_warned[0]:
            print(
                f"\u26a0\ufe0f  Grok API\u3078\u306e\u63a5\u7d9a\u306b\u5931\u6557\u3057\u307e\u3057\u305f\n"
                "    \u539f\u56e0: \u30cd\u30c3\u30c8\u30ef\u30fc\u30af\u30a8\u30e9\u30fc\u304c\u767a\u751f\u3057\u307e\u3057\u305f\n"
                "    \u5bfe\u51e6: \u30cd\u30c3\u30c8\u30ef\u30fc\u30af\u63a5\u7d9a\u3092\u78ba\u8a8d\u3057\u3001\u518d\u8a66\u884c\u3057\u3066\u304f\u3060\u3055\u3044\n"
                "    \u2192 yfinance\u30c7\u30fc\u30bf\u306e\u307f\u3067\u5b9f\u884c\u3057\u307e\u3059",
                file=sys.stderr,
            )
            _error_warned[0] = True
        _error_state["status"] = "other_error"
        _error_state["status_code"] = None
        _error_state["message"] = str(e)
        return ""
    except Exception as e:
        if not _error_warned[0]:
            print(
                f"\u26a0\ufe0f  Grok API\u3067\u4e88\u671f\u3057\u306a\u3044\u30a8\u30e9\u30fc\u304c\u767a\u751f\u3057\u307e\u3057\u305f\n"
                "    \u5bfe\u51e6: \u3057\u3070\u3089\u304f\u5f85\u3063\u3066\u304b\u3089\u518d\u8a66\u884c\u3057\u3066\u304f\u3060\u3055\u3044\n"
                "    \u2192 yfinance\u30c7\u30fc\u30bf\u306e\u307f\u3067\u5b9f\u884c\u3057\u307e\u3059",
                file=sys.stderr,
            )
            _error_warned[0] = True
        _error_state["status"] = "other_error"
        _error_state["status_code"] = None
        _error_state["message"] = str(e)
        return ""


def _parse_json_response(raw_text: str) -> dict:
    """Extract a JSON object from *raw_text*.

    Finds the first ``{`` and last ``}`` and attempts ``json.loads``.
    Returns an empty dict on failure.
    """
    try:
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(raw_text[json_start:json_end])
    except (json.JSONDecodeError, ValueError):
        pass
    return {}


def _parse_json_array_response(raw_text: str):
    """Extract a JSON array from *raw_text*.

    Finds the first ``[`` and last ``]`` and attempts ``json.loads``.
    Returns an empty list on failure.
    """
    try:
        json_start = raw_text.find("[")
        json_end = raw_text.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(raw_text[json_start:json_end])
            if isinstance(result, list):
                return result
    except (json.JSONDecodeError, ValueError):
        pass
    return []
