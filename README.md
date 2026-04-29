# stock-skills v2

> **Version 2** — [stock_skills v1](https://github.com/okikusan-public/stock_skills) を元に、Agentic AI Pattern で全面リニューアル。
> v1 ではスクリプトにルール・判断ロジックが埋め込まれていたが、v2 ではスクリプトを全廃し、AI が自律的にツール選択・パラメータ決定・実行・レビューする構成に移行した。

投資アシスタントシステム。Agentic AI Pattern で設計。自然言語で話しかけるだけで、銘柄探索・分析・ポートフォリオ管理・リスク評価が自動実行される。

## システム要件

- **[Claude Code](https://claude.ai/code)** — 本システムのランタイム。SKILL.md をオーケストレーターとして読み込み、エージェントを自律的に起動・制御する。Claude Code なしでは動作しない
- **Python 3.10+** — ツール（tools/）の実行環境
- **Anthropic サブスクリプション** — Claude Code の利用に必要

## セットアップ

```bash
pip install -r requirements.txt
```

依存: yfinance, pyyaml, numpy, pandas, requests, python-dotenv

### 環境変数

```bash
# Grok API（Xセンチメント分析、任意）
export XAI_API_KEY=xai-xxxxxxxxxxxxx

# Gemini API（マルチLLMレビュー、任意）
export GEMINI_API_KEY=AIzaSy...

# OpenAI API（マルチLLMレビュー、任意）
export OPENAI_API_KEY=sk-proj-...

# Neo4j（GraphRAG、任意）
export NEO4J_URI=bolt://localhost:7688
export NEO4J_MODE=full  # off/summary/full
export NEO4J_DEBUG=1    # 接続失敗時の診断を初回1回だけ stderr に出す（既定: 無音）
```

すべて任意。未設定でもデフォルト値で動作する。

## 使い方

自然言語で話しかけるだけ:

```
「いい日本株ある？」      → Screener が自律的にスクリーニング
「トヨタってどう？」      → Analyst がバリュエーション分析
「最新ニュース教えて」    → Researcher が Grok API でニュース取得
「PF大丈夫？」           → Health Checker が数値を出し、Strategist がレコメンド
「暴落したらどうなる？」   → Health Checker がストレステスト実行
「メモしておいて」        → 投資メモを直接保存
```

### 出力フォーマット（Output &amp; Visibility v1）

すべての応答は4レイヤ構成で表示される（KIK-729）。

```
🎯 [&lt;agent or chain&gt;] &lt;task summary&gt;        ← Layer 1 ヘッダ（常時表示）
✅ &lt;agent&gt; 完了 (X.Xs) — &lt;1行サマリ&gt;        ← Layer 2 進捗（連鎖時のみ）

[Layer 3 本体: Pattern A/B/Cで切替]
- Pattern A: ミニマル（VIX/TODO/価格 等の即答）
- Pattern B: 標準4セクション（単一エージェント分析）
- Pattern C: チェーン（複数エージェント連鎖・routine）

📊 実行: A → B → C                          ← Layer 4 フッタ（順序固定）
💾 保存: data/&lt;path&gt;
🔍 Reviewerでチェック？ [y/skip]
➡ 次: &lt;次アクション提案&gt;
```

Reviewer は **3分類で起動制御**:
- 🔒 **自動**: 売買確定直前 / conviction違反検知 / 週次routine
- 🔍 **アドホック**: その他strategist/screener等 → 末尾に [y/skip] プロンプト → 次ターンで `y` 入力で起動
- ⏭ **スキップ**: HC/researcher/analyst/risk-assessor 単独

## アーキテクチャ

```
Orchestrator (.claude/skills/stock-skills/)
  ├─ SKILL.md          — ルーティング・自律制御
  ├─ routing.yaml      — エージェント選択 few-shot
  └─ orchestration.yaml — リトライ・エスカレーション

Agents (.claude/agents/) — 7名
  ├─ screener/       — 銘柄探し（region/preset/theme を自律決定）
  ├─ analyst/        — バリュエーション・割安度・ETF評価
  ├─ researcher/     — ニュース・センチメント・業界・市況
  ├─ health-checker/ — PFの事実・数値（判断しない）
  ├─ strategist/     — 投資判断・レコメンド（他エージェントの結果を統合）
  ├─ risk-assessor/  — 市場リスク判定（risk-on/neutral/risk-off）
  └─ reviewer/       — 品質・リスクチェック（GPT+Gemini+Claude 並列レビュー）

Tools (tools/)
  ├─ yahoo_finance.py — 株価・ファンダメンタルズ
  ├─ graphrag.py      — Neo4j ナレッジグラフ
  ├─ grok.py          — Grok API（X/Web検索）
  └─ llm.py           — マルチLLM（Gemini/GPT/Grok）

Data (src/data/) — yahoo_client, grok_client, graph_store, graph_query, common, ticker_utils, portfolio_io
```

詳細は [docs/architecture.md](docs/architecture.md) を参照。

## Neo4j ナレッジグラフ（オプション）

エージェント実行履歴を Neo4j に蓄積し、過去の分析・取引・リサーチを横断検索できる。

```bash
docker compose up -d
```

**新規利用は data/ ローカルストレージで完結します。Neo4j はオプション機能です。** 既に Neo4j を運用中の方はそのまま使い続けられます（graceful degradation 完全対応）。Neo4j 未接続時は `data/notes/`・`data/portfolio.csv`・`data/screening_results/` 等から自動コンテキスト注入が動作します（KIK-719）。未接続時の警告は出力されません。診断したい場合は `NEO4J_DEBUG=1`（KIK-749）。

## テスト

```bash
# ユニットテスト（API key/ネットワーク不要、autouse fixture で外部I/Oを完全モック）
python3 -m pytest tests/ -q           # 1381 テスト (~55秒)

# Dry-run（routing.yaml + agent定義の整合性検証、< 1秒、API key不要）KIK-746
python3 tests/e2e/run_e2e.py --dry-run

# モック E2E（pytest fixture で tools 層 stub 化、< 1秒、API key不要）KIK-747
python3 -m pytest tests/e2e/test_mocked.py -q

# 実 API E2E テスト（Yahoo Finance / LLM 実呼び出し、要 API key）
python3 tests/e2e/run_e2e.py          # 全シナリオ実行 (~25秒)
python3 tests/e2e/run_e2e.py e2e_001  # 特定シナリオのみ
```

### Worktree セットアップ（KIK-745）

開発用 worktree は `scripts/setup_worktree.sh` で個人PFを使わず即セットアップ:

```bash
bash scripts/setup_worktree.sh KIK-NNN feature-name
# → ~/stock-skills-kikNNN に展開、tests/fixtures/sample_portfolio.csv を
#    data/ にコピー（汎用テスト銘柄、個人PFは流さない）
```

### E2E テストシナリオ

| ID | エージェント | 入力例 | 検証内容 |
|:---|:---|:---|:---|
| e2e_001 | Screener | いい日本株ある？ | EquityQuery、銘柄リスト、region |
| e2e_002 | Analyst | 7203.Tってどう？ | PER/PBR/ROE、価格履歴 |
| e2e_003 | Health Checker | PF大丈夫？ | 15銘柄、thesis/observation、還元率 |
| e2e_004 | Researcher | 最新ニュース | Grok API、センチメント、GraphRAG |
| e2e_005 | Risk Assessor | リスク判定して | VIX/金利/WTI、RSI計算 |
| e2e_006 | HC + Strategist | PF改善したい | lesson、thesis、what-if |

## v1 からの移行

v1（[stock_skills](https://github.com/okikusan-public/stock_skills)）からの移行が可能です。

### データ互換性

v1 で蓄積した以下のデータはそのまま v2 で利用できます:

| データ | v1 の場所 | v2 の場所 | 互換性 |
|:---|:---|:---|:---|
| 投資メモ・lesson | `data/notes/*.json` | `data/notes/*.json` | 完全互換 |
| スクリーニング履歴 | `data/history/screen/*.json` | `data/history/screen/*.json` | 完全互換 |
| 売買記録 | `data/history/trade/*.json` | `data/history/trade/*.json` | 完全互換 |
| レポート履歴 | `data/history/report/*.json` | `data/history/report/*.json` | 完全互換 |
| リサーチ履歴 | `data/history/research/*.json` | `data/history/research/*.json` | 完全互換 |
| ヘルスチェック履歴 | `data/history/health/*.json` | `data/history/health/*.json` | 完全互換 |
| ポートフォリオ | `data/portfolio.csv` | `data/portfolio.csv` | 完全互換 |
| ウォッチリスト | `data/watchlists/*.json` | `data/watchlists/*.json` | 完全互換 |
| Neo4j（GraphRAG） | そのまま接続 | そのまま接続 | 完全互換 |

### 移行手順

```bash
# 1. v2 をクローン
git clone https://github.com/okikusan-public/stock_skills_2.git
cd stock_skills_2

# 2. v1 の data/ ディレクトリをコピー
cp -r /path/to/stock_skills/data/ ./data/

# 3. 依存インストール
pip install -r requirements.txt

# 4. （任意）GraphRAG と同期
# v2 で「sync して」と話しかけると data/ → Neo4j の同期が実行される
```

v1 の `scripts/`、`src/output/`、旧 `SKILL.md` 群は v2 では不要です。`data/` だけをコピーすれば移行完了です。

## 免責事項

本ソフトウェアは投資判断の参考情報を提供するものであり、**投資成果を保証するものではありません**。本ソフトウェアの出力に基づく投資判断はすべて利用者自身の責任で行ってください。開発者は、本ソフトウェアの利用により生じたいかなる損害についても責任を負いません。

## ライセンス

MIT License。詳細は [LICENSE](LICENSE) を参照。
