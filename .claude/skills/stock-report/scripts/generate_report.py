#!/usr/bin/env python3
"""Entry point for the stock-report skill."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from scripts.common import try_import, HAS_HISTORY_STORE, HAS_GRAPH_QUERY as _HAS_GQ, print_context, print_suggestions
from src.data.yahoo_client import get_stock_info, get_stock_detail
from src.core.screening.indicators import calculate_value_score
from src.core.common import is_etf

HAS_SHAREHOLDER_RETURN, _sr = try_import("src.core.screening.indicators", "calculate_shareholder_return")
if HAS_SHAREHOLDER_RETURN: calculate_shareholder_return = _sr["calculate_shareholder_return"]

HAS_SHAREHOLDER_HISTORY, _sh = try_import("src.core.screening.indicators", "calculate_shareholder_return_history")
if HAS_SHAREHOLDER_HISTORY: calculate_shareholder_return_history = _sh["calculate_shareholder_return_history"]

HAS_RETURN_STABILITY, _rs = try_import("src.core.screening.indicators", "assess_return_stability")
if HAS_RETURN_STABILITY: assess_return_stability = _rs["assess_return_stability"]

# Module availability from common.py (KIK-448)
HAS_HISTORY = HAS_HISTORY_STORE
if HAS_HISTORY:
    from src.data.history_store import save_report as history_save_report

HAS_VALUE_TRAP, _vt = try_import("src.core.health_check", "_detect_value_trap")
if HAS_VALUE_TRAP: _detect_value_trap = _vt["_detect_value_trap"]

HAS_GRAPH_QUERY = _HAS_GQ
if HAS_GRAPH_QUERY:
    from src.data.graph_query import get_prior_report

HAS_INDUSTRY_CONTEXT = _HAS_GQ
if HAS_INDUSTRY_CONTEXT:
    from src.data.graph_query import get_industry_research_for_sector


def _print_etf_report(symbol: str, data: dict):
    """ETF専用レポートを出力する (KIK-469)."""
    def fmt(val, pct=False):
        if val is None:
            return "-"
        return f"{val * 100:.2f}%" if pct else f"{val:.4f}"

    def fmt_int(val):
        if val is None:
            return "-"
        return f"{val:,.0f}"

    print(f"# {data.get('name', symbol)} ({symbol}) [ETF]")
    print()

    # ファンド概要
    print("## ファンド概要")
    print("| 項目 | 値 |")
    print("|---:|:---|")
    print(f"| カテゴリ | {data.get('fund_category') or '-'} |")
    print(f"| ファンドファミリー | {data.get('fund_family') or '-'} |")
    print(f"| 純資産総額 (AUM) | {fmt_int(data.get('total_assets_fund'))} |")
    print(f"| 経費率 | {fmt(data.get('expense_ratio'), pct=True)} |")
    print()

    # 経費率評価
    er = data.get("expense_ratio")
    if er is not None:
        if er <= 0.001:
            er_verdict = "超低コスト（優良）"
        elif er <= 0.005:
            er_verdict = "低コスト（良好）"
        elif er <= 0.01:
            er_verdict = "やや高め"
        else:
            er_verdict = "高コスト（要検討）"
        print(f"- **経費率評価**: {er_verdict}")
        print()

    # パフォーマンス
    print("## パフォーマンス")
    print("| 指標 | 値 |")
    print("|---:|:---|")
    print(f"| 現在値 | {fmt_int(data.get('price'))} |")
    print(f"| 配当利回り | {fmt(data.get('dividend_yield_trailing'), pct=True)} |")
    print(f"| β値 | {fmt(data.get('beta'))} |")
    print(f"| 52週高値 | {fmt_int(data.get('fifty_two_week_high'))} |")
    print(f"| 52週安値 | {fmt_int(data.get('fifty_two_week_low'))} |")
    print()

    # AUM評価
    aum = data.get("total_assets_fund")
    if aum is not None:
        if aum >= 10_000_000_000:
            aum_verdict = "大規模（流動性十分）"
        elif aum >= 1_000_000_000:
            aum_verdict = "中規模（流動性良好）"
        elif aum >= 100_000_000:
            aum_verdict = "小規模（流動性に注意）"
        else:
            aum_verdict = "極小（償還リスクあり）"
        print(f"- **ファンド規模**: {aum_verdict}")

    # 履歴保存
    if HAS_HISTORY:
        try:
            history_save_report(symbol, data, 0, "ETF")
        except Exception:
            pass


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_report.py <ticker>")
        print("Example: generate_report.py 7203.T")
        sys.exit(1)

    symbol = sys.argv[1]

    # Context retrieval (KIK-465)
    print_context(f"report {symbol}")

    data = get_stock_detail(symbol)
    if data is None:
        data = get_stock_info(symbol)

    if data is None:
        print(f"Error: {symbol} のデータを取得できませんでした。")
        sys.exit(1)

    # KIK-469: ETF auto-detection
    if is_etf(data):
        _print_etf_report(symbol, data)
        print_suggestions(symbol=symbol, context_summary=f"ETFレポート生成: {symbol}")
        return

    thresholds = {"per_max": 15, "pbr_max": 1.0, "dividend_yield_min": 0.03, "roe_min": 0.08}
    score = calculate_value_score(data, thresholds)

    if score >= 70:
        verdict = "割安（買い検討）"
    elif score >= 50:
        verdict = "やや割安"
    elif score >= 30:
        verdict = "適正水準"
    else:
        verdict = "割高傾向"

    def fmt(val, pct=False):
        if val is None:
            return "-"
        return f"{val * 100:.2f}%" if pct else f"{val:.2f}"

    def fmt_int(val):
        if val is None:
            return "-"
        return f"{val:,.0f}"

    print(f"# {data.get('name', symbol)} ({symbol})")
    print()
    print(f"- **セクター**: {data.get('sector') or '-'}")
    print(f"- **業種**: {data.get('industry') or '-'}")
    print()
    print("## 株価情報")
    print(f"- **現在値**: {fmt_int(data.get('price'))}")
    print(f"- **時価総額**: {fmt_int(data.get('market_cap'))}")
    print()
    print("## バリュエーション")
    print(f"| 指標 | 値 |")
    print(f"|---:|:---|")
    print(f"| PER | {fmt(data.get('per'))} |")
    print(f"| PBR | {fmt(data.get('pbr'))} |")
    print(f"| 配当利回り(実績) | {fmt(data.get('dividend_yield_trailing'), pct=True)} |")
    print(f"| 配当利回り(予想) | {fmt(data.get('dividend_yield'), pct=True)} |")
    print(f"| ROE | {fmt(data.get('roe'), pct=True)} |")
    print(f"| ROA | {fmt(data.get('roa'), pct=True)} |")
    print(f"| 利益成長率 | {fmt(data.get('revenue_growth'), pct=True)} |")
    print()
    print("## 割安度判定")
    print(f"- **スコア**: {score:.1f} / 100")
    print(f"- **判定**: {verdict}")

    # KIK-381: Value trap warning
    if HAS_VALUE_TRAP:
        vt = _detect_value_trap(data)
        if vt["is_trap"]:
            print()
            print("## ⚠️ バリュートラップ注意")
            for reason in vt["reasons"]:
                print(f"- {reason}")

    # KIK-375: Shareholder return section
    if HAS_SHAREHOLDER_RETURN:
        sr = calculate_shareholder_return(data)
        total_rate = sr.get("total_return_rate")
        if total_rate is not None or sr.get("dividend_yield") is not None:
            print()
            print("## 株主還元")
            print("| 指標 | 値 |")
            print("|---:|:---|")
            print(f"| 配当利回り | {fmt(sr.get('dividend_yield'), pct=True)} |")
            print(f"| 自社株買い利回り | {fmt(sr.get('buyback_yield'), pct=True)} |")
            print(f"| **総株主還元率** | **{fmt(total_rate, pct=True)}** |")
            dp = sr.get("dividend_paid")
            br = sr.get("stock_repurchase")
            ta = sr.get("total_return_amount")
            if dp is not None or br is not None:
                print()
                print(f"- 配当総額: {fmt_int(dp)}")
                print(f"- 自社株買い額: {fmt_int(br)}")
                print(f"- 株主還元合計: {fmt_int(ta)}")

    # KIK-380: Shareholder return 3-year history
    if HAS_SHAREHOLDER_HISTORY:
        sr_hist = calculate_shareholder_return_history(data)
        if len(sr_hist) >= 2:
            print()
            print("## 株主還元推移")
            header_cols = []
            for entry in sr_hist:
                fy = entry.get("fiscal_year")
                header_cols.append(str(fy) if fy else "-")
            print("| 指標 | " + " | ".join(header_cols) + " |")
            print("|---:" + " | :---" * len(sr_hist) + " |")
            print("| 配当総額 | " + " | ".join(
                fmt_int(e.get("dividend_paid")) for e in sr_hist
            ) + " |")
            print("| 自社株買い額 | " + " | ".join(
                fmt_int(e.get("stock_repurchase")) for e in sr_hist
            ) + " |")
            print("| 還元合計 | " + " | ".join(
                fmt_int(e.get("total_return_amount")) for e in sr_hist
            ) + " |")
            print("| 総還元率 | " + " | ".join(
                fmt(e.get("total_return_rate"), pct=True) for e in sr_hist
            ) + " |")
            # Trend judgment
            rates = [e.get("total_return_rate") for e in sr_hist
                     if e.get("total_return_rate") is not None]
            if len(rates) >= 2:
                if all(rates[i] >= rates[i + 1] for i in range(len(rates) - 1)):
                    trend = "📈 増加傾向（株主還元に積極的）"
                elif all(rates[i] <= rates[i + 1] for i in range(len(rates) - 1)):
                    trend = "📉 減少傾向（注意）"
                else:
                    trend = "➡️ 横ばい"
                print()
                print(f"- **トレンド**: {trend}")

                # KIK-383: Return stability assessment
                if HAS_RETURN_STABILITY:
                    stability = assess_return_stability(sr_hist)
                    stab_label = stability.get("label", "")
                    avg_rate = stability.get("avg_rate")
                    if avg_rate is not None:
                        print(f"- **安定度**: {stab_label}（3年平均: {avg_rate*100:.2f}%）")
                    else:
                        print(f"- **安定度**: {stab_label}")
        elif len(sr_hist) == 1 and HAS_RETURN_STABILITY:
            stability = assess_return_stability(sr_hist)
            stab_label = stability.get("label", "")
            if stab_label and stab_label != "-":
                print()
                print("## 株主還元安定度")
                entry = sr_hist[0]
                rate = entry.get("total_return_rate")
                if rate is not None:
                    fy = entry.get("fiscal_year")
                    fy_str = f"{fy}年: " if fy else ""
                    print(f"- {fy_str}総還元率 {rate*100:.2f}%")
                print(f"- **安定度**: {stab_label}")

    # KIK-433: Industry context from Neo4j (same-sector research)
    _sector = data.get("sector") or ""
    if HAS_INDUSTRY_CONTEXT and _sector:
        try:
            industry_ctx = get_industry_research_for_sector(_sector, days=30)
        except Exception:
            industry_ctx = []
        if industry_ctx:
            print()
            print("## 業界コンテキスト（同セクター直近リサーチ）")
            for ctx in industry_ctx[:3]:
                target = ctx.get("target", "")
                date_str = ctx.get("date", "")
                summary = ctx.get("summary", "")
                cats = ctx.get("catalysts", [])
                growth = [c["text"] for c in cats if c.get("type") == "growth_driver"]
                risks  = [c["text"] for c in cats if c.get("type") == "risk"]
                print(f"\n### {target} ({date_str})")
                if summary:
                    print(summary[:200])
                if growth:
                    print("**追い風:** " + "、".join(growth[:3]))
                if risks:
                    print("**リスク:** " + "、".join(risks[:3]))

    # KIK-406: Prior report comparison
    if HAS_GRAPH_QUERY:
        try:
            prior = get_prior_report(symbol)
            if prior and prior.get("score") is not None:
                diff = score - prior["score"]
                print()
                print("## 前回レポートとの比較")
                print(f"- 前回: {prior['date']} / スコア {prior['score']:.1f} / {prior.get('verdict', '-')}")
                print(f"- 今回: スコア {score:.1f} / {verdict}")
                print(f"- 変化: {diff:+.1f}pt")
        except Exception:
            pass

    if HAS_HISTORY:
        try:
            history_save_report(symbol, data, score, verdict)
        except Exception as e:
            print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)

    # Proactive suggestions (KIK-465)
    print_suggestions(symbol=symbol, context_summary=f"レポート生成: {symbol}")


if __name__ == "__main__":
    main()
