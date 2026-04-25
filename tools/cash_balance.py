"""Cash Balance Tool — キャッシュ残高読み書きファサード.

tools/ 層は保存・取得のみを担う。判断ロジックは含めない。
data/cash_balance.json を直接読み書きする。
"""

import json
import os
from datetime import datetime
from pathlib import Path

_CASH_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "cash_balance.json"
)


def load_cash_balance(path: str = _CASH_PATH) -> dict:
    """キャッシュ残高を読み込む.

    Returns
    -------
    dict
        {"JPY": float, "USD": float, ..., "updated_at": str}
        ファイルが存在しない場合は空 dict を返す。
    """
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cash_balance(balances: dict, path: str = _CASH_PATH) -> None:
    """キャッシュ残高を保存する.

    Parameters
    ----------
    balances : dict
        {"JPY": 1115361, "USD": 2996.90, ...}
        updated_at は自動付与される。
    """
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    balances["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(balances, f, indent=2, ensure_ascii=False)


def update_currency(currency: str, amount: float, path: str = _CASH_PATH) -> dict:
    """特定通貨の残高を更新し、更新後の全残高を返す.

    Parameters
    ----------
    currency : str
        通貨コード（"JPY", "USD" 等）
    amount : float
        残高金額
    """
    balances = load_cash_balance(path)
    balances[currency.upper()] = amount
    save_cash_balance(balances, path)
    return balances


__all__ = [
    "load_cash_balance",
    "save_cash_balance",
    "update_currency",
]
