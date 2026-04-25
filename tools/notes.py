"""Notes Tool — 投資メモ・lesson 読み書きファサード.

tools/ 層は保存・取得のみを担う。判断ロジックは含めない。
src/data/note_manager の純粋なデータ操作関数を re-export する。
JSON ファイルが master、Neo4j は view（dual-write）。
"""

import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.note_manager import (  # noqa: E402
    save_note,
    load_notes,
    delete_note,
    get_exit_rules,
    check_exit_rule,
    check_lesson_conflicts,
)

__all__ = [
    "save_note",
    "load_notes",
    "delete_note",
    "get_exit_rules",
    "check_exit_rule",
    "check_lesson_conflicts",
]
