# 開発ワークフロールール

> コーディング規約・依存・テストインフラは [development.md](development.md) を参照。

## 原則

- すべての開発作業は **Worktree 上で実施**する（main ブランチ直接編集禁止）
- 各 issue は **設計→実装→単体テスト→コードレビュー→結合試験** の5フェーズで進める
- 結合試験は **Teams（エージェントチーム）** を組んで並列実施する

## 1. Worktree 作成

**推奨**: ヘルパースクリプトで一括セットアップ（KIK-745）

```bash
bash scripts/setup_worktree.sh KIK-NNN [short-desc]
# → worktree作成 + sample fixture コピー (個人PFは触らない)
# → ~/stock-skills-kik{NNN} に展開、即 pytest 実行可能
```

手動の場合:

```bash
git worktree add -b feature/kik-{NNN}-{short-desc} ~/stock-skills-kik{NNN} main
mkdir -p ~/stock-skills-kik{NNN}/data
cp tests/fixtures/sample_portfolio.csv ~/stock-skills-kik{NNN}/data/portfolio.csv
cp tests/fixtures/sample_cash_balance.json ~/stock-skills-kik{NNN}/data/cash_balance.json
```

- 作業ディレクトリ: `~/stock-skills-kik{NNN}`
- ブランチ名: `feature/kik-{NNN}-{short-desc}`
- 以降のすべての作業（実装・テスト・結合試験）はこのworktree上で行う

### Worktree 上の準備（KIK-745 で更新）

⚠️ **個人PF（`~/stock-skills/data/portfolio.csv` など）を `cp` で worktree に
コピーすることは禁止**。誤って `git add -f` した場合に個人銘柄・実数量が
公開リポへリークするため。

代わりに以下のいずれかを使用:

1. `tests/fixtures/sample_portfolio.csv` の汎用テスト銘柄（推奨）
2. 環境変数で個人 PF を**読み取り専用参照**:
   ```bash
   export STOCK_SKILLS_DATA_DIR=$HOME/stock-skills/data
   # tools/portfolio_io.py の csv_path 引数に渡す
   ```

## 2. 設計フェーズ

- `EnterPlanMode` でコードベースを調査し、実装方針を策定する
- 影響範囲・変更ファイル・テスト方針を明確にする
- ユーザー承認を得てから実装に進む

## 3. 実装フェーズ

- Worktree 上でコード変更を行う
- PostToolUse hook により `.py` ファイル編集時は自動で `pytest tests/ -q` が実行される
- 全テスト PASS を維持しながら実装を進める

## 4. 単体テスト

- 新規モジュールには対応するテストファイルを作成する
- `python3 -m pytest tests/ -q` で全件 PASS を確認する
- Worktree 上で実行: `cd ~/stock-skills-kik{NNN} && python3 -m pytest tests/ -q`

## 5. コードレビュー（Teams）

単体テスト PASS 後、**レビューチームを組んで変更内容を多角的に検証**する。

### チーム構成

| レビュアー名 | 観点 | チェック内容 |
|-------------|------|-------------|
| arch-reviewer | 設計・構造 | モジュール分割、責務分離、既存パターンとの整合性、循環依存の有無 |
| logic-reviewer | ロジック・正確性 | 計算ロジックの正しさ、エッジケース、エラーハンドリング、異常値ガードの漏れ |
| test-reviewer | テスト品質 | テストカバレッジ、境界値テスト、モックの適切さ、テストの独立性 |

### 実施手順

1. `TeamCreate` でチーム作成（例: `kik{NNN}-code-review`）
2. `TaskCreate` で各レビュアーのタスクを作成（対象ファイル・変更差分を明示）
3. `Task` で3レビュアーを並列起動（`subagent_type=Explore`、Worktree のパスを明示）
4. 各レビュアーから指摘を収集
5. 指摘があれば修正 → 単体テスト再実行 → 再レビュー（必要に応じて）
6. 全レビュアー LGTM で結合試験へ進む
7. チームをシャットダウン・削除

### レビュー対象の渡し方

レビュアーには以下の情報を提供する:

- Worktree パス: `~/stock-skills-kik{NNN}`
- 変更ファイル一覧: `git diff --name-only main` の結果
- 変更差分: `git diff main` の概要
- 設計意図: 設計フェーズで決めた方針の要約

### 影響範囲に応じたレビュアー選定

変更が小規模（1-2ファイル、ロジック変更なし）の場合、logic-reviewer のみで可。
新規モジュール追加や大規模リファクタリングは全レビュアー必須。

## 6. 結合試験（Teams）

実装完了後、**エージェントチームを組んで各スキルの動作を検証**する。

### チーム構成（標準）

| テスター名 | 担当 | 検証内容 |
|-----------|------|---------|
| screener-tester | スクリーニング | Screener エージェントを複数パターンで実行 |
| analyst-tester | 分析 | Analyst エージェントで銘柄分析・ETF評価 |
| portfolio-tester | ポートフォリオ | Health Checker + Strategist で PF 診断・レコメンド |
| researcher-tester | リサーチ | Researcher エージェントでニュース・センチメント取得 |

### 実施手順

1. `TeamCreate` でチーム作成（例: `kik{NNN}-integration-test`）
2. `TaskCreate` で各テスターのタスクを作成
3. `Task` で4テスターを並列起動（`team_name` 指定、Worktree のパスを明示）
4. 全テスター PASS を確認
5. チームをシャットダウン・削除

### 結合試験の実行方法

Worktree 上でエージェントを自然言語で呼び出して動作確認する:

```
「日本株のバリュー銘柄を探して」     → Screener エージェント
「7203.Tを分析して」               → Analyst エージェント
「最新ニュース教えて」              → Researcher エージェント
「PF大丈夫？」                     → Health Checker エージェント
```

### 影響範囲に応じたテスター選定

変更が特定のスキルに限定される場合、関連テスターのみで結合試験を実施してよい。
ただし共通モジュール（`src/data/common.py`, `src/data/ticker_utils.py`）の変更は全テスター必須。

## 7. ドキュメント・ルール更新

**機能実装後、マージ前に必ず以下を確認・更新する。**

### 更新チェックリスト

| 対象 | 更新条件 | 更新内容 |
|:---|:---|:---|
| 該当 `agent.md` + `examples.yaml` | エージェントの役割・ツールが変わった | 判断プロセス、few-shot 例 |
| `routing.yaml` | 新しい意図パターンが増えた | triggers、examples 追加 |
| `orchestration.yaml` | リトライ・レビュー条件が変わった | ルール追加 |
| `CLAUDE.md` | アーキテクチャが変わった | 構成図、ツール一覧 |
| `docs/data-models.md` | stock_info/stock_detail のフィールドが変わった | テーブル更新 |
| `README.md` | ユーザー向けの機能説明が必要 | 使い方、セットアップ |

### 判断基準

- **新機能追加**: agent.md + examples.yaml + routing.yaml + README.md を更新
- **既存機能の改善**: 該当 agent.md + examples.yaml のみ
- **バグ修正のみ**: ドキュメント更新不要（ただし挙動が変わる場合は agent.md を更新）

## 8. 完了

```bash
# main にマージ
cd ~/stock-skills
git merge --no-ff feature/kik-{NNN}-{short-desc}
git push

# Worktree 削除
git worktree remove ~/stock-skills-kik{NNN}
git branch -d feature/kik-{NNN}-{short-desc}
```

- Linear issue を Done に更新する
