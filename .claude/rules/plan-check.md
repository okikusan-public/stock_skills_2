# Plan-Check: 投資判断マルチエージェントフロー (KIK-596)

投資判断の実行を伴う発言（入替・購入・売却・リバランス・調整）に対して、
Plan → Execute → Review の3フェーズで複数エージェントが議論し、
過去のlessonが自動的に制約として適用される仕組み。

## トリガー条件

以下のアクションタイプに該当する発言があった場合、このフローを発動する。

| アクションタイプ | 判定キーワード |
|:---|:---|
| `swap_proposal` | 入替、乗り換え、代わり、スワップ |
| `new_buy` | 買いたい、エントリー、追加したい |
| `sell` | 売りたい、損切り、利確、売却 |
| `rebalance` | リバランス、配分調整、バランス改善 |
| `adjust` | 調整、処方箋、直して、改善して、アドバイス |

**発動しないケース**: 情報照会（"見せて"）、売買記録（"買った"過去形）、スクリーニング探索（"いい株ある？"）

## フロー

### Phase 1: Plan（3エージェント議論）

1. `python3 scripts/extract_constraints.py "<ユーザー入力>"` を実行し制約JSONを取得
2. TeamCreate で計画チームを作成
3. 以下3エージェントを並列起動し、各自の分析結果を出力させる

#### Strategist

実行計画を策定する。以下を含めること:
- 具体的なアクションステップ（何を、どの順番で実行するか）
- 各ステップで使用するスキル/スクリプト
- 成功基準（どうなったらOKか）
- 制約条件をどのように満たすか

#### Lesson Checker

制約条件（extract_constraints.pyの出力）に対して、計画が違反していないかチェックする:
- 各constraintのtriggerが現在の状況に該当するか
- expected_actionに沿った計画になっているか
- 判定: PASS（全制約クリア）/ WARN（注意必要）/ FAIL（明確な違反）

#### Devil's Advocate

計画に対して意図的に反論・盲点を指摘する:
- 見落としているリスク
- タイミングの適切性
- バイアスの有無（保守バイアス、確認バイアス等）
- 代替案の提示

4. 3エージェントの結果を統合
5. Lesson CheckerがFAIL → 制約違反を修正して再計画（最大2回）
6. TeamDelete

### Phase 2: Execute（並列実行）

Plan Phaseで策定した計画に従い、既存スキルを順番に実行する:

| アクションタイプ | 典型的な実行順序 |
|:---|:---|
| swap_proposal | health → screen-stocks（3地域以上）→ what-if |
| new_buy | get_context → stock-report → what-if |
| sell | get_context → health → what-if |
| rebalance | health → analyze → rebalance |
| adjust | health → adjust |

制約条件に「最低3地域で検索」がある場合、スクリーニングは必ず3地域以上で実行する。

### Phase 3: Review（3エージェント議論）

1. TeamCreate でレビューチームを作成
2. 以下3エージェントを並列起動

#### Constraint Checker

制約条件の充足を最終確認:
- 各constraintのexpected_actionが実行されたか
- 出力に制約違反がないか
- 判定: PASS / FAIL（差し戻し理由）

#### Quality Checker

出力の品質と論理整合性を確認:
- 数値の整合性（what-ifの資金収支、HHI変化等）
- 推奨の論理的根拠が明示されているか
- portfolio.mdのルール（スワップ前what-if必須、単元株コスト制限等）への準拠

#### Risk Checker

見落とされたリスクがないか最終確認:
- 通貨集中リスク（USD比率60%超等）
- セクター/地域集中リスク
- 流動性リスク（単元株コスト vs PF総額）
- 市況リスク（決算直前、地政学イベント等）

3. 結果統合
4. いずれかのCheckerがFAIL → Phase 1に差し戻し（差し戻し理由を付与）
5. 全PASS → 最終出力をユーザーに提示
6. TeamDelete

## 差し戻しルール

- 最大差し戻し回数: 2回
- 3回目はWARN付きで出力（無限ループ防止）
- 差し戻し時: FAIL理由 + 該当constraintをPlan Phaseの入力に追加

## 制約抽出コマンド

```bash
# JSON形式（エージェント入力用）
python3 scripts/extract_constraints.py "<ユーザー入力>"

# Markdown形式（人間可読）
python3 scripts/extract_constraints.py "<ユーザー入力>" --format markdown
```
