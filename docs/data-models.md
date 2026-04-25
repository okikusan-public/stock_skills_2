# データモデル定義 (KIK-524)

`yahoo_client` が返す 2 種類の dict スキーマ。スクリーナー・レポート・ヘルスチェック等すべてのコアモジュールがこの構造に依存する。

---

## stock_info dict（27 フィールド）

`yahoo_client.get_stock_info(symbol)` が返す基本データ。JSON キャッシュ対象。

| キー | 型 | 説明 | yfinance 生キー | 正規化 |
|:---|:---|:---|:---|:---|
| `symbol` | `str` | ティッカーシンボル | 引数 | — |
| `name` | `str \| None` | 企業名 | `shortName` / `longName` | — |
| `sector` | `str \| None` | セクター | `sector` | — |
| `industry` | `str \| None` | 業種 | `industry` | — |
| `currency` | `str \| None` | 通貨コード (JPY/USD 等) | `currency` | — |
| `price` | `float \| None` | 現在株価 | `regularMarketPrice` | — |
| `market_cap` | `float \| None` | 時価総額 | `marketCap` | — |
| `per` | `float \| None` | PER（株価収益率） | `trailingPE` | — |
| `forward_per` | `float \| None` | 予想PER | `forwardPE` | — |
| `pbr` | `float \| None` | PBR（株価純資産倍率） | `priceToBook` | — |
| `psr` | `float \| None` | PSR（株価売上高倍率） | `priceToSalesTrailing12Months` | — |
| `roe` | `float \| None` | ROE（自己資本利益率）。比率 (0.12 = 12%) | `returnOnEquity` | — |
| `roa` | `float \| None` | ROA（総資産利益率）。比率 | `returnOnAssets` | — |
| `profit_margin` | `float \| None` | 純利益率。比率 | `profitMargins` | — |
| `operating_margin` | `float \| None` | 営業利益率。比率 | `operatingMargins` | — |
| `dividend_yield` | `float \| None` | 配当利回り（予想）。比率 (0.028 = 2.8%) | `dividendYield` | `_normalize_ratio` |
| `dividend_yield_trailing` | `float \| None` | 配当利回り（実績）。比率 | `trailingAnnualDividendYield` | — |
| `payout_ratio` | `float \| None` | 配当性向。比率 | `payoutRatio` | — |
| `revenue_growth` | `float \| None` | 売上高成長率。比率 (0.15 = 15%) | `revenueGrowth` | — |
| `earnings_growth` | `float \| None` | 利益成長率。比率 | `earningsGrowth` | — |
| `debt_to_equity` | `float \| None` | D/Eレシオ（百分率、105.0 = 105%） | `debtToEquity` | — |
| `current_ratio` | `float \| None` | 流動比率 | `currentRatio` | — |
| `free_cashflow` | `float \| None` | フリーキャッシュフロー（絶対値） | `freeCashflow` | — |
| `beta` | `float \| None` | ベータ値 | `beta` | — |
| `fifty_two_week_high` | `float \| None` | 52週高値 | `fiftyTwoWeekHigh` | — |
| `fifty_two_week_low` | `float \| None` | 52週安値 | `fiftyTwoWeekLow` | — |
| `quoteType` | `str \| None` | 種別 ("EQUITY" / "ETF" 等) | `quoteType` | — |

**合計: 27 キー**（`quoteType` は KIK-469 で追加）

### 正規化ルール (`_normalize_ratio`)

yfinance は `dividendYield` をパーセンテージ値（例: 2.52）で返す。`_normalize_ratio()` は常に 100 で割って比率に変換する。

```python
def _normalize_ratio(value):
    if value is None:
        return None
    return value / 100.0  # 2.52 → 0.0252
```

`dividend_yield_trailing`（`trailingAnnualDividendYield`）は yfinance が比率で返すため正規化不要。

### 異常値サニタイズ (`_sanitize_anomalies`)

| フィールド | 条件 | 処理 |
|:---|:---|:---|
| `dividend_yield` | > 0.15 (15%) | → `None` |
| `dividend_yield_trailing` | > 0.15 (15%) | → `None` |
| `pbr` | < 0.05 | → `None` |
| `per` | 0 < per < 1.0 | → `None` |
| `roe` | < -1.0 or > 2.0 | → `None` |

### エイリアス対応

yfinance 生キーと正規化済みキーの対応表:

| 正規化キー | yfinance 生キー |
|:---|:---|
| `per` | `trailingPE` |
| `pbr` | `priceToBook` |
| `dividend_yield` | `dividendYield` |
| `roe` | `returnOnEquity` |
| `revenue_growth` | `revenueGrowth` |

---

## stock_detail dict（45+ フィールド）

`yahoo_client.get_stock_detail(symbol)` が返す詳細データ。`stock_info` の全フィールドを包含し、財務諸表データを追加。

### stock_info から継承（27 フィールド）

上記 `stock_info dict` の全キーがそのまま含まれる。

### 追加フィールド: 価格

| キー | 型 | 説明 | ソース |
|:---|:---|:---|:---|
| `price_history` | `list[float] \| None` | 2年分の終値リスト（時系列順） | `ticker.history(period="2y")` |

### 追加フィールド: バランスシート

| キー | 型 | 説明 | ソース |
|:---|:---|:---|:---|
| `equity_ratio` | `float \| None` | 自己資本比率（純資産/総資産） | `balance_sheet` |
| `total_assets` | `float \| None` | 総資産 | `balance_sheet` |
| `equity_history` | `list[float]` | 純資産の推移（最新→過去、最大4期） | `balance_sheet` |

### 追加フィールド: キャッシュフロー

| キー | 型 | 説明 | ソース |
|:---|:---|:---|:---|
| `operating_cashflow` | `float \| None` | 営業CF | `cashflow` |
| `fcf` | `float \| None` | フリーCF | `cashflow` |
| `dividend_paid` | `float \| None` | 配当金支払い（負値=支出） | `cashflow` (KIK-375) |
| `stock_repurchase` | `float \| None` | 自社株買い（負値=支出） | `cashflow` (KIK-375) |
| `dividend_paid_history` | `list[float]` | 配当金支払いの推移（最新→過去、最大4期） | `cashflow` (KIK-380) |
| `stock_repurchase_history` | `list[float]` | 自社株買いの推移（最新→過去、最大4期） | `cashflow` (KIK-380) |
| `cashflow_fiscal_years` | `list[int]` | 各期の会計年度（例: [2025, 2024, 2023]） | `cashflow` (KIK-380) |

### 追加フィールド: 損益計算書

| キー | 型 | 説明 | ソース |
|:---|:---|:---|:---|
| `net_income_stmt` | `float \| None` | 当期純利益 | `income_stmt` |
| `eps_current` | `float \| None` | 希薄化後EPS（最新期） | `income_stmt` |
| `eps_previous` | `float \| None` | 希薄化後EPS（前期） | `income_stmt` |
| `eps_growth` | `float \| None` | EPS成長率。比率 (0.094 = 9.4%) | 算出 |
| `revenue_history` | `list[float]` | 売上高の推移（最新→過去、最大4期） | `income_stmt` |
| `net_income_history` | `list[float]` | 純利益の推移（最新→過去、最大4期） | `income_stmt` |

### 追加フィールド: 債務・評価

| キー | 型 | 説明 | ソース |
|:---|:---|:---|:---|
| `total_debt` | `float \| None` | 有利子負債合計 | `ticker.info` |
| `ebitda` | `float \| None` | EBITDA | `ticker.info` |

### 追加フィールド: アナリスト (KIK-359)

| キー | 型 | 説明 | ソース |
|:---|:---|:---|:---|
| `target_high_price` | `float \| None` | アナリスト目標株価（上限） | `ticker.info` |
| `target_low_price` | `float \| None` | アナリスト目標株価（下限） | `ticker.info` |
| `target_mean_price` | `float \| None` | アナリスト目標株価（平均） | `ticker.info` |
| `number_of_analyst_opinions` | `int \| None` | アナリスト人数 | `ticker.info` |
| `recommendation_mean` | `float \| None` | 推奨平均値（1=Strong Buy 〜 5=Strong Sell） | `ticker.info` |
| `forward_eps` | `float \| None` | 予想EPS | `ticker.info` |

### 追加フィールド: ETF (KIK-469)

ETF の場合のみ有意な値を持つ。個別株では `None` が多い。

| キー | 型 | 説明 | ソース |
|:---|:---|:---|:---|
| `expense_ratio` | `float \| None` | 経費率 | `ticker.info` (`annualReportExpenseRatio`) |
| `total_assets_fund` | `float \| None` | AUM（運用資産残高） | `ticker.info` (`totalAssets`) |
| `fund_category` | `str \| None` | ファンドカテゴリ | `ticker.info` (`category`) |
| `fund_family` | `str \| None` | ファンドファミリー | `ticker.info` (`fundFamily`) |

---

## portfolio.csv（12 カラム）

`src/data/portfolio_io.py` が読み書きする保有銘柄データ。

| カラム | 型 | 説明 |
|:---|:---|:---|
| `symbol` | str | ティッカーシンボル（7203.T, AMZN 等） |
| `shares` | int | 保有株数 |
| `cost_price` | float | 平均取得単価 |
| `cost_currency` | str | 取得通貨（JPY, USD, SGD, IDR） |
| `purchase_date` | str | 取得日（YYYY-MM-DD） |
| `memo` | str | メモ |
| `next_earnings` | str | 直近決算日（YYYY-MM-DD）。ETF は空欄 (KIK-683) |
| `div_yield` | float? | 配当利回り（%）。None = 未設定 (KIK-694) |
| `buyback_yield` | float? | 自社株買い利回り（%）(KIK-694) |
| `total_return` | float? | 総還元率（%）= div_yield + buyback_yield (KIK-694) |
| `beta` | float? | ベータ値 (KIK-694) |
| `role` | str | PF内の役割（長期インカム/グロース/ヘッジ等）(KIK-694) |

**更新頻度**: div_yield は四半期決算後、buyback_yield は年次 or 発表時、beta は月次、role は変更時のみ。

---

## 共通ユーティリティ

### `finite_or_none(v)` (`src/data/common.py`)

Core モジュールで広く使われるヘルパー。NaN/Inf を `None` に変換し、安全に数値を取得する。

```python
def finite_or_none(v):
    """Return v if finite number, else None."""
    if v is None:
        return None
    f = float(v)
    return None if (math.isnan(f) or math.isinf(f)) else f
```

### `_safe_get(info, key)` (`yahoo_client/_normalize.py`)

yfinance の info dict から安全に値を取得。NaN/Inf は `None` に変換。

---

## テストフィクスチャ

| ファイル | 内容 | 用途 |
|:---|:---|:---|
| `tests/fixtures/stock_info.json` | stock_info 相当（27 フィールド、Toyota 7203.T） | `conftest.py` の `stock_info_data` フィクスチャ |
| `tests/fixtures/stock_detail.json` | stock_detail 相当（stock_info + 追加フィールド） | `conftest.py` の `stock_detail_data` フィクスチャ |

テストでは `monkeypatch` で `yahoo_client.get_stock_info` / `get_stock_detail` をモックし、これらの JSON を返す。
