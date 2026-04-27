---
name: deepthink
description: DeepThinking — 自律的に足りない観点を補完し、シナリオ分岐で深掘り分析する。Evaluator-Optimizer パターン。
user_invocable: true
---

# DeepThink

Evaluator-Optimizer パターンで自律的に深掘り分析する。通常の stock-skills が1回のエージェント起動で回答するのに対し、DeepThink は **評価→改善のループを収束するまで自律的に続ける**。

## いつ使うか

- 「イラン停戦したらPFはどうなる？」→ シナリオ分岐 + PF影響計算
- 「再投資先を提案して」→ 候補選定 + RSI確認 + シナリオ検証 + PFターゲット照合
- 「6ヶ月後を見据えたPF設計」→ マクロシナリオ × セクターローテーション × 通貨配分

通常の stock-skills で十分な場合は使わない。**複数の不確実性が絡む判断** に使う。

## ハーネス（強制ルール）

以下は省略・変更不可。

```
⚠️ MUST: Step 2b で GPT / Gemini / Grok + Claude自身 の4者を必ず実行。省略不可。
⚠️ MUST: 不足リストの各項目に「何を → どのLLM/ツールで → なぜ」を付与する。
⚠️ MUST: 収��条件を満たすまで自律的にループを続ける。毎回の承認待ちは不要。
⚠️ MUST: ハーネス上限到達時のみ停止し、ユーザー承認を求める。
```

## 実行フロー

### Step 0: 開始通知 + 実行プラン + 承認待ち

ユーザーに以下を通知する:

```
🧠 DeepThinkingモードで分析します
深度: [shallow / medium / deep]（max N agents, M LLM calls）

📋 実行プラン:
  Step 1: lesson ロード → [テーマに応じた初回分析内容]（[使用エージェント]）
  Step 2: 評価 + 4-Swarm並列レビュー（2層モデル: インフラ固定 + 推論動的割当）
  Step 3: 不足があれば追加調査（[想定される追加調査内容]）
  → 収束するまで Step 2-3 を自律ループ
  Step 5: 統合レポート

続けますか？ [このまま実行 / プラン修正 / キャンセル]
```

**⚠️ MUST (KIK-735): Step 1 開始前に preflight gate を必ず通す。**

```python
from tools.preflight import run_preflight
result = run_preflight(domain="pf")  # PF系テーマ。market/sector/stock も可
if not result["passed"]:
    # violations をユーザーに提示し abort
    raise SystemExit(f"Preflight failed: {result['violations']}")
```

これで cash_balance.json 未参照 / conviction 違反 / lot_size 不正をコードレベルで阻止できる
（2026-04-27 PF徹底レビューの誤推奨事故の再発防止）。

**実行プランはテーマから自動生成する（ゼロショット）。** 典型例:

| テーマ | Step 1 | 想定される Step 3 |
|:---|:---|:---|
| 「PFで再投資先を検討」 | HC + Researcher で PF現況 + 市況 | 候補 RSI 確認、シナリオ分岐 |
| 「イラン停戦の影響は？」 | Researcher で地政学調査 | PF銘柄別の感応度計算 |
| 「6ヶ月後のPF設計」 | HC + Researcher でマクロ調査 | セクターローテーション × 通貨配分 |

深度選択ガイド:
- **shallow**: 1回の追加調査。軽微な情報不足の補完（max 3 agents, 5 LLM calls, 推奨出力 ~1500字）
- **medium**: 2-3回の評価→改善ループ。標準的な深掘り（max 6 agents, 12 LLM calls, 推奨出力 ~2500字）
- **deep**: 最大5回のループ。徹底的な分析（max 10 agents, 20 LLM calls, 推奨出力 ~4000字）

**⚠️ Step 0 のみユーザーの明示的な応答を待つ。Step 1 以降は自律ループ。**
- 「このまま実行」→ Step 1 へ
- 「プラン修正」→ ユーザーの指示を反映してプランを再提示
- 「キャンセル」→ DeepThink を中止し通常モードに戻る

### 使用可能なツール

**[config/tools.yaml](../../config/tools.yaml) を参照。** 全ツールの関数名・役割・いつ使うかが定義されている。

**⚠️ MUST: 再投資・入替・候補選定を伴うテーマでは、`screen_stocks()` でデータドリブンに候補を出す。AIの知識ベースから手動選定してはならない。**

### Step 1: 初回分析

**⚠️ MUST (KIK-738): lesson は全件 load した上で `filter_relevant_lessons()` でテーマ関連分のみ抽出する。**
全件素読みは形骸化を招く（2026-04-27 / 2026-04-28 事故の真因）。テーマに関連する lesson のみ
明示的に絞り込み、その内容を以降の全ステップで参照する。

```python
python3 -c "
import sys; sys.path.insert(0, '.')
from tools.notes import load_notes
from src.data.lesson_enforcer import filter_relevant_lessons

# 1. Lesson 全件 load → ユーザー意図に関連するもののみ抽出（KIK-738 hook）
all_lessons = load_notes(note_type='lesson')
user_input = '<USER_PROMPT_HERE>'  # ユーザーの今回の指示文
relevant_lessons = filter_relevant_lessons(user_input, all_lessons)

print(f'=== Lessons {len(relevant_lessons)}/{len(all_lessons)} relevant ===')
for n in relevant_lessons:
    print(f'[{n.get(\"date\",\"\")}] trigger={n.get(\"trigger\",\"(none)\")[:60]}')
    print(f'  expected_action: {n.get(\"expected_action\",\"(none)\")[:100]}')

# 関連 0 件の場合の fallback 戦略：
#   (a) 該当 lesson の trigger フィールドが未バックフィル → 直近 10 件で代用
#   (b) ユーザー入力が真に新規パターン (どの trigger とも一致しない)
# どちらの場合も直近 10 件にフォールバック。バックフィル完了後 (KIK-738 Phase 2)
# 関連 0 件は (b) を意味するようになる。
if not relevant_lessons:
    print('[fallback] no trigger-match → recent 10 of', len(all_lessons))
    relevant_lessons = all_lessons[-10:]

# 2. 対象銘柄の thesis/observation（KIK-695）
import csv
with open('data/portfolio.csv') as f:
    symbols = [row['symbol'] for row in csv.DictReader(f)]
print(f'\n=== 戦略メモ ===')
for sym in symbols:
    notes = load_notes(symbol=sym)
    thesis = [n for n in notes if n.get('type') in ('thesis', 'observation')]
    if thesis:
        print(f'{sym}: {len(thesis)}件')
        for n in thesis[:2]:
            print(f'  [{n.get(\"type\")}] {n.get(\"content\",\"\")[:150]}')
"
```

`relevant_lessons` を以降の全ステップで参照する。Step 5 の verify_lesson_cited で
**この同じリスト**を引用検証に渡す（一貫性保証）。

次に stock-skills のエージェント（Screener / Analyst / Health Checker / Researcher / Strategist）を起動。使用可能なエージェントは [stock-skills routing.yaml](../stock-skills/routing.yaml) を参照。

### Step 2: 評価（自己評価 + 3LLM並列レビュー + 反証→再プラン）

DeepThink の価値は「なぜその結論に至ったか」の思考過程を見せること。

#### 2a. 自己評価

初回分析の結果を以下の観点で自己評価する:

| 観点 | チェック内容 |
|:---|:---|
| 情報充足 | 必要なデータが揃っているか（RSI? 決算日? センチメント?） |
| シナリオ | 複数のシナリオが検討されているか（楽観/悲観/中立） |
| PF整合 | ユーザーのPF構成・ターゲットと照合されているか |
| 反論 | Devil's Advocate の視点があるか |
| lesson | 過去の lesson と矛盾していないか（Step 1 でロード済みの lesson を参照） |

#### 2b. 4-Swarm 並列レビュー（⚠️ 4者全て必須。省略不可）

**2層モデル: インフラ層（固定）+ 推論層（動的）で構成する Swarm。**

オーケストレーターが GPT / Gemini / Grok を並列起動し、Claude 自身もオーケストレーター層で直接分析に参加する。

##### インフラ層（固定）— 物理的に代替不可能な能力

| LLM | 固定役割 | 理由 |
|:---|:---|:---|
| Grok | X/リアルタイム市場データ取得 | X Firehose は他LLMに不可能（ハード制約） |
| Gemini | Google検索 + 大量コンテキスト読込 | Google Search Grounding は他LLMに不可能（ハード制約） |

##### 推論層（動的）— テーマに応じて4者に割当

| 役割 | 内容 |
|:---|:---|
| Devil's Advocate | 反証・リスク指摘・見落とし検出 |
| Scenario Analyst | シナリオ分岐・感応度分析・長期推論 |
| Lesson Auditor | lesson整合性・過去学習との矛盾検出 |
| Portfolio Aligner | PF整合性・ターゲット照合・通貨/地域配分 |

##### 適性マトリクス（割当判断に使用）

| 役割 | GPT | Gemini | Grok | Claude |
|:---|:---|:---|:---|:---|
| Devil's Advocate | **最適** | 苦手（中立すぎる） | まあまあ | 可 |
| Scenario Analyst | **最適** | 得意（長文推論） | 表層的 | 可 |
| Lesson Auditor | 可 | **最適**（長コンテキスト） | 可 | 得意 |
| Portfolio Aligner | 可 | 可 | 可 | **最適** |

**⚠️ ハード制約を先に確認し、残りの推論役割をソフト制約（適性）で割り当てる。**

##### テーマ別割当例

```
地政学リスク:
  Grok   = [固定] X市場反応 + [動的] Devil's Advocate
  Gemini = [固定] Google検索 + [動的] Scenario Analyst
  GPT    = [動的] Lesson Auditor
  Claude = [動的] Portfolio Aligner

決算分析:
  Grok   = [固定] X決算反応 + [動的] （補助）
  Gemini = [固定] 決算データ検証 + [動的] Lesson Auditor
  GPT    = [動的] Scenario Analyst
  Claude = [動的] Devil's Advocate

PF再設計:
  Grok   = [固定] X市場評価 + [動的] Sentiment補強
  Gemini = [固定] Google検索 + [動的] Scenario Analyst
  GPT    = [動的] Devil's Advocate
  Claude = [動的] Portfolio Aligner
```

##### 呼び出し方法

| LLM | 呼び出し方法 |
|:---|:---|
| GPT | `call_llm('gpt', 'gpt-5.4', prompt, reasoning='high')` |
| Gemini | `call_llm('gemini', 'gemini-3-flash-preview', prompt, web_search=True)` or `call_llm('gemini', 'gemini-3.1-pro-preview', prompt)` |
| Grok | `tools/grok.py` の `search_x_sentiment()` / `search_market()` or `call_llm('grok', 'grok-4.20-0309-reasoning', prompt)` |
| Claude | オーケストレーター層で直接実行（Agent 起動不要） |

#### 2c. 反証→再プラン

外部レビューの反証を踏まえ、初回結論を **修正 or 強化** する:

```
📊 DeepThink Step 2 完了（Agents: X/Y, LLM calls: A/B）

初回結論: [初回分析の結論]

Swarm 割当: [テーマ名]
  GPT    = [固定: なし] + [動的: 割当された推論役割]
  Gemini = [固定: Google検索] + [動的: 割当された推論役割]
  Grok   = [固定: X市場データ] + [動的: 割当された推論役割]
  Claude = [動的: 割当された推論役割]

反証:
  [Devil's Advocate担当LLM]: [反証ポイント]
  [Scenario Analyst担当LLM]: [シナリオ分岐]
  [Lesson Auditor担当LLM]: [lesson整合性]
  [Portfolio Aligner担当LLM]: [PF整合性]

統合結論:
  [4者の指摘を踏まえ、オーケストレーターとして統合的に判断した結論]
  [「〜は妥当だが、〜の指摘を踏まえて〜に修正する」等]

再プラン:
  初回: [修正前の提案]
  修正: [修正後の提案]
  理由: [どの指摘がどう影響したか]
```

**⚠️ MUST: 統合結論では「各LLMの指摘をどう判断に反映したか」を明示する。指摘の羅列で終わらない。**

**評価結果**: 不足リストを作成（自己評価 + 外部レビューの指摘を統合）。

**収束条件**（以下の全てを満たしたら → Step 5 へ）:
1. 5つの評価観点が全て完了
2. 新たな不足が検出されない

**終了条件**（いずれかに該当 → 現時点の結果を提示 + ユーザー承認を要求）:
1. max_iterations に到達
2. max_llm_calls に到達
3. max_wall_time_minutes に到達

### Step 3: 改善（Optimizer）— 自律実行

不足リストに基づき、追加のエージェント/ツールを **自律的に** 起動する。

**⚠️ MUST: 各不足項目に「何を → どのLLM/ツールで → なぜ」を付与する。**

```
不足: 「Xセンチメント未取得」
  → 何を: UL のX上の投資家評価
  → どのLLM: Grok search_x_sentiment("UL", "Unilever")
  → なぜ: 候補の市場評価を定性的に補完

不足: 「イベントシナリオ未検討」
  → 何を: BOJ/FOMC最新予想
  → どのLLM: Gemini(web_search=True) で検索+推論
  → なぜ: 来週のイベントが候補の短期値動きに影響

不足: 「RSI未確認」
  → 何を: 候補銘柄のRSI(14)
  → どのツール: yahoo_finance.get_price_history + code interpreter
  → なぜ: 過熱圏での購入を回避（lesson参照）
```

**マルチLLMの活用**（`config/llm_capabilities.yaml` を参照）:

| 用途 | 優先LLM | 理由 |
|:---|:---|:---|
| **事実収集（Google検索）** | Gemini(web_search=True) | Google Search Grounding（ハード制約） |
| **Xセンチメント・リアルタイム** | Grok(tools/grok.py) | X Firehose アクセス（ハード制約） |
| **反証・リスク分析** | GPT(reasoning='high') | 批判的思考・深い推論（ソフト制約: 最適） |
| **lesson照合・長文分析** | Gemini-Pro | 1Mコンテキスト（ソフト制約: 最適） |
| **PF整合性・統合判断** | Claude（自身） | PF文脈保持・オーケストレーション |
| **徹底調査（業界網羅）** | Gemini Deep Research | 80-160 sources 自律巡回 + 引用付き（KIK-731） |
| **複数銘柄/テーマ並列** | Grok bulk_x / bulk_web | X firehose 並列・速報並列（KIK-732） |

**⚠️ ハード制約（物理的に不可能）を先に固定し、ソフト制約（得意不得意）で推論役割を割り当てる。**

#### Deep Research / Bulk Search トリガー (KIK-731 / KIK-732)

ユーザーが「**深く**」「**徹底的に**」「**DR で**」「**腰を据えて**」と発話、
または分析対象が >5銘柄 / >3テーマ横断の場合、Step 3 で以下を提案する:

```
🔍 Deep Research を起動できます
   ・gemini.deep_research: Web 徹底調査（80-160 sources、推定 $2.5、5-10分）
     → 業界全体像・規制動向・SEC等
   ・grok.bulk_x_search: X並列センチメント（推定 $0.5-2.5、~30秒）
     → 投資家センチメント・$cashtag・速報
   実行しますか？ [y/skip]
```

ユーザー `y` で実行。完了後、Layer 4 フッタに記録:
```
💰 cost=$X.XX | 📚 sources=N | ⏱ duration=Xs
```

`config/tools.yaml` の `provider` / `when` / `strength` / `not_for` で**用途を区別**:
- Web網羅 → `gemini.deep_research`（Google Search Grounding）
- X内データ → `grok.bulk_x_search`（X firehose 独占）
- 速報並列 → `grok.bulk_web_search`

ハード制約: `deepthink_limits.yaml` の `tool_limits` セクション（DR 月10回/$30、bulk 月20回/$10、合算 $50）。
`DEEPTHINK_DR_ENABLED=off` で DR 即停止。

### Step 4: チェックポイント（報告のみ — 承認待ちではない）

改善結果をユーザーに中間報告する。**報告後、不足があれば自律的に Step 2 に戻る。**

**以下のフォーマットに厳密に従うこと。省略・変更しない。**

```
📊 DeepThink Step N/M 完了（Agents: X/Y, LLM calls: A/B）

中間結果:
- [発見1]
- [発見2]
- [発見3]

不足: [残りの不足リスト or "なし（収束）"]
→ 自律続行: [次にやること] / 収束: Step 5 へ
```

ユーザーは **止めたい時だけ** 介入する。何も言わなければ自律ループを続行する。
ユーザーが「止めて」「方向修正」と言った場合のみ停止。

### Step 5: 統合レポート

**⚠️ MUST (KIK-735): 売買・トリム・売却提案を含む場合、Step 5 直前に preflight 再検証。**

```python
from tools.preflight import run_preflight
proposed = [("trim", "NVDA", 3), ("sell", "AMZN", 10)]  # 例
result = run_preflight(domain="pf", proposed_actions=proposed)
if not result["passed"]:
    # conviction 違反 / lot_size 不正 → 推奨を出力前に修正
    raise SystemExit(f"Preflight failed at Step 5: {result['violations']}")
```

**⚠️ MUST (KIK-738): Step 1 で抽出した `relevant_lessons` を最終提案文で**逐語引用**しているか検証。**

引用ゼロは「lesson 形骸化」の典型パターン (2026-04-27 撤回ログ / 2026-04-28 META 推奨ミス)。
Step 5 出力前に必ず以下を実行し、lesson が引用されていなければ提案を**書き直す**：

```python
from src.data.lesson_enforcer import verify_lesson_cited

final_proposal_text = "<エグゼクティブサマリー + Swarm 統合 + 詳細 の本文>"
ok, missing_lesson_ids = verify_lesson_cited(final_proposal_text, relevant_lessons)
if not ok:
    # missing_lesson_ids の lesson から expected_action / key_kpis を抜き出して、
    # エグゼクティブサマリー本文に組み込んで再生成。
    raise SystemExit(
        f"Step 5 lesson citation failed: {missing_lesson_ids} are not cited in proposal. "
        "提案テキストに該当 lesson の expected_action/key_kpis を逐語引用してから再出力すること。"
    )
```

加えて、**Deep Research / bulk_search を実行した場合は、DR の "不採用" 銘柄リストが**
**最終提案に混入していないか cross-check**：

```python
import re

# DR レポート本文 (Step 3 で取得した text) から不採用銘柄を動的抽出。
# 規則: 「見送り」「不採用」「除外」「除く」「リジェクト」を含むセクション内の
# ティッカー風トークン (大文字 2-5 文字 or 4桁.T/.Tの日本株コード) を拾う。
def _extract_dr_rejected(dr_text: str) -> list[str]:
    if not dr_text:
        return []
    pattern = r"(?:見送り|不採用|除外|除く|リジェクト|reject)[^\n]{0,400}"
    rejected: set[str] = set()
    for match in re.finditer(pattern, dr_text):
        sect = match.group(0)
        for sym in re.findall(r"\b([A-Z]{2,5}|\d{4}\.T)\b", sect):
            rejected.add(sym)
    return sorted(rejected)

dr_text = "<Step 3 で取得した DR 本文 (出力テキスト全体)>"
dr_rejected = _extract_dr_rejected(dr_text)  # 例: ["META", "VST", "TSM"]
for sym in dr_rejected:
    # plan に登場するが「DR 不採用」「DR rejected」のような明示的な逆論証も同時に
    # 含まれていなければ abort
    if sym in final_proposal_text and not re.search(
        rf"{sym}.{{0,80}}(不採用|rejected|見送り)", final_proposal_text
    ):
        raise SystemExit(
            f"DR cross-check failed: '{sym}' is in DR rejected list but is "
            "referenced in the proposal without explicit rejection rationale. "
            "DR で不採用判定された銘柄を組み入れるなら、その逆論拠を明示すること。"
        )
```

`_extract_dr_rejected()` は DR レポートのフォーマットに依存する best-effort 抽出。
DR が新フォーマットになったら正規表現を拡張すること。テストは
`tests/data/test_lesson_enforcer.py::TestStep5HookScenarios` に整合パターンあり。

**⚠️ MUST (KIK-739): 提案出力直前に Layer 5 (Cited Sources) を生成し、本文末尾に追加。**

「依拠した note の可視化 + 鮮度マーカー」で、古い情報の生ゴミ化を防ぐ
(2026-04-28 セッションで判明した「lesson が引用されない」「ATH 接近を見逃す」課題への対応)。

```python
from src.data.citation_formatter import format_cited_sources

# verify で実際に引用済みと判定された lessons を citation 候補に
cited_lessons = [l for l in relevant_lessons if l.get("id") not in missing_lesson_ids]
# 対象銘柄の thesis (Step 1 でロード済) のうち、提案文中に symbol が登場するものを cited に
cited_theses = [
    t for t in all_theses
    if (t.get("symbol") or "") and t["symbol"] in final_proposal_text
]
# 各引用ノートが提案のどこに使われたか 1 行でメモ。
# key は note['id'] (実際の保存形式: e.g. 'note_2026-04-24_portfolio_a1b2c3d4')
used_for_map = {
    cited_lessons[0]["id"]: "Cash 15-20% 判定",
    cited_lessons[1]["id"]: "売却対象除外",
    # ... 各 cited_lessons / cited_theses から id を引いてマッピング
}

citation_block = format_cited_sources(
    cited_lessons, cited_theses, used_for_map=used_for_map,
)
final_proposal_text = final_proposal_text.rstrip() + "\n\n" + citation_block
```

`format_cited_sources` の鮮度マーカー規則:
- `permanent` タグ → 🟢 (常時 fresh、永続ルール)
- `seasonal` (or タグ無し) → 0-30日 🟢 / 31-90日 🟡 / 91日+ 🔴
- `expired` → 出力から自動除外
- thesis に conviction_override → 🔒 (鮮度無視)

引用ゼロは **lesson 形骸化の典型** (2026-04-27 撤回ログのパターン) — 上の verify_lesson_cited
が abort するので、ここに到達した時点で必ず 1 件以上 citation がある状態。

**エグゼクティブサマリー先行の3部構成（サマリー、議論の統合、詳細）で出力する。**

**以下のフォーマットに厳密に従うこと。省略・変更しない。**

```
■ エグゼクティブサマリー
[結論を3-5行で。推奨アクション + 根拠の要点 + 主要な数値]

■ Swarm 議論の統合
[4者の指摘を踏まえた統合的な判断理由]
  - [LLM-A]は「〜」と指摘 → [採用/却下/部分採用]した理由
  - [LLM-B]は「〜」と分析 → [結論にどう反映したか]
  - [LLM-C]は「〜」を報告 → [判断にどう影響したか]
  - Claude（自身）は「〜」と評価
  → これらを総合し、[最終的な判断根拠]

■ 詳細
  シナリオ分析:
    [楽観/中立/悲観の確率と影響]
  ポートフォリオ影響:
    [具体的な数値変化]
  根拠データ:
    [使用した指標・ソース]
  推奨アクション:
    [具体的なアクションリスト（「何もしない」を含む）]
```

**⚠️ MUST: エグゼクティブサマリーだけで判断できる粒度にする。詳細は「なぜそう判断したか」の根拠。**
**⚠️ MUST: Swarm 議論の統合では、各LLMの指摘を「採用/却下/部分採用」の判断とともに示す。指摘の羅列で終わらない。**

## ハーネス制約

`deepthink_limits.yaml` に従い暴走を防止する:

- 上限到達時: ループ停止 → 現時点の結果を提示 → **続行にはユーザー承認が必要**
- 進捗は各ステップで表示: 「Agents 4/6, LLM calls 8/12」

## 進捗表示フォーマット

**このフォーマットに厳密に従うこと。省略・変更しない。**

ステップ開始時:
```
🔍 DeepThink Step N: [ステップ名]
   [実行中のLLM/ツール名] で [何をしているか]...
```

ステップ完了時:
```
✅ DeepThink Step N 完了
   発見: [主要な発見を1-2行]
   次のステップ: [次にやること]
```

## References

- ハーネス制約: [deepthink_limits.yaml](./deepthink_limits.yaml)
- LLM選択: [llm_capabilities.yaml](../../config/llm_capabilities.yaml)
- 通常モード: [stock-skills SKILL.md](../stock-skills/SKILL.md)
