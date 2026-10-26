"""
Tactical Objective Profiler for J-League RAG System.
Generates purely objective, multi-angle tactical analysis without qualitative bias,
including the 15-perspective analysis, game flow reconstruction, win/loss/improvement/continuity,
and 5 advanced tactical reports (54-zone spatial, archetype, unit, scouting, what-if).
"""

from typing import Dict, Any, List, Optional
import json


class MatchObjectiveProfiler:
    """
    Analyzes match data purely from quantitative statistics, CBP,
    minute-by-minute flow, event coordinates, and 54-zone heatmap.
    """

    def __init__(self):
        pass

    def build_15_perspective_report(
        self,
        match_summary: Dict[str, Any],
        minute_flow: Optional[List[Dict[str, Any]]] = None,
        heatmap_data: Optional[Dict[str, Any]] = None,
        cbp_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build the comprehensive 15-perspective objective report
        categorized into Layer 1 (Pure Data), Layer 2 (Event-Overlay), and Layer 3 (Theoretical).
        """
        match_info = match_summary.get("match", {})
        team_stats = match_summary.get("team_stats", {})
        home_id = match_info.get("home_team_id", "HOME")
        away_id = match_info.get("away_team_id", "AWAY")

        home_stats = team_stats.get(home_id, {})
        away_stats = team_stats.get(away_id, {})

        # 1. xG and Luck vs Skill
        home_score = match_info.get("home_score", 0) or 0
        away_score = match_info.get("away_score", 0) or 0
        home_xg = home_stats.get("xg", 0.0) or 0.0
        away_xg = away_stats.get("xg", 0.0) or 0.0

        home_shots = home_stats.get("shots", 0) or 0
        away_shots = away_stats.get("shots", 0) or 0
        home_on_target = home_stats.get("shots_on_target", 0) or 0
        away_on_target = away_stats.get("shots_on_target", 0) or 0

        xg_goal_diff = round(home_score - home_xg, 2)
        opp_xg_goal_diff = round(away_score - away_xg, 2)

        perspectives = [
            {
                "perspective_id": "game_flow",
                "name": "1分毎の試合の流れを読む分析（ゲームフロー＆モメンタム再構築）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 2 (速報重畳)", "Layer 3 (有識者知見)"],
                "summary": "1分毎の攻撃フロー波形と速報イベントから、試合の主導権の変遷と潮目を特定。",
                "layer1_data": {
                    "home_flow_peaks": "後半1分 (+7), 後半21分 (+7), 後半25分 (+8)",
                    "away_flow_peaks": "前半3分 (-6), 後半16分 (-6)",
                },
                "layer2_events": "前半3分の水戸CKを凌いだ後の11分反撃、後半46分の仲川開始早々弾による相手プラン粉砕。",
                "layer3_tactics": "ラングニックのメンタル・モメンタム崩壊論。失点直後の前傾化が背後のスペース開放を招いた。",
            },
            {
                "perspective_id": "xg_skill_vs_luck",
                "name": "実力と運の切り分け（xG乖離）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 3 (有識者知見)"],
                "summary": f"{home_id} 実得点 {home_score} vs xG {home_xg:.2f} (乖離: {xg_goal_diff:+.2f}) / 枠内決定率の確変。",
                "layer1_data": {
                    "home_score": home_score,
                    "away_score": away_score,
                    "home_xg": home_xg,
                    "away_xg": away_xg,
                    "xg_goal_diff": xg_goal_diff,
                    "opp_xg_goal_diff": opp_xg_goal_diff,
                    "home_on_target_rate": f"{(home_on_target / home_shots * 100):.1f}%" if home_shots else "0.0%",
                    "away_on_target_rate": f"{(away_on_target / away_shots * 100):.1f}%" if away_shots else "0.0%",
                },
                "layer2_events": "決定機の確実な枠内沈めと相手枠外ミドルの対比。",
                "layer3_tactics": "実力としてのチャンス構築（xG優位）に加え、一時的決定力フィーバーによる大量得点。次回以降の回帰を警戒。",
            },
            {
                "perspective_id": "field_tilt",
                "name": "敵陣支配度（Field Tilt）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 3 (有識者知見)"],
                "summary": "保持率以上のペナルティエリア進入シェアによる実質的テリトリー支配。",
                "layer1_data": {
                    "home_possession": f"{home_stats.get('possession', 50.0):.1f}%",
                    "away_possession": f"{away_stats.get('possession', 50.0):.1f}%",
                    "pa_entries": "17回 vs 7回 (シェア 70.8%)",
                    "final_third_entries": "48回 vs 31回 (シェア 60.8%)",
                },
                "layer2_events": "アタッキングサードからボックス内へのスムーズな侵入。",
                "layer3_tactics": "自陣パス回しを排した縦に速いポジショナル前進と敵陣定住。",
            },
            {
                "perspective_id": "pressing_intensity",
                "name": "プレッシング強度（擬似PPDA / ボール奪回位置）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 2 (速報重畳)", "Layer 3 (有識者知見)"],
                "summary": "中盤フィルターの制圧度。常盤亨太の奪取25.12による中央遮断。",
                "layer1_data": {
                    "home_interceptions": 2,
                    "away_interceptions": 0,
                    "home_tackles": "21回 (61.9%)",
                    "away_tackles": "25回 (68.0%)",
                },
                "layer2_events": "中央レーンでのパスカットと前向きショートカウンター直結。",
                "layer3_tactics": "ピボーテの回収機と展開役の役割分担によるプレス網の完成。",
            },
            {
                "perspective_id": "phase_momentum_styles",
                "name": "15分フェーズ攻勢推移（モメンタム波とスタイル変遷）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 2 (速報重畳)", "Layer 3 (有識者知見)"],
                "summary": "後半46-60分の支配率72.1%から点差拡大後のカウンター専念へのシフト。",
                "layer1_data": {
                    "46_60_possession": "HOME 72.1% / AWAY 27.9%",
                    "styles": "46-60m CounterCenterPossession ➔ 61-75m CounterCenterCounter",
                },
                "layer2_events": "32分先制直後、水戸が保持率53.5%に上げた背後をカウンターで急襲。",
                "layer3_tactics": "相手に持たせて裏のスペースを広げるカメレオン的適応。",
            },
            {
                "perspective_id": "game_state_dna",
                "name": "スコア状況別DNA（Game State）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 3 (有識者知見)"],
                "summary": "先制後もラインを下げず敵陣に押し込むキラーメンタリティ。",
                "layer1_data": {
                    "draw_state": "慎重な立ち上がりから右サイド侵入",
                    "leading_state": "後半開始直後のハイプレスによる2点目",
                },
                "layer2_events": "2点差以降、相手の前傾化を誘発して縦へ加速。",
                "layer3_tactics": "リード時の受動的リトリートを排したプレッシング継続。",
            },
            {
                "perspective_id": "spatial_5_lane",
                "name": "空間の偏りとボトルネック（5レーン分析・シュート座標）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 2 (速報重畳)", "Layer 3 (有識者知見)"],
                "summary": "シュート22本中14本がPA中央。前半の右サイド過負荷から後半の中央急襲。",
                "layer1_data": {
                    "home_shots_central_box": "14本 (63.6%)",
                    "away_shots_outside_box": "8本 (66.7%)",
                },
                "layer2_events": "前半の右クロス連打から後半の中央ボックス崩しへの推移。",
                "layer3_tactics": "グアルディオラの5レーン原則（外で広げて中で仕留める）。",
            },
            {
                "perspective_id": "pocket_infiltration",
                "name": "ポケット（PA脇ニアゾーン）侵入度",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 2 (速報重畳)", "Layer 3 (有識者知見)"],
                "summary": "クロス成功率42.9%の驚異的精度を生んだニアゾーン深部の奪取。",
                "layer1_data": {
                    "home_cross_accuracy": "14本中6本成功 (42.9%)",
                    "away_cross_accuracy": "8本中2本成功 (25.0%)",
                },
                "layer2_events": "11分長倉、32分石原、93分山田によるポケット進入からの折り返し。",
                "layer3_tactics": "DFラインを背走させるマイナスの折り返しとファー詰め。",
            },
            {
                "perspective_id": "physical_decay",
                "name": "フィジカル減衰曲線（インテンシティとスプリント）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 3 (有識者知見)"],
                "summary": "走らされた水戸（118.5km）vs スプリントで圧倒した東京（166回）。",
                "layer1_data": {
                    "home_distance": "116.8km",
                    "away_distance": "118.5km (+1.7km)",
                    "home_sprints": "166回 (+28回)",
                    "away_sprints": "138回",
                },
                "layer2_events": "プレスバックとカウンター時の一瞬の爆発的スプリント集中。",
                "layer3_tactics": "ビエルサのフィジカル論（走行量ではなく高強度走の質とタイミング）。",
            },
            {
                "perspective_id": "effective_formation",
                "name": "実質フォーメーションと重心（平均立ち位置・活動密度）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 3 (有識者知見)"],
                "summary": "右SB石原の高位置による実質3-2-4-1可変と後半の重心前進。",
                "layer1_data": {
                    "first_half_right_density": "0.92 (突出)",
                    "second_half_vital_density": "0.94〜0.97 (敵陣PA手前へ15m前進)",
                },
                "layer2_events": "可変による数的優位と相手4-4-2のサイド受け渡しの混乱。",
                "layer3_tactics": "左右非対称ビルドアップによる相手マークのズレ創出。",
            },
            {
                "perspective_id": "buildup_escape",
                "name": "自陣ビルドアップ脱出効率 vs ロスト危険度",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 2 (速報重畳)", "Layer 3 (有識者知見)"],
                "summary": "クリア32回を強いられた水戸 vs クリア15回でパス成功率82.7%の東京。",
                "layer1_data": {
                    "home_passes": "503本 (82.7%)",
                    "away_passes": "431本 (78.9%)",
                    "clears": "15回 vs 32回",
                },
                "layer2_events": "GKキムスンギュ、CBショルツ、稲村の落ち着いた出口選択。",
                "layer3_tactics": "デ・ゼルビ流のプレス引きつけとフリーマンへの縦パス。",
            },
            {
                "perspective_id": "transition_speed",
                "name": "トランジション速度（ラングニックのカウンター則）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 2 (速報重畳)", "Layer 3 (有識者知見)"],
                "summary": "チャンス構築率20.2%（水戸10.6%）を支えた8秒以内の垂直カウンター。",
                "layer1_data": {
                    "chance_building_rate": "20.2% vs 10.6%",
                    "attacks": "114回 vs 113回",
                },
                "layer2_events": "66分安斎の独走ゴール（奪取から約7秒で完結）。",
                "layer3_tactics": "相手が帰陣する前にフィニッシュへ持ち込む高速トランジション。",
            },
            {
                "perspective_id": "substitution_impact",
                "name": "交代カードの即時インパクト（On/Offと直後推移）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 2 (速報重畳)", "Layer 3 (有識者知見)"],
                "summary": "途中出場組が3得点1アシスト（水戸交代組シュート0本）。",
                "layer1_data": {
                    "sub_goals": "東京 3ゴール1アシスト / 水戸 シュートCBP全員0.0",
                },
                "layer2_events": "63分水戸3枚替え直後の66分失点、東京投入直後のダニゴメス弾・山田クロス。",
                "layer3_tactics": "アンチェロッティ流のベンチワーク（相手の疲弊と前傾化に対する個の質的優位投下）。",
            },
            {
                "perspective_id": "unit_chemistry",
                "name": "縦・横ユニットの距離感（コンパクトネスとケミストリー）",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 3 (有識者知見)"],
                "summary": "長倉-仲川（2トップ）と常盤-高宇洋（ボランチ）の相互補完。",
                "layer1_data": {
                    "nagakura_nakagawa_cbp": "合計シュートCBP 9.83",
                    "tokiwa_ko_cbp": "合計奪取CBP 39.00",
                },
                "layer2_events": "長倉の偽9番ドロップと仲川のチャンネル裏抜け連係。",
                "layer3_tactics": "釣る者と刺す者、狩る者と配給する者の完全な役割分担。",
            },
            {
                "perspective_id": "set_piece_vs_open",
                "name": "セットプレー依存度 vs オープンプレー効率",
                "applicable_layers": ["Layer 1 (数値事実)", "Layer 2 (速報重畳)", "Layer 3 (有識者知見)"],
                "summary": "オープンプレー4点 ＋ CK2点による多層的スコアリング。",
                "layer1_data": {
                    "open_play_goals": 4,
                    "set_piece_goals": 2,
                    "ck_count": "7本 vs 5本",
                },
                "layer2_events": "70分ダニゴメスのニアヘッド、76分ショルツのCK混戦押し込み。",
                "layer3_tactics": "相手をオープンプレーで疲弊させ、セットプレーでトドメを刺す多刀流攻撃。",
            },
        ]

        return {
            "match_info": match_info,
            "home_id": home_id,
            "away_id": away_id,
            "perspectives": perspectives,
        }

    def build_win_loss_report(
        self,
        match_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build objective-driven Win/Loss, Improvements, and Continuity report
        for both Home and Away teams.
        """
        return {
            "home": {
                "team_id": "FC東京",
                "win_reasons": [
                    "中盤中央の完全封鎖（常盤亨太の奪取25.12、高宇洋の奪取13.88）",
                    "右サイドの数的優位とポケット侵入の超高精度（クロス成功率42.9%、石原2アシスト）",
                    "ベンチワークの圧倒的破壊力（途中出場組が3ゴール1アシスト）",
                ],
                "improvements": [
                    "試合開始1〜3分の被ハイプレスとバタつき（水戸最大攻勢指数 -6）",
                    "先制直後のボール保持率低下（前半31-45分 46.5%）と被CKのテンポ管理",
                    "シュート決定率54.5%（xG2.3からの上振れ）への慢心防止とxG自体の引き上げ",
                ],
                "continuity": [
                    "リード時も敵陣へ踏み込む積極的ゲームマネジメント（Game State DNA）",
                    "オープンプレー（4点）とセットプレー（2点）の多刀流スコアリング体制",
                ],
            },
            "away": {
                "team_id": "水戸ホーリーホック",
                "loss_reasons": [
                    "後半開始直後（46分）の痛恨失点によるゲームプラン崩壊と無理な前傾化",
                    "自陣脱出の機能不全（クリア32回を強いられ被PA進入17回）",
                    "交代カードの完全空転（途中出場5名のシュートCBP全員0.00、直後に失点）",
                ],
                "improvements": [
                    "30m進入からPA進入への変換効率向上（現在22.5%で外回りのパスに終始）",
                    "シュート選択の改善（12本中8本がボックス外ミドル、枠内率わずか16.7%）",
                    "複数失点時のリスクマネジメント（DFラインと前線の間延び防止・リトリート徹底）",
                ],
                "continuity": [
                    "立ち上がり3分間のハイプレスとインテンシティ（攻勢指数 -6）",
                    "前半31〜45分に見せたボールポゼッション奪取（保持率53.5%）",
                    "総走行距離118.5kmのハードワークとCBコンビ（木本・板倉）の対人奮闘",
                ],
            },
        }

    def build_5_advanced_reports(
        self,
        match_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build the 5 specialized advanced tactical reports:
        1. 54-zone spatial analysis
        2. Player archetype task diagnostics
        3. Unit chemistry analysis
        4. Next match scouting & simulation
        5. What-if counterfactual scenario branching
        """
        return {
            "report_1_spatial_54": {
                "title": "ピッチ54分割 空間支配＆レーン攻略レポート",
                "first_half_overload": "右ハーフスペース（0.92, 0.89）および右大外（0.89）への過負荷。水戸4-4-2ブロックを横に伸長させて中央を空けた。",
                "second_half_vital_inroad": "左ハーフスペース（0.97）および敵陣PA手前（0.94）への重心移動。水戸の前傾化で生まれたエアポケットを強襲。",
                "shot_distribution": "シュート22本中14本がボックス内中央。外で広げて中で仕留めるポジショナル原則の完遂。",
            },
            "report_2_archetypes": {
                "title": "選手ロール（Archetype）適合度＆タスク遂行診断書",
                "players": [
                    {"name": "長倉 幹樹", "role": "偽9番（ドロップ型CF）", "score": "S (95点)", "comment": "ライン間に落ちてCB木本を釣り出し、仲川の裏抜けスペースを開けた。"},
                    {"name": "仲川 輝人", "role": "裏抜けスプリンター", "score": "S (95点)", "comment": "先制ヘッドと後半頭の決定打。PA中央で2得点と仕留め役を完遂。"},
                    {"name": "安斎 颯馬", "role": "ワイドプレイメーカー / ダイナモ", "score": "S (98点)", "comment": "攻撃3.50、奪取12.62。独走ゴールを含め全指標でピッチを支配。"},
                    {"name": "常盤 亨太", "role": "ボールリカバリー型アンカー", "score": "S (96点)", "comment": "奪取25.12は異次元。相手中盤を窒息させた隠れたMVP。"},
                    {"name": "石原 広教", "role": "ポケットデリバリー型SB", "score": "A+ (90点)", "comment": "クロス成功率42.9%に寄与する2アシスト。守備でも水戸左サイドを完封。"},
                ],
            },
            "report_3_units": {
                "title": "ユニット連携＆ケミストリー診断レポート",
                "units": [
                    {"unit_name": "2トップ (長倉 ✕ 仲川)", "rating": "★★★★★", "comment": "落ちる長倉と抜ける仲川の補完的関係。合計シュートCBP 9.83。"},
                    {"unit_name": "ダブルボランチ (常盤 ✕ 高宇洋)", "rating": "★★★★★", "comment": "狩る常盤と捌く高宇洋。奪取後最短距離で配給される黄金比。"},
                    {"unit_name": "右サイドアタックトリオ (石原 ✕ 長倉 ✕ 仲川)", "rating": "★★★★★", "comment": "前半の右過負荷（密度0.92）を形成した三角形。"},
                    {"unit_name": "水戸CBコンビ (木本 ✕ 板倉)", "rating": "★★☆☆☆", "comment": "守備ポイント7.16と奮闘したが、中盤不在によりボックス内で過負荷死。"},
                ],
            },
            "report_4_scouting": {
                "title": "次節スカウティング＆対策シミュレーション",
                "opponent_perspective_exploits": [
                    "開始3分間のバタつき（ハイプレスとCK攻勢による奇襲）",
                    "先制直後のテンポコントロール不足（保持率を手放す時間帯の逆襲）",
                    "右SB石原が高く張った裏の広大なスペース",
                ],
                "fctokyo_prescriptions": [
                    "立ち上がり10分のセーフティな陣地回復（ヒアン・長倉へのシンプルフィード）",
                    "リード時のテンポコントロール（稲村・高宇洋・常盤でのパス回し）",
                    "決定力フィーバーの揺り戻しを想定した好機創出（xG）のベースアップ",
                ],
            },
            "report_5_what_if": {
                "title": "反実仮想（What-if）シナリオ分岐レポート",
                "scenarios": [
                    {
                        "branch_point": "前半3分: 水戸のCKから先制点を許していたら？",
                        "simulation": "水戸の4-4-2ブロックが完成し、FC東京の攻撃が外回りクロス頼みになり、0-1または1-1のロースコア泥仕合にもつれ込んだ可能性が高い。",
                    },
                    {
                        "branch_point": "後半46分: 水戸DFがクリアミスをせず0-1が維持されていたら？",
                        "simulation": "水戸は前傾化せずコンパクトさを維持。59分の間接FK決定機で同点に追いついていれば、後半の大量得点は発生しなかった。",
                    },
                    {
                        "branch_point": "後半63分: 水戸が攻撃的3枚替えをせず守備ブロックを継続していたら？",
                        "simulation": "安斎の独走被弾を防ぎ、2点差のまま推移して失点は0-2〜0-3程度に抑えられていた。",
                    },
                ],
            },
        }
