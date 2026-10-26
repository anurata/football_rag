<USER_REQUEST>
以下のようなことがやりたい。実際にできるかどうかレビューして。

別チャットへそのまま貼り付けて開発や設計の続きを開始できるよう、ここまでの検討内容を「Jリーグ戦術分析・観戦ガイドRAG システム設計仕様書」としてまとめました。

---

# Jリーグ戦術分析・観戦ガイドRAG システム設計仕様書

## 1. プロジェクトの目的とゴール

* **目的**: Jリーグ（2026/27シーズン：第1〜12節の初期構築＋第13節以降の毎節更新）の試合データを収集・構造化し、LLMを用いた深い戦術分析・展開予測を行う。
* **最終ゴール**: 単なるスタッツの要約や定型的な相性診断にとどまらず、「なぜ起きたか」「どう改善すべきか」「戦術変更で何が起きるか」を推論し、最終的に「スタジアムや画面でどこに注目すれば観戦が面白くなるか（観戦の視点）」を導き出す。

---

## 2. 4大データの収集元と取得アプローチ

個人開発で取得可能な範囲で、HTMLスクレイピングと内部通信JSONの傍受（Playwright）を組み合わせて収集する。

| データ種別 | 主な収集元 | 取得データと実装アプローチ |
| --- | --- | --- |
| **1. スタッツ**<br>

<br>*(Stats)* | ・Jリーグ公式サイト<br>

<br>・Sofascore / FotMob<br>

<br>・Football LAB | ・**J公式**: 基本スタッツ、前後半別数値。<br>

<br>・**Sofascore (通信傍受)**: 前後半別のxG（ゴール期待値）、ビッグチャンス数、敵陣パス成功率、デュエル勝率。<br>

<br>・**Football LAB**: チャンス構築率、AGI（攻撃の勢い）、KGI、15分刻みのポゼッション推移。 |
| **2. イベントデータ**<br>

<br>*(Event Data)* | ・Sofascore / FotMob<br>

<br>・J公式 / スポナビ | ・**Sofascore (`/shotmap`, `/incidents`)**: 全シュート・ゴールイベントの座標 `(x, y)`、xG値、部位、状況（オープンプレー/セットプレー/カウンター）。<br>

<br>・**J公式 (`/live/`)**: 時系列テキスト速報（分、イベント種別、本文）を構造化。 |
| **3. トラッキングデータ**<br>

<br>*(Tracking代替特徴量)* | ・Jリーグ公式サイト<br>

<br>・Sofascore | ※25fpsの生座標データは非公開かつLLMに不向きなため、**空間・フィジカル特徴量**で代替。<br>

<br>・**J公式 (`/stats/`)**: チーム・選手別の総走行距離（km）、スプリント回数（時速24km以上）。<br>

<br>・**Sofascore (`/average-positions`, `/heatmap`)**: 全出場選手の平均ポジション座標 `(avg_x, avg_y)` とタッチ数、主力選手のヒートマップ座標。 |
| **4. マッチレポート**<br>

<br>*(Match Report)* | ・Jリーグ公式サイト<br>

<br>・スポーツメディア<br>

<br>・クラブ公式サイト | ・**J公式 (`/coach/`, `/player/`)**: 公式マッチレポート、両監督の試合後会見コメント全文、出場選手のインタビュー全文。 |

---

## 3. システムアーキテクチャ（2層RAG × ハイブリッドDB）

「試合で何が起きたか（結果の記録）」だけでは深い因果推論ができないため、【第1のRAG：試合ファクトDB】**と**【第2のRAG：戦術・因果推論ナレッジベース】の2層を掛け合わせる。

### A. 第1のRAG：試合ファクトDB（RDB + Vector DB）

#### ① RDBスキーマ（SQLite / PostgreSQL：定量集計・時系列検証用）

1. **`matches`**: `match_id` (PK), `season`, `matchweek`, `date`, `home_team_id`, `away_team_id`, `home_score`, `away_score`, `stadium`, `weather`, `pitch_condition`
2. **`team_match_stats`**: `match_id`, `team_id`, `period` (ALL/1H/2H), `game_state` (ALL/DRAW/LEADING/TRAILING), `possession`, `xg`, `shots`, `big_chances`, `final_third_passes`, `total_distance_km`, `sprints` 等
3. **`player_match_stats`**: `match_id`, `player_id`, `team_id`, `is_starter`, `minutes_played`, `position`, `goals`, `assists`, `xg`, `xa`, `touches`, `duels_won`, `distance_km`, `sprints`, `avg_x`, `avg_y`
4. **`match_events`**: `event_id` (PK), `match_id`, `minute`, `period`, `game_state` (発生時のスコア状況: DRAW/LEADING/TRAILING), `team_id`, `player_id`, `event_type`, `coord_x`, `coord_y`, `xg`, `situation`, `description_text`
5. **`entity_master`**: `entity_id` (PK), `entity_type` (team/player), `canonical_name`, `jleague_id`, `sofascore_id`, `football_lab_slug`, `aliases`（表記ゆれ名寄せ辞書）

#### ② 座標・数値の言語化（Semantic Serialization）

生座標 `(x, y)` をそのままベクトル化せず、100×100正規化座標を戦術エリア名へ自動翻訳してテキスト化する。

* **X軸（奥行）**: `0-33`: 自陣ビルドアップ / `34-66`: ミドルゾーン / `67-83`: ファイナルサード / `84-100`: ボックス内・ゴール前
* **Y軸（横幅）**: `0-20`: 右大外 / `21-38`: 右ハーフスペース / `39-61`: 中央（バイタル） / `62-79`: 左ハーフスペース / `80-100`: 左大外

#### ③ Vector DB（ChromaDB / Qdrant：1試合あたり4チャンク固定＋メタデータ）

* **共通メタデータ**: `season`, `matchweek`, `match_id`, `teams`, `chunk_type`, `speaker_team`（発言側）, `target_team`（言及対象）
* **4つのチャンク定義**:
1. `match_summary_and_stats`: 公式レポート本文 ＋ 前後半別の主要スタッツ・走行距離の比較Markdown表。
2. `tactical_timeline_and_zones`: 15分刻み（6フェーズ）の攻勢推移・主要イベント ＋ 平均座標から判定した実質フォーメーションと攻撃偏重エリアの記述。
3. `manager_interviews`: 両監督のコメント全文（戦術的意図、修正点、敗因）。
4. `player_interviews`: 選手コメント全文（ピッチ上の肌感覚、プレス強度、距離感の証言）。



---

### B. 第2のRAG：戦術・戦略ナレッジベース（YAML / Markdown）

LLMにプロの分析官の思考回路を与えるためのドメイン知識辞書。

1. **指標の多義性と因果ツリー辞書 (`Metric-to-Cause`)**:
* 数値変動に対する複数仮説の定義（例：「敵陣パス成功率低下」＝ ①相手プレス速度、②受け手のポジショニング不良、③リスクを冒す縦パス志向、の3仮説と検証指標）。


2. **戦術トレードオフ辞書 (`If-Then-Risk`)**:
* 戦術選択における「主作用（メリット）」と「副作用（構造的リスク）」のペア定義（例：ハイライン・ハイプレス ⇔ 背後のスペース被弾と後半60分以降の運動量減衰）。


3. **システム噛み合わせ・空間ミスマッチ辞書 (`System Matrix`)**:
* フォーメーション同士（例：`4-4-2` vs `3-4-2-1`）の構造的な数的優位エリア、ピン留めの力学、ハーフスペースの空き方。


4. **選手ロール＆チーム哲学プロファイル (`Archetype Tags`)**:
* 単なるポジション表記ではなく、プレースタイル（例：「偽SB型」「大外オーバーラップ型」「ライン間レシーバー」「裏抜けスプリンター」）のタグ定義。



---

## 4. 分析フレームワーク：データから引き出す「9つの問い」

SQL集計ツール（定量検証）とベクトル検索（定性文脈＋戦術ナレッジ）を組み合わせ、以下の9つの問いに答える。

### 基本の3つの問い（因果推論・戦術シミュレーション）

1. **【要因分析 (Why)】〇〇の要因として考えられるのは、データから見ると？**
* 現象（例：後半の被xG増）に対し、「①フィジカル減衰」「②ライン後退・間延び（`avg_x`の変化）」「③相手の戦術変更」の複数仮説を立て、データで消去法にかけて真因を特定する。


2. **【改善処方箋 (How)】〇〇を改善するためには、何をすればよいのか？**
* ボトルネックに対し、「構造的解決策（ピン留めとポケット侵入の仕組み等）」と「属人的解決策（特定ロールの選手起用・交代カード）」の2軸で改善策を提示する。


3. **【反実仮想予測 (What-if)】〇〇をすると、どんなことが起こると考えられるか？**
* 戦術変更案と相手の強みスタッツを衝突させ、「狙い通りのメインシナリオ（光）」と「相手に逆手に取られるリスクシナリオ（影）」を同時にシミュレーションする。



### 拡張の6つの問い（多角的インサイト）

4. **【言行一致の検証】** 監督は「狙い通り」「修正できた」と言っているが、データ上も本当に改善していたのか？（結果オーライの勝利と内容のある敗戦の切り分け）
5. **【黒子（陰のMVP）の発掘】** ゴールやアシストはゼロだが、出場時間帯（On/Off）でチームのxGやパス成功率が劇的に良くなっている献身的な選手は誰か？
6. **【相性・ケミストリー分析】** 選手Aの良さを最も引き出す「相棒（縦・横のペア）」は誰か？ 組む相手によって平均立ち位置やプレー選択はどう変わるか？
7. **【スコア状況別の体質診断】** 先制直後の15分間（`game_state: LEADING`）、畳みかけるチームか、無意識にラインが下がって受け身に回る体質か？
8. **【戦術の賞味期限と進化】** 開幕当初と比べて、相手からどう研究・対策され（相手監督コメント横断検索）、どうマイナーチェンジしているか？
9. **【実力と運の切り分け】** 現在の好不調は実力通りか、それとも「実得点とxGの乖離（運の偏り）」によるもので近く揺り戻しが来るか？

---

## 5. 最終アウトプット：「観戦が10倍面白くなる4つのレンズ」

分析の最終出力として、専門知識がなくてもスタジアムや画面で楽しめる以下の4つの観戦ガイドを生成する。

1. **開始10分の「配置の答え合わせ」**（ボールがないところで誰が誰をマークし、どこにスペースが空くか）
2. **守備のスイッチが入る「トリガー」の瞬間**（相手の誰にどんなパスが入った瞬間に一斉にプレスへ行くか）
3. **試合の流れを知らせる「炭鉱のカナリア（先行指標）」**（スコアが動く前に、セカンドボール回収位置やラインの高さで優劣を見極めるポイント）
4. **後半60分の「ベンチのチェス（交代カードの意図）」**（投入された選手のロールから読み解く、追加点狙いか逃げ切りかのベンチのメッセージ）

---

## 6. ディレクトリ構成とバッチ運用パイプライン

```text
jleague-rag/
├── config/
│   └── entity_master.json        # チーム・選手の名寄せ辞書
├── knowledge/                    # 【第2のRAG】戦術・戦略ナレッジベース
│   ├── metric_causal_trees.yaml  # ① 指標の多義性と因果ツリー辞書
│   ├── tactical_tradeoffs.yaml   # ② 戦術トレードオフ辞書
│   ├── system_matrix.yaml        # ③ システム噛み合わせ・空間ミスマッチ辞書
│   └── player_archetypes.json    # ④ 選手ロール＆チーム哲学プロファイル
├── scrapers/                     # データ収集層
│   ├── jleague_official.py       # J公式（スタッツ・走行距離・コメント・速報）
│   ├── sofascore_interceptor.py  # Playwright通信傍受（xG・座標・平均位置）
│   └── football_lab.py           # Football LAB（独自指数・時間帯ポゼッション）
├── pipeline/                     # 前処理・DB格納層
│   ├── normalizer.py             # Pydantic検証・名寄せ・game_state付与
│   ├── semantic_serializer.py    # 座標(x,y)・数値 → 戦術テキスト変換器
│   └── indexer.py                # SQLite および ChromaDB/Qdrant へのUpsert
├── agent/                        # 推論・分析エージェント層
│   ├── sql_tools.py              # LLM用データ集計関数群（Function Calling）
│   ├── retriever.py              # 2層RAGハイブリッド検索エンジン
│   └── analyst_prompts.py        # 9つの問い＆4つの観戦レンズ生成プロンプト
└── scripts/
    ├── backfill_mw1_to_12.py     # 第1〜12節の一括初期構築スクリプト
    └── update_matchweek.py       # 毎節実行用の差分更新スクリプト

```

### 毎節の2段階更新フロー

* **Stage 1（試合当日 23:00）**: J公式（基本スタッツ・速報・コメント）＋ Sofascore（xG・座標・平均位置）を取得し、速報版としてDBへ格納。
* **Stage 2（翌週火曜 12:00）**: J公式（トラッキングデータ：走行距離・スプリント）＋ Football LAB（戦術指数）を取得し、既存レコードとベクトルチャンクを上書き更新（Upsert）。

---

## 別チャット再開時のプロンプトテンプレート

新しいチャットで作業を再開する際は、上記の仕様書を貼り付けた上で、末尾に以下のように指示を追加してください。

> **【別チャットでの指示出し例】**
> 上記の「Jリーグ戦術分析・観戦ガイドRAG システム設計仕様書」をベースに開発を進めます。
> 今回はまず、`[やりたい項目：例1. scrapers/ の実装（J公式とSofascoreからの1試合データ取得） / 例2. knowledge/ の戦術ナレッジYAMLの作成 / 例3. pipeline/ のDBスキーマとシリアライザの実装]` から具体的に作成してください。
</USER_REQUEST>
<ADDITIONAL_METADATA>
The current local time is: 2026-10-26T14:56:18+09:00.

The user's current state is as follows:
Active Document: d:\workspace\flutter\football_rag\data\markdown\20261021_FCT_KAS_flab.md (LANGUAGE_MARKDOWN)
Cursor is on line: 1
Other open documents:
- d:\workspace\flutter\football_rag\test_fctokyo_scraper.py (LANGUAGE_PYTHON)
- d:\workspace\flutter\football_rag\scraper.py (LANGUAGE_PYTHON)
- d:\workspace\flutter\football_rag\football_lab_scraper.py (LANGUAGE_PYTHON)
- d:\workspace\flutter\football_rag\test_football_lab_scraper.py (LANGUAGE_PYTHON)
- d:\workspace\flutter\football_rag\data\markdown\20261021_FCT_KAS_flab.md (LANGUAGE_MARKDOWN)
</ADDITIONAL_METADATA>