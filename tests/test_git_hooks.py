"""tests/test_git_hooks.py

Git Hooks セットアップおよび post-commit スクリプトの単体テスト.
"""

import tempfile
import unittest
from pathlib import Path

from scripts.setup_git_hooks import (
    install_hook,
    setup_all_hooks,
    uninstall_hook,
)


class TestGitHooks(unittest.TestCase):
    """Git Hooks セットアップのテスト."""

    def test_post_commit_script_integrity(self):
        """post-commit スクリプトが必須のコマンドとロジックを含んでいるか検証."""
        source_hook = Path("scripts") / "hooks" / "post-commit"
        self.assertTrue(source_hook.exists(), "scripts/hooks/post-commit が存在しません")

        content = source_hook.read_text(encoding="utf-8")
        self.assertIn("CHANGED_DOCS", content)
        self.assertIn("docs/", content)
        self.assertIn("scripts/sync_docs_to_nlm.py", content)
        self.assertIn("powershell.exe", content)

    def test_install_and_uninstall_hook(self):
        """フックのインストールとアンインストールのライフサイクルを検証."""
        with tempfile.TemporaryDirectory() as tmp_source:
            with tempfile.TemporaryDirectory() as tmp_target:
                src_dir = Path(tmp_source)
                tgt_dir = Path(tmp_target)

                # テスト用フック作成
                test_hook = src_dir / "post-commit"
                test_hook.write_text("#!/bin/sh\necho test\n", encoding="utf-8")

                # インストール検証
                ok = install_hook("post-commit", source_dir=src_dir, target_dir=tgt_dir)
                self.assertTrue(ok)
                installed_file = tgt_dir / "post-commit"
                self.assertTrue(installed_file.exists())
                self.assertEqual(installed_file.read_text(encoding="utf-8"), "#!/bin/sh\necho test\n")

                # アンインストール検証
                ok_un = uninstall_hook("post-commit", target_dir=tgt_dir)
                self.assertTrue(ok_un)
                self.assertFalse(installed_file.exists())

    def test_install_missing_source(self):
        """存在しないフック元のエラーハンドリングを検証."""
        with tempfile.TemporaryDirectory() as tmp_source:
            with tempfile.TemporaryDirectory() as tmp_target:
                ok = install_hook("missing-hook", source_dir=Path(tmp_source), target_dir=Path(tmp_target))
                self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
