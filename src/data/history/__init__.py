"""History store -- save and load screening/report/trade/health/research JSON files.

Sub-modules (KIK-512 split, KIK-517 package):
  _helpers.py: Internal helpers (_sanitize, _build_embedding, _dual_write_graph)
  save.py: All save_* functions
  load.py: load_history, list_history_files

All public functions are re-exported here for backward compatibility.
"""

__all__ = [
    "Path",
    "_safe_filename", "_history_dir", "_HistoryEncoder",
    "_sanitize", "_build_embedding", "_dual_write_graph",
    "save_screening", "save_report", "save_trade", "save_health",
    "_build_research_summary", "save_research", "save_market_context",
    "save_stress_test", "save_forecast",
    "load_history", "list_history_files",
]

# Re-export Path for backward compat (tests may patch src.data.history_store.Path)
from pathlib import Path  # noqa: F401

# Re-export helpers (used by note_manager, manage_watchlist, backfill_embeddings)
from src.data.history._helpers import (  # noqa: F401
    _safe_filename,
    _history_dir,
    _HistoryEncoder,
    _sanitize,
    _build_embedding,
    _dual_write_graph,
)

# Re-export save functions
from src.data.history.save import (  # noqa: F401
    save_screening,
    save_report,
    save_trade,
    save_health,
    _build_research_summary,
    save_research,
    save_market_context,
    save_stress_test,
    save_forecast,
)

# Re-export load functions
from src.data.history.load import (  # noqa: F401
    load_history,
    list_history_files,
)
