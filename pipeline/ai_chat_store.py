"""
pipeline/ai_chat_store.py

Persistent store for ubiquitous AI Tactical Chat sessions and message history.
Backed by SQLite, allowing seamless resumption of conversations across views.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pipeline.db import DEFAULT_DB_PATH, get_db_connection, init_db

logger = logging.getLogger(__name__)


class AIChatStore:
    """Manages persistence of AI chat sessions and messages in SQLite."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Ensure database tables exist."""
        conn = init_db(self.db_path)
        conn.close()

    def create_or_get_session(
        self,
        session_id: Optional[str] = None,
        title: str = "新規対話",
        view_type: str = "GLOBAL",
        section_key: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fetch existing session or create a new one."""
        sid = session_id or str(uuid.uuid4())
        existing = self.get_session(sid)
        if existing is not None:
            return existing

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        ctx_json = json.dumps(context_data or {}, ensure_ascii=False)
        now_str = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO ai_chat_sessions (
                session_id, title, view_type, section_key,
                context_data_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                sid,
                title,
                view_type,
                section_key,
                ctx_json,
                now_str,
                now_str,
            ),
        )
        conn.commit()
        conn.close()

        return {
            "session_id": sid,
            "title": title,
            "view_type": view_type,
            "section_key": section_key,
            "context_data": context_data or {},
            "created_at": now_str,
            "updated_at": now_str,
            "messages": [],
        }

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a session by ID including all messages in chronological order."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT session_id, title, view_type, section_key,
                   context_data_json, created_at, updated_at
            FROM ai_chat_sessions
            WHERE session_id = ?;
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        cursor.execute(
            """
            SELECT id, role, content, metadata_json, created_at
            FROM ai_chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC, id ASC;
            """,
            (session_id,),
        )
        msg_rows = cursor.fetchall()
        conn.close()

        messages = [
            {
                "id": m["id"],
                "role": m["role"],
                "content": m["content"],
                "metadata": json.loads(m["metadata_json"] or "{}"),
                "created_at": m["created_at"],
            }
            for m in msg_rows
        ]

        return {
            "session_id": row["session_id"],
            "title": row["title"],
            "view_type": row["view_type"],
            "section_key": row["section_key"],
            "context_data": json.loads(row["context_data_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "messages": messages,
        }

    def list_sessions(
        self,
        view_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List sessions ordered by updated_at descending with message counts."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT s.session_id, s.title, s.view_type, s.section_key,
                   s.context_data_json, s.created_at, s.updated_at,
                   COUNT(m.id) AS message_count,
                   (
                       SELECT content
                       FROM ai_chat_messages
                       WHERE session_id = s.session_id
                       ORDER BY created_at DESC, id DESC
                       LIMIT 1
                   ) AS last_message
            FROM ai_chat_sessions s
            LEFT JOIN ai_chat_messages m ON s.session_id = m.session_id
        """
        params: List[Any] = []
        if view_type:
            query += " WHERE s.view_type = ? "
            params.append(view_type)

        query += """
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
            LIMIT ?;
        """
        params.append(limit)

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()

        results = []
        for r in rows:
            results.append(
                {
                    "session_id": r["session_id"],
                    "title": r["title"],
                    "view_type": r["view_type"],
                    "section_key": r["section_key"],
                    "context_data": json.loads(r["context_data_json"] or "{}"),
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "message_count": r["message_count"],
                    "last_message": r["last_message"] or "",
                },
            )
        return results

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Append a message to the session and update the session's updated_at timestamp."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        now_str = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO ai_chat_messages (
                session_id, role, content, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?);
            """,
            (
                session_id,
                role,
                content,
                meta_json,
                now_str,
            ),
        )
        msg_id = cursor.lastrowid or 0

        # Update updated_at of session
        cursor.execute(
            """
            UPDATE ai_chat_sessions
            SET updated_at = ?
            WHERE session_id = ?;
            """,
            (
                now_str,
                session_id,
            ),
        )

        conn.commit()
        conn.close()
        return msg_id

    def update_session_title(self, session_id: str, new_title: str) -> bool:
        """Update the title of a session."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE ai_chat_sessions
            SET title = ?, updated_at = ?
            WHERE session_id = ?;
            """,
            (
                new_title,
                datetime.now().isoformat(),
                session_id,
            ),
        )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and cascade delete its messages."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM ai_chat_sessions
            WHERE session_id = ?;
            """,
            (session_id,),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted
