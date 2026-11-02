# 運用サイクル設計 (Operation Cycle)

試合日 (D) を基準にした、データ更新・機能・出力のサイクル定義。
平日開催を含む全J1クラブが対象。自動化は GitHub Actions、公開は `git push` による Streamlit Cloud 自動反映。

## 1. 確定方針

| 項目 | 決定内容 |
|---|---|
| 対象 | 全クラブ（毎節 約10試合）。FC東京等の注目試合は共同作成で詳細化 |
| 開催パターン | 土日・平日（水曜ナイター等）を含む。**キックオフ時刻からの相対時間**でスケジュール算出 |
| 自動化基盤 | GitHub Actions（Linux ランナー）。private リポジトリ前提 |
| 公開 | データ更新後は自動で `git push`（Streamlit Cloud が再デプロイ） |
| 試合中の速報 | Actions は不向き（cron 最小5分・遅延あり）。**手動／対話中心** |
| スクレイピング失敗時 | Actions は失敗通知のみ。**手動実行へフォールバック** |
| DB・ChromaDB | 当面 repo にコミット。肥大したら GitHub Releases へ移行 |
| `data/raw` | `.gitignore` 対象とし、公開リポジトリには含めない |

## 2. タイミング表 (KO = キックオフ)

| タイミング | 実行方法 | 更新・処理 | 出力 / できること |
|---|---|---|---|
| 毎日 06:00 JST | 自動 | 日程同期 (`schedule_crawler.py`)、各試合のフェーズ算出 | 日程データ更新 |
| KO-72h 〜 KO-48h | 自動 | 前節確定データ反映、怪我・出場停止・移籍の更新 | 暫定プレビュー（`_auto`） |
| KO-24h | 自動 | 公式予告、チームニュース、記者会見の取得 | プレビュー草案、NotebookLM 用エクスポート |
| KO-1h | 手動（対話） | 公式スタメン・ベンチ取得 | 予想と実際の差分メモ |
| 試合中 | 手動（対話） | `live_match_forecaster.py` を随時実行 | 動的勝率、交代予測、HT 総括 |
| **Stage 1**: KO+約3h | 自動 | `update_matchweek.py --stage 1` | 速報、基本スタッツ、コメント、モバイルビューア更新 |
| **Stage 2**: KO+36〜48h | 自動 | `update_matchweek.py --stage 2`、深層指標の再計算 | 確定トラッキング、Football LAB 指標、戦術総括、Sheets エクスポート |
| 節完了後 | 自動 | 節単位でまとめて DB・ChromaDB をコミット | クラウド版へ反映 |

### Stage の定義
- **Stage 1**: 試合直後に取得できる速報、基本スタッツ、監督・選手コメントを取り込む。
- **Stage 2**: 公開が遅れる確定トラッキング（走行距離・スプリント）と Football LAB 戦術指標で同一試合を更新（`source_updated_stage=2`）。

## 3. 共同作成フロー（プレビュー・速報・総括）

自動生成の下書きがあってもなくても、対話で共同作成できる。

1. 決定的に抽出した事実（`preview_fact_extractor`）を提示する。
2. 予測の分岐点ごとに **2〜3案の選択肢** を、根拠データと【事実】/【推測】のタグ付きで提示する。
3. ユーザーの選択・意見を反映して確定する。
4. `exports/` に保存する。自動版 `_auto` は上書きせず、確定版は `_curated` として並置する。

事実と推測の分離、情緒的修飾語の排除など、`live-match-tracker` スキルの運用ポリシーを踏襲する。

## 4. GitHub Actions 設計方針

- **cron は UTC 指定**（JST−9h）。日程同期は `0 21 * * *`（= 毎日 06:00 JST）。
- 日程同期ジョブが「次に実行すべきフェーズ」を判定し、該当試合だけ処理する（ポーリング型）。
  - cron は遅延・欠落があるため、「予定時刻を過ぎていて未処理」なら実行する冪等な設計にする。
- `concurrency` グループで更新ジョブを直列化し、DB 競合・push 競合を防ぐ。
- Secrets: `GEMINI_API_KEY` ほか。`.env` はコミットしない。
- Playwright はブラウザをキャッシュ、または必要ジョブに限定する。
- 自動コミットが毎節入るため、60日無効化は発生しない。
- 無料枠 (private: 月2,000分) 内に収めるため、Linux ランナーのみ使用、未処理試合がない回は即終了。

## 5. 想定リスクと対策

| リスク | 対策 |
|---|---|
| データセンター IP がスクレイピング先にブロックされる | 失敗通知のみ。手動実行へフォールバック。リトライ間隔・UA を設定 |
| repo 肥大（`.git` 現状 180 MB） | `data/raw` を ignore。DB は節単位でまとめてコミット。必要時 Releases へ移行 |
| cron 遅延・欠落 | 冪等なポーリング型判定 |
| 手動実行と自動実行の競合 | `concurrency` ＋ 更新前の pull |

## 6. データサイズ目安

- 1試合: 約50 KB 未満（Markdown 14 KB + Football LAB 18 KB + 構造化 JSON）
- 1節（10試合）: Markdown 等で約0.5 MB、生データ込みで約3〜4 MB
- 現状合計: `data/raw` 40 MB、ChromaDB 30 MB、`football.db` 26 MB、`exports` 8 MB、その他 約8 MB
- 38節完了時の全体見込み: 約200〜250 MB

## 7. 実装ステップ

1. 本ドキュメント（運用定義）: 完了
2. 日程→フェーズ算出スクリプトとテスト: 完了 (`pipeline/phase_calculator.py`, `scripts/plan_phases.py`)
3. `.github/workflows/`（日程同期・Stage 1・Stage 2）と `.gitignore` 整理: 完了
4. 共同作成用スキル（プレビュー／速報／総括）: 完了 (`.agents/skills/match-curator/SKILL.md`, `pipeline/review_curation_service.py`, `scripts/curate_match_review.py`)
5. サイト運用・更新・デプロイ統合スキル: 完了 (`.agents/skills/site-operations/SKILL.md`, `docs/SITE_OPERATIONS_SPECIFICATION.md`)

---

## 8. サイト運用4大独立モード (`site-operations`)

手動・対話運用における変更の安全性と局所性を担保するため、以下の4モードを定義しています。
詳細は [SITE_OPERATIONS_SPECIFICATION.md](file:///d:/workspace/flutter/football_rag/docs/SITE_OPERATIONS_SPECIFICATION.md) を参照。

- **Mode 1: 試合単体アップデート (`match-update`)**: 指定試合の実名・スタッツ・Layer 2仮説レビュー・ダイレクト外部リンクの局所更新。
- **Mode 2: チーム単体アップデート (`team-update`)**: 指定クラブの名鑑Excel・怪我/警告トラッカー・戦術プロファイルの局所更新。
- **Mode 3: リーグ全体スタッツ更新 (`league-update`)**: 全カードの戦術JSON一括再構築と全節戦術カルテの同期。
- **Mode 4: デプロイ＆本番同期 (`site-deploy`)**: フルテスト365+件パス ➔ Rebase統合 ➔ コミット＆プッシュ ➔ Streamlit Cloud自動反映。


