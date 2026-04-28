"""Cash Balance Tool — キャッシュ残高読み書きファサード（KIK-742 階層形式SSoT）.

tools/ 層は保存・取得のみを担う。判断ロジックは含めない。
data/cash_balance.json を直接読み書きする。

# Cash Balance Schema (SSoT)

階層形式（実データ準拠、KIK-742 で統一）:

```json
{
  "date": "YYYY-MM-DD",
  "timestamp": "ISO-8601",
  "total_jpy": 1234567,
  "breakdown": {
    "USD": {"amount": 5934.21, "jpy_equivalent": 947634, "rate_jpy_per_usd": 159.69},
    "JPY": {"amount": 233969}
  },
  "changelog": ["..."]
}
```

`session_state.py` と `src/data/portfolio_io.py:load_cash_balance` も同形式を期待する。
"""

import json
import os
from datetime import datetime
from pathlib import Path

_CASH_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "cash_balance.json"
)


def load_cash_balance(path: str = _CASH_PATH) -> dict:
    """キャッシュ残高を読み込む（階層形式、KIK-742）.

    Returns
    -------
    dict
        {"date": str, "total_jpy": float, "breakdown": {...}, ...}
        ファイルが存在しない場合は空 dict を返す。
    """
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cash_balance(balances: dict, path: str = _CASH_PATH) -> None:
    """キャッシュ残高を保存する（階層形式、KIK-742）.

    Parameters
    ----------
    balances : dict
        階層形式（モジュール docstring 参照）。
        date / timestamp は自動付与される（既存値があれば上書きしない）。

    Notes
    -----
    旧フラット形式（{"JPY": 1234, "USD": 5.6}）はサポートしない。
    既存JSONを編集する場合は load_cash_balance() で読んでから渡すこと。
    """
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    balances.setdefault("date", now.strftime("%Y-%m-%d"))
    balances["timestamp"] = now.isoformat(timespec="seconds")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(balances, f, indent=2, ensure_ascii=False)


def update_currency(
    currency: str,
    amount: float,
    path: str = _CASH_PATH,
    *,
    jpy_equivalent: float | None = None,
    rate_jpy_per_usd: float | None = None,
) -> dict:
    """特定通貨の残高を更新し、更新後の全残高を返す（階層形式、KIK-742）.

    Parameters
    ----------
    currency : str
        通貨コード（"JPY", "USD" 等）
    amount : float
        残高金額（その通貨単位）
    jpy_equivalent : float, optional
        JPY換算額（USD等の外貨で必須相当）
    rate_jpy_per_usd : float, optional
        為替レート（USD等で記録）
    """
    balances = load_cash_balance(path)
    balances.setdefault("breakdown", {})
    entry: dict = {"amount": amount}
    if jpy_equivalent is not None:
        entry["jpy_equivalent"] = jpy_equivalent
    if rate_jpy_per_usd is not None:
        entry["rate_jpy_per_usd"] = rate_jpy_per_usd
    balances["breakdown"][currency.upper()] = entry
    # total_jpy は呼び出し側責任（多通貨合算ロジックは含まない）
    save_cash_balance(balances, path)
    return balances


__all__ = [
    "load_cash_balance",
    "save_cash_balance",
    "update_currency",
]
