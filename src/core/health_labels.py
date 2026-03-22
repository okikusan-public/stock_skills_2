"""Backward-compatible re-export (KIK-576). Import from src.core.health.labels directly."""
import warnings as _warnings

_warnings.warn(
    "Import from src.core.health.labels directly instead of src.core.health_labels",
    DeprecationWarning,
    stacklevel=2,
)
from src.core.health.labels import *  # noqa: F401,F403
