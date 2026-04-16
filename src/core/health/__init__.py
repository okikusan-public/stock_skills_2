"""Portfolio health check subpackage (KIK-576).

Re-exports all public functions for backward compatibility.
Import directly from submodules for new code:
    from src.core.health.trend import check_trend_health
    from src.core.health.alert import compute_alert_level, ALERT_NONE
"""

__all__ = [
    # Alert constants and computation
    "ALERT_NONE",
    "ALERT_EARLY_WARNING",
    "ALERT_CAUTION",
    "ALERT_EXIT",
    "compute_alert_level",
    # Trend analysis
    "SMA_APPROACHING_GAP",
    "RSI_PREV_THRESHOLD",
    "RSI_DROP_THRESHOLD",
    "check_trend_health",
    # Change quality
    "check_change_quality",
    # Orchestrator
    "run_health_check",
    # Community concentration (private but used by tests/other modules)
    "_compute_community_concentration",
    # Theme exposure (KIK-604)
    "_compute_theme_exposure",
    # ETF health
    "check_etf_health",
    # Labels / long-term suitability
    "check_long_term_suitability",
    # Value trap detector (re-exported for backward compat)
    "_detect_value_trap",
    # Common helpers (re-exported for backward compat)
    "_is_etf",
    "_is_cash",
]

# Alert constants and computation
from src.core.health.alert import (  # noqa: F401
    ALERT_NONE,
    ALERT_EARLY_WARNING,
    ALERT_CAUTION,
    ALERT_EXIT,
    compute_alert_level,
)

# Trend analysis
from src.core.health.trend import (  # noqa: F401
    SMA_APPROACHING_GAP,
    RSI_PREV_THRESHOLD,
    RSI_DROP_THRESHOLD,
    check_trend_health,
)

# Change quality evaluation
from src.core.health.quality import check_change_quality  # noqa: F401

# Orchestrator
from src.core.health.runner import run_health_check  # noqa: F401

# Community concentration (private but used by tests)
from src.core.health.community import _compute_community_concentration  # noqa: F401

# Theme exposure (KIK-604)
from src.core.health.theme import _compute_theme_exposure  # noqa: F401

# ETF health
from src.core.health.etf import check_etf_health  # noqa: F401

# Labels / long-term suitability
from src.core.health.labels import check_long_term_suitability  # noqa: F401

# Re-export value_trap detector (was available via health_check module)
from src.core.value_trap import detect_value_trap as _detect_value_trap  # noqa: F401

# Re-export common helpers that were importable from health_check
from src.core.common import is_etf as _is_etf  # noqa: F401
from src.core.common import is_cash as _is_cash  # noqa: F401
