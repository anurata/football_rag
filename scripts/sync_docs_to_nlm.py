"""docs/ ディレクトリの全仕様書を NotebookLM の管理ノートブックへ自動同期するスクリプト.

機能:
1. docs/*.md を走査
2. NotebookLM 上の既存ソース一覧を取得
3. SHA256ハッシュによる変更検知（未変更ファイルはスキップして高速化・クォータ節約）
4. 変更があった仕様書のみ旧ソース削除＆最新版アップロード（差分上書き）
5. 新規ファイルは追加
6. 削除されたファイルはリモートからも削除
7. --dry-run / --force フラグ対応
"""

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("sync_docs_to_nlm")

DOCS_DIR = Path("docs")
DEFAULT_NOTEBOOK_ALIAS = "football_rag_docs"
DEFAULT_CACHE_PATH = Path(".nlm_sync_cache.json")


def get_nlm_command_path() -> str:
    """nlm コマンドのパスを取得する."""
    local_bin = Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "nlm.EXE"
    if local_bin.exists():
        return str(local_bin)
    return "nlm"


def run_command(args: List[str]) -> subprocess.CompletedProcess:
    """コマンドを実行し、結果を返すヘルパー."""
    nlm_cmd = get_nlm_command_path()
    full_args = [nlm_cmd] + args
    return subprocess.run(
        full_args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def compute_file_hash(file_path: Path) -> str:
    """ファイルの SHA256 ハッシュを計算する."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_sync_cache(cache_path: Path = DEFAULT_CACHE_PATH) -> Dict[str, Any]:
    """同期キャッシュファイルを読み込む."""
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("キャッシュ読み込み失敗 (新規作成します): %s", e)
        return {}


def save_sync_cache(cache: Dict[str, Any], cache_path: Path = DEFAULT_CACHE_PATH) -> None:
    """同期キャッシュファイルを保存する."""
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("キャッシュ保存失敗: %s", e)


def fetch_remote_sources(alias: str = DEFAULT_NOTEBOOK_ALIAS) -> List[Dict[str, Any]]:
    """NotebookLM 上の既存ソース一覧を JSON で取得する."""
    res = run_command(["list", "sources", alias, "--json"])
    if res.returncode != 0:
        logger.error("ソース一覧の取得に失敗しました: %s", res.stderr)
        return []
    try:
        return json.loads(res.stdout.strip())
    except Exception as e:
        logger.error("JSONパースエラー: %s (出力: %s)", e, res.stdout)
        return []


def get_first_heading(file_path: Path) -> Optional[str]:
    """Markdownファイルの最初の見出し (# ...) を取得する."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("# "):
                    return stripped[2:].strip()
    except Exception:
        pass
    return None


def format_source_title(file_path: Path) -> str:
    """ファイル名と見出しからソースタイトルを生成する."""
    heading = get_first_heading(file_path)
    if heading:
        return f"{file_path.name} | {heading}"
    return file_path.name


def list_local_docs(docs_dir: Path = DOCS_DIR) -> Dict[str, Path]:
    """docs/ ディレクトリ内の Markdown ファイル一覧（ファイル名 -> パス）を取得する."""
    if not docs_dir.exists():
        logger.warning("ディレクトリが存在しません: %s", docs_dir)
        return {}

    docs_map: Dict[str, Path] = {}
    for p in docs_dir.glob("*.md"):
        docs_map[p.name] = p
    return docs_map


def build_remote_source_map(remote_sources: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """リモートソース一覧からファイル名キーの辞書を作成する."""
    remote_map: Dict[str, Dict[str, Any]] = {}
    for s in remote_sources:
        title = s.get("title", "")
        filename = title.split(" | ")[0].strip()
        remote_map[filename] = s
    return remote_map


def delete_remote_source(source_id: str) -> bool:
    """リモートのソースを削除する."""
    res = run_command(["source", "delete", source_id, "--confirm"])
    if res.returncode == 0:
        logger.info("旧ソース削除完了: %s", source_id)
        return True
    logger.error("旧ソース削除失敗: %s (%s)", source_id, res.stderr)
    return False


def add_remote_source(alias: str, file_path: Path, title: str) -> bool:
    """ローカルファイルをソースとしてアップロードする."""
    res = run_command(
        [
            "source",
            "add",
            alias,
            "--file",
            str(file_path),
            "--title",
            title,
            "--wait",
        ],
    )
    if res.returncode == 0:
        logger.info("ソース追加完了: %s -> %s", file_path.name, title)
        return True
    logger.error("ソース追加失敗: %s (%s)", file_path.name, res.stderr)
    return False


def plan_sync_actions(
    local_docs: Dict[str, Path],
    remote_map: Dict[str, Dict[str, Any]],
    cache: Dict[str, Any],
    force: bool = False,
) -> Dict[str, List[Any]]:
    """同期計画（追加、更新、スキップ、削除）を作成する."""
    plan: Dict[str, List[Any]] = {
        "to_add": [],
        "to_update": [],
        "to_skip": [],
        "to_delete": [],
    }

    cached_files = cache.get("files", {})

    for filename, path in local_docs.items():
        current_hash = compute_file_hash(path)
        is_in_remote = filename in remote_map
        cached_info = cached_files.get(filename, {})
        is_hash_matched = cached_info.get("hash") == current_hash

        if not is_in_remote:
            plan["to_add"].append({
                "filename": filename,
                "path": path,
                "hash": current_hash,
            })
        elif force or not is_hash_matched:
            plan["to_update"].append({
                "filename": filename,
                "path": path,
                "hash": current_hash,
                "old_id": remote_map[filename].get("id"),
            })
        else:
            plan["to_skip"].append({
                "filename": filename,
                "path": path,
                "hash": current_hash,
            })

    for filename, s in remote_map.items():
        if filename not in local_docs:
            plan["to_delete"].append({
                "filename": filename,
                "id": s.get("id"),
            })

    return plan


def execute_sync_actions(
    alias: str,
    plan: Dict[str, List[Any]],
    cache: Dict[str, Any],
    cache_path: Path,
) -> Dict[str, int]:
    """同期計画を実行し、結果統計を返す."""
    stats = {
        "added": 0,
        "updated": 0,
        "skipped": len(plan["to_skip"]),
        "deleted": 0,
        "failed": 0,
    }

    cached_files = cache.setdefault("files", {})

    # 1. 新規追加
    for item in plan["to_add"]:
        filename = item["filename"]
        path = item["path"]
        title = format_source_title(path)
        logger.info("[ADD] 新規追加対象: %s", filename)
        if add_remote_source(alias, path, title):
            stats["added"] += 1
            cached_files[filename] = {
                "hash": item["hash"],
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            stats["failed"] += 1

    # 2. 変更分更新
    for item in plan["to_update"]:
        filename = item["filename"]
        path = item["path"]
        title = format_source_title(path)
        old_id = item["old_id"]
        logger.info("[UPDATE] 変更検出のため更新: %s (旧ID: %s)", filename, old_id)
        if old_id:
            delete_remote_source(old_id)
        if add_remote_source(alias, path, title):
            stats["updated"] += 1
            cached_files[filename] = {
                "hash": item["hash"],
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            stats["failed"] += 1

    # 3. 削除対象
    for item in plan["to_delete"]:
        filename = item["filename"]
        source_id = item["id"]
        logger.info("[DELETE] ローカル不在のため削除: %s (ID: %s)", filename, source_id)
        if source_id and delete_remote_source(source_id):
            stats["deleted"] += 1
            cached_files.pop(filename, None)
        else:
            stats["failed"] += 1

    save_sync_cache(cache, cache_path)
    return stats


def sync_docs(
    alias: str = DEFAULT_NOTEBOOK_ALIAS,
    docs_dir: Path = DOCS_DIR,
    cache_path: Path = DEFAULT_CACHE_PATH,
    dry_run: bool = False,
    force: bool = False,
) -> Dict[str, int]:
    """docs/ ディレクトリのファイルを NotebookLM とスマート同期する."""
    local_docs = list_local_docs(docs_dir)
    remote_sources = fetch_remote_sources(alias)
    remote_map = build_remote_source_map(remote_sources)
    cache = load_sync_cache(cache_path)

    plan = plan_sync_actions(local_docs, remote_map, cache, force=force)

    logger.info(
        "同期計画: 新規 %d 件, 更新 %d 件, スキップ %d 件, 削除 %d 件",
        len(plan["to_add"]),
        len(plan["to_update"]),
        len(plan["to_skip"]),
        len(plan["to_delete"]),
    )

    if dry_run:
        logger.info("[DRY-RUN] 変更は適用されません。")
        for item in plan["to_add"]:
            logger.info("  [PLAN ADD] %s", item["filename"])
        for item in plan["to_update"]:
            logger.info("  [PLAN UPDATE] %s", item["filename"])
        for item in plan["to_skip"]:
            logger.info("  [PLAN SKIP] %s", item["filename"])
        for item in plan["to_delete"]:
            logger.info("  [PLAN DELETE] %s", item["filename"])
        return {
            "added": len(plan["to_add"]),
            "updated": len(plan["to_update"]),
            "skipped": len(plan["to_skip"]),
            "deleted": len(plan["to_delete"]),
            "failed": 0,
        }

    stats = execute_sync_actions(alias, plan, cache, cache_path)
    logger.info("同期完了: %s", stats)
    return stats


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する."""
    parser = argparse.ArgumentParser(
        description="docs/ の仕様書を NotebookLM とスマート差分同期するスクリプト",
    )
    parser.add_argument(
        "--alias",
        type=str,
        default=DEFAULT_NOTEBOOK_ALIAS,
        help=f"対象の NotebookLM エイリアス (デフォルト: {DEFAULT_NOTEBOOK_ALIAS})",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=DOCS_DIR,
        help="仕様書ディレクトリのパス",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="同期キャッシュのパス",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際のアップロード・削除を行わず計画のみ表示する",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="ハッシュ一致に関わらず全件強制再同期する",
    )
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = parse_args()
    sync_docs(
        alias=cli_args.alias,
        docs_dir=cli_args.docs_dir,
        cache_path=cli_args.cache_path,
        dry_run=cli_args.dry_run,
        force=cli_args.force,
    )
