# Think-Pod MVP — Implementation Plan

## Goal
A web app where you have a real-time voice conversation with AI Chris Williamson. You talk, he responds in his cloned voice. Full transcript saved.

## Architecture

```
Browser                          VPS (this machine)
┌──────────────────┐            ┌─────────────────────────────┐
│                  │            │  FastAPI Server (:8000)      │
│  Hold-to-talk    │──POST────→│                              │
│  button          │  (audio)  │  1. Save audio chunk         │
│                  │            │  2. Groq Whisper STT         │
│                  │            │     audio → text             │
│  Audio playback  │←─────────│  3. Claude API               │
│  + transcript    │  (json+   │     persona prompt + history │
│                  │   audio)  │     → Chris's response text  │
│                  │            │  4. Cartesia TTS             │
│                  │            │     text → mp3 audio         │
│                  │            │  5. Return {audio, text,     │
│                  │            │     user_text}               │
└──────────────────┘            └─────────────────────────────┘
```

## API Design

### `POST /session/start`
Create a new interview session.

**Request:**
```json
{
  "guest_name": "Kush",
  "topic": "early stage startups",
  "podcaster": "chris_williamson"
}
```

**Response:**
```json
{
  "session_id": "abc123",
  "greeting_audio": "<base64 mp3>",
  "greeting_text": "Kush, welcome to Modern Wisdom..."
}
```

### `POST /session/{session_id}/chat`
Send a voice message, get Chris's voice response.

**Request:** `multipart/form-data`
- `audio`: webm/wav audio blob from browser mic

**Response:**
```json
{
  "user_text": "I think revenue is the only signal...",
  "chris_text": "Revenue is the only signal — I love that...",
  "chris_audio": "<base64 mp3>",
  "turn": 3
}
```

### `POST /session/{session_id}/end`
End session and get full transcript.

**Response:**
```json
{
  "transcript_md": "# Session transcript...",
  "themes": ["revenue focus", "distribution vs product", ...],
  "turns": 8
}
```

## File Structure

```
src/
├── server/
│   ├── main.py              # FastAPI app, routes
│   ├── stt.py               # Groq Whisper integration
│   ├── llm.py               # Claude + persona prompt
│   ├── tts.py               # Cartesia TTS integration
│   ├── session.py           # Session state management
│   └── config.py            # API keys, voice IDs, settings
├── voice/
│   ├── voice_config.json    # Voice clone IDs
│   └── samples/             # Audio samples (gitignored)
└── interview/
    └── podcast_session.py   # CLI version (existing)

web/
├── index.html               # Single page app
├── style.css                # Styling
└── app.js                   # Mic recording, API calls, playback
```

## Dependencies

### Python (backend)
```
fastapi
uvicorn
python-multipart
requests
```

### External APIs
| Service | Purpose | Key env var |
|---------|---------|-------------|
| Groq | Whisper STT | `GROQ_API_KEY` |
| Anthropic | Claude (persona LLM) | `ANTHROPIC_API_KEY` |
| Cartesia | TTS voice clone | `CARTESIA_API_KEY` |

### API Keys Location
All keys stored in `src/server/config.py` (gitignored) or loaded from env.

## Frontend Design

### Layout
```
┌──────────────────────────────────┐
│        🎙️ Think-Pod              │
│     Modern Wisdom with Chris     │
├──────────────────────────────────┤
│                                  │
│     ┌────────────────────┐       │
│     │                    │       │
│     │   🔴 Hold to Talk  │       │
│     │                    │       │
│     └────────────────────┘       │
│                                  │
│  Status: Listening... / Thinking │
│                                  │
├──────────────────────────────────┤
│  Transcript                      │
│                                  │
│  🎙️ Chris: Welcome to Modern    │
│  Wisdom, Kush...                 │
│                                  │
│  🗣️ Kush: Yeah, I think the     │
│  most important thing...         │
│                                  │
│  🎙️ Chris: That's interesting   │
│  because...                      │
│                                  │
└──────────────────────────────────┘
```

### Behavior
1. Page loads → calls `/session/start` → plays Chris's greeting
2. User holds button → records from mic
3. User releases → sends audio to `/session/{id}/chat`
4. Shows "Chris is thinking..." while waiting
5. Plays back Chris's audio response
6. Appends both user + Chris text to transcript
7. Repeat until user clicks "End Session"
8. Calls `/session/{id}/end` → shows summary + download transcript

### Audio Recording
- Use `MediaRecorder` API (all modern browsers)
- Record as `audio/webm` (best browser support)
- Send raw blob to server
- Server converts if needed before sending to Groq

## Config

```python
# src/server/config.py
GROQ_API_KEY = "..."
CARTESIA_API_KEY = os.environ.get("CARTESIA_API_KEY", "")
CHRIS_VOICE_ID = "4ec2fc3a-5b02-4868-93df-26a1aa439922"

# LLM — use Claude via OpenClaw's configured auth or direct API
LLM_MODEL = "claude-sonnet-4-20250514"

# Persona prompt loaded from:
PERSONA_PATH = "data/personas/chris_williamson_v2.md"
```

## Implementation Order

### Step 1: Backend core (server/)
1. `config.py` — load all API keys
2. `stt.py` — audio blob → text via Groq
3. `llm.py` — load persona, manage history, generate response
4. `tts.py` — text → audio via Cartesia
5. `session.py` — session state (history, transcript)
6. `main.py` — FastAPI routes wiring it all together

### Step 2: Test backend
- Test each module independently (STT, LLM, TTS)
- Test full chain via curl
- Verify latency: target <3s total (STT ~0.5s + LLM ~1.5s + TTS ~0.5s)

### Step 3: Frontend
1. `index.html` — layout + start session form
2. `app.js` — mic recording, API calls, audio playback, transcript rendering
3. `style.css` — clean, minimal styling

### Step 4: Deploy
1. Run FastAPI on port 8000
2. Serve frontend from FastAPI static files
3. Open port 8000 in ufw (or proxy via nginx with SSL)
4. Test from phone browser

## Latency Budget

| Step | Target | Provider |
|------|--------|----------|
| Audio upload | ~200ms | Network |
| STT | ~500ms | Groq Whisper |
| LLM | ~1500ms | Claude Sonnet |
| TTS | ~300ms | Cartesia Sonic (90ms TTFA + generation) |
| Audio download | ~200ms | Network |
| **Total** | **~2.7s** | |

This is acceptable for v1. Feels like a natural conversational pause. Can optimize later with streaming.

## Future Optimizations (NOT for MVP)
- WebSocket streaming (start playing TTS before LLM finishes)
- VAD (voice activity detection) — auto-detect when user stops talking
- Interrupt handling — user talks while Chris is speaking
- WebRTC for lower latency audio transport
- Edge deployment for reduced network latency
