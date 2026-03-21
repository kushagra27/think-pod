"""Speech-to-text via Groq Whisper API."""
import requests
import tempfile
import os
from .config import GROQ_API_KEY


def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Transcribe audio bytes to text using Groq Whisper."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")

    # Write to temp file (Groq needs a file upload)
    suffix = os.path.splitext(filename)[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": (filename, open(tmp_path, "rb"), "audio/webm")},
            data={
                "model": "whisper-large-v3",
                "language": "en",
                "response_format": "json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("text", "").strip()
    finally:
        os.unlink(tmp_path)
