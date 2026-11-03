"""docs/ ディレクトリの全仕様書を NotebookLM の管理ノートブックへ自動同期するスクリプト.

機能:
1. docs/*.md を走査
2. NotebookLM 上の既存ソース一覧を取得
3. 既存の同名ソースがあれば削除して最新版をアップロード（差分上書き）
4. 新規ファイルは追加
5. 削除されたファイルはリモートからも削除
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("sync_docs_to_nlm")

DOCS_DIR = Path("docs")
NOTEBOOK_ALIAS = "football_rag_docs"


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


def fetch_remote_sources(alias: str = NOTEBOOK_ALIAS) -> List[Dict]:
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


def sync_docs(
    alias: str = NOTEBOOK_ALIAS,
    docs_dir: Path = DOCS_DIR,
) -> Dict[str, int]:
    """docs/ ディレクトリのファイルを NotebookLM と同期する."""
    local_docs = list_local_docs(docs_dir)
    remote_sources = fetch_remote_sources(alias)

    # リモートのタイトルプレフィックス (ファイル名) から既存ソースをマップ
    remote_map: Dict[str, Dict] = {}
    for s in remote_sources:
        title = s.get("title", "")
        # タイトルが "filename.md | ..." または "filename.md" の形式
        filename = title.split(" | ")[0].strip()
        remote_map[filename] = s

    stats = {
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "failed": 0,
    }

    # 1. ローカルファイルの追加または更新
    for filename, path in local_docs.items():
        title = format_source_title(path)
        if filename in remote_map:
            # 既存ソースが存在する場合は一旦削除して再登録（差分更新）
            old_id = remote_map[filename].get("id")
            logger.info("更新対象: %s (旧ID: %s)", filename, old_id)
            if old_id:
                delete_remote_source(old_id)
            ok = add_remote_source(alias, path, title)
            if ok:
                stats["updated"] += 1
            else:
                stats["failed"] += 1
        else:
            # 新規追加
            logger.info("新規追加対象: %s", filename)
            ok = add_remote_source(alias, path, title)
            if ok:
                stats["added"] += 1
            else:
                stats["failed"] += 1

    # 2. ローカルに存在しないリモートソースのクリーンアップ
    for filename, s in remote_map.items():
        if filename not in local_docs:
            old_id = s.get("id")
            logger.info("ローカル未存在のため削除: %s (ID: %s)", filename, old_id)
            if old_id:
                if delete_remote_source(old_id):
                    stats["deleted"] += 1
                else:
                    stats["failed"] += 1

    logger.info("同期完了: %s", stats)
    return stats


if __name__ == "__main__":
    alias_arg = sys.argv[1] if len(sys.argv) > 1 else NOTEBOOK_ALIAS
    sync_docs(alias_arg)

