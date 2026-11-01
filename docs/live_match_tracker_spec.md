# ⚽ インマッチ速報・ライブ分析エンジン 機能仕様書 (Live Match Tracker Spec)

- **モジュール名**: `live-match-tracker`
- **主要スクリプト**: `scripts/live_match_forecaster.py`
- **テストスイート**: `tests/test_live_match_forecaster.py`
- **スキル定義**: `.agents/skills/live-match-tracker/SKILL.md`
- **バージョン**: 1.0.0 (2026-10-31 策定)

---

## 1. システム目的と概要

Jリーグ公式戦（明治安田J1/J2等）の開催中に、
1. **公式実況ログ・確定スタッツ**（Yahoo! スポーツナビ / データスタジアム）
2. **リアルタイム個人詳細スタッツ**（SPAIA 内部API）
3. **サポーター感情・現地空気感**（X / Yahoo! リアルタイム検索）
4. **数理勝率・交代トリガー予測**（二変量ポアソン分布・ベイズ確率モデル）

を多層的に統合し、試合の各フェーズ（キックオフ前、前半、ハーフタイム、後半、イベント発生時、試合終了直後）において、**「熱気（エキサイティング）」と「冷静・客観（ハルシネーション根絶）」を両立したライブ分析レポート**を動的に提供する。

---

## 2. アーキテクチャとデータフロー

```
[外部データソース]
  ├── Yahoo! info (基本スコア・時間・得点者)
  ├── Yahoo! text (1分実況・公式xG・途中スタッツ)
  ├── Yahoo! stats (試合終了後の確定チーム・個人走行距離)
  ├── SPAIA API  (進行中の全選手パス率・クリア・シュート)
  └── X (Yahooリアルタイム #クラブハッシュタグ)
          │
          ▼
[データ正規化レイヤー] (Data Normalizer)
  ├── ステータス正規化 (BEFORE / 1ST_HALF / HT / 2ND_HALF / END)
  ├── スコア・得点者抽出 (totalHome / totalAway / goalPlayer)
  └── ノイズ除外 (bot、定型キャンペーン、無関係トレンド)
          │
          ▼
[数理・推論レイヤー] (Analytics & Inference)
  ├── ポアソン動的勝率モデル (Poisson Bivariate Convolution)
  ├── 戦術交代レコメンド (点差・時間帯ルールベース)
  └── 🛡️ ドライ・ファクト・ガードレール (事実と推測の厳格分離)
          │
          ▼
[プレゼンテーションレイヤー]
  └── Markdownライブレポート (CLI出力 / LLM統合)
```

---

## 3. CLI インターフェース仕様

```bash
# 基本実行 (デフォルト試合ID・Markdown出力)
python scripts/live_match_forecaster.py

# 次の試合など、任意の試合IDを指定して実行
python scripts/live_match_forecaster.py --game-id <YAHOO_GAME_ID>

# クラブハッシュタグを明示指定 (例: #fctokyo, #antlers, #frontale)
python scripts/live_match_forecaster.py --game-id <YAHOO_GAME_ID> --hashtag "#fctokyo"

# 外部ツール・Flutterアプリ連携用 JSON出力
python scripts/live_match_forecaster.py --game-id <YAHOO_GAME_ID> --json

# ドライ・ファクト（事実のみ・形容詞完全排除）モード
python scripts/live_match_forecaster.py --dry-fact
```

---

## 4. 厳格運用ポリシー（ハルシネーション防止ガイドライン）

1. **事実（Fact）の提示ルール**:
   - 一次データ（Yahooテキスト、SPAIA、公式X）に記載されている単語・数値のみを事実として扱う。
   - アシストやシュート部位は、公式確定発表があるまで「未確定（公式発表待ち）」と明記する。
2. **推測（Inference）の境界線**:
   - パスの軌道、プレスの状況、心理描写など、テキストから観測できないディテールは断定しない。
   - 推測を述べる場合は必ず接頭辞 `【※状況推測】` を付与する。
3. **情緒的修飾語の排除**:
   - `神がかった`、`ズバッと通した`、`抜群の落ち着き`、`冷静に流し込み` などの未観測な形容詞は禁止する。
4. **過剰迎合の禁止**:
   - ユーザーの熱い発言に同調して未確認の状況を創作しない。

---

## 5. 次節に向けた拡張ロードマップ

1. **試合ID自動ディスカバリー**: 日付から本日の対象試合IDを自動特定する機能。
2. **ビハインド効果のポアソン動的補正**: 追う側の攻撃シフトを反映するλの上方修正。
3. **試合終了後のLayer 1/2 DB自動同期**: 走行距離・CBP・xGの自動永続化。

