---
paths:
  - "src/core/screening/**"
  - ".claude/skills/screen-stocks/**"
  - "config/screening_presets.yaml"
---

# スクリーニング開発ルール

> 新スクリーニングプリセット追加の具体的な手順（ファイル一覧・コードテンプレート・テスト例）は [docs/patterns.md](../../docs/patterns.md) の「パターン1」を参照。

## 5つのスクリーナーエンジン

- **QueryScreener（デフォルト）**: `build_query()` → `screen_stocks()` [EquityQuery bulk API] → `_normalize_quote()` → `calculate_value_score()` → ソート
- **ValueScreener（Legacy）**: 銘柄リスト方式。`get_stock_info()` → `apply_filters()` → `calculate_value_score()`。japan/us/asean のみ
- **PullbackScreener**: 3段パイプライン。EquityQuery → `detect_pullback_in_uptrend()` → value_score。"full"（完全一致）と"partial"（bounce_score>=30）の2種
- **AlphaScreener**: 4段パイプライン。EquityQuery(割安足切り) → `compute_change_score()` → 押し目判定 → 2軸スコアリング
- **MomentumScreener** (KIK-506): 2段パイプライン。EquityQuery → `detect_momentum_surge()` → surge_score ランキング。"stable"（継続上昇, 50MA +10-15%）と"surge"（急騰, 50MA +15%+）の2サブモード

## バリュースコア配分

PER(25) + PBR(25) + 配当利回り(20) + ROE(15) + 売上成長率(15) = 100点

## EquityQuery ルール

- フィールド名は yfinance 準拠（`trailingPE`, `priceToBook`, `dividendYield` 等）
- プリセットは `config/screening_presets.yaml` で定義。criteria の閾値を YAML で管理

## yahoo_client データ取得

- `get_stock_info(symbol)`: `ticker.info` のみ。キャッシュ `{symbol}.json` (24h TTL)
- `get_stock_detail(symbol)`: info + price_history + balance_sheet + cashflow + income_stmt。キャッシュ `{symbol}_detail.json`
- `screen_stocks(query)`: EquityQuery ベースのバルクスクリーニング（キャッシュなし）
- `get_price_history(symbol, period)`: OHLCV DataFrame（キャッシュなし、デフォルト1年分）

## 異常値ガード

`_sanitize_anomalies()` で以下をサニタイズ:
- 配当利回り > 15% → None
- PBR < 0.1 or PBR > 100 → None
- PER < 0 or PER > 500 → None
- ROE > 200% → None

## コミュニティグルーピング (KIK-549)

スクリーニング結果の「📊 グラフコンテキスト」セクション（Neo4j接続時のみ）にコミュニティ別銘柄グルーピングが表示される。

- `screening_context.py`: `symbol_communities` キーで各銘柄のコミュニティ所属を取得
- `screening_summary_formatter.py`: コミュニティ名 × メンバー数で表示（例: 「Technology x AI: A、B（2銘柄）」）
- LLMはこのグルーピングを解釈し「半導体関連3銘柄が上位」等のサマリーを生成
- 活用: 類似銘柄の比較分析、既保有銘柄との重複確認、分散度判断
