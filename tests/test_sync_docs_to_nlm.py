"""tests/test_sync_docs_to_nlm.py

scripts/sync_docs_to_nlm.py の単体テスト.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.sync_docs_to_nlm import (
    compute_file_hash,
    format_source_title,
    get_first_heading,
    list_local_docs,
    load_sync_cache,
    plan_sync_actions,
    save_sync_cache,
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

    def test_compute_file_hash(self):
        """SHA256ハッシュの計算精度を検証."""
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("Test Hash Content")
            f_path = Path(f.name)

        try:
            h1 = compute_file_hash(f_path)
            self.assertEqual(len(h1), 64)
            # 同じ内容なら同じハッシュ
            h2 = compute_file_hash(f_path)
            self.assertEqual(h1, h2)
        finally:
            f_path.unlink()

    def test_cache_load_and_save(self):
        """キャッシュの保存と読み込みを検証."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache.json"
            empty_cache = load_sync_cache(cache_file)
            self.assertEqual(empty_cache, {})

            sample_data = {
                "files": {
                    "doc1.md": {"hash": "abc1234", "last_synced_at": "2026-11-03T00:00:00Z"},
                },
            }
            save_sync_cache(sample_data, cache_file)
            loaded = load_sync_cache(cache_file)
            self.assertEqual(loaded, sample_data)

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

    def test_plan_sync_actions(self):
        """スマート差分計画（add, update, skip, delete）の判定精度を検証."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dir_path = Path(tmpdir)
            p_unchanged = dir_path / "unchanged.md"
            p_modified = dir_path / "modified.md"
            p_new = dir_path / "new.md"

            p_unchanged.write_text("# Unchanged", encoding="utf-8")
            p_modified.write_text("# Modified Content v2", encoding="utf-8")
            p_new.write_text("# Brand New", encoding="utf-8")

            local_docs = {
                "unchanged.md": p_unchanged,
                "modified.md": p_modified,
                "new.md": p_new,
            }

            remote_map = {
                "unchanged.md": {"id": "id_unchanged", "title": "unchanged.md"},
                "modified.md": {"id": "id_modified", "title": "modified.md"},
                "deleted.md": {"id": "id_deleted", "title": "deleted.md"},
            }

            cache = {
                "files": {
                    "unchanged.md": {"hash": compute_file_hash(p_unchanged)},
                    "modified.md": {"hash": "old_different_hash"},
                },
            }

            # 1. 通常計画
            plan = plan_sync_actions(local_docs, remote_map, cache, force=False)
            self.assertEqual(len(plan["to_add"]), 1)
            self.assertEqual(plan["to_add"][0]["filename"], "new.md")

            self.assertEqual(len(plan["to_update"]), 1)
            self.assertEqual(plan["to_update"][0]["filename"], "modified.md")

            self.assertEqual(len(plan["to_skip"]), 1)
            self.assertEqual(plan["to_skip"][0]["filename"], "unchanged.md")

            self.assertEqual(len(plan["to_delete"]), 1)
            self.assertEqual(plan["to_delete"][0]["filename"], "deleted.md")

            # 2. force=True 時はスキップ対象も更新へ回る
            plan_force = plan_sync_actions(local_docs, remote_map, cache, force=True)
            self.assertEqual(len(plan_force["to_update"]), 2)
            self.assertEqual(len(plan_force["to_skip"]), 0)

    @patch("scripts.sync_docs_to_nlm.add_remote_source")
    @patch("scripts.sync_docs_to_nlm.delete_remote_source")
    @patch("scripts.sync_docs_to_nlm.fetch_remote_sources")
    def test_sync_docs_dry_run(
        self,
        mock_fetch,
        mock_delete,
        mock_add,
    ):
        """dry_run 時に実際のアップロード・削除が実行されないことを検証."""
        mock_fetch.return_value = [
            {"id": "id_old", "title": "doc.md | タイトル"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            dir_path = Path(tmpdir)
            cache_file = dir_path / "cache.json"
            (dir_path / "doc.md").write_text("# 更新内容", encoding="utf-8")

            stats = sync_docs(
                alias="test_alias",
                docs_dir=dir_path,
                cache_path=cache_file,
                dry_run=True,
            )

            self.assertEqual(stats["updated"], 1)
            self.assertEqual(mock_add.call_count, 0)
            self.assertEqual(mock_delete.call_count, 0)
            self.assertFalse(cache_file.exists())

    @patch("scripts.sync_docs_to_nlm.add_remote_source")
    @patch("scripts.sync_docs_to_nlm.delete_remote_source")
    @patch("scripts.sync_docs_to_nlm.fetch_remote_sources")
    def test_sync_docs_execution_and_cache_update(
        self,
        mock_fetch,
        mock_delete,
        mock_add,
    ):
        """実行時に正しくリモート連携され、キャッシュが更新されることを検証."""
        mock_fetch.return_value = [
            {"id": "old_id_1", "title": "existing.md | 旧タイトル"},
            {"id": "deleted_id", "title": "removed.md | 削除対象"},
        ]
        mock_add.return_value = True
        mock_delete.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            dir_path = Path(tmpdir)
            cache_file = dir_path / "cache.json"

            (dir_path / "existing.md").write_text("# 新タイトル", encoding="utf-8")
            (dir_path / "brand_new.md").write_text("# 新規", encoding="utf-8")

            stats = sync_docs(
                alias="test_alias",
                docs_dir=dir_path,
                cache_path=cache_file,
                dry_run=False,
            )

            self.assertEqual(stats["added"], 1)
            self.assertEqual(stats["updated"], 1)
            self.assertEqual(stats["deleted"], 1)
            self.assertEqual(stats["failed"], 0)

            # キャッシュが保存されていること
            self.assertTrue(cache_file.exists())
            saved_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            self.assertIn("existing.md", saved_cache.get("files", {}))
            self.assertIn("brand_new.md", saved_cache.get("files", {}))
            self.assertNotIn("removed.md", saved_cache.get("files", {}))


if __name__ == "__main__":
    unittest.main()
