"""Backfill structured metadata for lesson notes (KIK-738 Phase 2).

Many existing lessons (24/28 as of 2026-04-28) lack `trigger`,
`expected_action`, and `key_kpis` fields. KIK-736's lesson_enforcer
filters by trigger, so these lessons are effectively invisible.

This script reads each lesson without trigger, asks Gemini to extract the
3 fields from `content`, and updates the lesson via
`note_manager.update_lesson_metadata()`.

Usage
-----
Dry-run (writes CSV report to /tmp/lesson_backfill.csv, no JSON write):
    python3 scripts/backfill_lesson_fields.py --dry-run

Execute (also writes a git commit before editing for rollback):
    python3 scripts/backfill_lesson_fields.py --execute

Limit to N lessons (debugging):
    python3 scripts/backfill_lesson_fields.py --dry-run --limit 3
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env so GEMINI_API_KEY is visible when run as a script
from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

from tools.llm import call_llm  # noqa: E402
from tools.notes import load_notes  # noqa: E402
from src.data.note_manager import update_lesson_metadata  # noqa: E402


_SYSTEM_PROMPT = """\
あなたは投資 lesson のメタデータ抽出器です。lesson の `content` (narrative テキスト) から、\
KIK-736 lesson_enforcer がフィルタ・検証に使う 3 フィールドを JSON で抽出します。

抽出ルール:
- trigger: 2-5 個の自然言語条件をスラッシュ「/」で区切って 1 行に。各条件は 3-15 文字。\
  数値条件 (例: 含み損-15%超) や定性条件 (例: ユーザー確信表明時) を混在 OK。\
  「■trigger:」セクションが content に既存なら最優先で抽出。
- expected_action: 実行可能な single statement (20-40 文字、句点なし)。\
  曖昧形 (「検討する」) を避け、「○○を確認」「○○を実行」のような行為動詞で。
- key_kpis: メジャー可能な指標を 2-4 個リストアップ。\
  例: ["含み損率", "PER", "Cash 比率"]。content に明示的にある指標のみ。

出力は次の JSON フォーマットのみ。前置き・後置きの説明文は禁止。
{"trigger": "...", "expected_action": "...", "key_kpis": ["...", "..."]}
"""

_USER_TEMPLATE = """\
次の lesson から trigger / expected_action / key_kpis を JSON で抽出せよ。

date: {date}
symbol: {symbol}
content:
\"\"\"
{content}
\"\"\"
"""


def _extract_json(text: str) -> dict | None:
    """Best-effort JSON extraction from LLM output."""
    if not text:
        return None
    # Strip markdown code fences if present
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    payload = fence.group(1) if fence else text
    # Find first { ... } block
    brace = re.search(r"\{.*\}", payload, re.S)
    if not brace:
        return None
    try:
        obj = json.loads(brace.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _extract_one(lesson: dict) -> dict | None:
    """Call Gemini to extract metadata for a single lesson."""
    prompt = _USER_TEMPLATE.format(
        date=lesson.get("date", "(unknown)"),
        symbol=lesson.get("symbol") or "(none)",
        content=(lesson.get("content") or "")[:2000],
    )
    raw = call_llm(
        provider="gemini",
        model="gemini-2.5-pro",
        prompt=prompt,
        system_prompt=_SYSTEM_PROMPT,
        timeout=60,
    )
    if not raw:
        return None
    obj = _extract_json(raw)
    if not obj:
        return None
    # Normalize
    return {
        "trigger": (obj.get("trigger") or "").strip(),
        "expected_action": (obj.get("expected_action") or "").strip(),
        "key_kpis": [str(k).strip() for k in (obj.get("key_kpis") or []) if str(k).strip()][:4],
    }


def _validate_extracted(extracted: dict) -> list[str]:
    """Sanity checks. Returns a list of warnings (empty if OK)."""
    warns: list[str] = []
    trg = extracted.get("trigger", "")
    act = extracted.get("expected_action", "")
    if not trg:
        warns.append("trigger empty")
    elif len(trg) > 80:
        warns.append(f"trigger too long ({len(trg)} chars)")
    if not act:
        warns.append("expected_action empty")
    elif len(act) > 80:
        warns.append(f"expected_action too long ({len(act)} chars)")
    if extracted.get("key_kpis") is None or not isinstance(extracted["key_kpis"], list):
        warns.append("key_kpis not list")
    return warns


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Backfill lesson trigger/expected_action/key_kpis (KIK-738)")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true", help="Extract only, write CSV report, no JSON write")
    grp.add_argument("--execute", action="store_true", help="Apply changes via update_lesson_metadata")
    p.add_argument("--limit", type=int, default=None, help="Process only first N lessons (debugging)")
    p.add_argument(
        "--csv-out", default="/tmp/lesson_backfill.csv",
        help="CSV report path (dry-run mode)",
    )
    args = p.parse_args(argv)

    lessons = load_notes(note_type="lesson")
    targets = [l for l in lessons if not l.get("trigger")]
    if args.limit:
        targets = targets[: args.limit]

    print(f"Total lessons: {len(lessons)}, missing trigger: {len(targets)}", file=sys.stderr)
    if not targets:
        print("Nothing to backfill.", file=sys.stderr)
        return 0

    rows: list[dict] = []
    applied = 0
    for i, lesson in enumerate(targets, 1):
        nid = lesson.get("id", "")
        date = lesson.get("date", "")
        print(f"[{i}/{len(targets)}] {date} {nid[:30]} ...", file=sys.stderr, end=" ", flush=True)
        extracted = _extract_one(lesson)
        if extracted is None:
            print("SKIP (extraction failed)", file=sys.stderr)
            rows.append({
                "id": nid, "date": date,
                "trigger": "(failed)", "expected_action": "", "key_kpis": "",
                "warnings": "extraction failed",
                "content_preview": (lesson.get("content") or "")[:100].replace("\n", " "),
            })
            continue
        warns = _validate_extracted(extracted)
        rows.append({
            "id": nid, "date": date,
            "trigger": extracted["trigger"],
            "expected_action": extracted["expected_action"],
            "key_kpis": " / ".join(extracted["key_kpis"]),
            "warnings": "; ".join(warns),
            "content_preview": (lesson.get("content") or "")[:100].replace("\n", " "),
        })
        if args.execute:
            updated = update_lesson_metadata(
                nid,
                trigger=extracted["trigger"] or None,
                expected_action=extracted["expected_action"] or None,
                key_kpis=extracted["key_kpis"] or None,
            )
            if updated is None:
                print("WARN (update_lesson_metadata returned None)", file=sys.stderr)
            else:
                applied += 1
                print(f"OK {extracted['trigger'][:30]}", file=sys.stderr)
        else:
            print(f"OK (dry) {extracted['trigger'][:30]}", file=sys.stderr)

    # Write CSV
    out_path = Path(args.csv_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "date", "trigger", "expected_action", "key_kpis", "warnings", "content_preview",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV report: {out_path}", file=sys.stderr)

    if args.execute:
        print(f"Applied: {applied}/{len(targets)}", file=sys.stderr)
    else:
        print(f"Dry-run: {len(rows)} extracted (no JSON written)", file=sys.stderr)
        print("Review CSV, then re-run with --execute to apply.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
