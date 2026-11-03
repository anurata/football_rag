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

import base64
import json
import logging
import math
import re
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
METRIC_DEFS_PATH = ROOT_DIR / "knowledge" / "metric_definitions_55.json"

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
            "sprints": avg_val("スプリント", 130.0),
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
        ("18_守備プレス強度(PPDA)", "プレス強度 (PPDA)"),
        ("20b_スプリント回数", "スプリント数 (回)"),
        ("48_BPI(ボール前進総合指数)", "ボール前進総合指数 (BPI)"),
        ("50_守備ブロック弾力性(Box Resistance)", "ブロック守備弾力性"),
    ]

    def get_match_metric_val(m: Dict[str, Any], key: str) -> Optional[float]:
        """完全一致、プレフィックス一致、部分一致の順で堅牢にメトリクス値を取得する."""
        if key in m and isinstance(m[key], (int, float)):
            return float(m[key])
        # プレフィックス一致 (例: "18_" or "20b_")
        prefix = key.split("_")[0] + "_" if "_" in key else key
        for k, v in m.items():
            if k.startswith(prefix) and isinstance(v, (int, float)):
                return float(v)
        # 部分一致
        for k, v in m.items():
            if key in k and isinstance(v, (int, float)):
                return float(v)
        return None

    def calc_mean(match_list: List[Dict[str, Any]], key: str) -> float:
        if not match_list:
            return 0.0
        vals = [get_match_metric_val(m, key) for m in match_list]
        valid_vals = [v for v in vals if v is not None]
        return float(np.mean(valid_vals)) if valid_vals else 0.0

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
    ppda_diff = calc_mean(win_matches, "18_守備プレス強度(PPDA)") - calc_mean(loss_matches, "18_守備プレス強度(PPDA)")
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
        loss_takeaways.append(f"【負け筋】前線からのプレス強度が緩み（PPDA {calc_mean(loss_matches, '18_守備プレス強度(PPDA)'):.1f}）、相手に容易に縦パスを通された試合で崩れる。")
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
        ppda = float(m.get("18_守備プレス強度(PPDA)", m.get("18_プレス強度(PPDA)", 15.0)))
        sprints = float(m.get("20b_スプリント回数", m.get("20b_スプリント数", 120.0)))
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
# クラブ公式エンブレム（SVG / PNG）マッピング
# ---------------------------------------------------------------------------
TEAM_EMBLEM_MAP: Dict[str, str] = {
    "FCT": "https://www.jleague.jp/image/clubs/fc-tokyo.svg",
    "KAS": "https://www.jleague.jp/image/clubs/kashima.svg",
    "URA": "https://www.jleague.jp/image/clubs/urawa.svg",
    "REY": "https://www.jleague.jp/image/clubs/kashiwa.svg",
    "VER": "https://www.jleague.jp/image/clubs/tokyo-v.svg",
    "ZEL": "https://www.jleague.jp/image/clubs/machida.svg",
    "KAW": "https://www.jleague.jp/image/clubs/kawasaki.svg",
    "MAR": "https://www.jleague.jp/image/clubs/yokohama-fm.svg",
    "YFC": "https://www.jleague.jp/image/clubs/yokohama-fc.svg",
    "BEL": "https://www.jleague.jp/image/clubs/shonan.svg",
    "NII": "https://www.jleague.jp/image/clubs/niigata.svg",
    "PUL": "https://www.jleague.jp/image/clubs/shimizu.svg",
    "IWA": "https://www.jleague.jp/image/clubs/iwata.svg",
    "NAG": "https://www.jleague.jp/image/clubs/nagoya.svg",
    "SAN": "https://www.jleague.jp/image/clubs/kyoto.svg",
    "GAM": "https://www.jleague.jp/image/clubs/g-osaka.svg",
    "CER": "https://www.jleague.jp/image/clubs/c-osaka.svg",
    "VOB": "https://www.jleague.jp/image/clubs/kobe.svg",
    "OKA": "https://www.jleague.jp/image/clubs/okayama.svg",
    "HIR": "https://www.jleague.jp/image/clubs/hiroshima.svg",
    "FUK": "https://www.jleague.jp/image/clubs/fukuoka.svg",
    "SAG": "https://www.jleague.jp/image/clubs/tosu.svg",
    "VVN": "https://www.jleague.jp/image/clubs/nagasaki.svg",
    "CON": "https://www.jleague.jp/image/clubs/sapporo.svg",
    "JEF": "https://www.jleague.jp/image/clubs/chiba.svg",
    "MIT": "https://www.jleague.jp/image/clubs/mito.svg",
}

TEAM_FLAB_EMBLEM_MAP: Dict[str, str] = {
    "FCT": "https://www.football-lab.jp/img/team/FCTK_sdw.png",
    "KAS": "https://www.football-lab.jp/img/team/KASM_sdw.png",
    "URA": "https://www.football-lab.jp/img/team/URAW_sdw.png",
    "REY": "https://www.football-lab.jp/img/team/KASW_sdw.png",
    "VER": "https://www.football-lab.jp/img/team/TK-V_sdw.png",
    "ZEL": "https://www.football-lab.jp/img/team/MCD_sdw.png",
    "KAW": "https://www.football-lab.jp/img/team/KA-F_sdw.png",
    "MAR": "https://www.football-lab.jp/img/team/Y-FM_sdw.png",
    "YFC": "https://www.football-lab.jp/img/team/Y-FC_sdw.png",
    "BEL": "https://www.football-lab.jp/img/team/SHON_sdw.png",
    "NII": "https://www.football-lab.jp/img/team/NIIG_sdw.png",
    "PUL": "https://www.football-lab.jp/img/team/SHIM_sdw.png",
    "IWA": "https://www.football-lab.jp/img/team/IWAT_sdw.png",
    "NAG": "https://www.football-lab.jp/img/team/NAGO_sdw.png",
    "SAN": "https://www.football-lab.jp/img/team/KYOT_sdw.png",
    "GAM": "https://www.football-lab.jp/img/team/G-OS_sdw.png",
    "CER": "https://www.football-lab.jp/img/team/C-OS_sdw.png",
    "VOB": "https://www.football-lab.jp/img/team/KOBE_sdw.png",
    "OKA": "https://www.football-lab.jp/img/team/OKAY_sdw.png",
    "HIR": "https://www.football-lab.jp/img/team/HIRO_sdw.png",
    "FUK": "https://www.football-lab.jp/img/team/FUKU_sdw.png",
    "SAG": "https://www.football-lab.jp/img/team/TOSU_sdw.png",
    "VVN": "https://www.football-lab.jp/img/team/NGSK_sdw.png",
    "CON": "https://www.football-lab.jp/img/team/SAPP_sdw.png",
    "JEF": "https://www.football-lab.jp/img/team/CHIB_sdw.png",
    "MIT": "https://www.football-lab.jp/img/team/MITO_sdw.png",
}


def get_team_emblem_url(team_id: str, prefer_png: bool = False) -> str:
    """クラブ公式エンブレムの画像URL（公式SVGまたはFootball-LAB PNG）を返す."""
    tid = (team_id or "").upper()
    if prefer_png:
        return TEAM_FLAB_EMBLEM_MAP.get(tid, TEAM_EMBLEM_MAP.get(tid, ""))
    return TEAM_EMBLEM_MAP.get(tid, TEAM_FLAB_EMBLEM_MAP.get(tid, ""))


def get_team_emblem_html(team_id: str, width: int = 80, height: int = 80) -> str:
    """ローカルSVGまたは公式URLからクラブ公式エンブレムのHTML imgタグを返す."""
    tid = (team_id or "").upper()
    svg_path = Path(__file__).resolve().parent.parent / "assets" / "emblems" / f"team_{tid}.svg"
    if svg_path.exists():
        try:
            b64 = base64.b64encode(svg_path.read_bytes()).decode("utf-8")
            src = f"data:image/svg+xml;base64,{b64}"
        except Exception:
            src = get_team_emblem_url(tid)
    else:
        src = get_team_emblem_url(tid)

    if not src:
        return "<div style='font-size: 2.5rem; text-align: center;'>🛡️</div>"

    return (
        f'<img src="{src}" width="{width}" height="{height}" '
        f'alt="{tid}" style="object-fit: contain; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.18));" />'
    )


def get_team_manager_info(team_id: str) -> Dict[str, Any]:
    """クラブ監督名、公式スタッフID、顔写真URLを取得する."""
    meta = load_team_tactical_profile_meta(team_id)
    manager_name = meta.get("manager", "監督情報準備中")
    staff_id = meta.get("manager_staff_id")
    image_url = meta.get("manager_image_url")
    if not image_url and staff_id:
        image_url = f"https://data.j-league.or.jp/img/manager/{staff_id}.jpg"
    return {
        "manager_name": manager_name,
        "staff_id": staff_id,
        "image_url": image_url,
    }


def get_team_manager_avatar_html(team_id: str, size: int = 56) -> str:
    """監督の公式顔写真アバターHTML（円形・境界線・フォールバック付き）を返す."""
    mgr = get_team_manager_info(team_id)
    img_url = mgr.get("image_url")
    name = mgr.get("manager_name", "監督")

    if img_url:
        return (
            f'<img src="{img_url}" width="{size}" height="{size}" '
            f'alt="{name}" title="{name} 監督" '
            f'style="border-radius: 50%; object-fit: cover; border: 2px solid #e2e8f0; '
            f'box-shadow: 0 2px 5px rgba(0,0,0,0.12); vertical-align: middle;" />'
        )
    return (
        f'<div style="width: {size}px; height: {size}px; border-radius: 50%; '
        f'background: #f1f5f9; display: inline-flex; align-items: center; '
        f'justify-content: center; font-size: {size // 2}px; border: 2px solid #e2e8f0; '
        f'box-shadow: 0 2px 5px rgba(0,0,0,0.12); vertical-align: middle;">👔</div>'
    )


def romaji_to_hiragana(text: str, kanji_name: str = "") -> str:
    """ヘボン式ローマ字の長音省略（O, U等）を補正し、自然で正確な平仮名よみがなを生成する."""
    if not text:
        return ""
    
    # 既にカタカナまたは平仮名が含まれる場合はそのまま返す
    if any('\u3040' <= ch <= '\u30ff' for ch in text):
        return text

    # 特殊な漢字選手名・苗字の例外明示マップ
    clean_k = (kanji_name or "").strip()
    kanji_overrides = {
        "高 宇洋": "こう たかひろ",
        "高宇洋": "こう たかひろ",
        "常盤 亨太": "ときわ きょうた",
        "俵積田 晃太": "たわらつみだ こうた",
        "荒木 遼太郎": "あらき りょうたろう",
    }
    if clean_k in kanji_overrides:
        return kanji_overrides[clean_k]
    for k, v in kanji_overrides.items():
        if k.replace(" ", "").replace("　", "") == clean_k.replace(" ", "").replace("　", ""):
            return v

    table = {
        'kya': 'きゃ', 'kyu': 'きゅ', 'kyo': 'きょ',
        'sha': 'しゃ', 'shu': 'しゅ', 'sho': 'しょ', 'shi': 'し',
        'cha': 'ちゃ', 'chu': 'ちゅ', 'cho': 'ちょ', 'chi': 'ち',
        'tsu': 'つ',
        'nya': 'にゃ', 'nyu': 'にゅ', 'nyo': 'にょ',
        'hya': 'ひゃ', 'hyu': 'ひゅ', 'hyo': 'ひょ',
        'mya': 'みゃ', 'myu': 'みゅ', 'myo': 'みょ',
        'rya': 'りゃ', 'ryu': 'りゅ', 'ryo': 'りょ',
        'gya': 'ぎゃ', 'gyu': 'ぎゅ', 'gyo': 'ぎょ',
        'ja': 'じゃ', 'ju': 'じゅ', 'jo': 'じょ', 'ji': 'じ',
        'bya': 'びゃ', 'byu': 'びゅ', 'byo': 'びょ',
        'pya': 'ぴゃ', 'pyu': 'ぴゅ', 'pyo': 'ぴょ',
        'ka': 'か', 'ki': 'き', 'ku': 'く', 'ke': 'け', 'ko': 'こ',
        'sa': 'さ', 'su': 'す', 'se': 'せ', 'so': 'そ',
        'ta': 'た', 'te': 'て', 'to': 'と',
        'na': 'な', 'ni': 'に', 'nu': 'ぬ', 'ne': 'ね', 'no': 'の',
        'ha': 'は', 'hi': 'ひ', 'fu': 'ふ', 'he': 'へ', 'ho': 'ほ',
        'ma': 'ま', 'mi': 'み', 'mu': 'む', 'me': 'め', 'mo': 'も',
        'ya': 'や', 'yu': 'ゆ', 'yo': 'よ',
        'ra': 'ら', 'ri': 'り', 'ru': 'る', 're': 'れ', 'ro': 'ろ',
        'wa': 'わ', 'wo': 'を', 'nn': 'ん',
        'ga': 'が', 'gi': 'ぎ', 'gu': 'ぐ', 'ge': 'げ', 'go': 'ご',
        'za': 'ざ', 'zu': 'ず', 'ze': 'ぜ', 'zo': 'ぞ',
        'da': 'だ', 'di': 'ぢ', 'du': 'づ', 'de': 'で', 'do': 'ど',
        'ba': 'ば', 'bi': 'び', 'bu': 'ぶ', 'be': 'べ', 'bo': 'ぼ',
        'pa': 'ぱ', 'pi': 'ぴ', 'pu': 'ぷ', 'pe': 'ぺ', 'po': 'ぽ',
        'a': 'あ', 'i': 'い', 'u': 'う', 'e': 'え', 'o': 'お',
        'n': 'ん',
    }
    
    words = text.strip().split()
    converted_words = []
    
    for word_idx, raw_w in enumerate(words):
        w = raw_w.lower()
        is_first_name = (word_idx == len(words) - 1 and len(words) > 1)
        is_family_name = (word_idx == 0 and len(words) > 1)

        # 1. 苗字の漢字連携特例
        if is_family_name:
            if clean_k.startswith("高 ") or clean_k.startswith("高　") or clean_k == "高":
                if w == "ko":
                    converted_words.append("こう")
                    continue
            # 佐藤、加藤、後藤、近藤、遠藤、工藤、安藤、進藤等の「〜藤（-TO）」
            if any(clean_k.startswith(f) for f in ["佐藤", "加藤", "伊藤", "後藤", "近藤", "遠藤", "工藤", "安藤", "進藤", "武藤", "内藤", "斉藤", "齋藤"]):
                if w.endswith("to") and not w.endswith("uto"):
                    w = w[:-2] + "tou"
            # 大迫、大野、大森、大久保等の「大〜（O-）」
            if clean_k.startswith("大") and w.startswith("o") and not w.startswith("oo"):
                w = "oo" + w[1:]

        # 2. 拗音長音の自動復元（人名では kyo, ryo, sho, cho 等は例外なく長音）
        for stem in ['kyo', 'ryo', 'sho', 'cho', 'jyo', 'hyo', 'myo', 'gyo', 'byo', 'pyo']:
            if w.startswith(stem):
                if not w.startswith(stem + 'u') and not w.startswith(stem + 'o'):
                    w = stem + 'u' + w[len(stem):]
            else:
                pattern = r'(?<![a-z])' + stem + r'(?![uo])'
                w = re.sub(pattern, stem + 'u', w)

        # 3. 下の名前の長音自動復元
        if is_first_name:
            for prefix in ['kota', 'koki', 'kosuke', 'kosei', 'kotaro', 'koya', 'koyo']:
                if w.startswith(prefix) and not w.startswith('kou'):
                    w = 'kou' + w[2:]
                    break
            for prefix in ['sota', 'soma', 'sotaro', 'sosuke']:
                if w.startswith(prefix) and not w.startswith('sou'):
                    w = 'sou' + w[2:]
                    break
            for prefix in ['toma', 'toya', 'tosuke']:
                if w.startswith(prefix) and not w.startswith('tou'):
                    w = 'tou' + w[2:]
                    break
            for prefix in ['yuto', 'yuta', 'yuma', 'yuki', 'yusuke', 'yuya', 'yudai', 'yusei', 'yugo', 'yuri']:
                if w.startswith(prefix) and not w.startswith('yuu'):
                    w = 'yuu' + w[2:]
                    break
            for ending in ['taro', 'jiro', 'shiro', 'goro', 'ichiro', 'saburo']:
                if w.endswith(ending):
                    w = w[:-len(ending)] + ending + 'u'
                    break

        res = []
        i = 0
        while i < len(w):
            # 促音 (っ): 子音連続 (例: tt, ss, kk, pp, mm/nn->ん)
            if i + 1 < len(w) and w[i] == w[i+1] and w[i] not in 'aeiouy-':
                if w[i] in 'mn':
                    res.append('ん')
                else:
                    res.append('っ')
                i += 1
                continue
            if w[i:i+3] == 'tch':
                res.append('っ')
                i += 1
                continue
            
            matched = False
            for length in (3, 2, 1):
                part = w[i:i+length]
                if part in table:
                    res.append(table[part])
                    i += length
                    matched = True
                    break
            if not matched:
                res.append(w[i])
                i += 1
        
        res_word = "".join(res)
        # もし未解決のアルファベットが残り、漢字名側にカタカナがある場合は平仮名化して割り当て
        if any('a' <= ch <= 'z' for ch in res_word):
            kanji_parts = clean_k.split()
            if word_idx < len(kanji_parts):
                kp = kanji_parts[word_idx]
                if any('\u30a0' <= ch <= '\u30ff' for ch in kp):
                    res_word = "".join(chr(ord(ch) - 0x60) if '\u30a0' <= ch <= '\u30ff' else ch for ch in kp)
        converted_words.append(res_word)
    
    return " ".join(converted_words)


# ---------------------------------------------------------------------------
# 6. 所属選手ロスターのCBP＆スタッツ集計
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_team_squad_cbp(team_id: str) -> List[Dict[str, Any]]:
    """所属選手の出場時間、得点、アシスト、CBP指標、よみがなを集計する."""
    conn = _get_db()
    cursor = conn.cursor()

    query = """
    SELECT 
        COALESCE(MAX(emp.player_id), pms.player_id) AS resolved_player_id,
        COALESCE(MAX(emp.canonical_name), pms.player_name) AS resolved_player_name,
        COALESCE(MAX(emp.position), MAX(pms.position), 'MF') AS pos,
        COALESCE(MAX(emp.number), MAX(pms.number), 0) AS num,
        MAX(emp.photo_url) AS photo_url,
        MAX(emp.en_name) AS en_name,
        COUNT(DISTINCT pms.match_id) AS matches_count,
        SUM(pms.minutes_played) AS total_minutes,
        SUM(pms.goals) AS goals,
        SUM(pms.assists) AS assists,
        SUM(pms.sprints) AS sprints,
        SUM(pms.cbp_points) AS total_cbp,
        ROUND(AVG(pms.xg), 2) AS avg_xg,
        ROUND(AVG(pms.xa), 2) AS avg_xa
    FROM player_match_stats pms
    LEFT JOIN entity_master_players emp ON (
        pms.player_id = emp.player_id 
        OR (pms.team_id = emp.team_id AND REPLACE(REPLACE(pms.player_name, ' ', ''), '　', '') = REPLACE(REPLACE(emp.canonical_name, ' ', ''), '　', ''))
    )
    WHERE pms.team_id = ?
    GROUP BY COALESCE(emp.player_id, REPLACE(REPLACE(pms.player_name, ' ', ''), '　', ''))
    HAVING total_minutes > 0
    ORDER BY total_cbp DESC, total_minutes DESC
    """
    cursor.execute(query, (team_id.upper(),))
    rows = cursor.fetchall()
    conn.close()

    squad: List[Dict[str, Any]] = []
    for r in rows:
        p_name = r["resolved_player_name"]
        en_name = r["en_name"] or ""
        # 選手名が既にカタカナの場合はカタカナをそのまま、漢字の場合はローマ字から平仮名変換
        if any('\u30a0' <= ch <= '\u30ff' for ch in p_name) and not any('\u4e00' <= ch <= '\u9fff' for ch in p_name):
            yomi = p_name
        else:
            yomi = romaji_to_hiragana(en_name, kanji_name=p_name)

        squad.append({
            "player_id": r["resolved_player_id"],
            "player_name": p_name,
            "yomi": yomi,
            "en_name": en_name,
            "position": r["pos"] or "MF",
            "number": r["num"] or "-",
            "photo_url": r["photo_url"],
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
def load_metric_definitions_55() -> Dict[str, Dict[str, Any]]:
    """全55戦術指標の解説・基準値・反転フラグマスターを読み込む."""
    if not METRIC_DEFS_PATH.exists():
        return {}
    try:
        with open(METRIC_DEFS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load metric definitions: {e}")
        return {}


@st.cache_data(ttl=600)
def get_league_55_metrics_summary() -> Dict[str, Dict[str, Any]]:
    """J1全20クラブの55戦術指標について、最高値・平均値・クラブ別順位を事前集計する."""
    all_metrics = load_all_teams_55_metrics()
    metric_defs = load_metric_definitions_55()
    team_keys = list(TEAM_ID_MAP.keys())

    # 全クラブのシーズン平均を算出
    team_stats: Dict[str, Dict[str, float]] = defaultdict(dict)
    for tid, m_list in all_metrics.items():
        agg: Dict[str, List[float]] = defaultdict(list)
        for m in m_list:
            for k, v in m.items():
                if isinstance(v, (int, float)) and any(c.isdigit() for c in k[:3]):
                    agg[k].append(float(v))
        for k, vs in agg.items():
            if vs:
                team_stats[tid][k] = float(np.mean(vs))

    all_metric_names = sorted(
        list(set(k for tid in team_stats for k in team_stats[tid].keys())),
    )
    summary: Dict[str, Dict[str, Any]] = {}

    for m_name in all_metric_names:
        vals: Dict[str, float] = {}
        for tid in team_keys:
            if m_name in team_stats.get(tid, {}):
                vals[tid] = team_stats[tid][m_name]
        if not vals:
            continue

        m_def = metric_defs.get(m_name, {})
        lower_is_better = m_def.get("lower_is_better", "PPDA" in m_name)

        s = pd.Series(vals)
        ranks = s.rank(ascending=lower_is_better, method="min").to_dict()

        best_tid = str(s.idxmin() if lower_is_better else s.idxmax())
        best_val = float(s[best_tid])
        max_val = float(s.max())
        min_val = float(s.min())
        mean_val = float(s.mean())

        summary[m_name] = {
            "max_val": round(max_val, 2),
            "min_val": round(min_val, 2),
            "mean_val": round(mean_val, 2),
            "best_tid": best_tid,
            "best_team_name": TEAM_ID_MAP.get(best_tid, best_tid),
            "best_val": round(best_val, 2),
            "lower_is_better": lower_is_better,
            "ranks": {tid: int(r) for tid, r in ranks.items()},
            "team_vals": {tid: round(float(v), 2) for tid, v in vals.items()},
        }

    return summary


def _compute_metric_bar_ratio(
    val: float,
    best_val: float,
    max_val: float,
    min_val: float,
    lower_is_better: bool,
) -> float:
    """Jリーグトップを100%とした相対バー比率(0.0〜100.0%)を算出する."""
    if lower_is_better:
        if val > 0 and best_val > 0:
            ratio = (best_val / val) * 100.0
        else:
            ratio = 50.0
    else:
        if best_val > 0:
            ratio = (val / best_val) * 100.0
        else:
            denom = max_val - min_val
            ratio = ((val - min_val) / denom) * 100.0 if denom > 0 else 50.0

    return max(4.0, min(100.0, float(ratio)))


@st.cache_data(ttl=600)
def get_team_55_metrics_categorized(team_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """全55戦術指標を6つの戦術カテゴリに分類し、最新値・シーズン平均・リーグ順位・相対バー比率・解説を返す."""
    all_metrics = load_all_teams_55_metrics()
    matches = all_metrics.get(team_id, [])
    if not matches:
        return {}

    league_summary = get_league_55_metrics_summary()
    metric_defs = load_metric_definitions_55()

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
        "⚽ ポゼッション & パス循環": [
            "04_パス",
            "05_パス",
            "09_ボール支配",
            "10_ポゼッション",
            "35_タッチ関与",
            "36_ビルドアップ",
            "37_有向PageRank",
            "47_ポゼッション補正",
        ],
        "⚔️ チャンス創出 & 前進推進": [
            "01_xG期待値",
            "02_シュート数",
            "03_枠内シュート",
            "11_30mライン",
            "12_PA進入",
            "13_30m→PA",
            "38_攻撃チャンネル",
            "39_ゾーン別",
            "40_アクション価値",
            "41_オンザボール",
            "42_スペース創出",
            "45_1シュート",
            "48_BPI",
        ],
        "🛡️ 守備・プレッシング & 迎撃": [
            "07_クロス成功率",
            "08_ドリブル",
            "17_縦横コンパクト",
            "18_守備プレス強度",
            "29_プレッシング耐性",
            "31_チーム凸包",
            "32_伸縮指数",
            "33_縦横アスペクト",
            "49_プレス誘発",
            "49b_プレス強度",
            "50_守備ブロック",
        ],
        "⚡ フィジカル & 運動量強度": [
            "20_走行距離",
            "20b_スプリント",
            "21_選手間平均距離復元率",
            "52_温熱ストレス",
            "54_ピリオダイゼーション",
        ],
        "🎯 勝敗・期待値 & ゲーム管理": [
            "43_ポアソン",
            "43b_運指数",
            "44_ピタゴラス",
            "46_ベイズ",
            "51_ゲーム状態",
            "53_交替選手",
            "55_マルコフ",
        ],
        "📋 陣形・環境・セットプレー": [
            "06_クロス総数",
            "14_攻撃経路",
            "15_チーム重心",
            "16_チャンス構築",
            "19_シュート枠",
            "22_擬似xG",
            "23_擬似xA",
            "24_マッチ評点",
            "25_ホーム",
            "26_次戦対戦相手適合度",
            "28_セットプレー",
            "30_クロスターゲット",
            "34_ボロノイ",
        ],
    }

    categorized_result: Dict[str, List[Dict[str, Any]]] = {}

    for cat_name, patterns in categories.items():
        items: List[Dict[str, Any]] = []
        for pat in patterns:
            # マッチする指標を探す
            for k in team_mean_map.keys():
                if pat in k:
                    t_val = team_mean_map[k]
                    lat_val = team_latest_map.get(k, t_val)

                    l_info = league_summary.get(k, {})
                    l_val = l_info.get("mean_val", t_val)
                    rank = l_info.get("ranks", {}).get(team_id, 10)
                    best_val = l_info.get("best_val", t_val)
                    best_team = l_info.get("best_team_name", "J1トップ")
                    max_val = l_info.get("max_val", t_val)
                    min_val = l_info.get("min_val", t_val)
                    lower_is_better = l_info.get("lower_is_better", False)

                    bar_ratio = _compute_metric_bar_ratio(
                        val=t_val,
                        best_val=best_val,
                        max_val=max_val,
                        min_val=min_val,
                        lower_is_better=lower_is_better,
                    )

                    m_def = metric_defs.get(k, {})
                    desc = m_def.get("description", "戦術的指標の計測値です。")
                    std_val = m_def.get("standard_val", "リーグ標準水準を参照")

                    items.append({
                        "metric_name": k,
                        "season_avg": round(t_val, 2) if isinstance(t_val, float) else t_val,
                        "latest_val": round(lat_val, 2) if isinstance(lat_val, float) else lat_val,
                        "league_avg": round(l_val, 2) if isinstance(l_val, float) else l_val,
                        "rank": rank,
                        "total_teams": len(TEAM_ID_MAP),
                        "best_val": best_val,
                        "best_team_name": best_team,
                        "max_val": max_val,
                        "min_val": min_val,
                        "bar_ratio": round(bar_ratio, 1),
                        "description": desc,
                        "standard_val": std_val,
                        "lower_is_better": lower_is_better,
                    })
                    break
        categorized_result[cat_name] = items

    return categorized_result
