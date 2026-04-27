"""Preflight Tool — DeepThink 起動前ゲートのファサード (KIK-735).

tools/ 層は API 呼び出しのみを担う。判断ロジックは含めない。
src/data/preflight の純粋な関数を re-export する。
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.preflight import (  # noqa: E402
    PreflightError,
    run_preflight,
    extract_convictions,
)

__all__ = [
    "PreflightError",
    "run_preflight",
    "extract_convictions",
]
