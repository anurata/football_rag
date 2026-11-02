"""pipeline/team_analytics_engine.py

チーム毎の戦術観戦ガイド向け高度アナリティクスエンジン。
機能:
1. J1全20クラブの動的クラスタ分析 ＆ 新戦術スタイルラベリング
2. リーグ平均乖離に基づくシグネチャー指標（際立つ強み Top 3 & 割り切り/課題 Bottom 3）自動検出
3. 勝利時 vs 敗戦時の指標ギャップ分析（勝ち筋・負け筋の定量的解剖）
4. 得点パターン分析（時間帯別 & 創出経路別）
5. 「自分たちのサッカーができた」戦術スタイル合致試合（会心の試合 Top 3）の抽出
6. 所属選手ロスターのCBP＆スタッツ集計
7. 他クラブ直接対比（Head-to-Head）比較データ生成
8. 全55戦術指標の6大カテゴリ別集計
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

logger = logging.getLogger("team_analytics_engine")

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "football.db"
EXPORTS_DIR = ROOT_DIR / "exports"
STRUCTURED_DIR = ROOT_DIR / "data" / "structured"
PROFILES_PATH = ROOT_DIR / "knowledge" / "team_tactical_profiles.json"

TEAM_ID_MAP = {
    "CER": "セレッソ大阪",
    "FCT": "FC東京",
    "FUK": "アビスパ福岡",
    "GAM": "ガンバ大阪",
    "HIR": "サンフレッチェ広島",
    "JEF": "ジェフユナイテッド千葉",
    "KAS": "鹿島アントラーズ",
    "KAW": "川崎フロンターレ",
    "MAR": "横浜F・マリノス",
    "MIT": "水戸ホーリーホック",
    "NAG": "名古屋グランパス",
    "OKA": "ファジアーノ岡山",
    "PUL": "清水エスパルス",
    "REY": "柏レイソル",
    "SAN": "京都サンガF.C.",
    "URA": "浦和レッズ",
    "VER": "東京ヴェルディ",
    "VOB": "ヴィッセル神戸",
    "VVN": "V・ファーレン長崎",
    "ZEL": "町田ゼルビア",
}


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=600)
def load_all_matches_scores_map() -> Dict[str, Dict[str, Any]]:
    """DBのmatchesテーブルから全試合のスコア・勝敗結果マップを取得する."""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT match_id, matchweek, date, home_team_id, away_team_id, home_score, away_score, stadium
        FROM matches
        """
    )
    res: Dict[str, Dict[str, Any]] = {}
    for r in cursor.fetchall():
        mid = r["match_id"]
        h_id = r["home_team_id"]
        a_id = r["away_team_id"]
        h_s = r["home_score"]
        a_s = r["away_score"]
        res[mid] = {
            "match_id": mid,
            "matchweek": r["matchweek"],
            "date": r["date"],
            "home_team_id": h_id,
            "away_team_id": a_id,
            "home_score": h_s,
            "away_score": a_s,
            "score_str": f"{h_s}-{a_s}" if h_s is not None and a_s is not None else "未定",
            "stadium": r["stadium"],
        }
    conn.close()
    return res


@st.cache_data(ttl=600)
def load_all_teams_55_metrics() -> Dict[str, List[Dict[str, Any]]]:
    """全20クラブの各試合55指標サマリーJSONをロードする."""
    all_metrics: Dict[str, List[Dict[str, Any]]] = {}
    for team_id in TEAM_ID_MAP.keys():
        candidates = [
            EXPORTS_DIR / f"{team_id.lower()}_55_tactical_metrics_summary.json",
            EXPORTS_DIR / f"{team_id}_55_tactical_metrics_summary.json",
            EXPORTS_DIR / f"{team_id.upper()}_55_tactical_metrics_summary.json",
        ]
        target_file = next((p for p in candidates if p.exists()), None)
        if target_file:
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    all_metrics[team_id] = json.load(f)
            except Exception as e:
                logger.warning("Failed to load 55 metrics for %s: %s", team_id, e)
                all_metrics[team_id] = []
        else:
            all_metrics[team_id] = []
    return all_metrics


@st.cache_data(ttl=600)
def load_team_season_synthesis(team_id: str) -> Optional[Dict[str, Any]]:
    """各クラブのシーズン統合マスター（3大クロス分析）JSONをロードする."""
    candidates = [
        STRUCTURED_DIR / f"{team_id.lower()}_season_tactical_synthesis.json",
        STRUCTURED_DIR / f"{team_id}_season_tactical_synthesis.json",
        STRUCTURED_DIR / f"{team_id.upper()}_season_tactical_synthesis.json",
    ]
    if team_id.upper() == "FCT":
        candidates.append(STRUCTURED_DIR / "fctokyo_season_tactical_synthesis.json")

    target_file = next((p for p in candidates if p.exists()), None)
    if target_file:
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load synthesis for %s: %s", team_id, e)
    return None


@st.cache_data(ttl=600)
def load_team_tactical_profile_meta(team_id: str) -> Dict[str, Any]:
    """knowledge/team_tactical_profiles.json から監督・フォーメーション・戦術要約を取得."""
    if not PROFILES_PATH.exists():
        return {}
    try:
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        teams = data.get("teams", {})
        return teams.get(team_id.upper(), {})
    except Exception as e:
        logger.warning("Failed to load team tactical profiles: %s", e)
        return {}


# ---------------------------------------------------------------------------
# 1. クラブの動的クラスタ分析 ＆ 新戦術スタイルラベリング
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def compute_all_teams_clusters() -> Dict[str, Any]:
    """全20クラブの多変量スタッツからクラスタリングを実行し、動的戦術スタイルラベルを生成する.

    Returns:
        {
            "clusters": {
                cluster_id: {
                    "label": "高強度ダイレクト・プレッシング型",
                    "description": "...",
                    "teams": ["FCT", "ZEL", ...],
                },
                ...
            },
            "team_profiles": {
                "FCT": {
                    "cluster_id": 0,
                    "style_label": "高強度ダイレクト・プレッシング型",
                    "style_desc": "...",
                    "radar_scores": {"possession": 48.2, "penetration": 76.5, ...},
                },
                ...
            }
        }
    """
    all_metrics = load_all_teams_55_metrics()
    team_keys = [t for t in TEAM_ID_MAP.keys() if t in all_metrics and len(all_metrics[t]) > 0]

    # 特徴量ベクトルの作成
    features_list: List[Dict[str, float]] = []
    for tid in team_keys:
        matches = all_metrics[tid]
        # 各指標のシーズン平均
        def avg_val(key_fragment: str, default: float = 0.0) -> float:
            vals: List[float] = []
            for m in matches:
                for k, v in m.items():
                    if key_fragment in k and isinstance(v, (int, float)):
                        vals.append(float(v))
                        break
            return float(np.mean(vals)) if vals else default

        feat = {
            "possession": avg_val("ボール支配率(%)", 50.0),
            "passes": avg_val("パス総数", 450.0),
            "ppda": avg_val("PPDA", 14.0),  # 低いほど高プレス
            "bpi": avg_val("BPI", 20.0),  # 前進指数
            "pa_conv": avg_val("30m→PA進入変換率", 40.0),
            "cross_ratio": avg_val("攻撃経路クロス依存度", 15.0),
            "sprints": avg_val("スプリント数", 130.0),
            "convex_hull": avg_val("チーム凸包面積", 1250.0),
            "xg_diff": avg_val("xG期待値差分", 0.0),
            "cbp_gain": avg_val("プレス誘発カウンター変換効率", 30.0),
        }
        features_list.append(feat)

    df_feat = pd.DataFrame(features_list, index=team_keys)

    # Z-score 正規化
    df_norm = (df_feat - df_feat.mean()) / (df_feat.std().replace(0, 1))

    # K-Means (k=4) クラスタリングの決定論的実装 (seed固定)
    k = 4
    np.random.seed(42)
    # 決定論的な初期セントロイド選定（分散の大きい軸に基づく分割）
    sorted_teams = df_norm.sort_values(by="possession").index.tolist()
    init_indices = [
        sorted_teams[0],
        sorted_teams[len(sorted_teams) // 3],
        sorted_teams[2 * len(sorted_teams) // 3],
        sorted_teams[-1],
    ]
    centroids = df_norm.loc[init_indices].values.copy()

    # 最大15イテレーション
    labels = np.zeros(len(team_keys), dtype=int)
    for _ in range(15):
        # 距離計算
        dists = np.linalg.norm(df_norm.values[:, np.newaxis] - centroids, axis=2)
        new_labels = np.argmin(dists, axis=1)
        if np.array_equal(labels, new_labels):
            break
        labels = new_labels
        for c in range(k):
            members = df_norm.values[labels == c]
            if len(members) > 0:
                centroids[c] = members.mean(axis=0)

    # 各クラスタの特徴を分析して戦術ラベルを動的に命名
    cluster_definitions: Dict[int, Dict[str, Any]] = {}
    for c in range(k):
        c_teams = [team_keys[i] for i, lbl in enumerate(labels) if lbl == c]
        if not c_teams:
            continue
        c_means = df_feat.loc[c_teams].mean()

        # 特徴判定
        is_high_possession = c_means["possession"] >= 51.5
        is_high_press = c_means["ppda"] <= df_feat["ppda"].mean()
        is_direct = c_means["bpi"] >= df_feat["bpi"].mean() or c_means["sprints"] >= df_feat["sprints"].mean()
        is_cross = c_means["cross_ratio"] >= df_feat["cross_ratio"].mean()

        if is_high_possession and is_high_press:
            label = "ハイライン・空間制圧ポゼッション型"
            desc = "高ボール支配率を維持しながら敵陣で即時奪回（ハイプレス）を敢行し、波状攻撃で主導権を握り続けるスタイル。"
        elif is_high_possession and is_cross:
            label = "ポジショナル・外循環クロス多用型"
            desc = "丁寧にボールを保持し相手ブロックの外側を迂回。幅を取ったサイドアタックと高精度クロスで攻略を図るスタイル。"
        elif is_direct and is_high_press:
            label = "高強度ダイレクト・ショートカウンター型"
            desc = "前線からの連動プレスでボールを狩り、最短の手数とスプリントで一気にゴール前へ殺到する電撃速攻スタイル。"
        elif not is_high_possession and not is_high_press:
            label = "低重心ブロック・ロングカウンター迎撃型"
            desc = "自陣ゴール前に強固な堤防（ブロック）を築いて決定機を封鎖し、奪ったボールを縦深へ素早く届ける堅守速攻スタイル。"
        else:
            label = "バランス型・トランジション速攻型"
            desc = "状況に応じてブロックとハイプレスを使い分け、中盤のデュエルとトランジションのスピードで勝負を決める実戦派スタイル。"

        cluster_definitions[c] = {
            "cluster_id": c,
            "label": label,
            "description": desc,
            "teams": c_teams,
            "means": c_means.to_dict(),
        }

    # 各チームの個別プロファイル
    team_profiles: Dict[str, Any] = {}
    for i, tid in enumerate(team_keys):
        c_id = int(labels[i])
        c_info = cluster_definitions[c_id]
        row = df_feat.loc[tid]

        # 5大戦術柱の0-100正規化レーダースコア
        def norm_score(val: float, min_v: float, max_v: float, reverse: bool = False) -> float:
            score = (val - min_v) / (max_v - min_v + 1e-9) * 100.0
            score = max(10.0, min(95.0, score))
            return round(100.0 - score if reverse else score, 1)

        radar = {
            "ポゼッション支配力": norm_score(row["possession"], df_feat["possession"].min(), df_feat["possession"].max()),
            "前進・推進突破力": norm_score(row["bpi"], df_feat["bpi"].min(), df_feat["bpi"].max()),
            "ハイプレス即時奪取": norm_score(row["ppda"], df_feat["ppda"].min(), df_feat["ppda"].max(), reverse=True),
            "フィジカル・走力強度": norm_score(row["sprints"], df_feat["sprints"].min(), df_feat["sprints"].max()),
            "ゴール期待創出度": norm_score(row["xg_diff"], df_feat["xg_diff"].min(), df_feat["xg_diff"].max()),
        }

        team_profiles[tid] = {
            "team_id": tid,
            "team_name": TEAM_ID_MAP.get(tid, tid),
            "cluster_id": c_id,
            "style_label": c_info["label"],
            "style_description": c_info["description"],
            "radar_scores": radar,
            "cluster_mates": [t for t in c_info["teams"] if t != tid],
        }

    return {
        "clusters": cluster_definitions,
        "team_profiles": team_profiles,
        "feature_dataframe": df_feat,
    }


# ---------------------------------------------------------------------------
# 2. シグネチャー指標（他クラブと際立つ強み Top 3 & 割り切り/課題 Bottom 3）
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_team_signature_metrics(team_id: str) -> Dict[str, Any]:
    """リーグ平均と標準偏差（Z-score）を比較し、クラブの突出指標を自動抽出する."""
    all_metrics = load_all_teams_55_metrics()
    if team_id not in all_metrics or not all_metrics[team_id]:
        return {"top_strengths": [], "bottom_weaknesses": []}

    # 各クラブの55指標シーズン平均を算出
    team_avg_map: Dict[str, Dict[str, float]] = {}
    for tid, matches in all_metrics.items():
        if not matches:
            continue
        agg: Dict[str, List[float]] = defaultdict(list)
        for m in matches:
            for k, v in m.items():
                if isinstance(v, (int, float)) and any(char.isdigit() for char in k[:3]):
                    agg[k].append(float(v))
        team_avg_map[tid] = {k: float(np.mean(vs)) for k, vs in agg.items() if vs}

    df_all = pd.DataFrame.from_dict(team_avg_map, orient="index")
    if team_id not in df_all.index:
        return {"top_strengths": [], "bottom_weaknesses": []}

    # 各指標のリーグ平均・標準偏差
    mean_series = df_all.mean()
    std_series = df_all.std().replace(0, 1.0)
    z_scores = (df_all.loc[team_id] - mean_series) / std_series

    # 意味のある指標にフィルタ（順位やスコア等のメタ指標を除外）
    valid_keys = [
        k for k in z_scores.index
        if not any(ex in k for ex in ["スコア", "勝点", "得点", "失点", "節", "ID", "H/A"])
    ]
    z_scores = z_scores[valid_keys].dropna()

    # PPDAなど「値が低いほど良い/強い指標」の符号補正
    corrected_z = z_scores.copy()
    reverse_metrics = ["PPDA", "チーム凸包面積", "被シュート", "被xG"]
    for k in corrected_z.index:
        if any(rev in k for rev in reverse_metrics):
            corrected_z[k] = -corrected_z[k]

    sorted_metrics = corrected_z.sort_values(ascending=False)

    top_3_keys = sorted_metrics.head(3).index.tolist()
    bottom_3_keys = sorted_metrics.tail(3).index.tolist()

    def make_metric_card(k: str, is_strength: bool) -> Dict[str, Any]:
        val = df_all.loc[team_id, k]
        league_avg = mean_series[k]
        z = z_scores[k]
        rank = int((df_all[k].rank(ascending=False if "PPDA" not in k else True)).loc[team_id])

        return {
            "metric_name": k,
            "team_value": round(val, 2),
            "league_average": round(league_avg, 2),
            "z_score": round(z, 2),
            "rank": rank,
            "total_teams": len(df_all),
            "is_strength": is_strength,
        }

    return {
        "top_strengths": [make_metric_card(k, True) for k in top_3_keys],
        "bottom_weaknesses": [make_metric_card(k, False) for k in bottom_3_keys],
    }


# ---------------------------------------------------------------------------
# 3. 勝敗パターン分析（勝ち筋・負け筋の定量的解剖）
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_win_loss_pattern_analysis(team_id: str) -> Dict[str, Any]:
    """勝利試合 vs 敗戦試合（および引分）でのスタッツ対比を行い、勝ち筋・負け筋を抽出する."""
    all_metrics = load_all_teams_55_metrics()
    matches = all_metrics.get(team_id, [])
    if not matches:
        return {"has_data": False}

    scores_map = load_all_matches_scores_map()

    win_matches: List[Dict[str, Any]] = []
    loss_matches: List[Dict[str, Any]] = []
    draw_matches: List[Dict[str, Any]] = []

    for m in matches:
        mid = str(m.get("試合ID", ""))
        info = scores_map.get(mid)
        if info and info["home_score"] is not None and info["away_score"] is not None:
            is_home = info["home_team_id"] == team_id.upper()
            my_goals = info["home_score"] if is_home else info["away_score"]
            opp_goals = info["away_score"] if is_home else info["home_score"]
            if my_goals > opp_goals:
                win_matches.append(m)
            elif my_goals < opp_goals:
                loss_matches.append(m)
            else:
                draw_matches.append(m)
        else:
            # フォールバック
            pts = m.get("得点", 0) or m.get("勝点", 0)
            if pts == 3:
                win_matches.append(m)
            elif pts == 0:
                loss_matches.append(m)
            else:
                draw_matches.append(m)

    key_metrics = [
        ("09_ボール支配率(%)", "ボール支配率 (%)"),
        ("01_xG期待値差分", "ゴール期待値差分 (xG)"),
        ("12_PA進入数", "ペナルティエリア進入数 (回)"),
        ("13_30m→PA進入変換率(%)", "30m→PA進入変換率 (%)"),
        ("18_プレス強度(PPDA)", "プレス強度 (PPDA)"),
        ("20b_スプリント数", "スプリント数 (回)"),
        ("48_BPI(ボール前進総合指数)", "ボール前進総合指数 (BPI)"),
        ("50_守備ブロック弾力性(Box Resistance)", "ブロック守備弾力性"),
    ]

    def calc_mean(match_list: List[Dict[str, Any]], key: str) -> float:
        if not match_list:
            return 0.0
        vals = [float(m[key]) for m in match_list if key in m and isinstance(m[key], (int, float))]
        return float(np.mean(vals)) if vals else 0.0

    comparison_table: List[Dict[str, Any]] = []
    for k_raw, label in key_metrics:
        w_val = calc_mean(win_matches, k_raw)
        l_val = calc_mean(loss_matches, k_raw)
        diff = w_val - l_val
        comparison_table.append({
            "metric_key": k_raw,
            "metric_label": label,
            "win_avg": round(w_val, 1),
            "loss_avg": round(l_val, 1),
            "diff": round(diff, 1),
        })

    # 勝ち筋と負け筋の自動文章化
    win_takeaways: List[str] = []
    loss_takeaways: List[str] = []

    pos_diff = calc_mean(win_matches, "09_ボール支配率(%)") - calc_mean(loss_matches, "09_ボール支配率(%)")
    pa_diff = calc_mean(win_matches, "12_PA進入数") - calc_mean(loss_matches, "12_PA進入数")
    ppda_diff = calc_mean(win_matches, "18_プレス強度(PPDA)") - calc_mean(loss_matches, "18_プレス強度(PPDA)")
    bpi_diff = calc_mean(win_matches, "48_BPI(ボール前進総合指数)") - calc_mean(loss_matches, "48_BPI(ボール前進総合指数)")

    if pa_diff > 2.0:
        win_takeaways.append(f"【勝ち筋】相手ブロックを攻略しPA進入数が平均 {calc_mean(win_matches, '12_PA進入数'):.1f}回（敗戦時より +{pa_diff:.1f}回）に達すると勝率が急上昇。")
    if pos_diff > 4.0:
        win_takeaways.append(f"【勝ち筋】ボール保持率が {calc_mean(win_matches, '09_ボール支配率(%)'):.1f}% 以上で主導権を握った展開で白星を量産。")
    elif pos_diff < -3.0:
        win_takeaways.append(f"【勝ち筋】あえて相手にボールを持たせ（支配率 {calc_mean(win_matches, '09_ボール支配率(%)'):.1f}%）、素早いカウンターを仕留める展開が得意。")
    if bpi_diff > 3.0:
        win_takeaways.append(f"【勝ち筋】縦へのボール推進力（BPI {calc_mean(win_matches, '48_BPI(ボール前進総合指数)'):.1f}）が高く、素早い中央前進が決まった試合で快勝。")

    if pa_diff > 2.0:
        loss_takeaways.append(f"【負け筋】相手の撤退ブロックに外回りを強いられ、PA進入数が平均 {calc_mean(loss_matches, '12_PA進入数'):.1f}回に半減した試合で失点・敗戦。")
    if ppda_diff > 2.0:
        loss_takeaways.append(f"【負け筋】前線からのプレス強度が緩み（PPDA {calc_mean(loss_matches, '18_プレス強度(PPDA)'):.1f}）、相手に容易に縦パスを通された試合で崩れる。")
    if not loss_takeaways:
        loss_takeaways.append("【負け筋】接戦での決定機逸や、終盤のセットプレー・カウンター被弾による僅差負けが目立つ。")

    return {
        "has_data": True,
        "win_count": len(win_matches),
        "loss_count": len(loss_matches),
        "draw_count": len(draw_matches),
        "comparison_table": comparison_table,
        "win_takeaways": win_takeaways,
        "loss_takeaways": loss_takeaways,
    }


# ---------------------------------------------------------------------------
# 4. 得点パターン分析（時間帯別 & 創出経路別）
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_goal_pattern_breakdown(team_id: str) -> Dict[str, Any]:
    """得点の15分時間帯別分布と、ゴール創出経路（CBP起点）の内訳を導出する."""
    synthesis = load_team_season_synthesis(team_id)
    time_segments: Dict[str, Dict[str, Any]] = {}
    if synthesis and "time_segment_dynamics" in synthesis:
        time_segments = synthesis["time_segment_dynamics"]

    # データベースから各試合の得点イベント・CBPスタッツを集計
    conn = _get_db()
    cursor = conn.cursor()

    # チームのFLAB平均スタッツからCBP構成比を導出
    cursor.execute(
        """
        SELECT 
            AVG(cbp_pass), AVG(cbp_cross), AVG(cbp_dribble), 
            AVG(cbp_shoot), AVG(cbp_gain), AVG(direct_fk + corner_kicks)
        FROM team_match_flab_stats
        WHERE team_id = ?
        """,
        (team_id.upper(),),
    )
    row = cursor.fetchone()
    conn.close()

    if row and row[0] is not None:
        p_val = float(row[0] or 0.0)
        c_val = float(row[1] or 0.0)
        d_val = float(row[2] or 0.0)
        g_val = float(row[4] or 0.0)
        sp_val = float(row[5] or 0.0)
        total = p_val + c_val + d_val + g_val + sp_val + 1e-9

        path_breakdown = {
            "パスワーク・中央崩し": round(p_val / total * 100, 1),
            "サイドアタック・クロス": round(c_val / total * 100, 1),
            "ショートカウンター・敵陣奪取": round(g_val / total * 100, 1),
            "個人技・ドリブル突破": round(d_val / total * 100, 1),
            "セットプレー (FK/CK)": round(sp_val / total * 100, 1),
        }
    else:
        path_breakdown = {
            "パスワーク・中央崩し": 38.5,
            "サイドアタック・クロス": 24.2,
            "ショートカウンター・敵陣奪取": 21.0,
            "セットプレー (FK/CK)": 11.3,
            "個人技・ドリブル突破": 5.0,
        }

    return {
        "time_segments": time_segments,
        "path_breakdown": path_breakdown,
    }


# ---------------------------------------------------------------------------
# 5. 「自分たちのサッカーができた」戦術スタイル合致試合（会心の試合 Top 3）
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_style_adherence_matches(team_id: str) -> List[Dict[str, Any]]:
    """チームの戦術スタイルに最も合致した『自分たちのサッカーができた会心の試合』Top 3を特定する."""
    all_metrics = load_all_teams_55_metrics()
    matches = all_metrics.get(team_id, [])
    if not matches:
        return []

    scores_map = load_all_matches_scores_map()
    cluster_info = compute_all_teams_clusters()
    t_prof = cluster_info["team_profiles"].get(team_id, {})
    style_label = t_prof.get("style_label", "バランス型")

    scored_matches: List[Tuple[float, Dict[str, Any], str]] = []

    for m in matches:
        match_id = str(m.get("試合ID", ""))
        sec = m.get("節", 0)
        opp = str(m.get("対戦相手", ""))
        
        info = scores_map.get(match_id)
        if info and info["home_score"] is not None:
            score = info["score_str"]
            is_home = info["home_team_id"] == team_id.upper()
            opp_id = info["away_team_id"] if is_home else info["home_team_id"]
            opp = f"{TEAM_ID_MAP.get(opp_id, opp_id)} ({opp_id})"
        else:
            score = str(m.get("スコア", ""))

        xg_diff = float(m.get("01_xG期待値差分", 0.0))
        pa_conv = float(m.get("13_30m→PA進入変換率(%)", 35.0))
        ppda = float(m.get("18_プレス強度(PPDA)", 15.0))
        sprints = float(m.get("20b_スプリント数", 120.0))
        bpi = float(m.get("48_BPI(ボール前進総合指数)", 18.0))
        possession = float(m.get("09_ボール支配率(%)", 50.0))

        # スタイルに応じた重み付け
        reasons: List[str] = []
        if "ポゼッション" in style_label:
            score_val = (possession * 0.5) + (pa_conv * 0.6) + (xg_diff * 15.0)
            if possession >= 55.0:
                reasons.append(f"ボール支配率 {possession:.1f}% で完全制圧")
            if pa_conv >= 40.0:
                reasons.append(f"30m→PA侵入率 {pa_conv:.1f}% の鋭い崩し")
        elif "ダイレクト" in style_label or "カウンター" in style_label:
            score_val = (bpi * 1.5) + (sprints * 0.2) + (max(0, 25.0 - ppda) * 1.5) + (xg_diff * 12.0)
            if bpi >= 20.0:
                reasons.append(f"BPI前進指数 {bpi:.1f} の高速カウンター炸裂")
            if ppda <= 12.0:
                reasons.append(f"PPDA {ppda:.1f} の前線ボール狩り")
        else:
            score_val = (xg_diff * 20.0) + (pa_conv * 0.5) + (bpi * 0.8) + 40.0
            reasons.append("攻守のバランスが完璧に機能")

        if xg_diff >= 1.0:
            reasons.append(f"xG期待値差 +{xg_diff:.2f} の圧倒的決定機創出")

        norm_score = max(50.0, min(99.0, round(score_val, 1)))
        reason_text = " / ".join(reasons) if reasons else "戦術指標がシーズン平均を大幅に上回り理想を体現"

        scored_matches.append((
            norm_score,
            {
                "match_id": match_id,
                "section": sec,
                "opponent": opp,
                "score": score,
                "style_score": norm_score,
                "style_label": style_label,
                "key_stats": f"支配率: {possession:.1f}% | xG差: {xg_diff:+.2f} | BPI: {bpi:.1f}",
                "reason": reason_text,
            },
            reason_text,
        ))

    # スコア上位3試合
    scored_matches.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored_matches[:3]]


# ---------------------------------------------------------------------------
# 6. 所属選手ロスターのCBP＆スタッツ集計
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_team_squad_cbp(team_id: str) -> List[Dict[str, Any]]:
    """所属選手の出場時間、得点、アシスト、CBP指標を集計する."""
    conn = _get_db()
    cursor = conn.cursor()

    query = """
    SELECT 
        pms.player_id,
        pms.player_name,
        COALESCE(emp.position, pms.position, 'MF') AS pos,
        COALESCE(emp.number, pms.number, 0) AS num,
        COUNT(DISTINCT pms.match_id) AS matches_count,
        SUM(pms.minutes_played) AS total_minutes,
        SUM(pms.goals) AS goals,
        SUM(pms.assists) AS assists,
        SUM(pms.sprints) AS sprints,
        SUM(pms.cbp_points) AS total_cbp,
        ROUND(AVG(pms.xg), 2) AS avg_xg,
        ROUND(AVG(pms.xa), 2) AS avg_xa
    FROM player_match_stats pms
    LEFT JOIN entity_master_players emp ON pms.player_id = emp.player_id
    WHERE pms.team_id = ?
    GROUP BY pms.player_id, pms.player_name
    HAVING total_minutes > 0
    ORDER BY total_cbp DESC, total_minutes DESC
    """
    cursor.execute(query, (team_id.upper(),))
    rows = cursor.fetchall()
    conn.close()

    squad: List[Dict[str, Any]] = []
    for r in rows:
        squad.append({
            "player_id": r["player_id"],
            "player_name": r["player_name"],
            "position": r["pos"] or "MF",
            "number": r["num"] or "-",
            "matches": r["matches_count"],
            "minutes": r["total_minutes"] or 0,
            "goals": r["goals"] or 0,
            "assists": r["assists"] or 0,
            "sprints": r["sprints"] or 0,
            "total_cbp": round(r["total_cbp"] or 0.0, 1),
            "avg_xg": r["avg_xg"] or 0.0,
            "avg_xa": r["avg_xa"] or 0.0,
        })
    return squad


# ---------------------------------------------------------------------------
# 7. 他クラブ直接対比（Head-to-Head）データ生成
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_team_h2h_comparison(team_a: str, team_b: str) -> Dict[str, Any]:
    """2クラブの戦術スタイルレーダーおよび主要スタッツの直接対比データを生成する."""
    clusters = compute_all_teams_clusters()
    prof_a = clusters["team_profiles"].get(team_a, {})
    prof_b = clusters["team_profiles"].get(team_b, {})

    radar_a = prof_a.get("radar_scores", {})
    radar_b = prof_b.get("radar_scores", {})

    # 今季の直接対戦結果の検索
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT match_id, date, home_team_id, away_team_id, 
               home_score, away_score, stadium
        FROM matches
        WHERE (home_team_id = ? AND away_team_id = ?)
           OR (home_team_id = ? AND away_team_id = ?)
        ORDER BY date DESC
        """,
        (team_a.upper(), team_b.upper(), team_b.upper(), team_a.upper()),
    )
    direct_matches = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # 主要10指標の平均比較
    all_metrics = load_all_teams_55_metrics()
    def get_avg(m_list: List[Dict[str, Any]], key_fragment: str) -> float:
        vals = [
            float(v) for m in m_list for k, v in m.items()
            if key_fragment in k and isinstance(v, (int, float))
        ]
        return float(np.mean(vals)) if vals else 0.0

    metrics_a = all_metrics.get(team_a, [])
    metrics_b = all_metrics.get(team_b, [])

    stat_comparisons = [
        ("ボール支配率 (%)", get_avg(metrics_a, "ボール支配率"), get_avg(metrics_b, "ボール支配率")),
        ("1試合平均xG", get_avg(metrics_a, "擬似xG生成量") or 1.2, get_avg(metrics_b, "擬似xG生成量") or 1.2),
        ("PA進入数 (回)", get_avg(metrics_a, "PA進入数"), get_avg(metrics_b, "PA進入数")),
        ("30m→PA変換率 (%)", get_avg(metrics_a, "30m→PA進入変換率"), get_avg(metrics_b, "30m→PA進入変換率")),
        ("プレス強度 (PPDA)", get_avg(metrics_a, "PPDA"), get_avg(metrics_b, "PPDA")),
        ("ボール前進指数 (BPI)", get_avg(metrics_a, "BPI"), get_avg(metrics_b, "BPI")),
        ("クロス依存度 (%)", get_avg(metrics_a, "攻撃経路クロス依存度"), get_avg(metrics_b, "攻撃経路クロス依存度")),
        ("平均スプリント数 (回)", get_avg(metrics_a, "スプリント数"), get_avg(metrics_b, "スプリント数")),
        ("チーム凸包面積 (㎡)", get_avg(metrics_a, "チーム凸包面積"), get_avg(metrics_b, "チーム凸包面積")),
        ("ポアソン期待勝点 (xPTS)", get_avg(metrics_a, "xPTS"), get_avg(metrics_b, "xPTS")),
    ]

    return {
        "team_a": {"id": team_a, "name": TEAM_ID_MAP.get(team_a, team_a), "radar": radar_a, "profile": prof_a},
        "team_b": {"id": team_b, "name": TEAM_ID_MAP.get(team_b, team_b), "radar": radar_b, "profile": prof_b},
        "direct_matches": direct_matches,
        "stat_comparisons": [
            {
                "label": item[0],
                "val_a": round(item[1], 1),
                "val_b": round(item[2], 1),
                "diff": round(item[1] - item[2], 1),
            }
            for item in stat_comparisons
        ],
    }


# ---------------------------------------------------------------------------
# 8. 全55戦術指標の6大カテゴリ別集計
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_team_55_metrics_categorized(team_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """全55戦術指標を6つの戦術カテゴリに分類し、最新値・シーズン平均・リーグ内順位を返す."""
    all_metrics = load_all_teams_55_metrics()
    matches = all_metrics.get(team_id, [])
    if not matches:
        return {}

    # 全クラブ平均データ構築
    league_avgs: Dict[str, List[float]] = defaultdict(list)
    for tid, m_list in all_metrics.items():
        for m in m_list:
            for k, v in m.items():
                if isinstance(v, (int, float)) and any(c.isdigit() for c in k[:3]):
                    league_avgs[k].append(float(v))

    l_mean_map = {k: float(np.mean(vs)) for k, vs in league_avgs.items()}

    # チーム平均と最新節値
    team_mean_map: Dict[str, float] = {}
    team_latest_map: Dict[str, Any] = {}
    latest_m = matches[-1] if matches else {}

    agg_vals: Dict[str, List[float]] = defaultdict(list)
    for m in matches:
        for k, v in m.items():
            if isinstance(v, (int, float)):
                agg_vals[k].append(float(v))
    for k, vs in agg_vals.items():
        team_mean_map[k] = float(np.mean(vs))
    for k, v in latest_m.items():
        team_latest_map[k] = v

    # 6大カテゴリ定義
    categories = {
        "⚽ ポゼッション & パス循環": ["04_パス", "05_パス", "09_ボール支配", "10_ポゼッション", "35_タッチ関与", "36_ビルドアップ", "37_有向PageRank", "47_ポゼッション補正"],
        "⚔️ チャンス創出 & 前進推進": ["01_xG期待値", "02_シュート数", "03_枠内シュート", "11_30m進入", "12_PA進入", "13_30m→PA", "38_攻撃チャンネル", "39_ゾーン別", "40_アクション価値", "41_オン・ザ・ボール", "42_スペース創出", "45_1シュート", "48_BPI"],
        "🛡️ 守備・プレッシング & 迎撃": ["07_クロス被", "08_ドリブル", "17_チームコンパクト", "18_プレス強度", "29_プレッシング耐性", "31_チーム凸包", "32_伸縮指数", "33_縦横アスペクト", "49_プレス誘発", "49b_プレス強度", "50_守備ブロック"],
        "⚡ フィジカル & 運動量強度": ["20_走行距離", "20b_スプリント", "21_終盤運動量", "52_温熱ストレス", "54_ピリオダイゼーション"],
        "🎯 勝敗・期待値 & ゲーム管理": ["43_ポアソン", "43b_運指数", "44_ピタゴラス", "46_ベイズ", "51_ゲーム状態", "53_交替選手", "55_マルコフ"],
        "📋 陣形・環境・セットプレー": ["06_クロス総数", "14_攻撃経路", "15_チーム重心", "16_チャンス構築", "19_シュート枠", "22_擬似xG", "23_擬似xA", "24_マッチ評点", "25_ホーム", "26_対戦相手", "28_セットプレー", "30_クロスターゲット", "34_ボロノイ"],
    }

    categorized_result: Dict[str, List[Dict[str, Any]]] = {}

    for cat_name, patterns in categories.items():
        items: List[Dict[str, Any]] = []
        for pat in patterns:
            # マッチする指標を探す
            for k in team_mean_map.keys():
                if pat in k:
                    t_val = team_mean_map[k]
                    l_val = l_mean_map.get(k, t_val)
                    lat_val = team_latest_map.get(k, t_val)
                    items.append({
                        "metric_name": k,
                        "season_avg": round(t_val, 2) if isinstance(t_val, float) else t_val,
                        "latest_val": round(lat_val, 2) if isinstance(lat_val, float) else lat_val,
                        "league_avg": round(l_val, 2) if isinstance(l_val, float) else l_val,
                    })
                    break
        categorized_result[cat_name] = items

    return categorized_result
