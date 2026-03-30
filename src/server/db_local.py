"""Local SQLite database backend for Think-Pod (no Supabase dependency)."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import DB_PATH

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    """Lazy-init SQLite connection with WAL mode."""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'local',
            podcaster TEXT NOT NULL,
            guest_name TEXT NOT NULL DEFAULT 'Guest',
            topic TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            turns INTEGER NOT NULL DEFAULT 0,
            reflect INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            ended_at TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            turn_number INTEGER NOT NULL DEFAULT 0,
            stt_ms INTEGER NOT NULL DEFAULT 0,
            llm_ms INTEGER NOT NULL DEFAULT 0,
            tts_ms INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
    """)
    conn.commit()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    d = dict(row)
    # Convert reflect from int back to bool for compatibility
    if "reflect" in d:
        d["reflect"] = bool(d["reflect"])
    return d


# ── Sessions ──────────────────────────────────────────────────────────

def create_session_db(
    user_id: str,
    podcaster: str,
    guest_name: str,
    topic: str,
    reflect: bool = False,
) -> dict[str, Any]:
    """Insert a new session row and return it."""
    conn = _get_conn()
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "podcaster": podcaster,
        "guest_name": guest_name,
        "topic": topic,
        "status": "active",
        "turns": 0,
        "reflect": int(reflect),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    conn.execute(
        """INSERT INTO sessions (id, user_id, podcaster, guest_name, topic, status, turns, reflect, created_at)
           VALUES (:id, :user_id, :podcaster, :guest_name, :topic, :status, :turns, :reflect, :created_at)""",
        row,
    )
    conn.commit()
    row["reflect"] = reflect  # return bool, not int
    return row


def get_session_db(session_id: str) -> dict[str, Any] | None:
    """Fetch a single session by ID."""
    conn = _get_conn()
    cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    return _row_to_dict(row)


def list_user_sessions(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List sessions for a user, newest first."""
    conn = _get_conn()
    cursor = conn.execute(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset),
    )
    return [_row_to_dict(r) for r in cursor.fetchall()]


def update_session_status(
    session_id: str,
    status: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Update session status (and optional extra fields)."""
    conn = _get_conn()
    fields = {"status": status}
    if extra:
        fields.update(extra)
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [session_id]
    conn.execute(f"UPDATE sessions SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return get_session_db(session_id)


def update_session_turns(session_id: str, turns: int) -> None:
    """Bump the turn counter on a session."""
    conn = _get_conn()
    conn.execute("UPDATE sessions SET turns = ? WHERE id = ?", (turns, session_id))
    conn.commit()


def delete_session_db(session_id: str) -> None:
    """Delete a session and its messages."""
    conn = _get_conn()
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()


# ── Messages ──────────────────────────────────────────────────────────

def add_message_db(
    session_id: str,
    role: str,
    content: str,
    turn_number: int = 0,
    stt_ms: int = 0,
    llm_ms: int = 0,
    tts_ms: int = 0,
) -> dict[str, Any]:
    """Insert a single message row."""
    conn = _get_conn()
    row = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": role,
        "content": content,
        "turn_number": turn_number,
        "stt_ms": stt_ms,
        "llm_ms": llm_ms,
        "tts_ms": tts_ms,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    conn.execute(
        """INSERT INTO messages (id, session_id, role, content, turn_number, stt_ms, llm_ms, tts_ms, created_at)
           VALUES (:id, :session_id, :role, :content, :turn_number, :stt_ms, :llm_ms, :tts_ms, :created_at)""",
        row,
    )
    conn.commit()
    return row


def get_session_messages(session_id: str) -> list[dict[str, Any]]:
    """Fetch all messages for a session, ordered by creation time."""
    conn = _get_conn()
    cursor = conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    return [_row_to_dict(r) for r in cursor.fetchall()]
