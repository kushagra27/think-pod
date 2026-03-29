"""Session state management for podcast interviews — backed by Supabase."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from . import db
from .config import SESSION_DIR


class Session:
    """Represents an active interview session.

    All mutations write through to the database immediately.
    """

    def __init__(
        self,
        session_id: str,
        guest_name: str,
        topic: str,
        podcaster: str = "chris-williamson",
        user_id: str = "",
        turn: int = 0,
        status: str = "active",
        created_at: str | None = None,
        messages: list[dict] | None = None,
        reflect: bool = False,
        checkpoint_notes: list[str] | None = None,
    ):
        self.session_id = session_id
        self.guest_name = guest_name
        self.topic = topic
        self.podcaster = podcaster
        self.user_id = user_id
        self.turn = turn
        self.status = status
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        # Claude message format [{role, content}]
        self.messages: list[dict] = messages or []
        # Flat transcript for display [{speaker, text, timestamp}]
        self.transcript: list[dict] = []
        # Reflection mode state
        self.reflect: bool = reflect
        self.steering_note: str | None = None
        self.steering_turns_remaining: int = 0
        self.checkpoint_notes: list[str] = checkpoint_notes or []

    def save_checkpoint(self, steering_signal: str):
        """Persist a checkpoint steering signal as a system message in the DB and append a session log file."""
        checkpoint_text = f"[CHECKPOINT {self.turn}] {steering_signal}"
        db.add_message_db(
            self.session_id,
            "system",
            checkpoint_text,
            turn_number=self.turn,
        )
        self.checkpoint_notes.append(steering_signal)
        checkpoint_log = os.path.join(SESSION_DIR, f"{self.session_id}-checkpoints.md")
        with open(checkpoint_log, "a") as f:
            f.write(f"## Checkpoint at turn {self.turn}\n\n")
            f.write(steering_signal.strip())
            f.write("\n\n")

    def add_greeting(self, greeting_text: str):
        """Add the host's opening greeting."""
        user_msg = (
            f"Your guest today is {self.guest_name}. "
            f"They want to discuss: {self.topic}. "
            f"Welcome them warmly and kick things off with your first question."
        )
        self.messages.append({"role": "user", "content": user_msg})
        self.messages.append({"role": "assistant", "content": greeting_text})
        self.transcript.append({
            "speaker": "Host",
            "text": greeting_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Persist the two messages (setup prompt + greeting)
        db.add_message_db(self.session_id, "user", user_msg, turn_number=0)
        db.add_message_db(self.session_id, "assistant", greeting_text, turn_number=0)

    def add_turn(
        self,
        user_text: str,
        chris_text: str,
        stt_ms: int = 0,
        llm_ms: int = 0,
        tts_ms: int = 0,
    ):
        """Add a conversation turn and persist to DB."""
        self.turn += 1
        self.messages.append({"role": "user", "content": user_text})
        self.messages.append({"role": "assistant", "content": chris_text})
        now = datetime.now(timezone.utc).isoformat()
        self.transcript.append({"speaker": self.guest_name, "text": user_text, "timestamp": now})
        self.transcript.append({"speaker": "Host", "text": chris_text, "timestamp": now})
        # Write both messages to DB
        db.add_message_db(self.session_id, "user", user_text, turn_number=self.turn, stt_ms=stt_ms)
        db.add_message_db(self.session_id, "assistant", chris_text, turn_number=self.turn, llm_ms=llm_ms, tts_ms=tts_ms)
        # Bump turn counter in sessions table
        db.update_session_turns(self.session_id, self.turn)

    def get_messages_for_llm(self) -> list[dict]:
        """Get message history for Claude API."""
        return self.messages

    def get_transcript_md(self) -> str:
        """Generate markdown transcript."""
        lines = [
            f"# Think-Pod Session — {self.podcaster} × {self.guest_name}",
            f"# Topic: {self.topic}",
            f"# Date: {self.created_at[:10]}",
            f"# Turns: {self.turn}",
            "",
            "---",
            "",
        ]
        for entry in self.transcript:
            lines.append(f"**{entry['speaker']}:** {entry['text']}")
            lines.append("")
        return "\n".join(lines)

    def get_transcript_text(self) -> str:
        """Get plain text transcript for analysis (checkpoint/post-session)."""
        lines = []
        for entry in self.transcript:
            lines.append(f"**{entry['speaker']}:** {entry['text']}")
            lines.append("")
        return "\n".join(lines)

    def save(self):
        """No-op — all writes happen per-turn now."""
        pass


# ── Public API (backward-compatible) ──────────────────────────────────

def create_session(
    guest_name: str,
    topic: str,
    podcaster: str = "chris-williamson",
    user_id: str = "",
    reflect: bool = False,
) -> Session:
    """Create a new session in the database and return a Session object."""
    row = db.create_session_db(
        user_id=user_id,
        podcaster=podcaster,
        guest_name=guest_name,
        topic=topic,
        reflect=reflect,
    )
    return Session(
        session_id=row["id"],
        guest_name=guest_name,
        topic=topic,
        podcaster=podcaster,
        user_id=user_id,
        turn=0,
        status="active",
        created_at=row["created_at"],
        reflect=reflect,
    )


def get_session(session_id: str) -> Session | None:
    """Load a session from the database, including its message history."""
    row = db.get_session_db(session_id)
    if not row:
        return None
    msgs_rows = db.get_session_messages(session_id)
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in msgs_rows
        if m["role"] in {"user", "assistant"}
    ]
    checkpoint_notes = [
        m["content"].split("] ", 1)[1] if "] " in m["content"] else m["content"]
        for m in msgs_rows
        if m["role"] == "system" and m["content"].startswith("[CHECKPOINT")
    ]
    sess = Session(
        session_id=row["id"],
        guest_name=row["guest_name"],
        topic=row["topic"],
        podcaster=row["podcaster"],
        user_id=row["user_id"],
        turn=row["turns"],
        status=row["status"],
        created_at=row["created_at"],
        messages=messages,
        reflect=row.get("reflect", False),
        checkpoint_notes=checkpoint_notes,
    )
    # Rebuild transcript from messages for display
    for m in msgs_rows:
        if m["role"] == "assistant":
            sess.transcript.append({
                "speaker": "Host",
                "text": m["content"],
                "timestamp": m["created_at"],
            })
        elif m["role"] == "user" and m["turn_number"] > 0:
            sess.transcript.append({
                "speaker": row["guest_name"],
                "text": m["content"],
                "timestamp": m["created_at"],
            })
    return sess


def list_sessions(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """List a user's sessions, newest first."""
    return db.list_user_sessions(user_id, limit=limit, offset=offset)


def end_session(session_id: str) -> None:
    """Mark a session as ended."""
    db.update_session_status(
        session_id,
        "ended",
        extra={"ended_at": datetime.now(timezone.utc).isoformat()},
    )


def delete_session(session_id: str) -> None:
    """Delete a session and its messages."""
    db.delete_session_db(session_id)
