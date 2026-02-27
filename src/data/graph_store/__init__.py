"""Neo4j graph store for investment knowledge graph (KIK-397/398/413/507).

Split into node-type-specific submodules (KIK-507):
  _common.py  — connection, mode, helpers, schema, AI relationships
  stock.py    — Stock, Screen, Report, Watchlist, Theme
  research.py — Research + News/Sentiment/Catalyst/AnalystView
  portfolio.py — Trade, HealthCheck, Portfolio sync, StressTest, Forecast
  market.py   — MarketContext + Indicator/UpcomingEvent/SectorRotation
  note.py     — Note, ActionItem

All public functions are re-exported here for backward compatibility.

IMPORTANT: Tests set mutable state (gs._driver, gs._unavailable_warned) and
patch functions (gs._get_driver, gs.is_available) on this package module.
Submodules access shared state through `_common` module reference, so
__getattr__/__setattr__ proxy mutable state to _common.
"""

import sys as _sys
import types as _types

from src.data.graph_store import _common  # noqa: F401

# --- _common.py: connection, mode, helpers, schema, AI rels ---
from src.data.graph_store._common import (  # noqa: F401
    _get_driver,
    _get_mode,
    _mode_cache,
    _MODE_TTL,
    _safe_id,
    _set_embedding,
    _truncate,
    clear_all,
    close,
    create_ai_relationship,
    get_mode,
    init_schema,
    is_available,
)

# --- stock.py: Stock, Screen, Report, Watchlist, Theme ---
from src.data.graph_store.stock import (  # noqa: F401
    get_stock_history,
    merge_report,
    merge_report_full,
    merge_screen,
    merge_stock,
    merge_watchlist,
    tag_theme,
)

# --- research.py: Research + sub-nodes ---
from src.data.graph_store.research import (  # noqa: F401
    link_research_supersedes,
    merge_research,
    merge_research_full,
)

# --- portfolio.py: Trade, HealthCheck, Portfolio, StressTest, Forecast ---
from src.data.graph_store.portfolio import (  # noqa: F401
    get_held_symbols,
    is_held,
    merge_forecast,
    merge_health,
    merge_stress_test,
    merge_trade,
    sync_portfolio,
)

# --- market.py: MarketContext + sub-nodes ---
from src.data.graph_store.market import (  # noqa: F401
    merge_market_context,
    merge_market_context_full,
)

# --- note.py: Note, ActionItem ---
from src.data.graph_store.note import (  # noqa: F401
    get_open_action_items,
    merge_action_item,
    merge_note,
    update_action_item_linear,
)

# Re-export schema/vector constants for tests that reference them
from src.data.graph_store._common import (  # noqa: F401
    _AI_REL_CYPHERS,
    _SCHEMA_CONSTRAINTS,
    _SCHEMA_INDEXES,
    _VECTOR_INDEXES,
)

# Expose _unavailable_warned at package level (initial value)
_unavailable_warned = _common._unavailable_warned


# ---------------------------------------------------------------------------
# Attribute proxy for mutable state (KIK-507)
# ---------------------------------------------------------------------------
# Tests do `gs._driver = mock_driver` and `gs._unavailable_warned = True`.
# These must propagate to _common so submodules see the change.
# Also, `patch("src.data.graph_store._get_driver", ...)` must propagate
# to _common so that `_common._get_driver()` returns the patched value.
#
# We use a module wrapper class to intercept __setattr__ and propagate
# writes of key names to _common.

class _ModuleProxy(_types.ModuleType):
    """Module wrapper that proxies attribute reads/writes to _common."""

    _PROXIED_ATTRS = frozenset({"_driver", "_unavailable_warned", "_mode_cache"})
    _PROXIED_FUNCS = frozenset({"_get_driver", "is_available", "_get_mode"})

    def __setattr__(self, name, value):
        pa = type(self)._PROXIED_ATTRS
        pf = type(self)._PROXIED_FUNCS
        if name in pa or name in pf:
            setattr(_common, name, value)
        super().__setattr__(name, value)

    def __getattribute__(self, name):
        # For proxied mutable state, always read from _common
        pa = type(self)._PROXIED_ATTRS
        if name in pa:
            return getattr(_common, name)
        return super().__getattribute__(name)


# Replace this module in sys.modules with the proxy
_this = _sys.modules[__name__]
_proxy = _ModuleProxy(__name__)
_proxy.__dict__.update(_this.__dict__)
_proxy.__path__ = _this.__path__
_proxy.__package__ = _this.__package__
_proxy.__file__ = _this.__file__
_proxy.__spec__ = _this.__spec__
_proxy.__loader__ = getattr(_this, "__loader__", None)
_sys.modules[__name__] = _proxy
