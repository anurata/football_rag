"""
Unit tests for GCP Cloud Run deployment configuration and environment overrides.
"""

import os
import unittest
from pathlib import Path


class TestGCPConfig(unittest.TestCase):
    """Test suite for GCP deployment settings, Docker configs, and environment variable fallbacks."""

    def setUp(self):
        self.root_dir = Path(__file__).resolve().parent.parent
        self.orig_football_db_path = os.environ.get("FOOTBALL_DB_PATH")
        self.orig_chroma_persist_dir = os.environ.get("CHROMA_PERSIST_DIR")

    def tearDown(self):
        # Restore environment variables
        if self.orig_football_db_path is not None:
            os.environ["FOOTBALL_DB_PATH"] = self.orig_football_db_path
        else:
            os.environ.pop("FOOTBALL_DB_PATH", None)

        if self.orig_chroma_persist_dir is not None:
            os.environ["CHROMA_PERSIST_DIR"] = self.orig_chroma_persist_dir
        else:
            os.environ.pop("CHROMA_PERSIST_DIR", None)

    def test_dockerfile_and_dockerignore_configuration(self):
        """Verify Dockerfile and .dockerignore exist and enforce data separation & security."""
        dockerfile_path = self.root_dir / "Dockerfile"
        dockerignore_path = self.root_dir / ".dockerignore"

        self.assertTrue(dockerfile_path.exists(), "Dockerfile must exist.")
        self.assertTrue(dockerignore_path.exists(), ".dockerignore must exist.")

        dockerfile_content = dockerfile_path.read_text(encoding="utf-8")
        self.assertIn("python:3.11-slim", dockerfile_content)
        self.assertIn("EXPOSE 8080", dockerfile_content)
        self.assertIn("appuser", dockerfile_content)

        dockerignore_content = dockerignore_path.read_text(encoding="utf-8")
        # Ensure data separation and secret protection
        self.assertIn("data/", dockerignore_content)
        self.assertIn(".env", dockerignore_content)
        self.assertIn(".git/", dockerignore_content)

    def test_docker_entrypoint_script(self):
        """Verify docker entrypoint handles both streamlit and api modes."""
        entrypoint_path = self.root_dir / "scripts" / "docker_entrypoint.sh"
        self.assertTrue(entrypoint_path.exists(), "docker_entrypoint.sh must exist.")

        content = entrypoint_path.read_text(encoding="utf-8")
        self.assertIn("APP_MODE", content)
        self.assertIn("uvicorn api.main:app", content)
        self.assertIn("streamlit run app.py", content)
        self.assertIn("PORT", content)
        self.assertIn("/mnt/gcs", content)
        self.assertIn("ln -sfn", content)

    def test_gcp_deploy_script(self):
        """Verify PowerShell deployment script contains volume mount and required parameters."""
        deploy_script = self.root_dir / "scripts" / "gcp_deploy.ps1"
        self.assertTrue(deploy_script.exists(), "gcp_deploy.ps1 must exist.")

        content = deploy_script.read_text(encoding="utf-8")
        self.assertIn("cloud-storage", content)
        self.assertIn("--add-volume-mount", content)
        self.assertIn("FOOTBALL_DB_PATH=/mnt/gcs/football.db", content)
        self.assertIn("CHROMA_PERSIST_DIR=/mnt/gcs/chroma_db", content)
        self.assertIn("AppMode", content)
        self.assertIn("football-rag-api", content)
        self.assertIn("SkipBuild", content)
        self.assertIn("PHOTO_STORAGE_BACKEND=gcs", content)
        self.assertIn("GCS_PHOTO_BUCKET=", content)

    def test_env_db_path_override(self):
        """Test that FOOTBALL_DB_PATH environment variable overrides default SQLite path."""
        import importlib
        import pipeline.db
        import pipeline.team_analytics_engine

        custom_path = "/tmp/test_custom_football.db"
        os.environ["FOOTBALL_DB_PATH"] = custom_path

        importlib.reload(pipeline.db)
        importlib.reload(pipeline.team_analytics_engine)
        self.assertEqual(pipeline.db.DEFAULT_DB_PATH, custom_path)
        self.assertEqual(str(pipeline.team_analytics_engine.DB_PATH), str(Path(custom_path)))

    def test_env_chroma_dir_override(self):
        """Test that CHROMA_PERSIST_DIR environment variable overrides default ChromaDB directory."""
        import importlib
        import pipeline.vector_indexer

        custom_chroma_dir = "/tmp/test_custom_chroma"
        os.environ["CHROMA_PERSIST_DIR"] = custom_chroma_dir

        importlib.reload(pipeline.vector_indexer)
        self.assertEqual(pipeline.vector_indexer.DEFAULT_CHROMA_DIR, custom_chroma_dir)


if __name__ == "__main__":
    unittest.main()
