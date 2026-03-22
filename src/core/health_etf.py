"""Backward-compatible re-export (KIK-576). Import from src.core.health.etf directly."""
import warnings as _warnings

_warnings.warn(
    "Import from src.core.health.etf directly instead of src.core.health_etf",
    DeprecationWarning,
    stacklevel=2,
)
from src.core.health.etf import *  # noqa: F401,F403
