"""
Storage adapter module for stadium photos and binary artifacts.
Supports local filesystem and Google Cloud Storage (GCS).
"""

from __future__ import annotations

import logging
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_UPLOAD_DIR = Path("data") / "uploads" / "photos"
DEFAULT_GCS_BUCKET = os.getenv("GCS_PHOTO_BUCKET", "football-rag-app-football-rag-data")
DEFAULT_GCS_PREFIX = os.getenv("GCS_PHOTO_PREFIX", "photos")


class BaseStorageAdapter(ABC):
    """Abstract storage adapter interface."""

    @abstractmethod
    def save_photo(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
    ) -> str:
        """
        Save photo binary and return accessible path or URL.

        Args:
            file_bytes: Raw binary bytes of the image.
            filename: Target filename (e.g. 2026_M01_FCT_ZEL_uuid.jpg).
            content_type: MIME type of the file.

        Returns:
            Public URL or local relative path.
        """
        pass

    @abstractmethod
    def get_photo_url(self, stored_path: str) -> str:
        """Resolve full accessible URL from stored path."""
        pass

    @abstractmethod
    def delete_photo(self, stored_path: str) -> bool:
        """Delete photo from storage."""
        pass


class LocalStorageAdapter(BaseStorageAdapter):
    """Local filesystem storage adapter."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or DEFAULT_UPLOAD_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_photo(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
    ) -> str:
        target_path = self.base_dir / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "wb") as f:
            f.write(file_bytes)
        return f"/uploads/photos/{filename}"

    def get_photo_url(self, stored_path: str) -> str:
        if stored_path.startswith("http://") or stored_path.startswith("https://"):
            return stored_path
        if not stored_path.startswith("/"):
            return f"/{stored_path}"
        return stored_path

    def delete_photo(self, stored_path: str) -> bool:
        filename = Path(stored_path).name
        target = self.base_dir / filename
        if target.exists():
            target.unlink()
            return True
        return False


class GCSStorageAdapter(BaseStorageAdapter):
    """Google Cloud Storage adapter."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        prefix: Optional[str] = None,
    ) -> None:
        self.bucket_name = bucket_name or DEFAULT_GCS_BUCKET
        self.prefix = (prefix or DEFAULT_GCS_PREFIX).strip("/")
        self._client = None
        self._bucket = None

    def _get_bucket(self):
        """Lazy load GCS client and bucket instance."""
        if self._bucket is None:
            try:
                from google.cloud import storage
                self._client = storage.Client()
                self._bucket = self._client.bucket(self.bucket_name)
            except Exception as e:
                logger.error(
                    f"Failed to initialize GCS bucket {self.bucket_name}: {e}",
                )
                raise
        return self._bucket

    def save_photo(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
    ) -> str:
        """Upload file directly to GCS bucket."""
        clean_filename = Path(filename).name
        blob_path = f"{self.prefix}/{clean_filename}" if self.prefix else clean_filename

        bucket = self._get_bucket()
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            file_bytes,
            content_type=content_type,
        )

        # Return standard public URL for Cloud Storage object
        return f"https://storage.googleapis.com/{self.bucket_name}/{blob_path}"

    def get_photo_url(self, stored_path: str) -> str:
        if stored_path.startswith("gs://"):
            parts = stored_path[5:].split("/", 1)
            if len(parts) == 2:
                bucket_name, blob_name = parts
                return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
        return stored_path

    def delete_photo(self, stored_path: str) -> bool:
        """Delete blob from GCS."""
        clean_filename = Path(stored_path).name
        blob_path = f"{self.prefix}/{clean_filename}" if self.prefix else clean_filename
        try:
            bucket = self._get_bucket()
            blob = bucket.blob(blob_path)
            if blob.exists():
                blob.delete()
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to delete {blob_path} from GCS: {e}")
            return False


def get_storage_adapter(
    force_local: bool = False,
    custom_dir: Optional[Path] = None,
) -> BaseStorageAdapter:
    """
    Factory function to retrieve the configured storage adapter.
    Falls back gracefully to LocalStorageAdapter if GCS is unavailable.
    """
    if force_local:
        return LocalStorageAdapter(base_dir=custom_dir)

    backend = os.getenv("PHOTO_STORAGE_BACKEND", "").lower().strip()
    gcs_bucket = os.getenv("GCS_PHOTO_BUCKET", "").strip()

    # If backend explicitly requests gcs or GCS_PHOTO_BUCKET is provided
    if backend == "gcs" or (backend != "local" and gcs_bucket):
        try:
            return GCSStorageAdapter(bucket_name=gcs_bucket or DEFAULT_GCS_BUCKET)
        except Exception as e:
            logger.warning(
                f"Falling back to LocalStorageAdapter due to GCS init error: {e}",
            )
            return LocalStorageAdapter(base_dir=custom_dir)

    return LocalStorageAdapter(base_dir=custom_dir)
