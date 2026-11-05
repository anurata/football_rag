"""
Unit and integration tests for storage adapters and GCS photo persistence.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from api.main import app
import pipeline.db as db_module
from pipeline.db import get_db_connection, init_db
from pipeline.storage_adapter import (
    BaseStorageAdapter,
    GCSStorageAdapter,
    LocalStorageAdapter,
    get_storage_adapter,
)


class TestStorageAdapter(unittest.TestCase):
    """Test suite for LocalStorageAdapter and GCSStorageAdapter."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.upload_dir = Path(self.temp_dir) / "photos"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_local_storage_adapter_save_and_delete(self) -> None:
        """Verify local adapter saves binary file and deletes it."""
        adapter = LocalStorageAdapter(base_dir=self.upload_dir)
        dummy_bytes = b"\xff\xd8\xff\xe0dummy_jpeg_content"
        filename = "test_photo_01.jpg"

        url = adapter.save_photo(
            file_bytes=dummy_bytes,
            filename=filename,
            content_type="image/jpeg",
        )

        # Check URL and file on disk
        self.assertEqual(url, f"/uploads/photos/{filename}")
        saved_file = self.upload_dir / filename
        self.assertTrue(saved_file.exists())
        self.assertEqual(saved_file.read_bytes(), dummy_bytes)

        # Test URL resolution
        resolved_url = adapter.get_photo_url(url)
        self.assertEqual(resolved_url, f"/uploads/photos/{filename}")

        # Delete photo
        deleted = adapter.delete_photo(url)
        self.assertTrue(deleted)
        self.assertFalse(saved_file.exists())

    @patch("google.cloud.storage.Client")
    def test_gcs_storage_adapter_save_and_delete(
        self,
        mock_storage_client_cls: MagicMock,
    ) -> None:
        """Verify GCS adapter uploads to bucket blob and resolves public URL."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_storage_client_cls.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True

        adapter = GCSStorageAdapter(
            bucket_name="my-test-bucket",
            prefix="stadium_photos",
        )

        dummy_bytes = b"fake_photo_bytes"
        filename = "2026_M01_test.jpg"

        url = adapter.save_photo(
            file_bytes=dummy_bytes,
            filename=filename,
            content_type="image/jpeg",
        )

        expected_url = (
            "https://storage.googleapis.com/my-test-bucket/stadium_photos/2026_M01_test.jpg"
        )
        self.assertEqual(url, expected_url)

        # Verify blob upload called with correct bytes and mime type
        mock_bucket.blob.assert_called_with("stadium_photos/2026_M01_test.jpg")
        mock_blob.upload_from_string.assert_called_once_with(
            dummy_bytes,
            content_type="image/jpeg",
        )

        # Test get_photo_url
        gs_url = "gs://my-test-bucket/stadium_photos/2026_M01_test.jpg"
        self.assertEqual(adapter.get_photo_url(gs_url), expected_url)

        # Test delete
        deleted = adapter.delete_photo(expected_url)
        self.assertTrue(deleted)
        mock_blob.delete.assert_called_once()

    def test_factory_fallback_to_local(self) -> None:
        """Verify factory returns LocalStorageAdapter when GCS is not configured."""
        with patch.dict(os.environ, {}, clear=True):
            adapter = get_storage_adapter(force_local=True, custom_dir=self.upload_dir)
            self.assertIsInstance(adapter, LocalStorageAdapter)

    @patch("google.cloud.storage.Client")
    def test_factory_selects_gcs_when_env_configured(
        self,
        mock_storage_client_cls: MagicMock,
    ) -> None:
        """Verify factory returns GCSStorageAdapter when env variables are present."""
        env = {
            "PHOTO_STORAGE_BACKEND": "gcs",
            "GCS_PHOTO_BUCKET": "custom-photo-bucket",
        }
        with patch.dict(os.environ, env, clear=True):
            adapter = get_storage_adapter()
            self.assertIsInstance(adapter, GCSStorageAdapter)
            self.assertEqual(adapter.bucket_name, "custom-photo-bucket")


class TestApiGCSPhotoIntegration(unittest.TestCase):
    """Integration test for API /api/sync/photos with GCS backend."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_football.db")

        self.db_patcher = patch.object(db_module, "DEFAULT_DB_PATH", self.test_db_path)
        self.db_patcher.start()

        init_db(self.test_db_path)
        self._seed_test_match()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.db_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _seed_test_match(self) -> None:
        conn = get_db_connection(self.test_db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO matches (
                match_id, season, matchweek, date, home_team_id, away_team_id,
                home_score, away_score, stadium, weather
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "2026_M01_FCT_ZEL",
                2026,
                1,
                "2026-02-23",
                "FCT",
                "ZEL",
                2,
                1,
                "味の素スタジアム",
                "晴",
            ),
        )
        conn.commit()
        conn.close()

    @patch("google.cloud.storage.Client")
    def test_upload_photo_persists_to_gcs_and_database(
        self,
        mock_storage_client_cls: MagicMock,
    ) -> None:
        """Ensure POST /api/sync/photos stores GCS URL in DB when backend=gcs."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_storage_client_cls.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        env = {
            "PHOTO_STORAGE_BACKEND": "gcs",
            "GCS_PHOTO_BUCKET": "football-rag-app-football-rag-data",
        }
        with patch.dict(os.environ, env, clear=True):
            file_content = b"sample_stadium_photo_binary"
            response = self.client.post(
                "/api/sync/photos",
                data={
                    "match_id": "2026_M01_FCT_ZEL",
                    "stadium_id": "STAD_AJINOMOTO",
                    "phase": "pre-match",
                    "caption": "Sunny stadium entrance",
                    "photo_id": "photo_test_gcs_001",
                },
                files={
                    "file": ("entrance.jpg", file_content, "image/jpeg"),
                },
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["photo"]["id"], "photo_test_gcs_001")

            expected_gcs_url = (
                "https://storage.googleapis.com/football-rag-app-football-rag-data/photos/"
                "2026_M01_FCT_ZEL_photo_test_gcs_001.jpg"
            )
            self.assertEqual(data["photo"]["file_url"], expected_gcs_url)

            # Verify saved record in SQLite database
            conn = get_db_connection(self.test_db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT file_path, caption FROM user_stadium_photos WHERE id = ?;",
                ("photo_test_gcs_001",),
            )
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["file_path"], expected_gcs_url)
            self.assertEqual(row["caption"], "Sunny stadium entrance")
            conn.close()


if __name__ == "__main__":
    unittest.main()
