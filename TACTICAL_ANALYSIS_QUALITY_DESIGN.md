# 戦術分析品質向上・完全自動生成 詳細設計書
*(Tactical Analysis Quality Enrichment & Automated Generation Architecture)*

---

## 1. 背景と現状の課題分析（なぜ低品質に見えるのか）

### 1.1 現状の課題の根本原因
現在、FC東京の試合分析（特にMW1〜MW11）において「分析品質が明らかに低く見える」根本原因は以下の3点に集約されます：

1. **定型文テンプレートへの依存（フォールバック露出）**:
   - `agent/objective_profiler.py` の `_build_perspectives_list()` において、「ボール保持率とスプリント回数が示す通り、双方が異なるゲームプランで挑んだ90分間」「ペナルティエリア角（ポケット）からのマイナスクロスと折り返し」といった固定文字列が全試合で機械的に穴埋めされている。
2. **生データ（200KB/試合）の潜在情報の未活用**:
   - SPAIA（選手50項目詳細、100件超の時系列速報ログ）、Football LAB（全選手8大CBP、15分毎攻勢指数）、Yahoo!サッカー（シュート位置・枠内率・タイムライン）の正規生データを取得済みであるにもかかわらず、その9割以上の数値・イベントが分析テキストに反映されていない。
3. **戦術的因果関係の欠如（WhatはあるがWhy/Howがない）**:
   - 水戸戦（MW12）の成功事例では「誰がどこにポジショニングし、誰を釣り出し、どこで数的優位が生まれたか」という**プロ分析官レベルの深層因果・アウェイ視点**が言語化されていたのに対し、他11試合は単純なスコア要約と短い定型文にとどまっている。

---

## 2. 目指すべき品質基準（Goal State / Specification準拠）

`data_analysis_specification.md` の5大原則に完全準拠し、全12試合において水戸戦と同等以上の解像度を達成します。

| 項目 | 現状（低品質版） | 刷新後（プロ分析官水準） |
| :--- | :--- | :--- |
| **データ根拠** | スコア・保持率・シュート数の表面値のみ | SPAIA 50項目・Football LAB CBP・進入変換率（30m→PA、PA→シュート） |
| **テキスト文量** | 1観点あたり 50〜100文字（定型文） | 1観点あたり **350文字以上（重厚な論理展開）**、全体で数千文字 |
| **実名言及** | 得点者のみ | 先発・途中交代・監督の実名、背番号、関与局面を具体名指し |
| **3層構造 & 4要素** | 定型文で形骸化 | ①数値事実と示唆、②速報具体カウント、③戦術理論タグ＆構造、④**AWAY対等視点** |
| **深層指標** | 未算出 | 進入変換効率（%）、Box内シュート比率、CBPトップ＆ワーストを数値化 |

---

## 3. システムアーキテクチャ設計

```mermaid
graph TD
    subgraph Raw Data (200KB/match)
        SP[SPAIA: Player Stats 50 items & Text Logs]
        FL[Football LAB: CBP Matrix & Offensive Index]
        YS[Yahoo: Timeline & Team Stats]
    end

    subgraph Step 1: Deterministic Metrics Calculator
        MC[scripts/calculate_deep_metrics.py]
        MC --> CR[進入変換率: 30m→PA, PA→シュート]
        MC --> CBP[選手別CBPランキング Top/Worst]
        MC --> EV[速報事象集計: 時間・エリア・選手]
    end

    SP & FL & YS --> MC

    subgraph Step 2: Gemini 3.8 Flash Tactical Engine
        LLM[pipeline/tactical_enricher.py<br>System: Jリーグ専属トップ戦術分析官]
        Prompt[事前計算指標 + 時系列速報ログ + 監督会見]
        Prompt --> LLM
    end

    CR & CBP & EV --> Prompt

    subgraph Step 3: Structured Cache & Profiler
        JSON[data/structured/{match_id}_tactical.json<br>完全な15観点・4要素・採点データ]
        Profiler[agent/objective_profiler.py]
        UI[Streamlit UI / RAG Agent]
    end

    LLM --> JSON
    JSON --> Profiler --> UI
```

### 3.1 深層指標の決定論的算出モジュール (`scripts/calculate_deep_metrics.py`)
AIのハルシネーション（嘘）をゼロにするため、客観数値はPythonで100%決定論的に計算してプロンプトに渡します。
1. **進入変換率（Conversion Efficiency）**:
   - $30\text{m} \to \text{PA変換率} = (\text{PAPlayCount} / \text{M30PlayCount}) \times 100$ (%)
   - $\text{PA} \to \text{シュート変換率} = (\text{Shoot} / \text{PAPlayCount}) \times 100$ (%)
2. **シュート品質（Box内 vs ミドル比率）**:
   - PA内シュート数 vs PA外シュート数の比率（崩しの精度判定）。
3. **CBP格差とキーマン特定**:
   - 全選手の「奪取」「守備」「攻撃」「パス」CBPをソートし、突出した選手（上位3名）と沈黙したユニットを抽出。
4. **速報ログ事象カウント**:
   - 15分刻み（0-15, 15-30, 30-45, 45-60, 60-75, 75-90）におけるシュート、クロス、被ファウル、交代の発生件数と主要関与選手。

### 3.2 Gemini 3.8 Flash による戦術推論エンジン (`pipeline/tactical_enricher.py`)
- **ペルソナ**: Jリーグ専属トッププロ戦術分析官（ポジショナルプレー、5レーン、カウンタープレス、Game State理論に精通）。
- **入力**: 3.1で算出した深層メトリクス辞書 ＋ SPAIA時系列実況ログ ＋ Football LAB戦評 ＋ クラブ公式戦評・監督コメント。
- **出力形式**: Pydanticで定義された完全な15観点構造化JSONスキーマ（各観点に `layer1_summary`, `layer2_counts`, `layer3_theory`, `away_perspective` を必須化）。

### 3.3 構造化データの保存・キャッシュ仕様
- 生成結果は `data/structured/{match_id}_tactical.json` および `{game_id}_tactical.json` に完全同期保存。
- `objective_profiler.py` は、この高解像度JSONに15観点データが含まれている場合、**定型文を一切使わずに直接プロ分析官の推論データを展開**するよう改修。

---

## 4. 段階的実装ステップ（提案）

作業効率と品質検証を確実にするため、以下の**4ステップ**に分けて進めることを提案します：

### 【ステップ1】決定論的深層指標算出モジュールの実装と検証
- **内容**: `scripts/calculate_deep_metrics.py` を作成。生データ（SPAIA, FL, Yahoo）から進入変換率、Box内外比率、CBPトップ/ワースト、速報カウントを正確に集計するユニットテストを作成してパスさせる。
- **成果物**: 深層指標集計関数、`tests/test_deep_metrics.py`

### 【ステップ2】Gemini 3.8 Flash 戦術推論パイプラインの実装
- **内容**: `pipeline/tactical_enricher.py` を実装。水戸戦の成功プロンプトをベースに、15観点×4要素＋勝因敗因＋選手寸評を出力する厳密なPydanticモデルとジェネレータを構築。
- **成果物**: `pipeline/tactical_enricher.py`, `tests/test_tactical_enricher.py`

### 【ステップ3】FC東京 2026シーズン（MW1〜MW11）のバッチ再生成
- **内容**: MW1〜MW11の11試合についてGemini APIを実行し、`data/structured/` 内のデータを高解像度版に完全刷新（MW12水戸戦は正本として保護）。
- **成果物**: 11試合分の高解像度 `*_tactical.json`

### 【ステップ4】UI/Profiler結合とフルテスト・品質レビュー
- **内容**: `agent/objective_profiler.py` を改修して新構造データを完全統合。テストスイート（146件＋新規テスト）を実行し、Streamlit UI上で町田戦や浦和戦の表示品質を目視検証。
- **成果物**: フルテストPASS、UIスクリーンショット、完了報告

---

## 5. エラー防止・コーディング規約遵守チェックリスト
- [ ] カッコ `{ }`、`[ ]`、`( )` の不一致エラー防止（1メソッドのネストを浅く保ち、Widget/Helper関数に分割）。
- [ ] 末尾カンマの徹底。
- [ ] 既存の動作を壊さない下位互換性（フォールバックの維持）。
- [ ] コミット前のフルテスト実行（勝手なコミットは行わない）。
