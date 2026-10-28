# Jリーグ戦術分析・観戦ガイドRAG システム基本設計仕様書
*(J-League Tactical Analysis & Match Viewing Guide RAG - Architecture & System Specification)*

---

## 1. プロジェクトの目的とゴール

* **目的**: Jリーグ（2026シーズン：第1〜12節の初期構築＋第13節以降の毎節更新）の公式試合データを網羅的に収集・構造化し、LLM（Gemini 3.8 Flash）と決定論的計算モジュールを用いた深い戦術分析・因果推論を行う。
* **最終ゴール**: 単なるスコアやスタッツの要約にとどまらず、「なぜ起きたか（Why）」「ピッチ外の前提条件（怪我・警告・過密日程中◯日・契約制限・気候）はどう作用したか」「どう改善すべきか」を論理的に解明し、最終的に「スタジアムや画面でどこに注目すれば観戦が10倍面白くなるか（観戦の視点）」を導き出す。

---

## 2. 収集生データ体系と取得アプローチ

公式データスタジアム（SPAIA / Yahoo!サッカー）および Football LAB、クラブ公式レビューの正規生データセット（各試合約200KB）を正規収集・保持する。

| データ種別 | 主な収集元 | 取得データと実装アプローチ |
| :--- | :--- | :--- |
| **1. 選手詳細スタッツ** | SPAIA (`live_player_detail_stats`) | 全出場選手×50項目の詳細スタッツ（枠内シュート、パス方向・成功率、アタッキングサード進入・PA進入数、タックル・クリア・ブロック、イエロー/レッド）。 |
| **2. チーム指標・CBP** | Football LAB (`/report/`, `/match/`) | 全選手の8大チャンスビルディングポイント（攻撃・パス・クロス・ドリブル・シュート・奪取・守備・セーブ）、15分刻みの攻勢指数、進入変換率。 |
| **3. 実況ログ・タイムライン** | SPAIA / Yahoo!サッカー | 100件超の時系列テキスト速報、シュート位置座標、ファウル・交代・警告事象。 |
| **4. 定性レビュー・会見** | J公式 / クラブ公式サイト | 公式マッチレポート、両軍監督の試合後会見コメント全文、出場選手のインタビュー全文。 |
| **5. 試合メタデータ** | J公式 (`matches`) | 開催日時、スタジアム、天候、気温、湿度、観客数。 |

---

## 3. システムアーキテクチャ（3層ハイブリッド推論基盤）

ピッチ内の数値記録だけでなく、プロ分析官の戦術理論と試合前提の外部コンテキストを統合した3層ハイブリッド構成を採用する。

```mermaid
graph TD
    subgraph Layer 1: Deterministic Metrics & Context Engine
        Raw[生データ: SPAIA, FL, Yahoo, Markdown] --> CalcM[scripts/calculate_deep_metrics.py<br>進入変換率・CBPランキング・Box内外比率]
        Raw --> CalcC[scripts/calculate_match_context.py<br>過密日程中◯日・累積警告・気候・ローン制限・怪我]
        Master[config/ 各種マスタ<br>stadium, loan, injury, entity] --> CalcC
    end

    subgraph Layer 2: Tactical Knowledge & AI Reasoning Engine
        CalcM & CalcC --> Prompt[pipeline/tactical_enricher.py<br>プロ分析官システムプロンプト]
        Prompt --> LLM[Gemini 3.8 Flash<br>Zero-Hallucination & High-Fidelity]
        LLM --> Struct[data/structured/{match_id}_tactical.json<br>完全な15観点・6フェーズ・深層因果・match_context]
    end

    subgraph Layer 3: Application & Viewer Layer
        Struct --> Prof[agent/objective_profiler.py<br>15観点客観プロファイラー]
        Prof & Struct --> UI[Streamlit UI app.py<br>🛡️ 試合前提サポートバー ＆ 15観点多角分析]
        Struct --> Mobile[scripts/generate_mobile_viewer.py<br>exports/mobile_viewer/index.html (PWA対応)]
    end
```

### A. 第1層：決定論的深層指標 ＆ 試合前提コンテキスト基盤 (Deterministic Engine)
* **客観深層指標 (`scripts/calculate_deep_metrics.py`)**:
  - 進入変換率（30m→PA、PA→シュート）
  - 敵陣支配度（Field Tilt %）
  - CBPトップ3＆ベンチインパクト
  - 15分刻みの重要事象カウント
* **試合前提サポート情報 (`scripts/calculate_match_context.py`)**:
  1. 🏥 **怪我・コンディション調整**: `config/injury_tracker.json` ＋ 監督会見からの言及抽出
  2. 🟨 **累積警告・出場停止**: SPAIA全選手時系列集計（直前節退場による停止、3枚リーチ）
  3. 🗓️ **過密日程・中何日・移動負担**: 全日程差分計算、アウェイ連戦、遠征距離（`config/stadium_master.json`）
  4. 📄 **契約上の出場制限**: `config/loan_restrictions.json` による保有元クラブ対戦制限の自動判定
  5. 🌦️ **気候・ピッチ状態**: 気温・湿度による酷暑飲水タイム判定、雨天重馬場ピッチ判定

### B. 第2層：AI戦術推論エンジン (`pipeline/tactical_enricher.py`)
* 事前計算された客観数値と5大サポート情報をGemini 3.8 Flashに注入し、定型文を完全排除した15観点のプロ分析官レベルの論理因果・アウェイ対等視点を自動生成。
* 出力結果は `data/structured/{match_id}_tactical.json` にキャッシュ同期。

### C. 第3層：マルチプラットフォーム可視化層
* **Streamlit Web UI (`app.py`)**: 試合ヘッダー、🛡️前提条件サポートバー、15観点多角分析、定性対比、採点寸評を一覧表示。
* **モバイルHTMLビューア (`exports/mobile_viewer/index.html`)**: スマートフォンで即座に参照可能なレスポンシブWebアプリ。

---

## 4. 分析フレームワーク：データから引き出す「9つの問い」

1. **【要因分析 (Why)】**: 外部コンテキスト（怪我・警告・過密日程）とピッチ内指標を突き合わせ、現象の真因を特定。
2. **【改善処方箋 (How)】**: ボトルネックに対し、構造的解決策と交代カードの2軸で改善策を提示。
3. **【反実仮想予測 (What-if)】**: 戦術変更案と相手の強みを衝突させ、光と影のシナリオを予測。
4. **【言行一致の検証】**: 監督会見の主張と客観データ事実を突き合わせ、言行一致・認識ギャップ・隠れた真実を検証。
5. **【黒子（陰のMVP）の発掘】**: ゴール・アシスト以外の局面奪取・守備CBPで貢献した選手を抽出。
6. **【相性・ケミストリー分析】**: 縦・横のユニット連携の成立状況を検証。
7. **【スコア状況別の体質診断】**: 先制直後・ビハインド時のラインコントロールと重心変化を診断。
8. **【戦術の賞味期限と進化】**: 相手からの研究・対策に対するチーム戦術のマイナーチェンジを追跡。
9. **【実力と運の切り分け】**: 進入変換率やxGとスコアの乖離から、勝敗の必然性と揺り戻しを判定。

---

## 5. ディレクトリ構成

```text
football_rag/
├── config/
│   ├── entity_master.json        # チーム・選手表記ゆれ名寄せ辞書
│   ├── stadium_master.json       # スタジアム所在地・東京からの移動距離(km)・移動手段マスタ
│   ├── loan_restrictions.json    # 期限付き移籍（ローン）選手・保有元対戦制限マスタ
│   └── injury_tracker.json       # 公式負傷リリース・全治期間・コンディション追跡マスタ
├── data/
│   ├── football.db               # SQLite正規化データベース (matches, team_match_stats, etc.)
│   ├── raw/                      # 収集生データ (spaia, football_lab, yahoo)
│   ├── markdown/2026/            # 公式戦評・監督会見・選手証言Markdown
│   └── structured/               # 完全構造化JSON ({match_id}_tactical.json)
├── pipeline/
│   ├── tactical_enricher.py      # Gemini 3.8 Flash AI戦術推論エンジン (Zero-Hallucination)
│   ├── normalizer.py             # Pydantic検証・名寄せ
│   ├── semantic_serializer.py    # 座標・数値の戦術言語化
│   └── indexer.py                # SQLite / ChromaDB Upsert
├── agent/
│   ├── objective_profiler.py     # 15観点客観多角分析プロファイラー
│   ├── qualitative_comparator.py # 客観事実 vs 定性言説 答え合わせエンジン
│   ├── player_rater.py           # 選手・監督の客観データ＆定性統合採点
│   └── engine.py                 # 統合分析エンジン
├── scripts/
│   ├── calculate_deep_metrics.py # 進入変換率・CBP集計モジュール
│   ├── calculate_match_context.py# 5大サポート情報（日程・規律・気候・ローン・怪我）算出
│   ├── enrich_fct_tactics_batch.py # MW1〜MW11 戦術構造化バッチ
│   ├── enrich_fct_match_context_batch.py # 5大サポート情報一括同期バッチ
│   └── generate_mobile_viewer.py # スマホ用モバイルHTMLビューア生成
├── tests/
│   ├── test_match_context.py     # 5大サポート情報単体テスト (10テスト)
│   └── ...                       # 全170件の包括ユニットテスト群
└── app.py                        # Streamlit 統合分析ダッシュボード
```

---

## 6. 改定履歴
* **2026-10-26 (初期設計)**: 2層RAGおよび4大データ収集仕様の策定。
* **2026-10-27 (高解像度戦術設計)**: 15観点プロ分析官水準、水戸戦品質の完全自動生成アーキテクチャ策定。
* **2026-10-28 (5大分析サポート情報・外部コンテキスト仕様策定)**: 外部要因（怪我・警告・過密日程中◯日・契約制限・気候ピッチ）の決定論的算出モジュール、マスタ群、UIバッジおよびモバイルHTMLビューア仕様を追加統合。