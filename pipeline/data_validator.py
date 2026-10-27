"""生データ完全性バリデーションモジュール (Data Integrity Validator).

data/raw/ 配下の生データが、ダミーや欠損のない「本物の完全実データ」であることを
厳格に検証し、不正データ混入を Fail-Fast で防止する.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


class InvalidRawDataError(ValueError):
    """生データが仕様を満たさない、またはダミーデータである場合に送出される例外."""
    pass


# -----------------------------------------------------------------------------
# 閾値定数
# -----------------------------------------------------------------------------
MIN_BYTES_SPAIA_PLAYER_STATS = 30000
MIN_BYTES_SPAIA_COMMENTS = 30000
MIN_BYTES_FOOTBALL_LAB = 40000
MIN_BYTES_YAHOO_TEXT = 20000
MIN_BYTES_YAHOO_STATS = 20000

REQUIRED_SPAIA_PLAYER_KEYS = (
    "Uni",
    "HV",
    "Pos",
    "StartF",
    "Time",
    "At3rdPlayCount",
    "M30PlayCount",
    "PAPlayCount",
    "PassDirection1Count",
    "PassDirection1Success",
)

REQUIRED_FLAB_CBP_KEYS = (
    "attack",
    "defense",
    "gain",
)


# -----------------------------------------------------------------------------
# 内部ヘルパー関数（ネストを浅く保つための分離設計）
# -----------------------------------------------------------------------------
def _check_file_size(file_path: str, min_bytes: int, label: str) -> int:
    """ファイルが存在し、規定の最小バイト数以上であることを検証する."""
    if not os.path.exists(file_path):
        raise InvalidRawDataError(f"[{label}] ファイルが存在しません: {file_path}")

    size = os.path.getsize(file_path)
    if size < min_bytes:
        raise InvalidRawDataError(
            f"[{label}] ファイルサイズが不足しています ({size} bytes < {min_bytes} bytes). "
            f"ダミーデータの可能性があります: {file_path}",
        )
    return size


def _load_json_safely(file_path: str, label: str) -> Dict[str, Any]:
    """JSONファイルを安全に読み込む."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise InvalidRawDataError(f"[{label}] ルートは辞書型である必要があります: {file_path}")
        return data
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise InvalidRawDataError(f"[{label}] JSONパースに失敗しました: {e} ({file_path})") from e


# -----------------------------------------------------------------------------
# 個別バリデータ関数群
# -----------------------------------------------------------------------------
def validate_spaia_player_stats(file_path: str) -> Dict[str, Any]:
    """SPAIAの選手詳細スタッツ生データを厳格に検証する."""
    _check_file_size(file_path, MIN_BYTES_SPAIA_PLAYER_STATS, "SPAIA Player Stats")
    data = _load_json_safely(file_path, "SPAIA Player Stats")

    # 1. 禁止キー（ダミーデータ判定）
    if "stats_summary" in data:
        raise InvalidRawDataError(
            f"[SPAIA Player Stats] 禁止キー 'stats_summary' が存在します。"
            f"これはダミーファイルの形式です: {file_path}",
        )

    # 2. player_stats 配列の存在と件数
    player_stats = data.get("player_stats")
    if not isinstance(player_stats, list):
        raise InvalidRawDataError(
            f"[SPAIA Player Stats] 'player_stats' リストが存在しません: {file_path}",
        )

    if len(player_stats) < 20:
        raise InvalidRawDataError(
            f"[SPAIA Player Stats] 登録選手数が不足しています ({len(player_stats)} < 20名): {file_path}",
        )

    # 3. 各選手オブジェクトの必須キー検査
    for i, p in enumerate(player_stats):
        if not isinstance(p, dict):
            raise InvalidRawDataError(f"[SPAIA Player Stats] 選手インデックス {i} が辞書ではありません")
        for key in REQUIRED_SPAIA_PLAYER_KEYS:
            if key not in p:
                raise InvalidRawDataError(
                    f"[SPAIA Player Stats] 選手 '{p.get('Name', i)}' に必須キー '{key}' が存在しません",
                )

    return data


def validate_spaia_comments(file_path: str) -> Dict[str, Any]:
    """SPAIAの実況速報コメント生データを厳格に検証する."""
    _check_file_size(file_path, MIN_BYTES_SPAIA_COMMENTS, "SPAIA Comments")
    data = _load_json_safely(file_path, "SPAIA Comments")

    comments = data.get("comments")
    if not isinstance(comments, list):
        raise InvalidRawDataError(f"[SPAIA Comments] 'comments' リストが存在しません: {file_path}")

    if len(comments) < 40:
        raise InvalidRawDataError(
            f"[SPAIA Comments] コメント件数が少なすぎます ({len(comments)} < 40件): {file_path}",
        )

    first_item = comments[0]
    for key in ("order", "state_name", "half", "text"):
        if key not in first_item:
            raise InvalidRawDataError(f"[SPAIA Comments] コメント要素に必須キー '{key}' がありません")

    return data


def validate_football_lab_data(file_path: str) -> Dict[str, Any]:
    """Football LABの試合生データを厳格に検証する."""
    _check_file_size(file_path, MIN_BYTES_FOOTBALL_LAB, "Football LAB")
    data = _load_json_safely(file_path, "Football LAB")

    inner_data = data.get("data")
    if not isinstance(inner_data, dict):
        raise InvalidRawDataError(f"[Football LAB] 'data' オブジェクトが存在しません: {file_path}")

    # 1. CBP player_matrix の検査
    cbp = inner_data.get("cbp", {})
    player_matrix = cbp.get("player_matrix") if isinstance(cbp, dict) else None
    if not isinstance(player_matrix, list) or len(player_matrix) < 20:
        actual_count = len(player_matrix) if isinstance(player_matrix, list) else 0
        raise InvalidRawDataError(
            f"[Football LAB] 'cbp.player_matrix' の選手数が不足しています ({actual_count} < 20): {file_path}",
        )

    for key in REQUIRED_FLAB_CBP_KEYS:
        if key not in player_matrix[0]:
            raise InvalidRawDataError(f"[Football LAB] player_matrix に必須CBPキー '{key}' がありません")

    # 2. timeline_blocks の検査 (全6フェーズ)
    timeline_blocks = inner_data.get("timeline_blocks")
    if not isinstance(timeline_blocks, list) or len(timeline_blocks) < 6:
        actual_blocks = len(timeline_blocks) if isinstance(timeline_blocks, list) else 0
        raise InvalidRawDataError(
            f"[Football LAB] 'timeline_blocks' は全6フェーズ必要です (実際: {actual_blocks}): {file_path}",
        )

    return data


def validate_yahoo_text(file_path: str) -> Dict[str, Any]:
    """Yahoo!サッカーの速報タイムライン生データを厳格に検証する."""
    _check_file_size(file_path, MIN_BYTES_YAHOO_TEXT, "Yahoo Text")
    data = _load_json_safely(file_path, "Yahoo Text")

    timeline = data.get("timeline")
    if not isinstance(timeline, list) or len(timeline) < 40:
        actual_count = len(timeline) if isinstance(timeline, list) else 0
        raise InvalidRawDataError(
            f"[Yahoo Text] 'timeline' イベント件数が不足しています ({actual_count} < 40件): {file_path}",
        )

    first_item = timeline[0]
    for key in ("time", "text", "is_goal", "is_card", "is_substitution"):
        if key not in first_item:
            raise InvalidRawDataError(f"[Yahoo Text] timeline要素に必須キー '{key}' がありません")

    return data


# -----------------------------------------------------------------------------
# 試合単位の一括バリデータ
# -----------------------------------------------------------------------------
def validate_match_data_bundle(
    game_id: str,
    raw_dir: str = "data/raw",
) -> Dict[str, Any]:
    """指定されたgame_idの全生データ（SPAIA選手・コメント、FootballLAB、Yahoo速報）を一括検証する.

    いずれか1つでも不備がある場合は InvalidRawDataError を送出する.
    """
    spaia_stats_path = os.path.join(raw_dir, "spaia", f"{game_id}_player_stats.json")
    spaia_comments_path = os.path.join(raw_dir, "spaia", f"{game_id}_comments.json")
    flab_path = os.path.join(raw_dir, "football_lab", f"{game_id}.json")
    yahoo_text_path = os.path.join(raw_dir, "yahoo", f"{game_id}_text.json")

    results = {
        "game_id": game_id,
        "spaia_player_stats": validate_spaia_player_stats(spaia_stats_path),
        "spaia_comments": validate_spaia_comments(spaia_comments_path),
        "football_lab": validate_football_lab_data(flab_path),
        "yahoo_text": validate_yahoo_text(yahoo_text_path),
    }

    return results
