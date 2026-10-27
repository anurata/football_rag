"""SPAIA（spaia.jp）のデータスクレイパー / APIクライアント.

Jリーグの試合における:
- テキスト速報（タイムラインコメント）
- 出場成績（個人詳細スタッツ）
- 試合メタ情報・スコア
を内部API経由で取得し、Raw JSONとして保存する.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class SpaiasoccerScraper:
    """SPAIAサッカーのデータ取得スクレイパー."""

    BASE_URL = "https://spaia.jp"

    def __init__(self, headers: Optional[Dict[str, str]] = None) -> None:
        """スクレイパーを初期化する."""
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }

    def fetch_comments(self, game_id: str) -> List[Dict[str, Any]]:
        """指定されたgame_idのテキスト速報（実況コメント）を取得する.

        Args:
            game_id: 試合ID (例: '2025050301' や '2026102502')

        Returns:
            時系列コメント辞書のリスト
        """
        endpoint = "/football/jleague/api/comment"
        params = {"GameID": game_id}
        data = self._request_api(endpoint, params=params)

        if not isinstance(data, list):
            logger.warning(
                "Unexpected response type for comments: %s",
                type(data),
            )
            return []

        return self._format_comments(data)

    def fetch_player_detail_stats(self, game_id: str) -> List[Dict[str, Any]]:
        """指定されたgame_idの選手出場成績（個人詳細スタッツ）を取得する.

        Args:
            game_id: 試合ID

        Returns:
            全出場選手の個人詳細スタッツ辞書のリスト
        """
        endpoint = "/football/jleague/api/live_player_detail_stats"
        params = {"GameID": game_id}
        data = self._request_api(endpoint, params=params)

        if not isinstance(data, list):
            logger.warning(
                "Unexpected response type for player detail stats: %s",
                type(data),
            )
            return []

        return data

    def fetch_game_meta(self, game_id: str) -> Dict[str, Any]:
        """指定されたgame_idの試合基本情報・スコアを取得する.

        Args:
            game_id: 試合ID

        Returns:
            試合メタ情報の辞書
        """
        endpoint = "/football/jleague/api/live_games"
        params = {"ID": game_id}
        data = self._request_api(endpoint, params=params)

        if isinstance(data, list) and len(data) > 0:
            return data[0]
        elif isinstance(data, dict):
            return data

        return {}

    def save_raw_data(
        self,
        game_id: str,
        output_dir: str = "data/raw/spaia",
        save_game_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """指定試合のコメントと選手詳細スタッツを取得し、JSONとして保存する.

        Args:
            game_id: 取得元試合ID
            output_dir: 出力先ディレクトリ
            save_game_id: 保存ファイル名に使用する試合ID (指定時はこちらで保存)

        Returns:
            保存したファイルパスの辞書
        """
        os.makedirs(output_dir, exist_ok=True)
        target_id = save_game_id or game_id

        comments = self.fetch_comments(game_id)
        player_stats = self.fetch_player_detail_stats(game_id)
        meta = self.fetch_game_meta(game_id)

        comments_path = os.path.join(output_dir, f"{target_id}_comments.json")
        stats_path = os.path.join(output_dir, f"{target_id}_player_stats.json")
        meta_path = os.path.join(output_dir, f"{target_id}_meta.json")

        self._write_json_file(comments_path, {
            "game_id": target_id,
            "count": len(comments),
            "comments": comments,
        })
        self._write_json_file(stats_path, {
            "game_id": target_id,
            "count": len(player_stats),
            "player_stats": player_stats,
        })
        self._write_json_file(meta_path, {
            "game_id": target_id,
            "meta": meta,
        })

        return {
            "comments_path": comments_path,
            "stats_path": stats_path,
            "meta_path": meta_path,
        }

    # -------------------------------------------------------------------------
    # 内部ヘルパーメソッド群（ネストを浅く保つための分割設計）
    # -------------------------------------------------------------------------

    def _request_api(
        self,
        endpoint: str,
        params: Dict[str, Any],
    ) -> Any:
        """SPAIAのREST APIにGETリクエストを送信する."""
        url = f"{self.BASE_URL}{endpoint}"
        req_headers = dict(self.headers)
        # Refererヘッダーを設定
        game_id = params.get("GameID") or params.get("ID") or ""
        req_headers["Referer"] = f"{self.BASE_URL}/football/jleague/j1/game/{game_id}/text"

        try:
            resp = requests.get(
                url,
                params=params,
                headers=req_headers,
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error("Failed to request SPAIA API (%s): %s", url, e)
            return []

    def _format_comments(
        self,
        raw_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """生のコメント配列をタイムライン用に整形する."""
        formatted: List[Dict[str, Any]] = []

        for index, item in enumerate(raw_items):
            entry = self._build_comment_entry(item, index)
            formatted.append(entry)

        return formatted

    def _build_comment_entry(
        self,
        item: Dict[str, Any],
        index: int,
    ) -> Dict[str, Any]:
        """単一のコメント生データから整形辞書を生成する."""
        raw_comment = item.get("CommentInfo_Comment", "")
        state_name = item.get("CommentInfo_StateName", "")
        half = item.get("CommentInfo_Half", "")
        time_label = f"{state_name} ({half})" if half else state_name

        # チーム名と本文の簡易分離（SPAIAは全角スペース「　」で区切る場合がある）
        team_name: Optional[str] = None
        comment_body = raw_comment
        if "　" in raw_comment:
            parts = raw_comment.split("　", 1)
            # 1つ目がチーム名らしき短縮文字列の場合
            if len(parts[0]) <= 8:
                team_name = parts[0]
                comment_body = parts[1]

        return {
            "order": index,
            "id": item.get("ID"),
            "state_name": state_name,
            "half": half,
            "time_label": time_label,
            "team_name": team_name,
            "text": comment_body,
            "raw_comment": raw_comment,
            "created_at": item.get("CreatedAt") or item.get("createdAt"),
        }

    def _write_json_file(self, path: str, data: Any) -> None:
        """JSONファイルへ安全に書き込む."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
