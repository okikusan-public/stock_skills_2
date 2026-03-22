"""Alert level computation for portfolio health checks (KIK-576).

Computes 3-level alert system: early_warning, caution, exit.
"""

from src.core.value_trap import detect_value_trap as _detect_value_trap

# Alert level constants
ALERT_NONE = "none"
ALERT_EARLY_WARNING = "early_warning"
ALERT_CAUTION = "caution"
ALERT_EXIT = "exit"


def compute_alert_level(
    trend_health: dict,
    change_quality: dict,
    stock_detail=None,
    return_stability: dict | None = None,
    is_small_cap: bool = False,
) -> dict:
    """Compute 3-level alert from trend and change quality.

    Level priority: exit > caution > early_warning > none.

    Parameters
    ----------
    is_small_cap : bool
        If True, escalate early_warning to caution (KIK-438).

    Returns
    -------
    dict
        Keys: level, emoji, label, reasons.
    """
    reasons: list[str] = []
    level = ALERT_NONE

    trend = trend_health.get("trend", "不明")
    quality_label = change_quality.get("quality_label", "良好")
    dead_cross = trend_health.get("dead_cross", False)
    rsi_drop = trend_health.get("rsi_drop", False)
    price_above_sma50 = trend_health.get("price_above_sma50", True)
    sma50_approaching = trend_health.get("sma50_approaching_sma200", False)
    cross_signal = trend_health.get("cross_signal", "none")
    days_since_cross = trend_health.get("days_since_cross")
    cross_date = trend_health.get("cross_date")

    if quality_label == "対象外":
        # ETF: evaluate technical conditions only (no quality data)
        if not price_above_sma50:
            level = ALERT_EARLY_WARNING
            sma50_val = trend_health.get("sma50", 0)
            price_val = trend_health.get("current_price", 0)
            reasons.append(f"SMA50を下回り（現在{price_val}、SMA50={sma50_val}）")
        if dead_cross:
            level = ALERT_CAUTION
            reasons.append("デッドクロス")
        if rsi_drop:
            if level == ALERT_NONE:
                level = ALERT_EARLY_WARNING
            rsi_val = trend_health.get("rsi", 0)
            reasons.append(f"RSI急低下（{rsi_val}）")
    else:
        # --- EXIT ---
        # KIK-357: EXIT requires technical collapse AND fundamental deterioration.
        # Dead cross + good fundamentals = CAUTION (not EXIT).
        if dead_cross and quality_label == "複数悪化":
            level = ALERT_EXIT
            reasons.append("デッドクロス + 変化スコア複数悪化")
        elif dead_cross and trend == "下降":
            if quality_label == "良好":
                level = ALERT_CAUTION
                reasons.append("デッドクロス（ファンダメンタル良好のためCAUTION）")
            else:
                # quality_label is "1指標↓" — technical + fundamental confirm
                level = ALERT_EXIT
                reasons.append("トレンド崩壊（デッドクロス + ファンダ悪化）")

        # --- CAUTION ---
        elif sma50_approaching and quality_label in ("1指標↓", "複数悪化"):
            level = ALERT_CAUTION
            if quality_label == "複数悪化":
                reasons.append("変化スコア複数悪化")
            else:
                reasons.append("変化スコア1指標悪化")
            reasons.append("SMA50がSMA200に接近")
        elif quality_label == "複数悪化":
            level = ALERT_CAUTION
            reasons.append("変化スコア複数悪化")

        # --- EARLY WARNING ---
        elif not price_above_sma50:
            level = ALERT_EARLY_WARNING
            sma50_val = trend_health.get("sma50", 0)
            price_val = trend_health.get("current_price", 0)
            reasons.append(f"SMA50を下回り（現在{price_val}、SMA50={sma50_val}）")
        elif rsi_drop:
            level = ALERT_EARLY_WARNING
            rsi_val = trend_health.get("rsi", 0)
            reasons.append(f"RSI急低下（{rsi_val}）")
        elif quality_label == "1指標↓":
            level = ALERT_EARLY_WARNING
            reasons.append("変化スコア1指標悪化")

    # Recent death cross event: add date context to reasons
    if cross_signal == "death_cross" and days_since_cross is not None and days_since_cross <= 10:
        reasons.append(f"デッドクロス発生（{days_since_cross}日前、{cross_date}）")

    # Recent golden cross: positive signal -> early warning if no other alert
    if cross_signal == "golden_cross" and days_since_cross is not None and days_since_cross <= 20:
        if level == ALERT_NONE:
            level = ALERT_EARLY_WARNING
        reasons.append(
            f"ゴールデンクロス発生（{days_since_cross}日前、{cross_date}）"
            "- 上昇トレンド転換の可能性"
        )

    # Value trap detection (KIK-381)
    value_trap = _detect_value_trap(stock_detail)
    if value_trap["is_trap"]:
        for reason in value_trap["reasons"]:
            if reason not in reasons:
                reasons.append(reason)
        # Escalate to at least EARLY_WARNING
        if level == ALERT_NONE:
            level = ALERT_EARLY_WARNING

    # Shareholder return stability (KIK-403)
    if return_stability is not None:
        stability = return_stability.get("stability")
        if stability == "temporary":
            reason_text = return_stability.get("reason", "一時的高還元")
            reason_str = f"一時的高還元の可能性（{reason_text}）"
            if reason_str not in reasons:
                reasons.append(reason_str)
            if level == ALERT_NONE:
                level = ALERT_EARLY_WARNING
        elif stability == "decreasing":
            reason_text = return_stability.get("reason", "還元率減少傾向")
            reason_str = f"株主還元率が減少傾向（{reason_text}）"
            if reason_str not in reasons:
                reasons.append(reason_str)

    # Small-cap escalation (KIK-438): early_warning -> caution
    if is_small_cap and level == ALERT_EARLY_WARNING:
        level = ALERT_CAUTION
        reasons.append("[小型] 小型株のため注意に引き上げ")

    level_map = {
        ALERT_NONE: ("", "なし"),
        ALERT_EARLY_WARNING: ("\u26a1", "早期警告"),
        ALERT_CAUTION: ("\u26a0", "注意"),
        ALERT_EXIT: ("\U0001f6a8", "撤退"),
    }
    emoji, label = level_map[level]

    return {
        "level": level,
        "emoji": emoji,
        "label": label,
        "reasons": reasons,
    }
