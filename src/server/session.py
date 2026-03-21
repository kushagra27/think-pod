"""Session state management for podcast interviews."""
import uuid
import json
import os
from datetime import datetime
from .config import SESSION_DIR


class Session:
    def __init__(self, session_id: str, guest_name: str, topic: str, podcaster: str = "chris_williamson"):
        self.session_id = session_id
        self.guest_name = guest_name
        self.topic = topic
        self.podcaster = podcaster
        self.messages = []  # Claude message format [{role, content}]
        self.transcript = []  # [{speaker, text, timestamp}]
        self.created_at = datetime.utcnow().isoformat()
        self.turn = 0

    def add_greeting(self, greeting_text: str):
        """Add Chris's opening greeting."""
        # Add the setup message and greeting to history
        self.messages.append({
            "role": "user",
            "content": f"Your guest today is {self.guest_name}. They want to discuss: {self.topic}. Welcome them warmly and kick things off with your first question.",
        })
        self.messages.append({"role": "assistant", "content": greeting_text})
        self.transcript.append({
            "speaker": "Chris",
            "text": greeting_text,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def add_turn(self, user_text: str, chris_text: str):
        """Add a conversation turn."""
        self.turn += 1
        self.messages.append({"role": "user", "content": user_text})
        self.messages.append({"role": "assistant", "content": chris_text})
        self.transcript.append({
            "speaker": self.guest_name,
            "text": user_text,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.transcript.append({
            "speaker": "Chris",
            "text": chris_text,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_messages_for_llm(self) -> list[dict]:
        """Get message history for Claude API."""
        return self.messages

    def get_transcript_md(self) -> str:
        """Generate markdown transcript."""
        lines = [
            f"# Think-Pod Session — Chris Williamson × {self.guest_name}",
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

    def save(self):
        """Save session to disk."""
        path = os.path.join(SESSION_DIR, f"{self.session_id}.json")
        with open(path, "w") as f:
            json.dump({
                "session_id": self.session_id,
                "guest_name": self.guest_name,
                "topic": self.topic,
                "podcaster": self.podcaster,
                "messages": self.messages,
                "transcript": self.transcript,
                "created_at": self.created_at,
                "turn": self.turn,
            }, f, indent=2)


# In-memory session store
_sessions: dict[str, Session] = {}


def create_session(guest_name: str, topic: str, podcaster: str = "chris_williamson") -> Session:
    session_id = uuid.uuid4().hex[:12]
    session = Session(session_id, guest_name, topic, podcaster)
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> Session | None:
    return _sessions.get(session_id)
