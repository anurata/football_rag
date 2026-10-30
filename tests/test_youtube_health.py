"""
Unit tests for YouTube Transcript API health check and rate limit handling.
"""

import unittest
from unittest.mock import patch
from scripts.ingest_youtube_tactics import YouTubeRateLimitError


def check_youtube_api_available(sample_video_id: str = "04sbclmheZk") -> bool:
    """Check if YouTube Transcript API is available without IpBlocked."""
    from scripts.ingest_youtube_tactics import fetch_video_transcript
    try:
        res = fetch_video_transcript(sample_video_id)
        return res is not None and len(res) > 0
    except YouTubeRateLimitError:
        return False
    except Exception:
        return False


class TestYouTubeHealth(unittest.TestCase):
    """Test suite for YouTube Transcript API availability and circuit breaker."""

    def test_youtube_api_available_success(self):
        """Verify returns True when transcript is fetched successfully."""
        with patch("scripts.ingest_youtube_tactics.fetch_video_transcript") as mock_fetch:
            mock_fetch.return_value = [{"text": "テスト戦術", "start": 0.0, "duration": 2.0}]
            self.assertTrue(check_youtube_api_available("dummy_vid"))

    def test_youtube_api_available_rate_limited(self):
        """Verify returns False when rate limited / IpBlocked."""
        with patch("scripts.ingest_youtube_tactics.fetch_video_transcript") as mock_fetch:
            mock_fetch.side_effect = YouTubeRateLimitError("Rate limited on dummy: IpBlocked")
            self.assertFalse(check_youtube_api_available("dummy_vid"))

    def test_youtube_api_available_none(self):
        """Verify returns False when no transcript is found."""
        with patch("scripts.ingest_youtube_tactics.fetch_video_transcript") as mock_fetch:
            mock_fetch.return_value = None
            self.assertFalse(check_youtube_api_available("dummy_vid"))


if __name__ == "__main__":
    unittest.main()
