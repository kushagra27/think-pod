"""Text-to-speech via Cartesia API."""
import requests
import base64
from .config import CARTESIA_API_KEY, CHRIS_VOICE_ID, CARTESIA_MODEL


def synthesize(text: str, voice_id: str = None) -> bytes:
    """Convert text to speech, return MP3 bytes."""
    if not CARTESIA_API_KEY:
        raise ValueError("CARTESIA_API_KEY not set")

    voice_id = voice_id or CHRIS_VOICE_ID

    resp = requests.post(
        "https://api.cartesia.ai/tts/bytes",
        headers={
            "X-API-Key": CARTESIA_API_KEY,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json",
        },
        json={
            "model_id": CARTESIA_MODEL,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "output_format": {
                "container": "mp3",
                "bit_rate": 128000,
                "sample_rate": 44100,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content


def synthesize_b64(text: str, voice_id: str = None) -> str:
    """Convert text to speech, return base64-encoded MP3."""
    audio_bytes = synthesize(text, voice_id)
    return base64.b64encode(audio_bytes).decode("utf-8")
