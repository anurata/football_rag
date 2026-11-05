"""
API endpoints for user match notes and stadium photo uploads.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from api.schemas import (
    NotesListResponse,
    NotesSyncRequest,
    NotesSyncResponse,
    PhotoItem,
    PhotosListResponse,
    PhotoUploadResponse,
    UserNoteItem,
)
from pipeline.db import get_db_connection
from pipeline.storage_adapter import (
    DEFAULT_UPLOAD_DIR,
    get_storage_adapter,
)

router = APIRouter(prefix="/api", tags=["notes_photos"])

# Backward compatibility alias for tests patching UPLOAD_BASE_DIR directly
UPLOAD_BASE_DIR = DEFAULT_UPLOAD_DIR


def _upsert_user_note(
    cursor: sqlite3.Cursor,
    note: UserNoteItem,
) -> None:
    """Insert or update user note by match_id and phase."""
    note_id = note.id or str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO user_match_notes (
            id,
            match_id,
            phase,
            note,
            mom_player_id,
            created_at,
            updated_at,
            is_synced
        ) VALUES (?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP, 1)
        ON CONFLICT(match_id, phase) DO UPDATE SET
            note = excluded.note,
            mom_player_id = excluded.mom_player_id,
            updated_at = CURRENT_TIMESTAMP,
            is_synced = 1;
        """,
        (
            note_id,
            note.match_id,
            note.phase,
            note.note,
            note.mom_player_id,
            note.created_at,
        ),
    )


@router.post("/sync/notes", response_model=NotesSyncResponse)
def sync_user_notes(payload: NotesSyncRequest) -> NotesSyncResponse:
    """Sync pre-match, half-time, or post-match notes."""
    if not payload.notes:
        return NotesSyncResponse(
            success=True,
            synced_count=0,
            message="No notes provided",
        )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for n in payload.notes:
            _upsert_user_note(cursor, n)
        conn.commit()
        return NotesSyncResponse(
            success=True,
            synced_count=len(payload.notes),
            message=f"Synced {len(payload.notes)} notes successfully",
        )
    finally:
        conn.close()


@router.get("/matches/{match_id}/notes", response_model=NotesListResponse)
def get_match_notes(match_id: str) -> NotesListResponse:
    """Get all saved observation notes for a match."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                id,
                match_id,
                phase,
                note,
                mom_player_id,
                created_at,
                updated_at
            FROM user_match_notes
            WHERE match_id = ?
            ORDER BY created_at ASC;
            """,
            (match_id,),
        )
        rows = cursor.fetchall()
        notes = [
            UserNoteItem(
                id=r["id"],
                match_id=r["match_id"],
                phase=r["phase"],
                note=r["note"],
                mom_player_id=r["mom_player_id"],
                created_at=str(r["created_at"]),
                updated_at=str(r["updated_at"]),
            )
            for r in rows
        ]
        return NotesListResponse(
            match_id=match_id,
            notes=notes,
        )
    finally:
        conn.close()


@router.post("/sync/photos", response_model=PhotoUploadResponse)
async def upload_stadium_photo(
    file: UploadFile = File(...),
    match_id: str = Form(...),
    stadium_id: str = Form(...),
    phase: Optional[str] = Form(None),
    caption: Optional[str] = Form(None),
    photo_id: Optional[str] = Form(None),
) -> PhotoUploadResponse:
    """Upload stadium/match photo with metadata."""
    p_id = photo_id or str(uuid.uuid4())
    ext = Path(file.filename or "image.jpg").suffix.lower()
    if not ext or ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".jpg"

    safe_filename = f"{match_id}_{p_id}{ext}"

    # Read binary content and save via configured storage adapter (GCS or Local)
    file_bytes = await file.read()
    adapter = get_storage_adapter(custom_dir=UPLOAD_BASE_DIR)
    stored_url = adapter.save_photo(
        file_bytes=file_bytes,
        filename=safe_filename,
        content_type=file.content_type or "image/jpeg",
    )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_stadium_photos (
                id,
                match_id,
                stadium_id,
                phase,
                file_path,
                caption,
                created_at,
                is_synced
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
            ON CONFLICT(id) DO UPDATE SET
                caption = excluded.caption,
                phase = excluded.phase,
                is_synced = 1;
            """,
            (
                p_id,
                match_id,
                stadium_id,
                phase,
                stored_url,
                caption,
            ),
        )
        conn.commit()

        cursor.execute(
            "SELECT created_at FROM user_stadium_photos WHERE id = ?;",
            (p_id,),
        )
        row = cursor.fetchone()
        created_at_str = str(row["created_at"]) if row else ""

        photo_item = PhotoItem(
            id=p_id,
            match_id=match_id,
            stadium_id=stadium_id,
            phase=phase,
            file_url=stored_url,
            caption=caption,
            created_at=created_at_str,
        )
        return PhotoUploadResponse(
            success=True,
            photo=photo_item,
            message="Photo uploaded and registered successfully",
        )
    finally:
        conn.close()


def _fetch_photos_by_query(
    query: str,
    params: tuple,
) -> List[PhotoItem]:
    """Helper to query photos."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            PhotoItem(
                id=r["id"],
                match_id=r["match_id"],
                stadium_id=r["stadium_id"],
                phase=r["phase"],
                file_url=r["file_path"],
                caption=r["caption"],
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/matches/{match_id}/photos", response_model=PhotosListResponse)
def get_photos_for_match(match_id: str) -> PhotosListResponse:
    """Get all photos taken during or around a match."""
    query = """
        SELECT id, match_id, stadium_id, phase, file_path, caption, created_at
        FROM user_stadium_photos
        WHERE match_id = ?
        ORDER BY created_at DESC;
    """
    items = _fetch_photos_by_query(query, (match_id,))
    return PhotosListResponse(items=items)


@router.get("/stadiums/{stadium_id}/photos", response_model=PhotosListResponse)
def get_photos_for_stadium(stadium_id: str) -> PhotosListResponse:
    """Get all historical gallery photos for a stadium."""
    query = """
        SELECT id, match_id, stadium_id, phase, file_path, caption, created_at
        FROM user_stadium_photos
        WHERE stadium_id = ?
        ORDER BY created_at DESC;
    """
    items = _fetch_photos_by_query(query, (stadium_id,))
    return PhotosListResponse(items=items)
