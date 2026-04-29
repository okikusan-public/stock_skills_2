---
paths:
  - "tests/**/*.py"
  - "tests/conftest.py"
  - "tests/fixtures/**"
---

# テスト開発ルール

## テスト実行

```bash
# ユニットテスト（API key/ネットワーク不要）
python3 -m pytest tests/ -q                          # 全件実行（約1381テスト, ~55秒）
python3 -m pytest tests/core/test_ticker_utils.py -v # 特定モジュール
python3 -m pytest tests/ -k "test_note"              # キーワード指定

# Dry-run: routing.yaml + agent定義の整合性検証（< 1秒、API key不要）KIK-746
python3 tests/e2e/run_e2e.py --dry-run

# モック E2E（pytest fixture で tools 層 stub 化、< 1秒、API key不要）KIK-747
python3 -m pytest tests/e2e/test_mocked.py -q

# 実 API E2E テスト（実際の API でエージェント動作を検証、要 API key）
python3 tests/e2e/run_e2e.py                         # 全シナリオ（~25秒）
python3 tests/e2e/run_e2e.py e2e_001                 # 特定シナリオのみ
```

## Worktree セットアップ（KIK-745）

開発用 worktree は専用ヘルパースクリプトで作成し、個人PFを流さない:

```bash
bash scripts/setup_worktree.sh KIK-NNN feature-name
# → ~/stock-skills-kikNNN に展開、tests/fixtures/sample_portfolio.csv を
#    data/portfolio.csv にコピー。個人PF（実銘柄・実数量）は触らない。
```

⚠️ `cp ~/stock-skills/data/portfolio.csv` は禁止。誤コミットで個人PFがリークするリスクのため、
   `tests/fixtures/sample_portfolio.csv`（汎用テスト銘柄）を使うこと。

## テスト構造

- `tests/core/` — コアロジックのユニットテスト（ticker_utils 等）
- `tests/data/` — データ取得層のテスト（yahoo_client, grok_client, graph_store, note_manager 等）
- `tests/e2e/` — E2E エージェントテスト
  - `run_e2e.py` — 実 API シナリオランナー（`--dry-run` で API なし検証）
  - `test_mocked.py` — pytest fixture stub によるモック E2E（KIK-747）
  - `test_scenarios.yaml` — シナリオ定義
- `tests/conftest.py` — 共通フィクスチャ（`_block_external_io` autouse で
  Neo4j/TEI/Grok を全自動モック）
- `tests/fixtures/` — JSON/CSV テストデータ
  - `stock_info.json` / `stock_detail.json` — Toyota 7203.T ベース
  - `sample_portfolio.csv` / `sample_cash_balance.json` — KIK-745 worktree用

## モック方法

### autouse の自動モック (`_block_external_io`)

- Neo4j: `_get_mode()` → "off"、`is_available()` → False
- TEI: `embedding_client.is_available()` → False
- Grok: `XAI_API_KEY` 削除
- mode cache reset (KIK-743)

### モック E2E でのstub対象（test_mocked.py, KIK-747）

- `tools.llm.call_llm` → 固定文字列応答
- `tools.yahoo_finance.get_stock_info / get_stock_detail / screen_stocks /
  get_price_history / get_macro_indicators` → `tests/fixtures/*.json` から返す
- `tools.grok.search_market / search_x_sentiment` → 固定 dict
- API key 全削除（OPENAI/GEMINI/ANTHROPIC/XAI）

### sample fixture の利用

```python
SAMPLE_PORTFOLIO = REPO_ROOT / "tests/fixtures/sample_portfolio.csv"
positions = load_portfolio(str(SAMPLE_PORTFOLIO))  # 個人PF不参照
```

## テスト作成の注意点

- 各テストは独立して実行可能であること（外部 API 依存なし）
- yahoo_client の呼び出しは必ずモックする
- テストデータは `tests/fixtures/` の既存データを再利用
- 新しいモジュールには対応するテストファイルを作成
- 新しいエージェント追加時は `tests/e2e/test_mocked.py` にシナリオ追加（KIK-747）
- routing.yaml 変更時は `tests/test_kik746_dry_run.py::test_routing_yaml_integrity_passes_currently` で検証
