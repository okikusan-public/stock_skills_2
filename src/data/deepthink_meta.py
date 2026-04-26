"""Shared deepthink meta log path (SSoT for KIK-731/732).

Used by:
- src/data/gemini_client/deep_research.py
- src/data/grok_client/bulk_search.py
- tools/deepthink_summary.py
"""

from pathlib import Path

# data/logs/deepthink_meta.jsonl (project root)
META_LOG_PATH = Path(__file__).resolve().parents[2] / "data" / "logs" / "deepthink_meta.jsonl"
