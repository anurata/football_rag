"""
tests/test_ai_chat_store.py

Unit tests for AIChatStore persistence layer (sessions and message history).
"""

import os
import tempfile
import unittest

from pipeline.ai_chat_store import AIChatStore


class TestAIChatStore(unittest.TestCase):
    """Test suite for AIChatStore."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_chat.db")
        self.store = AIChatStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_and_get_session(self) -> None:
        """Verify creating a new session and retrieving it."""
        session = self.store.create_or_get_session(
            session_id="session_test_01",
            title="FC東京 vs 町田 採点QA",
            view_type="MATCH",
            section_key="ratings",
            context_data={"match_id": "2026102505", "team_id": "FCT"},
        )
        self.assertEqual(session["session_id"], "session_test_01")
        self.assertEqual(session["title"], "FC東京 vs 町田 採点QA")
        self.assertEqual(session["view_type"], "MATCH")
        self.assertEqual(session["context_data"]["match_id"], "2026102505")

        fetched = self.store.get_session("session_test_01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], "FC東京 vs 町田 採点QA")
        self.assertEqual(len(fetched["messages"]), 0)

    def test_add_messages_and_retrieval(self) -> None:
        """Verify message addition and chronological ordering."""
        self.store.create_or_get_session(
            session_id="session_test_02",
            title="町田のプレッシング分析",
            view_type="TEAM",
            section_key="profile",
            context_data={"team_id": "ZEL"},
        )

        msg_id1 = self.store.add_message(
            session_id="session_test_02",
            role="user",
            content="町田のハイプレス成功率は？",
        )
        msg_id2 = self.store.add_message(
            session_id="session_test_02",
            role="assistant",
            content="敵陣ボール奪取率はリーグ2位の48.2%です。",
            metadata={"sources": ["football_lab"]},
        )
        self.assertGreater(msg_id1, 0)
        self.assertGreater(msg_id2, msg_id1)

        session = self.store.get_session("session_test_02")
        self.assertEqual(len(session["messages"]), 2)
        self.assertEqual(session["messages"][0]["role"], "user")
        self.assertEqual(session["messages"][0]["content"], "町田のハイプレス成功率は？")
        self.assertEqual(session["messages"][1]["role"], "assistant")
        self.assertEqual(session["messages"][1]["metadata"]["sources"], ["football_lab"])

    def test_list_sessions_and_filtering(self) -> None:
        """Verify listing sessions with sorting and optional filtering."""
        self.store.create_or_get_session(
            session_id="s_match",
            title="試合QA",
            view_type="MATCH",
        )
        self.store.create_or_get_session(
            session_id="s_team",
            title="チームQA",
            view_type="TEAM",
        )

        self.store.add_message(
            session_id="s_match",
            role="user",
            content="最新の試合について質問",
        )

        all_sessions = self.store.list_sessions()
        self.assertEqual(len(all_sessions), 2)
        # s_match was updated after s_team due to add_message
        self.assertEqual(all_sessions[0]["session_id"], "s_match")
        self.assertEqual(all_sessions[0]["message_count"], 1)
        self.assertEqual(all_sessions[0]["last_message"], "最新の試合について質問")

        team_sessions = self.store.list_sessions(view_type="TEAM")
        self.assertEqual(len(team_sessions), 1)
        self.assertEqual(team_sessions[0]["session_id"], "s_team")

    def test_update_title_and_delete_session(self) -> None:
        """Verify updating title and deleting a session."""
        self.store.create_or_get_session(
            session_id="s_del",
            title="初期タイトル",
            view_type="GLOBAL",
        )
        self.store.add_message(
            session_id="s_del",
            role="user",
            content="テストメッセージ",
        )

        self.store.update_session_title("s_del", "更新後タイトル")
        session = self.store.get_session("s_del")
        self.assertEqual(session["title"], "更新後タイトル")

        self.store.delete_session("s_del")
        self.assertIsNone(self.store.get_session("s_del"))


if __name__ == "__main__":
    unittest.main()

