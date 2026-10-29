import argparse
import os
import sys

# プロジェクトルートをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from jleague_player_scraper import J1_CLUBS_2026, run_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="J.LEAGUE.jp 選手名鑑スクレイピングスクリプト",
    )
    parser.add_argument(
        "--team",
        type=str,
        default=None,
        help="対象チームID（例: FCT, KAS, URA 等）。指定しない場合は全チームが対象。",
    )
    parser.add_argument(
        "--max-players",
        type=int,
        default=None,
        help="1チームあたりの最大取得選手数（テスト用）。省略時は全選手。",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/players",
        help="出力先ディレクトリ（デフォルト: data/players）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Headlessモードでブラウザを起動（デフォルト: True）",
    )

    args = parser.parse_args()

    if args.team:
        target_clubs = [c for c in J1_CLUBS_2026 if c["team_id"].upper() == args.team.upper()]
        if not target_clubs:
            print(f"[エラー] 指定されたチームID '{args.team}' は見つかりません。")
            print(f"利用可能なチームID: {', '.join([c['team_id'] for c in J1_CLUBS_2026])}")
            sys.exit(1)
    else:
        target_clubs = J1_CLUBS_2026

    run_pipeline(
        teams=target_clubs,
        max_players_per_team=args.max_players,
        output_dir=args.output_dir,
        headless=args.headless,
    )


if __name__ == "__main__":
    main()
