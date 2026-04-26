"""Gemini API client package (KIK-731).

Wraps Google Gemini APIs. Currently:
- Deep Research API (deep-research-preview-04-2026)

KIK-731: Initial Gemini Deep Research wrapper for DeepThink integration.
"""

from src.data.gemini_client.deep_research import (
    gemini_deep_research,
    is_deep_research_enabled,
    is_available,
)

__all__ = [
    "gemini_deep_research",
    "is_deep_research_enabled",
    "is_available",
]
