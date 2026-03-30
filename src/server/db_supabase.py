"""Supabase database wrapper for Think-Pod sessions and messages."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from supabase import create_client, Client
from .config import SUPABASE_URL, SUPABASE_SERVICE_KEY

_client: Client | None = None


def _get_client() -> Client:
    """Lazy-init Supabase client with service key (bypasses RLS)."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


# ── Sessions ──────────────────────────────────────────────────────────

def create_session_db(
    user_id: str,
    podcaster: str,
    guest_name: str,
    topic: str,
    reflect: bool = False,
) -> dict[str, Any]:
    """Insert a new session row and return it."""
    client = _get_client()
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "podcaster": podcaster,
        "guest_name": guest_name,
        "topic": topic,
        "status": "active",
        "turns": 0,
        "reflect": reflect,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = client.table("sessions").insert(row).execute()
    return resp.data[0]


def get_session_db(session_id: str) -> dict[str, Any] | None:
    """Fetch a single session by ID."""
    client = _get_client()
    resp = client.table("sessions").select("*").eq("id", session_id).execute()
    return resp.data[0] if resp.data else None


def list_user_sessions(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List sessions for a user, newest first."""
    client = _get_client()
    resp = (
        client.table("sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return resp.data


def update_session_status(
    session_id: str,
    status: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Update session status (and optional extra fields like turns, ended_at)."""
    client = _get_client()
    payload: dict[str, Any] = {"status": status}
    if extra:
        payload.update(extra)
    resp = client.table("sessions").update(payload).eq("id", session_id).execute()
    return resp.data[0] if resp.data else None


def update_session_turns(session_id: str, turns: int) -> None:
    """Bump the turn counter on a session."""
    client = _get_client()
    client.table("sessions").update({"turns": turns}).eq("id", session_id).execute()


def delete_session_db(session_id: str) -> None:
    """Delete a session and its messages."""
    client = _get_client()
    # Delete messages first (FK constraint)
    client.table("messages").delete().eq("session_id", session_id).execute()
    client.table("sessions").delete().eq("id", session_id).execute()


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
    client = _get_client()
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
    resp = client.table("messages").insert(row).execute()
    return resp.data[0]


def get_session_messages(session_id: str) -> list[dict[str, Any]]:
    """Fetch all messages for a session, ordered by creation time."""
    client = _get_client()
    resp = (
        client.table("messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    return resp.data
