---
name: plan-execute
description: プランモード — ワークフロー設計後にスキルを実行する。「プランモードで」と言われたときに起動。
user_invocable: true
---

# Plan-Execute スキル (KIK-600)

ユーザーの意図を分析し、使用するスキル・スクリプトの選定と実行順序を設計してから実行する。

## トリガー

「プランモードで」「プランで」「プラン立てて」「プランモードで実行」等の発言。

## 動作フロー

1. **コンテキスト取得**: `python3 scripts/get_context.py "<ユーザー入力>"` でグラフコンテキストを取得
2. **制約抽出**（投資判断の可能性がある場合）: `python3 scripts/extract_constraints.py "<ユーザー入力>"` でlesson制約を取得
3. **ユーザー前提設定参照**: `config/user_profile.yaml` から証券口座・手数料・税制を読み込み（ファイルがない場合はスキップ）
4. **プラン設計**: 以下を決定し、ユーザーに提示
   - 使用するスキル/スクリプトの一覧
   - 実行順序
   - 各ステップの目的
   - 投資判断を伴うかどうか
5. **エスカレーション判定**:
   - 投資判断を伴う場合（売買・入替・リバランス・調整） → Plan-Check の Phase 1（3エージェント体制）にエスカレーション
   - 情報照会・分析の場合 → そのままワークフロー実行
6. **実行**: プランに従ってスキル/スクリプトを順次実行

## エスカレーション判定基準

以下のいずれかに該当する場合、Plan-Check にエスカレーション:
- ユーザーの意図が売買・入替・リバランス・調整を含む
- extract_constraints.py が action_type として swap_proposal / new_buy / sell / rebalance / adjust を返す
- プラン内に what-if / adjust / rebalance コマンドが含まれる

## 出力フォーマット

プラン提示:
```
📋 プラン:
1. [スクリプト/スキル名] → [目的]
2. [スクリプト/スキル名] → [目的]
...
→ 実行します
```

エスカレーション時:
```
📋 プラン:
1. extract_constraints → lesson制約抽出（N件）
2. → Plan-Check発動（投資判断を伴うため）
   - Strategist: ワークフロー設計
   - Lesson Checker: 制約充足チェック
   - Devil's Advocate: 盲点指摘
→ 実行します
```

## 利用可能なスキル/スクリプト一覧

| スキル | スクリプト | 用途 |
|:---|:---|:---|
| screen-stocks | run_screen.py | スクリーニング |
| stock-report | generate_report.py | 個別銘柄レポート |
| stock-portfolio | run_portfolio.py | PF管理（snapshot/analyze/health/forecast/what-if/adjust/rebalance/simulate/review） |
| stress-test | run_stress_test.py | ストレステスト |
| market-research | run_research.py | 市場・業界・銘柄リサーチ |
| watchlist | manage_watchlist.py | ウォッチリスト |
| investment-note | manage_notes.py | 投資メモ |
| graph-query | run_graph_query.py | ナレッジグラフ検索 |
| — | market_dashboard.py | 市況ダッシュボード |
| — | get_context.py | グラフコンテキスト取得 |
| — | extract_constraints.py | lesson制約抽出 |
