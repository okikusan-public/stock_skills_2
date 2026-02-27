# 開発ワークフロールール

> コーディング規約・依存・テストインフラは [development.md](development.md) を参照。

## 原則

- すべての開発作業は **Worktree 上で実施**する（main ブランチ直接編集禁止）
- 各 issue は **設計→実装→単体テスト→コードレビュー→結合試験** の5フェーズで進める
- 結合試験は **Teams（エージェントチーム）** を組んで並列実施する

## 1. Worktree 作成

```bash
# Linear issue KIK-NNN に対して
git worktree add -b feature/kik-{NNN}-{short-desc} ~/stock-skills-kik{NNN} main
```

- 作業ディレクトリ: `~/stock-skills-kik{NNN}`
- ブランチ名: `feature/kik-{NNN}-{short-desc}`
- 以降のすべての作業（実装・テスト・結合試験）はこのworktree上で行う

### Worktree 上の準備（gitignore対象ファイル）

結合試験でポートフォリオ系コマンドを使う場合、gitignore対象のデータをコピーする:

```bash
mkdir -p ~/stock-skills-kik{NNN}/.claude/skills/stock-portfolio/data
cp ~/stock-skills/.claude/skills/stock-portfolio/data/portfolio.csv \
   ~/stock-skills-kik{NNN}/.claude/skills/stock-portfolio/data/
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
| screener-tester | スクリーニング | `run_screen.py` を複数プリセット・リージョンで実行 |
| report-tester | レポート+ウォッチリスト | `generate_report.py` + `manage_watchlist.py` の CRUD |
| portfolio-tester | ポートフォリオ | `run_portfolio.py` の全サブコマンド（list/snapshot/analyze/health/forecast） |
| stress-tester | ストレステスト | `run_stress_test.py` を複数シナリオで実行 |

### 実施手順

1. `TeamCreate` でチーム作成（例: `kik{NNN}-integration-test`）
2. `TaskCreate` で各テスターのタスクを作成
3. `Task` で4テスターを並列起動（`team_name` 指定、Worktree のパスを明示）
4. 全テスター PASS を確認
5. チームをシャットダウン・削除

### 結合試験のスクリプト実行パス

Worktree上で実行するため、パスを明示する:

```bash
cd ~/stock-skills-kik{NNN}
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region japan --preset value --top 5
python3 .claude/skills/stock-report/scripts/generate_report.py 7203.T
python3 .claude/skills/watchlist/scripts/manage_watchlist.py list
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py snapshot
python3 .claude/skills/stress-test/scripts/run_stress_test.py --portfolio 7203.T,AAPL
```

### 影響範囲に応じたテスター選定

変更が特定のスキルに限定される場合、関連テスターのみで結合試験を実施してよい。
ただしコアモジュール（`src/core/`）の変更は全テスター必須。

## 7. ドキュメント・ルール更新

**機能実装後、マージ前に必ず以下を確認・更新する。**

### 自動生成ドキュメント（KIK-525）

以下は `scripts/generate_docs.py all` で自動生成されるため手動更新不要:

| 対象 | 自動生成内容 |
|:---|:---|
| `docs/api-reference.md` | src/ の public 関数・クラスのシグネチャ |
| `CLAUDE.md` Architecture | レイヤー概要（モジュール一覧 + KIK アノテーション） |
| `development.md` テスト数 | `約NNNテスト` のカウント |
| `docs/skill-catalog.md` 概要 | スキル一覧テーブル |

pre-commit hook で src/ 変更時に自動実行される。新しいモジュールにKIKアノテーションを付けたい場合は `config/module_annotations.yaml` を編集する。

### 手動更新チェックリスト

| 対象 | 更新条件 | 更新内容 |
|:---|:---|:---|
| `intent-routing.md` | 新しいキーワード・意図が増えた | ドメイン判定テーブル、キーワード追加 |
| 該当 `SKILL.md` | スキルの機能・出力が変わった | description、出力項目、コマンド例 |
| `rules/portfolio.md` | PF系の機能が追加・変更された | セクション追加、KIK番号追記 |
| `rules/screening.md` | スクリーニング系の機能が追加・変更された | ルール追記 |
| `docs/data-models.md` | stock_info/stock_detail のフィールドが変わった | テーブル更新（fixture と整合性検証あり） |
| `README.md` | ユーザー向けの機能説明が必要 | スキル説明、使用例 |

### 判断基準

- **新機能追加**: intent-routing + SKILL.md + README.md を手動更新（CLAUDE.md Architecture は自動）
- **既存機能の改善**: 該当する SKILL.md + rules のみ
- **バグ修正のみ**: ドキュメント更新不要（ただし挙動が変わる場合は SKILL.md を更新）

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
