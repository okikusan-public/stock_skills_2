"""Watchlist Tool — ウォッチリスト読み書きファサード.

tools/ 層は保存・取得のみを担う。判断ロジックは含めない。
data/watchlists/ の JSON ファイルを直接読み書きする。
"""

import json
import os
from pathlib import Path

_WATCHLISTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "watchlists"
)


def _ensure_dir() -> Path:
    d = Path(_WATCHLISTS_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_path(list_name: str) -> Path:
    return _ensure_dir() / f"{list_name}.json"


def list_watchlists() -> list[str]:
    """利用可能なウォッチリスト名を返す."""
    d = _ensure_dir()
    return [p.stem for p in sorted(d.glob("*.json"))]


def load_watchlist(list_name: str = "default") -> list[str]:
    """ウォッチリストのシンボル一覧を読み込む."""
    path = _list_path(list_name)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_watchlist(list_name: str, symbols: list[str]) -> None:
    """ウォッチリストを保存する."""
    path = _list_path(list_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(set(symbols)), f, indent=2, ensure_ascii=False)


def add_to_watchlist(list_name: str, *symbols: str) -> list[str]:
    """ウォッチリストにシンボルを追加し、更新後のリストを返す."""
    current = load_watchlist(list_name)
    updated = sorted(set(current) | set(symbols))
    save_watchlist(list_name, updated)
    return updated


def remove_from_watchlist(list_name: str, *symbols: str) -> list[str]:
    """ウォッチリストからシンボルを削除し、更新後のリストを返す."""
    current = load_watchlist(list_name)
    updated = sorted(set(current) - set(symbols))
    save_watchlist(list_name, updated)
    return updated


__all__ = [
    "list_watchlists",
    "load_watchlist",
    "save_watchlist",
    "add_to_watchlist",
    "remove_from_watchlist",
]
