# J1番記者通信簿（Match Report Card）評価仕様書

---

## 1. 概要・設計思想

本仕様書は、サッカー専門新聞『エル・ゴラッソ』の「番記者通信簿」企画に準拠し、J1公式戦における各クラブのパフォーマンスを**6つの評価項目（各10点満点・合計60点満点）**および総合ランク（S〜D）として自動採点・可視化する「番記者通信簿エンジン（`MatchReportCardCalculator`）」の仕様を定義するものです。

### 設計のコア方針
1. **ハイブリッド採点体系**:
   - 試合内の絶対スタッツ（支配、個人、球際、リレーション）と、リーグ全体比較（スタイル発揮）、試合展開のドラマ性（興奮度）を統合。
2. **強豪不利益の排除（全チームパーセンタイル）**:
   - 「③ スタイル発揮」において、チーム自身の過去平均のみを基準とせず、リーグ全チーム中の上位割合（パーセンタイル）をベースラインとすることで、ハイパフォーマンスな強豪チームが正当に9〜10点を獲得できる公平性を担保。
3. **自己成長ボーナス（ブレイクスルー加点）**:
   - リーグ中位・下位のクラブであっても、これまでの自チーム平均を著しく上回って持ち味を開花させた場合は小幅に加点（+0.5〜+1.0点）。
4. **55指標および詳細パスデータの融合**:
   - アタッキングサード傾斜度（`field_tilt`）、ボロノイ空間支配率（`voronoi_control`）、前方向パス成功数、敵陣パス成功率、シャノン・エントロピー、陣形コンパクトネス等を活用。
5. **ドラマ性・因縁ボーナスのルール化（興奮度）**:
   - 伝統のダービーマッチ勝利、数的不利（退場者発生）からの逆転・ドロー、終盤（80分以降/後半AT）の劇的弾などを客観加点。

---

## 2. 評価項目体系と採点基準

### 2.1 6つの評価項目（各0〜10点・整数）
1. **① ゲーム支配 (Game Dominance)**: ボール支配率、敵陣30m/PA進入比率（`field_tilt`）、相手シュート・xG抑制率
2. **② 個人パワー (Individual Power)**: ドリブル成功数、デュエル勝数、個人最高採点の突出度、非シュート期待脅威度（`non_shot_obv`）、途中交代選手の付加価値（`sub_mva`）
3. **③ スタイル発揮 (Tactical Style Execution)**: クラブ固有の志向スタイルKPIにおけるリーグ全チーム上位割合（パーセンタイル） ＋ 自チーム平均超過ボーナス
4. **④ 球際 (Duels & Intensity)**: タックル数・成功率、デュエル勝利数、ボール奪取CBP（`cbp_gain`）、ハイプレス強度（`proxy_ppda`）
5. **⑤ リレーション (Team Cohesion & Chemistry)**: 前方向パス数、敵陣パス成功率、パスCBP、アシスト連動得点、タッチ分散エントロピー、陣形コンパクトネス（`stretch_index`）
6. **⑥ 興奮度 (Excitement Index)**: 総得点、総xG、インテンシティ、逆転劇、劇的弾、ダービーマッチ勝利、数的不利での激闘

### 2.2 採点基準（エル・ゴラッソ準拠）
* **9〜10点**：すごく良い（リーグ最高峰・圧倒的）
* **7〜8点**：良い（明確な強みを発揮）
* **5〜6点**：及第点（リーグ中央値・標準的）
* **3〜4点**：ややもの足りない（課題が残る）
* **0〜2点**：次節に期待（精彩を欠く）

### 2.3 総合評価点（0〜60点）と総合ランク基準
各項目スコアの合計値（$0 \le \text{Total} \le 60$）により判定：
* **Sランク**：49〜60点（文句なしの最高評価・快勝劇）
* **A+ランク**：43〜48点（高い完成度と勝利）
* **A-ランク**：37〜42点（好内容・手応えのある戦い）
* **B+ランク**：31〜36点（標準以上の及第点）
* **B-ランク**：25〜30点（一進一退・やや課題あり）
* **Cランク**：13〜24点（劣勢・課題山積）
* **Dランク**：0〜12点（完敗・厳しい内容）

---

## 3. 各項目の詳細算出アルゴリズム

### 3.1 ① ゲーム支配 (Game Dominance)
$$\text{Score}_1 = \text{clamp}(\text{round}(5.0 + S_{\text{possession}} + S_{\text{tilt}} + S_{\text{suppress}}), 0, 10)$$

* $S_{\text{possession}} = (\text{possession\_rate} - 50.0) \times 0.08$
* $S_{\text{tilt}} = (\text{field\_tilt} - 50.0) \times 0.05$
  * $\text{field\_tilt} = \frac{\text{自30m進入}}{\text{自30m進入} + \text{相手30m進入}} \times 100$
* $S_{\text{suppress}} = (\text{自xG} - \text{相手xG}) \times 0.8$

---

### 3.2 ② 個人パワー (Individual Power)
$$\text{Score}_2 = \text{clamp}(\text{round}(5.0 + S_{\text{dribble}} + S_{\text{rating}} + S_{\text{threat}} + S_{\text{sub}}), 0, 10)$$

* $S_{\text{dribble}} = (\text{ドリブル成功数} - 6.0) \times 0.2$
* $S_{\text{rating}} = (\text{チーム内最高選手採点} - 6.0) \times 1.2$
* $S_{\text{threat}} = (\text{non\_shot\_obv} - 1.5) \times 0.3$ （アタッキングサード進入脅威度）
* $S_{\text{sub}} = \text{sub\_mva} \times 1.0$ （途中交代選手のxG+xA創出貢献、最大+1.0点）

---

### 3.3 ③ スタイル発揮 (Tactical Style Execution)
$$\text{Score}_3 = \text{clamp}(\text{round}(\text{Base}_{\text{percentile}} + \text{Bonus}_{\text{growth}}), 0, 10)$$

1. **基礎点 $\text{Base}_{\text{percentile}}$（全チーム中上位割合）**:
   * 当該チームの重視KPI群（マスター定義）について、リーグ当節全チームのパーセンタイル平均 $P \in [0.0, 1.0]$ を算出：
     $$\text{Base}_{\text{percentile}} = P \times 10.0$$
2. **自チーム成長ボーナス $\text{Bonus}_{\text{growth}}$**:
   * 対象KPI群の試合値合計が、自チームのシーズン平均（`_avg`）合計を著しく上回った場合に加算：
     * 平均比 $+25\%$ 以上：**$+1.0$点**
     * 平均比 $+15\%$ 以上：**$+0.5$点**
     * 平均比 $+15\%$ 未満：**$+0.0$点**（※減点はせず、上位を逆転しない範囲で評価）

---

### 3.4 ④ 球際 (Duels & Intensity)
$$\text{Score}_4 = \text{clamp}(\text{round}(5.0 + S_{\text{tackle}} + S_{\text{duel}} + S_{\text{gain}} + S_{\text{ppda}}), 0, 10)$$

* $S_{\text{tackle}} = (\text{tackles\_rate} - 60.0) \times 0.08$
* $S_{\text{duel}} = (\text{duels\_won} - 45.0) \times 0.08$
* $S_{\text{gain}} = (\text{cbp\_gain} - 60.0) \times 0.04$
* $S_{\text{ppda}} = (12.0 - \text{proxy\_ppda}) \times 0.15$ （低いほどハイプレス高強度）

---

### 3.5 ⑤ リレーション (Team Cohesion & Chemistry)
$$\text{Score}_5 = \text{clamp}(\text{round}(5.0 + S_{\text{forward}} + S_{\text{opp\_pass}} + S_{\text{entropy}} + S_{\text{assist}}), 0, 10)$$

* $S_{\text{forward}} = (\text{前方向パス成功数} - 120.0) \times 0.02$
* $S_{\text{opp\_pass}} = (\text{敵陣パス成功率} - 70.0) \times 0.08$
* $S_{\text{entropy}} = (\text{shannon\_entropy} - 0.85) \times 5.0$ （パス・タッチの全員関与度）
* $S_{\text{assist}}$: アシスト付き得点が2得点以上なら **$+1.0$点**、1得点なら **$+0.5$点**

---

### 3.6 ⑥ 興奮度 (Excitement Index)
$$\text{Score}_6 = \text{clamp}(\text{round}(5.0 + \sum \text{Bonuses} - \text{Penalty}), 0, 10)$$

* **ドラマ・因縁ボーナス**:
  * **伝統のダービーマッチでの勝利**: **$+1.5$点**
  * **数的不利（自チーム退場発生後）での勝利**: **$+2.0$点**
  * **数的不利（自チーム退場発生後）での同点ドロー**: **$+1.5$点**
  * **逆転勝利（ビハインドからの白星）**: **$+1.5$点**
  * **劇的ゴール（80分以降または後半ATの決勝・同点弾）**: **$+1.5$点**
  * **白熱した接戦持続（スコア差1点以内の時間が70分以上）**: **$+0.5$点**
* **激闘・打ち合いボーナス**:
  * 総得点 4点以上：**$+1.0$点**（3点：**$+0.5$点**）
  * 両チーム総xG $\ge 3.0$：**$+0.5$点**
  * 両チーム総スプリント $\ge 240$ または 総デュエル $\ge 100$：**$+0.5$点**
* **凡戦ペナルティ**:
  * 0-0のスコアレスドロー かつ 両チーム枠内シュート計4本以下：**$-2.0$点**

---

## 4. チームスタイル定義マスター仕様 (`config/team_style_archetypes.json`)

各クラブのアイデンティティと最重要KPI群の対応定義。

```json
{
  "FCT": {
    "style_name": "ハイプレス・ショートカウンター",
    "description": "前線からの連動プレスと鋭いトランジション速攻",
    "key_metrics": ["cbp_gain", "sprints", "chance_create_rate", "proxy_ppda"],
    "direction": {"cbp_gain": "high", "sprints": "high", "chance_create_rate": "high", "proxy_ppda": "low"}
  },
  "KAW": {
    "style_name": "ポジショナル・アタッキングフットボール",
    "description": "圧倒的なポゼッションと密集打開のパスワーク",
    "key_metrics": ["cbp_pass", "passes_rate", "pa_entries", "field_tilt"],
    "direction": {"cbp_pass": "high", "passes_rate": "high", "pa_entries": "high", "field_tilt": "high"}
  },
  "ZEL": {
    "style_name": "ハイインテンシティ・ロングボール＆ストロングデュエル",
    "description": "徹底した球際強度と縦に速いハイボール推進",
    "key_metrics": ["duels_won", "cbp_gain", "clears", "tackles"],
    "direction": {"duels_won": "high", "cbp_gain": "high", "clears": "high", "tackles": "high"}
  }
}
```

---

## 5. ダービーマッチ定義マスター (`config/derby_matches.json`)

伝統のライバル対決（勝者に興奮度ボーナス +1.5点付与）。

* **神奈川ダービー**: 横浜FM vs 川崎F、横浜FM vs 横浜FC、川崎F vs 湘南
* **多摩川クラシコ**: FC東京 vs 川崎F
* **東京ダービー**: FC東京 vs 東京V
* **東京クラシック**: FC東京 vs 町田、東京V vs 町田
* **千葉ダービー**: 柏 vs 千葉
* **埼玉ダービー**: 浦和 vs 大宮
* **大阪ダービー**: G大阪 vs C大阪
* **静岡ダービー**: 清水 vs 磐田
* **九州ダービー**: 福岡 vs 鳥栖、福岡 vs 長崎

---

## 6. 実装コンポーネント構成

1. **`config/team_style_archetypes.json`**: J1全20クラブの戦術スタイル・重視KPI定義
2. **`config/derby_matches.json`**: ダービーマッチ対戦カード定義
3. **`pipeline/match_report_card_calculator.py`**:
   - `MatchReportCardCalculator` クラス
   - `calculate_match_report_card(match_id, team_id) -> Dict[str, Any]`
4. **`tests/test_match_report_card_calculator.py`**: 単体テストスイート
