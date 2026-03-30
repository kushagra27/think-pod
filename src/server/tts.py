"""Text-to-speech via Cartesia API with per-podcaster voice."""
import requests
import base64
import json
import os
from .config import CARTESIA_API_KEY, CARTESIA_MODEL, BASE_DIR

_VOICE_MAP = None


def _load_voice_map() -> dict:
    """Load voice IDs from podcasters.json."""
    global _VOICE_MAP
    if _VOICE_MAP is not None:
        return _VOICE_MAP
    path = os.path.join(BASE_DIR, "data", "podcasters.json")
    with open(path) as f:
        podcasters = json.load(f)
    _VOICE_MAP = {}
    for pid, info in podcasters.items():
        voice = info.get("voice", {})
        _VOICE_MAP[pid] = voice.get("voice_id", "")
    return _VOICE_MAP


def get_voice_id(podcaster_id: str) -> str:
    """Get Cartesia voice ID for a podcaster."""
    voice_map = _load_voice_map()
    return voice_map.get(podcaster_id, voice_map.get("chris-williamson", ""))


def synthesize(text: str, podcaster_id: str = "chris-williamson") -> bytes:
    """Convert text to speech, return MP3 bytes."""
    if not CARTESIA_API_KEY:
        raise ValueError("CARTESIA_API_KEY not set")

    voice_id = get_voice_id(podcaster_id)
    if not voice_id:
        raise ValueError(f"No voice configured for {podcaster_id}")

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


def synthesize_b64(text: str, podcaster_id: str = "chris-williamson") -> str:
    """Convert text to speech, return base64-encoded MP3. Returns empty string if TTS unavailable."""
    if not CARTESIA_API_KEY:
        return ""
    audio_bytes = synthesize(text, podcaster_id)
    return base64.b64encode(audio_bytes).decode("utf-8")
