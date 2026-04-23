"""Sector Relative Strength — セクターETFの相対強度を計算.

中規模以上のPF($50K+)で使用。小規模PFでは不要。
RS = (セクターETF/SPYのリターン比) で S&P500対比の強弱を定量化する。
"""

from __future__ import annotations

from typing import Optional

from .history import get_price_history


# GICS 11セクター対応ETF
SECTOR_ETFS: dict[str, str] = {
    "金融": "XLF",
    "エネルギー": "XLE",
    "ヘルスケア": "XLV",
    "公益": "XLU",
    "テクノロジー": "XLK",
    "資本財": "XLI",
    "一般消費財": "XLY",
    "生活必需品": "XLP",
    "通信": "XLC",
    "素材": "XLB",
    "不動産": "XLRE",
}

BENCHMARK = "SPY"


def get_sector_rs(period: str = "6mo") -> Optional[list[dict]]:
    """全セクターETFの相対強度(RS)を計算し、RS降順で返す.

    RS = (セクターETF/SPYの20日リターン比) * 0.4
       + (セクターETF/SPYの60日リターン比) * 0.4
       + (セクターETF出来高変化率)           * 0.2

    Parameters
    ----------
    period : str
        get_price_history に渡す期間。60日リターンに "6mo" 必要。

    Returns
    -------
    list[dict] or None
        RS降順のリスト。取得失敗時は None。
        各要素:
        {
            "name": "テクノロジー",
            "symbol": "XLK",
            "rs_score": 1.15,
            "return_20d": 0.05,
            "return_60d": 0.12,
            "volume_change": 0.10,
            "rank": 1,
        }
    """
    # ベンチマーク取得
    spy_df = get_price_history(BENCHMARK, period=period)
    if spy_df is None or len(spy_df) < 60:
        return None

    spy_close = spy_df["Close"]
    spy_ret_20d = _safe_return(spy_close, 20)
    spy_ret_60d = _safe_return(spy_close, 60)

    if spy_ret_20d is None or spy_ret_60d is None:
        return None

    results: list[dict] = []

    for name, symbol in SECTOR_ETFS.items():
        df = get_price_history(symbol, period=period)
        if df is None or len(df) < 60:
            continue

        close = df["Close"]
        ret_20d = _safe_return(close, 20)
        ret_60d = _safe_return(close, 60)

        if ret_20d is None or ret_60d is None:
            continue

        # 出来高変化率（20日平均 / 60日平均 - 1）
        vol = df.get("Volume")
        vol_change = 0.0
        if vol is not None and len(vol) >= 60:
            vol_20 = vol.iloc[-20:].mean()
            vol_60 = vol.iloc[-60:].mean()
            if vol_60 > 0:
                vol_change = vol_20 / vol_60 - 1.0

        # RS計算（ゼロ除算ガード）
        rs_20d = ret_20d / spy_ret_20d if abs(spy_ret_20d) > 1e-6 else 1.0
        rs_60d = ret_60d / spy_ret_60d if abs(spy_ret_60d) > 1e-6 else 1.0

        rs_score = rs_20d * 0.4 + rs_60d * 0.4 + vol_change * 0.2

        results.append({
            "name": name,
            "symbol": symbol,
            "rs_score": round(rs_score, 3),
            "return_20d": round(ret_20d, 4),
            "return_60d": round(ret_60d, 4),
            "volume_change": round(vol_change, 4),
        })

    # RS降順ソート + rank付与
    results.sort(key=lambda x: -x["rs_score"])
    for i, r in enumerate(results, 1):
        r["rank"] = i

    return results if results else None


def _safe_return(series, days: int) -> Optional[float]:
    """N日リターンを安全に計算."""
    if len(series) < days + 1:
        return None
    current = float(series.iloc[-1])
    past = float(series.iloc[-days])
    if past == 0:
        return None
    return current / past - 1.0
