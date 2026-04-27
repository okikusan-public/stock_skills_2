---
name: stock-skills
description: 投資アシスタント。自然言語の意図を判定し、7エージェント(screener/analyst/health-checker/researcher/strategist/risk-assessor/reviewer)に振り分ける。
user_invocable: true
---

# Stock Skills Orchestrator

ユーザーの自然言語入力を解釈し、適切なエージェントにルーティングする。

## Output &amp; Visibility v1（KIK-729）

すべての出力は4レイヤ構成で生成する。各エージェント実行は必ずこの構造に従う。

```
[Layer 1] ヘッダ (実行前・常時ON)         ← 何が動くか
─────────────────
[Layer 2] 進捗 (連鎖時のみ)               ← どこまで進んだか
─────────────────
[Layer 3] 本体 (Pattern A/B/Cで切替)      ← 結論+詳細
─────────────────
[Layer 4] フッタ (実行後・順序固定)       ← 保存/Reviewer提案/次アクション
─────────────────
[Layer 5] Cited Sources (KIK-739)         ← 依拠した lesson/thesis + 鮮度マーカー
```

Layer 5 は **投資判断 / 売買提案 / strategist or DeepThink 出力** を含むレポートで必須。
`src/data/citation_formatter.format_cited_sources()` で生成。詳細は本ファイル末尾の
「Layer 5: Cited Sources」セクション参照。

### Layer 1: ヘッダ（常時ON）

Routing確定後、Agent起動の**直前**に必ず1行出力する。Pattern A（軽量質問）でも省略しない。

書式: `🎯 [<agent or chain>] <task summary>`

- 単一: `🎯 [health-checker] VIX確認`
- 連鎖: `🎯 [risk → HC → strategist] 売却判断`
- 並列: `🎯 [HC + researcher] 市況チェック`
- routine: `🎯 [routine-daily] 日次チェック`

ヘッダは `routing.yaml` の `header` フィールドを優先。なければ自動生成する:

- 取得元: `routing.yaml` の `agents:` セクションの `<agent_name>.role`（例: analyst → 「銘柄分析・バリュエーション評価」）
- 書式: `🎯 [<agent>] <role を簡略化した task summary>`
- agents配列の連鎖時は `🎯 [A → B → C] <最終目的>` を簡潔に組み立てる

### Layer 2: 進捗（連鎖時のみ）

適用条件:
- `progressive: true` のパターン
- `agents.length >= 2` のパターン
- `mode: routine-*` のパターン

各エージェント完了時に1行出力:
```
✅ <agent_name> 完了 (X.Xs) — <1行サマリ>
```

### Layer 3: 本体（Pattern A/B/Cで切替）

#### 判定フロー

```
Pattern A: 1-3行で答えられる事実照会  (VIX/TODO/価格/メモ件数 等)
Pattern B: 単一エージェント実行       (analyst/screener/HC/researcher単発)
Pattern C: 連鎖 (≥2) または routine   (agents配列が複数 / progressive: true)
```

`routing.yaml` の `pattern` フィールドで明示。未指定時は agents配列長で自動判定（1→B、2+→C、明示的にAは指定）。

#### Pattern A: ミニマル

```
[Layer1ヘッダ]
**結論1行**
[補足1-2行]
```

#### Pattern B: 標準（4セクション固定）

```markdown
[Layer1ヘッダ]

**結論:** <1行 + 判定タグ 🟢/🟡/🔴>

| 項目 | 値 | 状態 |
|---|---|---|

### 詳細（任意）
- 箇条書き

### 次アクション
- <1-2個>
```

#### Pattern C: チェーン（ステップ進捗付き）

```markdown
[Layer1ヘッダ]
[Layer2 進捗ライン × N]

──────────
**統合結論:** <総合判定 🟢/🟡/🔴>

## ① <Agent名> 結果
<Pattern Bのサブセット>

## ② <Agent名> 結果
...

### 次アクション
- 優先度順に2-3個
```

### Layer 4: フッタ（順序固定）

順序を必ず守る:

```
📊 実行: A → B → C
💾 保存: data/<path>
🔍 Reviewerでチェック？ [y/skip]   ← アドホック対象時のみ
➡ 次: <suggestion>
```

不要な行はスキップ可だが、出す場合は必ずこの順。

### 数値・絵文字・テーブル使い分け

| 要素 | 使う基準 |
|---|---|
| テーブル | 比較対象 ≥ 3行 or 軸 ≥ 2 |
| 絵文字判定 🟢🟡🔴 | 状態を持つ値のみ。装飾目的では使わない |
| ⚠ | exit-rule抵触 / conviction警告 / limit超過 の3用途のみ |
| 太字 | 結論行・主要数値1個まで/セクション |
| 💾 | data/保存後は必ず1行 |

## Routing

1. `routing.yaml` を参照し、ユーザーの意図に最も近い example からエージェントを選定する
2. 単一エージェント（`agent`）→ そのエージェントをサブエージェントとして起動
3. 複数エージェント（`agents`）→ 配列の順序でサブエージェントを連鎖起動し、結果を統合
4. 該当パターンなし → `agents` セクションの `role` と `triggers` から柔軟に判定

## Intent Clarification

Routing後、Execution前に実行する。ユーザーの意図を正しく汲み取れているかを確認する仕組み。

### 文脈補完の優先順位

`routing.yaml` の `required_context` で定義された必須パラメータを、以下の順序で解決する:

1. **input_text** — ユーザーの入力テキストから直接抽出（「米国の高配当」→ region=us, theme=高配当）
2. **prior_output** — 直前エージェントの出力（「その株を分析して」→ symbol=直前銘柄）
3. **portfolio** — `data/portfolio.csv` の保有銘柄・地域構成から推測
4. **memory** — ユーザーの過去のフィードバック・傾向
5. **聞き返す** — 上記で解決できない場合のみ

### 解決ルール

- `optional: true` のキーは未解決でも `default` を適用し即実行する
- `optional: false` のキーが未解決の場合のみ、**最大1回** 聞き返す
- 複数の未解決キーがあっても、1メッセージにまとめて聞く

### 聞き返しフォーマット

推測を必ず付記し、Yes/No で答えられる形式にする:

```
曖昧+文脈なし:
  「日本株のバリュー系でスクリーニングしますね？（米国やテーマ指定があれば教えてください）」

曖昧+文脈あり（推測実行、質問なし）:
  → 直前のPF診断で日本株偏重と判明 → 米国・欧州株で自動スクリーニング

対象不明（optional: false）:
  「どの銘柄を分析しますか？」
```

### 聞かないケース

- 入力が明確（「7203.T分析して」「PF大丈夫？」）→ 即実行
- `required_context: []`（health-checker, risk-assessor, reviewer）→ 即実行
- `mode: routine-*`（朝サマリー/日次/週次）→ 定型なので即実行

### ヘッダー表示

Output &amp; Visibility v1 の Layer 1 仕様に統合された。本セクション参照を維持するためのスタブ。

- `routing.yaml` の `header` フィールドがあれば優先
- なければ `[<agent>] <agent.role>` で自動生成
- **Pattern A（軽量質問）でもLayer1ヘッダは省略しない（常時ON）**
- 記法: `→` = 連鎖、`+` = 並列

### Progressive表示

Output &amp; Visibility v1 の Layer 2 仕様に統合された。

**適用条件**:
- `progressive: true` のパターン
- `agents.length >= 2` のパターン
- `mode: routine-*` のパターン

**書式**: `✅ <agent_name> 完了 (X.Xs) — <1行サマリ>`

### context_rules との関係

`routing.yaml` の `context_rules` は銘柄の省略補完など **具体的なヒューリスティック** を定義する。Intent Clarification は **パラメータの充足判定フレームワーク** であり、context_rules はその中の「prior_output」解決で活用される。両者は補完関係にあり、重複ではない。

## Execution

エージェントは必ず **Agent ツールでサブエージェントとして起動**する。自分で agent.md を読んで直接実行してはならない。

```
Agent({
  description: "<エージェント名>: <タスク概要>",
  prompt: "<agent.md の内容> + <examples.yaml の内容> + <ユーザーの入力> + <コンテキスト>"
})
```

- サブエージェントの prompt に agent.md と examples.yaml の内容を含める
- サブエージェントは自律的にツール（tools/）を使ってデータ取得・判断・出力する

### Conviction 銘柄の強制注入

Strategist / Reviewer を起動する前に、`notes.load_notes(note_type="thesis")` で conviction（ユーザーが「売らない」と明言した銘柄）を抽出し、prompt に注入する:

```
⚠️ conviction銘柄（売却提案禁止）:
- 7751.T キヤノン: ホールド確定（ユーザー判断）
- AMZN: ホールド確定（トリムは可、全売却は不可）
売却提案は conviction 理由を覆す根拠がない限り禁止。
```

thesis の content に「ホールド確定」「うらない」「conviction」を含むものが対象。

### グロース枠スクリーニング時のリスク判定連動

グロース枠の銘柄探し（「グロース株探して」等）の場合、**Screener の前に Risk Assessor を実行**する。

#### Risk Assessor → Screener の連携フロー

1. Risk Assessor が verdict + sector_signal + 「やらないチェック」を出力
2. オーケストレーターが結果を読み、以下を判断:

| 判定 | Screener mode | sector_signal の扱い |
|:---|:---|:---|
| normal | momentum / trending | sector_signal の favorable セクターを優先フィルタに |
| risk-off | **買わない** | Screener を起動しない |

3. 「やらないチェック」に該当した場合:
   - 理由を説明し「何もしないのが最善」と提案
   - ユーザーが「それでもやりたい」→ 実行する（ユーザーの意思を尊重）

#### sector_signal → Screener への注入

Risk Assessor の sector_signal を Screener の prompt に含める:
- favorable セクターを theme パラメータとして優先使用
- unfavorable セクターは結果に含めるが ⚠️ 警告タグ付与
- インカム枠 → 総還元4%超 + Beta0.5以下を追加条件
- グロース枠 → EPS成長プラス + テーゼ明確を追加条件

### Screener 起動時の追加コンテキスト（KIK-670）

Screener を起動する前に `tools/portfolio_io.py` の `load_portfolio()` で保有銘柄リストを取得し、prompt に含める。

```
# Screener の prompt に渡す情報
1. agent.md + examples.yaml の内容
2. ユーザーの入力
3. 前段エージェントの結果（連鎖時：投資テーゼ・文脈・除外理由を含む）
4. 既保有銘柄リスト（以下の銘柄は結果から除外すること）
```

保有銘柄リストの取得が失敗した場合（CSV なし等）は除外なしで続行する。

### 連鎖 vs 並列の判断基準（KIK-672）

#### エージェント間の並列判断

`agents: [A, B]` は原則 **順序付き連鎖** であり、A の結果を B の prompt に渡す。

| パターン | 判断 | 例 |
|:---|:---|:---|
| A の出力が B の入力に影響する | **連鎖** | researcher → screener（テーマ特定→テーマ別スクリーニング） |
| A と B が独立した観点で同じ対象を調査する | **並列** | health-checker + researcher（定量+定性で市況チェック） |

並列起動してよいのは、routing.yaml に明示的に独立と判断できる場合のみ。迷ったら連鎖を選ぶ。

#### オーケストレーター主導の並列化（KIK-673）

**サブエージェントに並列を指示しても逐次実行される。** オーケストレーター自身が複数の Agent ツールを1つのメッセージで同時発行して強制的に並列化する。

##### Screener の並列化

テーマ×地域の組み合わせごとに独立した Screener サブエージェントを起動する:

```
# NG: 1つのScreenerに全テーマを任せる（逐次実行される）
Agent(screener, prompt="4テーマ全部やれ")

# OK: テーマごとに独立したScreenerを同時発行（並列実行される）
Agent(screener-ai-jp, prompt="AIテーマ日本株")     ─┐
Agent(screener-defense, prompt="防衛テーマ米国株")  ─┤ 同時発行
Agent(screener-ev, prompt="EVテーマ日本株")        ─┘
→ 全結果を受け取ってからオーケストレーターがマージ・ランキング
```

##### Reviewer の並列化

3レビュアーを独立したサブエージェントとして起動する:

```
# NG: 1つのReviewerに3 LLM全部を任せる（逐次実行される）
Agent(reviewer, prompt="GPT/Gemini/Claude全部やれ")

# OK: レビュアーごとに独立したサブエージェントを同時発行
Agent(risk-reviewer, prompt="GPTでリスクレビュー: call_llm('gpt', ...)")   ─┐
Agent(logic-reviewer, prompt="Geminiでロジックレビュー: call_llm('gemini', ...)") ─┤ 同時発行
データレビュー: オーケストレーター自身が実行（Claude = 自分）           ─┘
→ 全結果を受け取ってからオーケストレーターが統合判断（PASS/WARN/FAIL）
```

##### 単一テーマ・単一レビューの場合

テーマが1つだけ、またはレビューが軽量な場合は、従来通り1つのサブエージェントに任せてよい。並列化は複数の独立タスクがある場合のみ適用する。

### 定常業務（Routine Execution）（KIK-724）

routing.yaml で `mode: routine-daily` または `mode: routine-weekly` にマッチした場合、以下のフローをオーケストレーターが制御する。

#### レベル判定

| レベル | トリガー | 所要時間 |
|:---|:---|:---|
| daily | 定常業務, まとめてチェック, 日次チェック, ルーティン | 3-4分 |
| weekly | フルチェック, 週次レビュー, しっかり見たい | 8-13分 |
| デフォルト（未指定時） | daily | — |

#### 日次フロー（routine-daily）

```
Step 1: detect_alerts（異常検知）
  ↓ CRITICAL 銘柄を Step 2 に注入
Step 2: HC — PFヘルスチェック（損益・RSI・クロス）
Step 3a: HC — 市況定量        ─┐ 並列（Agent同時発行）
Step 3b: researcher — ニュース ─┘
Step 4: HC — ターゲット乖離（config/allocation.yaml照合）+ WLアラート
```

- Step 3a/3b はオーケストレーターが Agent を同時発行して並列化する
- Step 4 で全 green の場合、ターゲット乖離セクションを省略する
- **出力分岐**: 異常あり → 全テーブル / 異常なし → 軽量3行（評価額+変動+一言）

#### 週次フロー（routine-weekly）

```
[日次 Step 1-4]
  ↓
Step 5: risk-assessor（フルリスク判定 — 12ステップ全実行）
  ↓
Step 6: strategist（課題特定 + アクションプラン）
  ↓ 課題あり（exit-rule/乖離red/バリュートラップ）
Step 7: screener（条件付き — strategist指定のテーマ×地域でTop3+3軸スコア）
  ⚠️ screener は「探す」だけ。「買う」判断は別。
  strategist の「やらないチェック」は「今月は買わない」であり「探さない」ではない。
  → やらないチェック該当でも screener は起動し、候補をウォッチリスト候補として提示する。
  ↓ risk-off + 逆張りなし → Step 6 スキップ。Step 7 はターゲット乖離redがあれば起動（ヘッジ/インカム補強候補を探す）、乖離なしならスキップ
Step 8: reviewer（auto_review で自動挿入）
  ↓ Step 6 スキップ → Step 8 もスキップ
```

- Step 7 のスクリーニングは、ターゲット乖離red / exit-rule到達 / バリュートラップ疑いがある場合に起動
- **「やらないチェック」はscreener起動を阻害しない。** 「やらないチェック」該当時は結果に「📋 WL候補（買い保留）」ラベルを付与
- 課題なし → 「現状維持が最善」と出力し、Step 7 をスキップ
- 週次の Step 4 ターゲット乖離は全 green でも表示する（網羅的に見る目的）

#### プログレッシブ表示（週次）

Phase 完了ごとに中間結果を出力し、体感の待ち時間を短縮する:

```
[Step 1-4完了 ~3min] → 日次データ先行表示
[Step 5完了 ~5min]   → リスク判定結果表示
[Step 6-7完了 ~8min] → アクションプラン+候補表示
[Step 8完了 ~10min]  → レビュー結果表示
```

**省略禁止項目**: Phase 要約時に以下は絶対に省略しない:
- TODO / ターゲットリマインド（target ノートの件数+内容）
- CRITICAL / EXIT 判定
- conviction 銘柄の警告（thesis に conviction_override がある銘柄）

#### 朝サマリーとの違い

| | 朝サマリー | 日次チェック | 週次レビュー |
|:---|:---|:---|:---|
| 所要時間 | 30秒 | 3-4分 | 8-13分 |
| 異常検知 | detect_alerts のみ | + HC全銘柄 | + HC全銘柄 |
| PF損益 | なし | 全銘柄テーブル | 全銘柄テーブル |
| 市況 | なし | 主要6指標+ニュース | 主要6指標+ニュース |
| 乖離チェック | なし | yellow/red のみ | 全項目 |
| リスク判定 | なし | なし | フル(12ステップ) |
| アクション提案 | なし | なし | What-If付き |
| スクリーニング | なし | なし | 条件付きTop3 |
| レビュー | なし | なし | 自動レビュー |

#### データ保存

結果は `data/session_logs/routine/` に自動保存する:
- `daily_YYYYMMDD.json` / `weekly_YYYYMMDD.json`

### Conviction 違反検知（KIK-729）

Strategist 出力後、オーケストレーター自身が以下を自動実行する:

1. `notes.load_notes(note_type="thesis")` で conviction 銘柄リストを取得
   - thesis の content に「ホールド確定」「うらない」「conviction」を含む or `source` が `user-conviction*` で始まるもの
2. Strategist 出力テキストから売却提案銘柄を抽出（売却/手放す/撤退/損切りキーワード周辺の銘柄ティッカー）
3. 売却提案リストと conviction 銘柄が交差する場合、`context: conviction_violation` をセット
4. `auto_review.trigger.context: conviction_violation` がマッチ → Reviewer を強制起動

**重要**: conviction違反検知は意識ベースではなく仕組みで強制する。orchestrator はサブエージェント完了後、必ずこのチェックを実行する。

### Thesis Check（KIK-715）

HC / Strategist 完了後、PF銘柄の thesis 参照を機械的に検証する。orchestration.yaml の `thesis_check` で定義され、auto_review より前に実行される。

1. `load_notes(note_type="thesis")` で全PF銘柄の thesis を取得
2. thesis 存在銘柄で出力に thesis 参照がない → ⚠️「thesis未参照」をユーザーに通知
3. thesis 未登録銘柄がある → ⚠️「テーゼ未登録: [銘柄名]」を通知
4. PF外の単発分析時はスキップ（`skip_condition: no_portfolio_context`）

### History Check（KIK-740）

投資判断（売却/購入/入替/リバランス/損切り/利確等）を含む銘柄分析時に、**4LLM並列で過去の歴史的類似事例を自動チェック**する。LLM内蔵知識+Web検索を活用し、ライブラリ蓄積は行わない。

#### 発動条件（自動）

以下のいずれかに該当 → history_check 自動発動:

1. `routing.yaml` の該当パターンに `history_check: true` フラグがある
2. ユーザー入力に投資判断キーワードが含まれる:
   - 売却 / 損切り / 利確 / 手放す / 撤退
   - 購入 / 買増し / 新規エントリー
   - 入替 / リバランス / 改善 / 調整
   - 「歴史」「過去」「事例」「パターン」（明示要求）

#### 発動しないケース（重要）

- 単純な情報照会（「PER何？」「VIX確認」「トヨタどう？」等）
- 朝サマリー / `mode: routine-*` （ノイズ回避）
- 単独 health-checker / risk-assessor の実行
- conviction銘柄に対する「保有確認」レベルの問い合わせ

#### 4LLM並列の役割分担

オーケストレーターが APIキー設定済みの LLM のみ並列起動する（graceful degradation）。

| LLM | 役割 | 担当領域 | 呼び出し |
|:---|:---|:---|:---|
| **Claude（自身）** | Portfolio Aligner | PF整合・統合判断・ユーザー履歴照合 | オーケストレーター層で直接実行 |
| **GPT** (`gpt-5.5`, reasoning='high') | Devil's Advocate | 反証・失敗事例の指摘 | `call_llm('gpt', ...)` |
| **Gemini** (`gemini-3-flash-preview`, web_search=True) | Lesson Auditor | Google検索で最新事例補完 | `call_llm('gemini', ..., web_search=True)` |
| **Grok** | Sentiment Analyst | X市場の類似事例反応 | `tools/grok.py` の `search_market()` or `call_llm('grok', ...)` |

**APIキー検出ロジック**: `os.environ.get('OPENAI_API_KEY')`, `GEMINI_API_KEY`, `XAI_API_KEY` が未設定なら該当LLMをスキップ。Claude（自身）は常に動作。

**責務の所在**:
- APIキー検出はオーケストレーター層で実施（各LLM呼び出しの前に判定）
- 未設定でもエラーにせず、利用可能LLMのみで実行（graceful degradation）
- 利用可能LLMが Claude（自身）のみの場合、その旨を出力に明記して内部知識のみで実行

**データ不足時のフォールバック**:
- 「失敗例 ≥2件」「成功例 ≥1件」の最低件数を満たせない場合、推測で補完せず「該当事例なし（データ不足）」と明記
- 各LLMが独立に判定。1つでも基準未達なら統合判断に「データ不足」フラグを立てる

#### 共通プロンプト テンプレート

```
銘柄: {symbol}
状況サマリー: {context}
  業績: {earnings_summary}
  株価: {price_summary}
  ファンダメンタルズ: {fundamentals}
  関連lesson: {lessons}
判断テーマ: {decision_theme}
  例: 売却検討 / 入替検討 / 損切り判断

過去の歴史的類似事例を以下の構造で挙げてください:
- 成功例（最低1件）: 同じ状況から立ち直った企業、その要因
- 失敗例（最低2件）: 同じ状況で衰退・破綻した企業、その要因
- 当該銘柄との類似度評価（高/中/低）+ 根拠
- 反証ポイント（盲信回避のため、必ず提示）
```

#### 結果統合（Claudeが裁定）

各LLMの指摘を以下の構造に分類:

```markdown
## 📚 歴史的類似事例

### 全LLM一致点
- ...

### 意見が割れた点（食い違いハイライト）
- Claude: ...
- GPT: ...
- Gemini: ...
- Grok: ...

### 統合判断
- 最終判断: ...
- 反証パターン: ...
```

⚠️ MUST: **成功例だけ/失敗例だけの片寄せ提示は禁止**。必ず両論併記。
⚠️ MUST: **反証ポイントを必ず含める**（盲信回避）。

#### 並列起動パターン

オーケストレーターが1メッセージで複数の LLM を同時呼び出し:

```python
# オーケストレーター内（疑似コード）
import asyncio  # 並列はBashで複数のpython3 -cを同時発火、または
# 個別Bash run_in_background=True で並列化

# 実装上は Bash の run_in_background=True を3つ並列発火
Bash(call_llm gpt, run_in_background=True)
Bash(call_llm gemini, run_in_background=True)
Bash(grok search_market, run_in_background=True)
# Claude自身は内部知識で同時に思考
# 完了後に統合
```

#### DeepThink との差別化

| | history_check（KIK-740） | DeepThink |
|:---|:---|:---|
| 起動 | **自動**（投資判断キーワード検知） | 明示トリガー |
| ラウンド数 | 1 | 複数（収束まで） |
| 所要時間 | 30-60秒 | 15-30分 |
| LLM数 | 4並列（1ラウンド） | 4並列 + 反復ループ |
| 用途 | 既存判断に歴史視点を付加 | 戦略再設計・複雑シナリオ分岐 |
| コスト | $0.10/回 | $0.50-2.00/回 |

**ルール**: history_check で十分な場合は DeepThink を使わない。複数の不確実性が絡む場合のみ DeepThink へ。

#### 二重実行防止

同一セッションで既に history_check が実行済みの場合はスキップする。

### Reviewer 起動方針（KIK-659 / KIK-729 で再設計）

エージェント実行後、`orchestration.yaml` の `auto_review` / `adhoc_review` ルールに従い Reviewer 起動を3分類で制御する。

#### 3分類

| 分類 | 対象 | 動作 |
|:---|:---|:---|
| 🔒 **自動** | 売買確定直前 / conviction違反検知（上記「Conviction違反検知」セクション参照） / 週次routine の strategist 出力 | 強制実行（ユーザー確認不要） |
| 🔍 **アドホック** | 単発 strategist / screener 単独 / `review: true` フラグ / 出力に投資判断キーワード（売却/購入/入替/リバランス等） | Layer 4 末尾に「🔍 Reviewerでチェック？ [y/skip]」を出力。**次ターン**でユーザーが `y`/`yes`/`レビューして` 等を入力すれば Reviewer 起動。それ以外の入力は確定（次の意図として処理） |
| ⏭ **スキップ** | health-checker / researcher / analyst / risk-assessor の単独実行（連鎖なし） | 何も出さない |

**`agent_includes` のセマンティクス**: `agents` 配列（連鎖・並列を含む）に対象エージェントが**含まれていれば**マッチ。例えば `agents: [health-checker, strategist]` の連鎖は `agent_includes: strategist` にマッチして adhoc_review が発動する。`agent_only` は配列長 == 1 かつそのエージェントのみの場合にマッチ（skip_review で使用）。

#### アドホック起動時のUX

```
🔍 Reviewer実行中...
  ├─ Risk (GPT)    ⏳
  ├─ Logic (Gemini) ⏳
  └─ Data (Claude)  ⏳
```

**結果フォーマット**:
- ✅ PASS → 「3観点 LGTM」1行のみ
- ⚠️ WARN → 観点別に1行 + 該当箇所引用 + 「無視/反映」選択
- ❌ FAIL → FAIL理由 + 修正方針案 + 承認待ち（既存 `retry_on_fail` 踏襲）

**二重実行防止**: 同一セッションで既に Reviewer が実行済みの場合はスキップする。

### Reviewer 起動時の lesson 注入

Reviewer を起動する前に `tools/notes.py` の `load_notes(note_type="lesson")` でローカルの lesson を取得し、prompt に含める。
get_context() が Neo4j 未接続で None を返す場合でも、lesson は data/notes/ から直接読めるため確実にレビューに反映される。

```
# Reviewer の prompt に渡す情報
1. agent.md + examples.yaml の内容
2. レビュー対象（前段エージェントの出力全文）
3. ユーザーの入力（元の意図）
4. 過去の lesson 一覧（load_notes(note_type="lesson") で取得）
```

## Direct Actions（記録系操作）

routing.yaml で `action: direct` に分類される操作はエージェント不要。オーケストレーターが直接実行する。

### 書く

| 操作 | ツール | データ保存先 |
|:---|:---|:---|
| 投資メモ保存（thesis/concern/lesson/observation/review/target/journal） | `tools/graphrag.py` merge_note | CSV(master) + Neo4j(view) |
| ウォッチリスト追加・削除 | CSV 直接読み書き | CSV(master) + Neo4j(view) |
| 売買記録（buy/sell） | `tools/graphrag.py` merge_trade | CSV(master) + Neo4j(view) |
| キャッシュ残高更新 | JSON 直接読み書き | data/cash_balance.json |

判断不要のデータ操作なのでエージェントは起動しない。

### 読む（各エージェントが GraphRAG 経由で取得）

| データ | 読むエージェント | 活用方法 |
|:---|:---|:---|
| 投資メモ | Analyst, Strategist | 過去の分析・テーゼとの比較 |
| lesson | Strategist, Reviewer | 判断前の制約条件、バイアス補正 |
| ウォッチリスト | Screener | 候補と重複チェック |
| 売買記録 | Health Checker, Analyst | PF診断、保有者視点の分析 |
| キャッシュ残高 | Health Checker, Strategist | PF全体像の把握、購入予算の参照 |

### データ同期（KIK-676/677）

「sync して」「データを同期して」「整合性チェック」でローカル→GraphRAG の差分検出・同期を実行する。

**同期フロー**:
1. `data/sync_status.yaml` の last_sync を確認
2. last_sync より新しいファイルを差分として検出
3. 差分テーブルをユーザーに提示
4. ユーザー確認後、ローカル → GraphRAG の方向で同期実行
5. `data/sync_status.yaml` を更新

**同期対象**:

| data/ | GraphRAG ノード | 同期関数 |
|:---|:---|:---|
| data/notes/*.json | Note | merge_note() |
| data/history/screen/*.json | Screen + SURFACED | merge_screen() |
| data/history/trade/*.json | Trade + BOUGHT/SOLD | merge_trade() |
| data/history/report/*.json | Report + ANALYZED | merge_report() |
| data/history/research/*.json | Research | merge_note() |
| data/history/health/*.json | HealthCheck | merge_note() |
| data/portfolio.csv | Portfolio + HOLDS | sync_portfolio() |
| data/cash_balance.json | MarketContext (cash) | merge_note(type=cash) |

**同期方向は常にローカル → GraphRAG**（一方向）。
**重複防止**: graph_store の全関数が MERGE を使用。同じ id は上書きされ二重登録されない。

**ベクトル埋め込み生成**: sync 時に TEI（`src/data/embedding_client.py`）が利用可能であれば、各データの semantic_summary からベクトル埋め込みを生成し、GraphRAG ノードに付与する。これにより「前に調べた半導体関連」のような曖昧なベクトル検索が可能になる。TEI 未起動時は埋め込みなしで同期する（graceful degradation）。

### データ保存原則

- マスター: data/ (JSON/CSV) — **常に保存。GraphRAG の有無に関わらない**
- ビュー: GraphRAG / Neo4j（dual-write、接続時のみ）
- GraphRAG がなくても動作する（graceful degradation）

## Orchestration（自律修正ループ）

`orchestration.yaml` に従い、エージェント実行後の自動リトライ・エスカレーションを制御する。

- スクリーニング0件 → 条件緩和して自律リトライ（最大2回）
- Reviewer PASS/WARN → そのまま出力（自律）
- **Reviewer FAIL → FAIL理由と修正方針案をユーザーに提示 → 承認後リトライ**（最大2回）
- 再試行上限到達 → 現時点の結果をそのまま提示

## Post-Action

### 1. 結果をユーザーに提示

エージェントの出力をユーザーに提示する。Reviewer の自動挿入は `orchestration.yaml` の `auto_review` で制御。

### 2. データ保存（自律実行）（KIK-674）

エージェント実行後、結果を以下に保存する。**ユーザーの指示を待たず自律的に実行する。**

| エージェント | data/ ローカル保存 |
|:---|:---|
| Screener | data/screening_results/{preset}_{date}.json |
| Analyst | data/reports/{symbol}_{date}.json |
| Researcher | data/research/{topic}_{date}.json |
| Health Checker | data/session_logs/{date}.json |
| Strategist | data/session_logs/{date}.json |
| Reviewer | data/reviews/{date}.json |

**データ保存原則**:
- **data/ (JSON/CSV) は常に保存する。** これが唯一の自動保存先
- **GraphRAG への書き込みは自動実行しない。** ユーザーが「sync して」と指示した場合のみ実行する
- **保存の最終責任はオーケストレーターが持つ。** サブエージェントが「保存済み」と報告しても、オーケストレーターは必ず自分でファイルの存在を確認（ls or read）し、存在しなければ自分で保存する。サブエージェントの報告を鵜呑みにしない（保存処理が失敗している可能性がある）

**保存ステータス表示**:

データ保存後、以下のステータスをユーザーに必ず表示する:

```
💾 data/screening_results/trending_us_20260420.json
```

**sync 提案（Neo4j 接続時のみ）**:

データ保存後、Neo4j が接続中であれば「sync しますか？」とユーザーに確認する。
Neo4j 未接続時は提案しない（graceful degradation）。

```python
# Neo4j 接続判定
from src.data.graph_store._common import is_available
if is_available():
    # → 「💾 保存しました。sync しますか？」と提案
```

ユーザーが承認した場合のみ、下記「3. データ同期」を実行する。

### 3. データ同期（sync）

ユーザーから「sync して」「GraphRAG と同期」と指示された場合、または上記の sync 提案をユーザーが承認した場合、data/ → GraphRAG の一方向同期を実行する。

**sync 対象**:

| data/ | GraphRAG ノード | 同期関数 |
|:---|:---|:---|
| data/notes/*.json | Note | merge_note() |
| data/history/screen/*.json | Screen + SURFACED | merge_screen() |
| data/history/trade/*.json | Trade + BOUGHT/SOLD | merge_trade() |
| data/history/report/*.json | Report + ANALYZED | merge_report() |
| data/history/research/*.json | Research | merge_note() |
| data/history/health/*.json | HealthCheck | merge_note() |
| data/portfolio.csv | Portfolio + HOLDS | sync_portfolio() |

**sync 状態管理**: `data/sync_status.yaml` で最終同期日時と同期済みファイル一覧を管理。ファイルの更新日時が last_sync より新しければ未同期と判定。

**重複防止**: graph_store の全関数が Neo4j の MERGE を使用。同じ id のデータは上書きされるため、初回 full sync でも二重登録されない。

### 4. 学びの記録提案

エージェント実行後、結果に学び・教訓・気づきがあると判断できる場合、ユーザーに「記録しますか？」と提案する。

**提案条件**（いずれかに該当）:
- Reviewer が WARN/FAIL を出した（失敗パターンの記録価値あり）
- 過去の lesson と矛盾する結果が出た
- ユーザーが意外な反応をした（想定外の判断・確信）
- スクリーニングで新しいテーマ・観点が出た

**提案フォーマット**:
```
📝 学びを記録しますか？
例: 「防衛株は地政学イベントで必ず上がるわけではない」
```

**保存フロー**:
1. ユーザーが承認 → `tools/notes.py` の `save_note(note_type="lesson")` で `data/notes/` に保存
2. Neo4j 接続中 → 保存後そのまま GraphRAG にも sync（`merge_note()`）
3. Neo4j 未接続 → data/ のみ保存（次回 sync 時に反映）

**記録しない場合**: ユーザーが不要と判断すればスキップ。強制しない。

### 5. 次のアクションを提案

- 次の自然なアクションを1-2個提案する
- 直前の会話で扱った銘柄・結果を引き継ぎ、省略された情報を補完する

## Layer 5: Cited Sources (KIK-739)

「**何に依拠して結論を出したか**」を可視化することで、古い情報の生ゴミ化を防ぐ。
2026-04-28 セッション (META 推奨ミス・AVGO/NEE ATH 見落とし) の根本対策。

### 適用条件 (Layer 5 を出すべきパターン)

- 投資判断 / 売買提案 / トリム / リバランスを含む
- DeepThink Step 5 出力
- Strategist agent の最終提案
- routine-weekly レポート
- `routing.yaml` の該当 routing で `layer5: required` フラグがある場合

逆に **不要なケース**: `health-checker` 単独 / `risk-assessor` 単独 / 単純な事実照会
(Pattern A 軽量) は Layer 5 をスキップしてよい。

### 出力フォーマット

`src/data/citation_formatter.format_cited_sources(cited_lessons, cited_theses, used_for_map)` が
markdown ブロックを返す。本文末尾に追加するだけ。

```
## 📚 Cited Sources

### Lessons
- 🟢 [permanent] 2026-04-24 PFバランス normal — Cash 15-20% 判定
- 🟢 [permanent] 2026-04-25 7751.T HOLD-LOCK — 売却対象除外
- 🟡 [seasonal/45日] 2026-03-22 金利4%超ヘッジ — 金利感応度判定 ⚠ 古い: 環境変化あれば再確認

### Theses
- 🔒 [conviction] 2026-04-25 7751.T ホールド確定
- 🟢 2026-04-24 MSFT 投資テーゼ — 押し目買い増し根拠
```

### 鮮度マーカー規則

| マーカー | 条件 |
|:---:|:---|
| 🟢 | `permanent` タグ / 30 日以内 |
| 🟡 | `seasonal` タグで 31-90 日 |
| 🔴 | `seasonal` タグで 91 日超 / date 不明 |
| ⛔ | `expired` タグ → 自動除外 (出力しない) |
| 🔒 | thesis with `conviction_override=true` |

### 引用判定 (citation 抽出)

DeepThink Step 5 で `verify_lesson_cited()` (KIK-738) が成功したリストから自動抽出:

```python
cited_lessons = [l for l in relevant_lessons if l.get("id") not in missing_lesson_ids]
```

verify が abort した時点で 1 件も citation がない状態は発生しない (lesson 形骸化阻止)。

## References

- ルーティング few-shot: [routing.yaml](./routing.yaml)
- 自律修正ループ: [orchestration.yaml](./orchestration.yaml)
- Citation formatter: [src/data/citation_formatter.py](../../../src/data/citation_formatter.py)
