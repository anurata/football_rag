"""tests/test_sync_docs_to_nlm.py

scripts/sync_docs_to_nlm.py の単体テスト.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.sync_docs_to_nlm import (
    format_source_title,
    get_first_heading,
    list_local_docs,
    sync_docs,
)


class TestSyncDocsToNLM(unittest.TestCase):
    """sync_docs_to_nlm のロジックテスト."""

    def test_get_first_heading(self):
        """Markdown の第1見出しを正しく取得できるかを検証."""
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# サンプルタイトル\n\n本文テキスト\n## サブ見出し")
            f_path = Path(f.name)

        try:
            heading = get_first_heading(f_path)
            self.assertEqual(heading, "サンプルタイトル")
        finally:
            f_path.unlink()

    def test_format_source_title(self):
        """ファイル名と見出しのフォーマットを検証."""
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# 仕様書見出し\n\n本文")
            f_path = Path(f.name)

        try:
            formatted = format_source_title(f_path)
            self.assertEqual(formatted, f"{f_path.name} | 仕様書見出し")
        finally:
            f_path.unlink()

    def test_list_local_docs(self):
        """ローカルの docs ディレクトリ一覧取得を検証."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dir_path = Path(tmpdir)
            (dir_path / "doc1.md").write_text("# Doc 1", encoding="utf-8")
            (dir_path / "doc2.md").write_text("# Doc 2", encoding="utf-8")
            (dir_path / "ignore.txt").write_text("ignore", encoding="utf-8")

            docs = list_local_docs(dir_path)
            self.assertIn("doc1.md", docs)
            self.assertIn("doc2.md", docs)
            self.assertNotIn("ignore.txt", docs)

    @patch("scripts.sync_docs_to_nlm.add_remote_source")
    @patch("scripts.sync_docs_to_nlm.delete_remote_source")
    @patch("scripts.sync_docs_to_nlm.fetch_remote_sources")
    def test_sync_docs_logic(
        self,
        mock_fetch,
        mock_delete,
        mock_add,
    ):
        """sync_docs の追加・更新・削除判定ロジックを検証."""
        mock_fetch.return_value = [
            {
                "id": "old_id_1",
                "title": "existing.md | 旧タイトル",
            },
            {
                "id": "deleted_id",
                "title": "removed.md | 削除されたドキュメント",
            },
        ]
        mock_add.return_value = True
        mock_delete.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            dir_path = Path(tmpdir)
            (dir_path / "existing.md").write_text("# 新タイトル", encoding="utf-8")
            (dir_path / "brand_new.md").write_text("# 新規", encoding="utf-8")

            stats = sync_docs(alias="test_alias", docs_dir=dir_path)

            # existing.md -> 更新 (old_id_1 削除 & add)
            # brand_new.md -> 新規追加 (add)
            # removed.md -> 削除 (deleted_id 削除)
            self.assertEqual(stats["added"], 1)
            self.assertEqual(stats["updated"], 1)
            self.assertEqual(stats["deleted"], 1)
            self.assertEqual(stats["failed"], 0)

            # delete_remote_source が old_id_1 と deleted_id で呼ばれたか
            self.assertEqual(mock_delete.call_count, 2)
            mock_delete.assert_any_call("old_id_1")
            mock_delete.assert_any_call("deleted_id")

            # add_remote_source が 2回呼ばれたか
            self.assertEqual(mock_add.call_count, 2)


if __name__ == "__main__":
    unittest.main()

