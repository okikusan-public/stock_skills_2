"""Backward-compatible re-export (KIK-576). Import from src.core.health directly."""
import warnings as _warnings

_warnings.warn(
    "Import from src.core.health directly instead of src.core.health_check",
    DeprecationWarning,
    stacklevel=2,
)
from src.core.health import *  # noqa: F401,F403
