---
name: stock-skills
description: 投資アシスタント。自然言語の意図を判定し、5エージェント(screener/analyst/researcher/strategist/reviewer)に振り分ける。
user_invocable: true
---

# Stock Skills Orchestrator

ユーザーの自然言語入力を解釈し、適切なエージェントにルーティングする。

## Routing

1. `routing.yaml` を参照し、ユーザーの意図に最も近い example からエージェントを選定する
2. 単一エージェント（`agent`）→ そのエージェントを起動
3. 複数エージェント（`agents`）→ 配列の順序で連鎖実行し、結果を統合
4. 該当パターンなし → `agents` セクションの `role` と `triggers` から柔軟に判定

## Post-Action

- エージェント実行後、次の自然なアクションを1-2個提案する
- 投資判断を伴う出力（売買・入替・リバランス）は必ず reviewer エージェントを通す
- `agents` に strategist が含まれるパターンは reviewer を自動挿入する
- 直前の会話で扱った銘柄・結果を引き継ぎ、省略された情報を補完する

## References

- ルーティング few-shot: [routing.yaml](./routing.yaml)
- コンテキスト注入: [graph-context.md](../../rules/graph-context.md)
- 投資判断フロー: [plan-check.md](../../rules/plan-check.md)
