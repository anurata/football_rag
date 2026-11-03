"""Git Hooks 自動登録スクリプト.

機能:
1. scripts/hooks/post-commit を .git/hooks/post-commit へインストール
2. 実行権限の付与 (Unix系: chmod +x)
3. --uninstall オプションによる解除対応
"""

import argparse
import logging
import os
import shutil
import stat
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("setup_git_hooks")

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT_HOOKS_DIR = REPO_ROOT / ".git" / "hooks"
SOURCE_HOOKS_DIR = REPO_ROOT / "scripts" / "hooks"


def get_git_hooks_dir(repo_root: Path = REPO_ROOT) -> Path:
    """Gitのhooksディレクトリパスを取得する."""
    return repo_root / ".git" / "hooks"


def install_hook(
    hook_name: str,
    source_dir: Path = SOURCE_HOOKS_DIR,
    target_dir: Path = GIT_HOOKS_DIR,
) -> bool:
    """指定されたフックファイルを .git/hooks へインストールする."""
    source_file = source_dir / hook_name
    target_file = target_dir / hook_name

    if not source_file.exists():
        logger.error("フック元ファイルが存在しません: %s", source_file)
        return False

    if not target_dir.exists():
        logger.error(".git/hooks ディレクトリが見つかりません: %s", target_dir)
        return False

    try:
        shutil.copyfile(source_file, target_file)
        # 実行権限を付与 (chmod +x 相当)
        current_mode = target_file.stat().st_mode
        target_file.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        logger.info("Hook インストール成功: %s -> %s", source_file.name, target_file)
        return True
    except Exception as e:
        logger.error("Hook インストール失敗: %s", e)
        return False


def uninstall_hook(
    hook_name: str,
    target_dir: Path = GIT_HOOKS_DIR,
) -> bool:
    """指定されたフックファイルを .git/hooks から削除する."""
    target_file = target_dir / hook_name
    if not target_file.exists():
        logger.info("削除対象の Hook は存在しません: %s", target_file)
        return True

    try:
        target_file.unlink()
        logger.info("Hook 削除完了: %s", target_file)
        return True
    except Exception as e:
        logger.error("Hook 削除失敗: %s", e)
        return False


def setup_all_hooks(
    repo_root: Path = REPO_ROOT,
    uninstall: bool = False,
) -> bool:
    """全フックのセットアップまたはアンインストールを実行する."""
    hooks_dir = get_git_hooks_dir(repo_root)
    source_dir = repo_root / "scripts" / "hooks"

    target_hooks = ["post-commit"]
    success = True

    for hook_name in target_hooks:
        if uninstall:
            if not uninstall_hook(hook_name, target_dir=hooks_dir):
                success = False
        else:
            if not install_hook(hook_name, source_dir=source_dir, target_dir=hooks_dir):
                success = False

    return success


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する."""
    parser = argparse.ArgumentParser(description="Git Hooks 自動登録スクリプト")
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="登録済み Hook を削除する",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    ok = setup_all_hooks(uninstall=args.uninstall)
    if ok:
        action_name = "削除" if args.uninstall else "登録"
        logger.info("Git Hooks の%sが正常に完了しました。", action_name)
    else:
        sys.exit(1)
