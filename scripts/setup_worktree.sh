#!/usr/bin/env bash
# scripts/setup_worktree.sh — KIK-745
#
# 開発用 worktree を作成し、tests/fixtures/ のサンプルデータを data/ に
# コピーして即座に開発・結合試験できる状態にする。
#
# Usage:
#   bash scripts/setup_worktree.sh KIK-NNN [short-desc]
#
# Example:
#   bash scripts/setup_worktree.sh KIK-748 add-feature
#
# 重要:
#   個人 PF データ（~/stock-skills/data/portfolio.csv 等）は **絶対に**
#   コピーしない。汎用テスト銘柄のみを含む sample fixture を使う。

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 KIK-NNN [short-desc]" >&2
    exit 1
fi

ISSUE="$1"
SHORT_DESC="${2:-task}"

# Issue 番号を小文字化（KIK-748 → kik748）
ISSUE_LOWER=$(echo "$ISSUE" | tr '[:upper:]' '[:lower:]' | tr -d '-')
BRANCH="feature/$(echo "$ISSUE" | tr '[:upper:]' '[:lower:]')-${SHORT_DESC}"
WORKTREE="${HOME}/stock-skills-${ISSUE_LOWER}"

# main repo path（このスクリプトが置かれているリポジトリのルート）
MAIN_REPO="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -d "$WORKTREE" ]]; then
    echo "Error: worktree already exists at $WORKTREE" >&2
    exit 1
fi

echo "Creating worktree:"
echo "  branch:  $BRANCH"
echo "  path:    $WORKTREE"
git -C "$MAIN_REPO" worktree add -b "$BRANCH" "$WORKTREE" main

echo "Seeding sample fixtures (NOT personal PF):"
mkdir -p "$WORKTREE/data"
cp "$MAIN_REPO/tests/fixtures/sample_portfolio.csv" "$WORKTREE/data/portfolio.csv"
cp "$MAIN_REPO/tests/fixtures/sample_cash_balance.json" "$WORKTREE/data/cash_balance.json"
echo "  ✓ data/portfolio.csv      (from sample_portfolio.csv)"
echo "  ✓ data/cash_balance.json  (from sample_cash_balance.json)"

cat <<EOF

✅ Worktree ready: $WORKTREE
   cd $WORKTREE
   python3 -m pytest tests/ -q   # ← unit tests pass without personal data

⚠ 注意:
   このworktreeには汎用テスト銘柄しか入っていません。
   個人 PF を反映した結合試験が必要な場合は環境変数で参照:
     export STOCK_SKILLS_DATA_DIR=$HOME/stock-skills/data
   個人 PF を worktree に cp しないでください（誤コミット防止）。
EOF
