#!/usr/bin/env python3
"""Backfill LessonCommunity for existing lesson notes (KIK-571).

Usage:
    python3 scripts/backfill_lesson_communities.py [--dry-run]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.note_manager import load_notes
from src.data.lesson_community import classify_lesson, merge_lesson_community
from src.data.lesson_conflict import extract_trigger


def backfill(dry_run: bool = False) -> dict:
    lessons = load_notes(note_type="lesson")
    if not lessons:
        print("No lessons found.")
        return {"total": 0, "classified": {}}

    classified: dict[str, list[str]] = {}
    for les in lessons:
        content = les.get("content", "")
        trigger = extract_trigger(les)
        community = classify_lesson(content, trigger)

        symbol = les.get("symbol", "")
        label = f"{symbol}: {(content or trigger)[:40]}" if symbol else (content or trigger)[:50]

        classified.setdefault(community, []).append(label)

        if not dry_run:
            note_id = les.get("id", "")
            if note_id:
                merge_lesson_community(note_id, community)

    return {"total": len(lessons), "classified": classified}


def main():
    parser = argparse.ArgumentParser(description="Backfill lesson communities (KIK-571)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY-RUN] No changes will be made.\n")

    stats = backfill(dry_run=args.dry_run)

    print(f"Total lessons: {stats['total']}")
    for community, items in sorted(stats["classified"].items()):
        print(f"\n  [{community}] ({len(items)}件)")
        for item in items:
            print(f"    - {item}")


if __name__ == "__main__":
    main()
