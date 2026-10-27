"""
tests/test_serve_mobile.py

Unit tests for serve_mobile helper functions.
"""

import unittest
from scripts.serve_mobile import get_local_ip


class TestServeMobile(unittest.TestCase):
    """Test suite for serve_mobile module."""

    def test_get_local_ip(self) -> None:
        """Verify local IP detection returns a valid string."""
        ip = get_local_ip()
        self.assertIsInstance(ip, str)
        self.assertTrue(len(ip.split(".")) == 4)


if __name__ == "__main__":
    unittest.main()
