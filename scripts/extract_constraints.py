#!/usr/bin/env python3
"""CLI wrapper for constraint extraction (KIK-596).

Extracts action type and relevant lesson constraints from user query.

Usage:
    python3 scripts/extract_constraints.py "7751.Tを売って代わりを探して"
    python3 scripts/extract_constraints.py "NVDAを買いたい" --format markdown
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TIMEOUT = 10


def _timeout_handler(signum, frame):
    print("タイムアウト: 制約抽出に時間がかかりすぎました", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Extract constraints from lessons")
    parser.add_argument("query", nargs="?", help="User query text")
    parser.add_argument("--query", dest="query_opt", help="User query (alternative)")
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--max-constraints",
        type=int,
        default=5,
        help="Maximum constraints to return (default: 5)",
    )
    args = parser.parse_args()

    query = args.query or args.query_opt
    if not query:
        parser.error("query is required")

    # Set timeout
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_TIMEOUT)

    try:
        from src.data.context.constraint_extractor import (
            extract_constraints,
            format_constraints_markdown,
        )

        result = extract_constraints(query, max_constraints=args.max_constraints)

        if args.format == "markdown":
            print(format_constraints_markdown(result))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)


if __name__ == "__main__":
    main()
