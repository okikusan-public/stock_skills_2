"""Shared helpers for graph_query package: driver access, session management.

Extracted from graph_query.py during KIK-508 submodule split.
"""

import json
from typing import Optional


def _get_driver():
    """Reuse graph_store's driver."""
    from src.data.graph_store import _get_driver as _gs_driver
    return _gs_driver()
