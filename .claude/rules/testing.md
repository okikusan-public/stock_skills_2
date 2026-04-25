---
paths:
  - "tests/**/*.py"
  - "tests/conftest.py"
  - "tests/fixtures/**"
---

# テスト開発ルール

## テスト実行

```bash
# ユニットテスト
python3 -m pytest tests/ -q                        # 全件実行（約979テスト, ~4秒）
python3 -m pytest tests/core/test_ticker_utils.py -v # 特定モジュール
python3 -m pytest tests/ -k "test_note"             # キーワード指定

# E2E テスト（実際の API でエージェント動作を検証）
python3 tests/e2e/run_e2e.py                       # 全6シナリオ（~25秒）
python3 tests/e2e/run_e2e.py e2e_001               # 特定シナリオのみ
```

## テスト構造

- `tests/core/` — コアロジックのユニットテスト（ticker_utils 等）
- `tests/data/` — データ取得層のテスト（yahoo_client, grok_client, graph_store, note_manager 等）
- `tests/e2e/` — E2E エージェントテスト（Screener, Analyst, HC, Researcher, Risk, Strategist）
- `tests/conftest.py` — 共通フィクスチャ
- `tests/fixtures/` — JSON/CSV テストデータ（Toyota 7203.T ベース）

## モック方法

- `mock_yahoo_client` フィクスチャ: monkeypatch で yahoo_client モジュール関数をモック
- `return_value` を設定して使用
- yahoo_client はクラスではなくモジュール関数なので monkeypatch が容易

## テスト作成の注意点

- 各テストは独立して実行可能であること（外部 API 依存なし）
- yahoo_client の呼び出しは必ずモックする
- テストデータは `tests/fixtures/` の既存データを再利用
- 新しいモジュールには対応するテストファイルを作成
