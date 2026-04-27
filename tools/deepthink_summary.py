"""DeepThink 月次集計コマンド (KIK-732).

Reads data/logs/deepthink_meta.jsonl and prints monthly aggregation:
  - Per-tool call count and cost (gemini_deep_research / bulk_x_search / bulk_web_search)
  - Total cost vs monthly budget ($50 default from deepthink_limits.yaml)

Usage:
  python3 tools/deepthink_summary.py                # Current month
  python3 tools/deepthink_summary.py --month 2026-04
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for SSoT import
_project_root = str(Path(__file__).resolve().parent.parent)
import sys as _sys
if _project_root not in _sys.path:
    _sys.path.insert(0, _project_root)

from src.data.deepthink_meta import META_LOG_PATH as _META_LOG_PATH  # noqa: E402

_DEFAULT_MONTHLY_BUDGET_USD = 50.0


def load_meta_records(month: str) -> list[dict]:
    """Load JSONL records whose 'ts' falls in the given month (YYYY-MM)."""
    if not _META_LOG_PATH.exists():
        return []
    records = []
    with open(_META_LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("ts", "")
            if ts.startswith(month):
                records.append(rec)
    return records


def summarize(records: list[dict]) -> dict:
    """Aggregate by tool: count, total_cost_usd, actual_cost_usd, errors.

    KIK-737: actual_cost_usd is summed from records that include it
    (Gemini DR usageMetadata-based). Used for estimate vs actual divergence.
    """
    by_tool: dict = defaultdict(
        lambda: {"count": 0, "cost_usd": 0.0, "actual_cost_usd": 0.0, "errors": 0}
    )
    total_cost = 0.0
    total_actual = 0.0
    for r in records:
        tool = r.get("tool", "unknown")
        by_tool[tool]["count"] += 1
        cost = float(r.get("cost_usd") or 0)
        actual = float(r.get("actual_cost_usd") or 0)
        by_tool[tool]["cost_usd"] += cost
        by_tool[tool]["actual_cost_usd"] += actual
        total_cost += cost
        total_actual += actual
        if r.get("status") not in (None, "ok") or r.get("error"):
            by_tool[tool]["errors"] += 1
    return {
        "total_cost_usd": round(total_cost, 2),
        "total_actual_cost_usd": round(total_actual, 2),
        "by_tool": {
            k: {
                **v,
                "cost_usd": round(v["cost_usd"], 2),
                "actual_cost_usd": round(v["actual_cost_usd"], 2),
            }
            for k, v in by_tool.items()
        },
    }


def format_summary(month: str, summary: dict, budget_usd: float) -> str:
    lines = [f"📊 DeepThink 利用状況（{month}）"]
    by_tool = summary["by_tool"]
    if not by_tool:
        lines.append("  実行記録なし")
    else:
        for tool, data in sorted(by_tool.items()):
            err_part = f" (errors: {data['errors']})" if data["errors"] else ""
            actual = data.get("actual_cost_usd", 0.0)
            actual_part = f" / actual ${actual:.2f}" if actual else ""
            lines.append(
                f"  {tool}: {data['count']}回 / est ${data['cost_usd']:.2f}{actual_part}{err_part}"
            )
    lines.append("  ────────────────────")
    total = summary["total_cost_usd"]
    actual_total = summary.get("total_actual_cost_usd", 0.0)
    pct = (total / budget_usd * 100) if budget_usd else 0
    lines.append(
        f"  合計: estimate ${total:.2f} / actual ${actual_total:.2f} / 月予算 ${budget_usd:.2f} ({pct:.0f}%)"
    )
    if pct >= 80:
        lines.append("  ⚠ 月予算 80% 到達。残り使用は要注意")
    # KIK-737: Estimate vs Actual divergence warning (>20%)
    if actual_total > 0 and total > 0:
        divergence = abs(actual_total - total) / total * 100
        if divergence > 20:
            direction = "過大" if total > actual_total else "過小"
            lines.append(
                f"  ⚠ コスト推定の精度を再校正してください（estimate {direction}見積もり、乖離 {divergence:.0f}%）"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DeepThink monthly cost summary")
    parser.add_argument(
        "--month",
        default=None,
        help="Target month YYYY-MM (default: current UTC month)",
    )
    parser.add_argument(
        "--budget-usd",
        type=float,
        default=_DEFAULT_MONTHLY_BUDGET_USD,
        help=f"Monthly budget USD (default {_DEFAULT_MONTHLY_BUDGET_USD})",
    )
    args = parser.parse_args(argv)

    month = args.month or datetime.now(timezone.utc).strftime("%Y-%m")
    records = load_meta_records(month)
    summary = summarize(records)
    print(format_summary(month, summary, args.budget_usd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
