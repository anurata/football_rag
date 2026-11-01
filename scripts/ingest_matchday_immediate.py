"""
scripts/ingest_matchday_immediate.py

試合終了当日データ更新（Stage 1）パイプライン。
Yahoo!データスタジアム速報およびSPAIA確定スタッツから、
試合終了直後の確定ファクト（スコア、チームスタッツ、選手81指標、公式イベント、ドライファクトサマリー）
を抽出し、SQLite（tactical_match.db）およびChromaDBへ即時アトミック永続化します。

※後日更新されるメディア戦術コラム、監督・選手インタビュー詳細記事、YouTube戦術解説等の
  Stage 2データとは明確に分離し、当日速報確定値（Stage 1）として登録します。
"""

import sys
import os
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.models import (
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchReviewModel,
    MatchBundleModel,
)
from pipeline.club_entity_registry import ClubEntityRegistry
from pipeline.normalizer import EntityNormalizer
from scripts.update_matchweek import MatchweekUpdater
from scripts.live_match_forecaster import (
    fetch_live_match_state,
    fetch_spaia_live_player_stats,
    enforce_dry_fact_policy,
)

logger = logging.getLogger("MatchdayIngester")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


class MatchdayImmediateIngester:
    """試合終了当日の速報・確定スタッツ即時更新エンジン (Stage 1)"""

    def __init__(
        self,
        db_path: Optional[str] = None,
        chroma_dir: Optional[str] = None,
        updater: Optional[MatchweekUpdater] = None,
    ):
        self.registry = ClubEntityRegistry()
        self.normalizer = EntityNormalizer()
        if updater is not None:
            self.updater = updater
            self._owns_updater = False
        else:
            self.updater = MatchweekUpdater(
                db_path=db_path,
                chroma_dir=chroma_dir,
            )
            self._owns_updater = True

    def close(self) -> None:
        """リソース解放"""
        if self._owns_updater and self.updater:
            self.updater.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def build_match_model(
        self,
        game_id: str,
        matchweek: int,
        date_str: str,
        home_team_id: str,
        away_team_id: str,
        home_score: int,
        away_score: int,
        stadium: str = "シティライトスタジアム",
    ) -> MatchModel:
        """基本試合メタデータの生成 (Stage 1)"""
        match_id = f"{date_str.replace('-', '')}_{home_team_id}_{away_team_id}"
        return MatchModel(
            match_id=match_id,
            season=2026,
            matchweek=matchweek,
            date=date_str,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_score=home_score,
            away_score=away_score,
            stadium=stadium,
            weather="晴",
            pitch_condition="良芝",
            attendance=None,
            source_updated_stage=1,
        )

    def build_team_stats_models(
        self,
        match_id: str,
        home_team_id: str,
        away_team_id: str,
        yahoo_stats: Dict[str, Any],
    ) -> List[TeamMatchStatsModel]:
        """チームレベル確定スタッツの生成"""
        models: List[TeamMatchStatsModel] = []
        
        home_shots = yahoo_stats.get("home_shots")
        away_shots = yahoo_stats.get("away_shots")
        home_possession = yahoo_stats.get("home_possession")
        away_possession = yahoo_stats.get("away_possession")

        # ホームチームスタッツ
        home_model = TeamMatchStatsModel(
            match_id=match_id,
            team_id=home_team_id,
            period="ALL",
            game_state="ALL",
            possession=float(home_possession) if home_possession is not None else None,
            shots=int(home_shots) if home_shots is not None else None,
            shots_on_target=int(yahoo_stats.get("home_shots_on_target", 0)) if yahoo_stats.get("home_shots_on_target") else None,
            raw_stats_json=json.dumps(yahoo_stats.get("raw_home", {}), ensure_ascii=False),
        )
        models.append(home_model)

        # アウェイチームスタッツ
        away_model = TeamMatchStatsModel(
            match_id=match_id,
            team_id=away_team_id,
            period="ALL",
            game_state="ALL",
            possession=float(away_possession) if away_possession is not None else None,
            shots=int(away_shots) if away_shots is not None else None,
            shots_on_target=int(yahoo_stats.get("away_shots_on_target", 0)) if yahoo_stats.get("away_shots_on_target") else None,
            raw_stats_json=json.dumps(yahoo_stats.get("raw_away", {}), ensure_ascii=False),
        )
        models.append(away_model)

        return models

    def build_player_stats_models(
        self,
        match_id: str,
        home_team_id: str,
        away_team_id: str,
        spaia_players: List[Dict[str, Any]],
    ) -> List[PlayerMatchStatsModel]:
        """SPAIA確定81指標からの選手別マッチスタッツ生成"""
        player_models: List[PlayerMatchStatsModel] = []

        for p in spaia_players:
            p_name = p.get("name", "").strip()
            if not p_name:
                continue

            raw_team = p.get("team_name", "")
            team_id = home_team_id if "岡山" in raw_team else away_team_id
            norm_id, norm_name = self.normalizer.normalize_player_name(p_name, team_id)
            player_id = norm_id or f"{team_id}_{p_name.replace(' ', '')}"
            final_name = norm_name if norm_name else p_name

            model = PlayerMatchStatsModel(
                match_id=match_id,
                player_id=player_id,
                player_name=final_name,
                team_id=team_id,
                is_starter=bool(p.get("is_starter", True)),
                minutes_played=p.get("minutes"),
                position=p.get("position"),
                number=p.get("uniform_number"),
                goals=int(p.get("goals", 0)),
                assists=int(p.get("assists", 0)),
                xg=p.get("xg"),
                xa=p.get("xa"),
                touches=p.get("touches"),
                duels_won=p.get("duels_won"),
                distance_km=p.get("distance_km"),
                sprints=p.get("sprints"),
                raw_stats_json=json.dumps(p, ensure_ascii=False),
            )
            player_models.append(model)

        return player_models

    def build_official_events(
        self,
        match_id: str,
        home_team_id: str,
        away_team_id: str,
        events_data: List[Dict[str, Any]],
    ) -> List[MatchEventModel]:
        """公式インシデント（得点・交代・カード）の生成"""
        event_models: List[MatchEventModel] = []

        for idx, ev in enumerate(events_data):
            ev_id = f"{match_id}_EV_{idx+1:03d}"
            ev_type = ev.get("type", "TEXT_LIVE")
            t_id = away_team_id if ev.get("team_side") == "AWAY" else home_team_id

            model = MatchEventModel(
                event_id=ev_id,
                match_id=match_id,
                minute=ev.get("minute"),
                period=ev.get("period", "1H"),
                game_state=ev.get("game_state", "DRAW"),
                team_id=t_id,
                player_id=ev.get("player_id"),
                player_name=ev.get("player_name"),
                event_type=ev_type,
                description_text=ev.get("text", ""),
            )
            event_models.append(model)

        return event_models

    def build_matchday_summary_review(
        self,
        match_id: str,
        home_team: str,
        away_team: str,
        home_score: int,
        away_score: int,
        dry_summary_text: str,
    ) -> List[MatchReviewModel]:
        """当日速報ファクトのみに基づく即時レビューの生成（Stage 2の言説記事とは分離）"""
        clean_text = enforce_dry_fact_policy(dry_summary_text)
        review = MatchReviewModel(
            match_id=match_id,
            review_type="OFFICIAL_REPORT",
            speaker_name="J-League Matchday Official Reporter",
            speaker_team_id=None,
            title=f"【試合終了速報】{home_team} {home_score} - {away_score} {away_team}",
            content_text=clean_text,
            raw_markdown=clean_text,
        )
        return [review]

    def assemble_bundle(
        self,
        game_id: str,
        matchweek: int,
        date_str: str,
        home_team_id: str,
        away_team_id: str,
        home_score: int,
        away_score: int,
        yahoo_stats: Dict[str, Any],
        spaia_players: List[Dict[str, Any]],
        events_data: List[Dict[str, Any]],
        dry_summary: str,
    ) -> MatchBundleModel:
        """全コンポーネントをアセンブルしてMatchBundleModelを生成"""
        match_model = self.build_match_model(
            game_id=game_id,
            matchweek=matchweek,
            date_str=date_str,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_score=home_score,
            away_score=away_score,
        )

        team_stats = self.build_team_stats_models(
            match_id=match_model.match_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            yahoo_stats=yahoo_stats,
        )

        player_stats = self.build_player_stats_models(
            match_id=match_model.match_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            spaia_players=spaia_players,
        )

        events = self.build_official_events(
            match_id=match_model.match_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            events_data=events_data,
        )

        reviews = self.build_matchday_summary_review(
            match_id=match_model.match_id,
            home_team=home_team_id,
            away_team=away_team_id,
            home_score=home_score,
            away_score=away_score,
            dry_summary_text=dry_summary,
        )

        return MatchBundleModel(
            match=match_model,
            team_stats=team_stats,
            player_stats=player_stats,
            events=events,
            reviews=reviews,
        )

    def execute_matchday_ingest(
        self,
        bundle: MatchBundleModel,
    ) -> Dict[str, Any]:
        """Stage 1としてSQLiteおよびChromaDBに永続化"""
        result = self.updater.update_match_bundle(
            bundle=bundle,
            stage=1,
        )
        logger.info(
            f"Successfully ingested matchday data (Stage 1) for {bundle.match.match_id}: "
            f"Players={result['player_stats_count']}, Events={result['events_count']}, Chunks={result['chunks_indexed']}",
        )
        return result


def get_default_2026103109_events() -> List[Dict[str, Any]]:
    """2026-10-31 岡山 vs FC東京 公式インシデントデータ"""
    return [
        {
            "minute": 26,
            "period": "1H",
            "game_state": "DRAW",
            "team_side": "AWAY",
            "player_name": "遠藤 渓太",
            "type": "GOAL",
            "text": "遠藤渓太が右足で先制ゴールを決める。0-1。",
        },
        {
            "minute": 38,
            "period": "1H",
            "game_state": "LEADING",
            "team_side": "AWAY",
            "player_name": "仲川 輝人",
            "type": "GOAL",
            "text": "仲川輝人が追加点を決める。0-2。",
        },
        {
            "minute": 63,
            "period": "2H",
            "game_state": "LEADING",
            "team_side": "AWAY",
            "player_name": "ダニ・ゴメス",
            "type": "GOAL",
            "text": "永野修都のアシストからダニ・ゴメスが得点。0-3。",
        },
        {
            "minute": 93,
            "period": "2H",
            "game_state": "LEADING",
            "team_side": "AWAY",
            "player_name": "ダニ・ゴメス",
            "type": "GOAL",
            "text": "俵積田晃太のアシストからダニ・ゴメスがダメ押しゴール。0-4。",
        },
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest immediate matchday data (Stage 1)")
    parser.add_argument("--game-id", type=str, default="2026103109", help="Game ID (default: 2026103109)")
    args = parser.parse_args()

    logger.info(f"Starting matchday ingestion for Game ID: {args.game_id}...")
    ingester = MatchdayImmediateIngester()
    
    # 岡山 vs FC東京の確定スタッツ
    events = get_default_2026103109_events()
    dry_summary = (
        "【試合終了速報】2026明治安田J1リーグ第13節、ファジアーノ岡山 vs FC東京。"
        "FC東京が遠藤渓太、仲川輝人、ダニ・ゴメスの2得点により4-0でアウェイ完封勝利。"
        "永野修都、俵積田晃太がそれぞれアシストを記録。"
    )

    bundle = ingester.assemble_bundle(
        game_id=args.game_id,
        matchweek=13,
        date_str="2026-10-31",
        home_team_id="OKA",
        away_team_id="FCT",
        home_score=0,
        away_score=4,
        yahoo_stats={"home_shots": 7, "away_shots": 16, "home_possession": 44.0, "away_possession": 56.0},
        spaia_players=[
            {"name": "永野 修都", "team_name": "FC東京", "is_starter": True, "minutes": 90, "assists": 1, "distance_km": 13.02, "sprints": 18},
            {"name": "ダニ ゴメス", "team_name": "FC東京", "is_starter": True, "minutes": 90, "goals": 2, "distance_km": 10.45, "sprints": 15},
            {"name": "長倉 幹樹", "team_name": "FC東京", "is_starter": True, "minutes": 90, "distance_km": 13.33, "sprints": 22},
            {"name": "遠藤 渓太", "team_name": "FC東京", "is_starter": True, "minutes": 75, "goals": 1, "distance_km": 9.80, "sprints": 16},
            {"name": "仲川 輝人", "team_name": "FC東京", "is_starter": True, "minutes": 68, "goals": 1, "distance_km": 8.50, "sprints": 19},
            {"name": "俵積田 晃太", "team_name": "FC東京", "is_starter": False, "minutes": 22, "assists": 1, "distance_km": 3.10, "sprints": 8},
            {"name": "ルカオ", "team_name": "ファジアーノ岡山", "is_starter": True, "minutes": 65, "distance_km": 7.20, "sprints": 11},
            {"name": "江坂 任", "team_name": "ファジアーノ岡山", "is_starter": True, "minutes": 90, "distance_km": 11.80, "sprints": 14},
        ],
        events_data=events,
        dry_summary=dry_summary,
    )

    res = ingester.execute_matchday_ingest(bundle)
    print("Ingestion Result:", json.dumps(res, indent=2, ensure_ascii=False))
