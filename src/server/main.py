"""Think-Pod — FastAPI server with Supabase auth."""
import os
import time
from datetime import datetime, timezone

import jwt
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from . import stt, llm, tts, session
from .config import SUPABASE_URL, SUPABASE_ANON_KEY

app = FastAPI(title="Think-Pod", version="0.3.0")

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web")

_security = HTTPBearer(auto_error=False)

# ── JWKS cache ────────────────────────────────────────────────────────

_jwks: dict | None = None
_jwks_fetched_at: float = 0


def _get_jwks() -> dict:
    """Fetch and cache Supabase JWKS (refresh every 1h)."""
    global _jwks, _jwks_fetched_at
    if _jwks and (time.time() - _jwks_fetched_at < 3600):
        return _jwks
    url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    _jwks = resp.json()
    _jwks_fetched_at = time.time()
    return _jwks


def _decode_supabase_jwt(token: str) -> dict:
    """Verify a Supabase access token and return its claims."""
    jwks_data = _get_jwks()
    # Build public keys from JWKS
    from jwt.algorithms import RSAAlgorithm
    public_keys = {}
    for key_data in jwks_data.get("keys", []):
        kid = key_data.get("kid")
        if kid:
            public_keys[kid] = RSAAlgorithm.from_jwk(key_data)

    # Decode header to find kid
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if kid not in public_keys:
        raise ValueError("Unknown key ID in JWT")

    claims = jwt.decode(
        token,
        key=public_keys[kid],
        algorithms=["RS256"],
        audience="authenticated",
        options={"verify_exp": True},
    )
    return claims


# ── Auth dependency ───────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> dict:
    """Extract and verify user from Supabase JWT. Returns {"id": ..., "email": ..., ...}."""
    if not credentials:
        raise HTTPException(401, "Missing authorization header")
    try:
        claims = _decode_supabase_jwt(credentials.credentials)
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}")
    return {
        "id": claims.get("sub", ""),
        "email": claims.get("email", ""),
        "user_metadata": claims.get("user_metadata", {}),
    }


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> dict | None:
    """Same as get_current_user but returns None instead of 401."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# ── Models ────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    guest_name: str = "Guest"
    topic: str = "life, ideas, and the future"
    podcaster: str = "chris-williamson"
    text_only: bool = False


class StartResponse(BaseModel):
    session_id: str
    greeting_text: str
    greeting_audio: str
    podcaster: str
    podcaster_name: str


class ChatTextRequest(BaseModel):
    text: str
    text_only: bool = False


class ChatResponse(BaseModel):
    user_text: str
    chris_text: str
    chris_audio: str
    turn: int
    stt_ms: int
    llm_ms: int
    tts_ms: int


class EndResponse(BaseModel):
    transcript_md: str
    turns: int


# ── Public endpoints ──────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Return public Supabase config for the frontend."""
    return {
        "supabase_url": SUPABASE_URL,
        "supabase_anon_key": SUPABASE_ANON_KEY,
    }


@app.get("/api/podcasters")
async def list_podcasters():
    """List all available podcasters (no auth required)."""
    podcasters = llm.get_all_podcasters()
    result = []
    for pid, info in podcasters.items():
        result.append({
            "id": pid,
            "name": info["name"],
            "show": info["show"],
            "description": info.get("description", ""),
            "avatar": info.get("avatar", ""),
            "voice_cloned": info.get("voice", {}).get("cloned", False),
        })
    return result


# ── Session management endpoints ──────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions_endpoint(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """List the current user's past sessions."""
    sessions = session.list_sessions(user["id"], limit=limit, offset=offset)
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session_detail(session_id: str, user: dict = Depends(get_current_user)):
    """Get a session with full transcript."""
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.user_id != user["id"]:
        raise HTTPException(403, "Not your session")
    from . import db as _db
    messages = _db.get_session_messages(session_id)
    return {
        "session": {
            "id": sess.session_id,
            "podcaster": sess.podcaster,
            "guest_name": sess.guest_name,
            "topic": sess.topic,
            "status": sess.status,
            "turns": sess.turn,
            "created_at": sess.created_at,
        },
        "messages": messages,
    }


@app.delete("/api/sessions/{session_id}")
async def delete_session_endpoint(session_id: str, user: dict = Depends(get_current_user)):
    """Delete a session and its messages."""
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.user_id != user["id"]:
        raise HTTPException(403, "Not your session")
    session.delete_session(session_id)
    return {"ok": True}


@app.post("/api/sessions/{session_id}/resume")
async def resume_session(session_id: str, user: dict = Depends(get_current_user)):
    """Resume an active session — returns state needed to rejoin the interview."""
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.user_id != user["id"]:
        raise HTTPException(403, "Not your session")
    if sess.status != "active":
        raise HTTPException(400, "Session is already ended")
    info = llm.get_podcaster_info(sess.podcaster)
    return {
        "session_id": sess.session_id,
        "podcaster": sess.podcaster,
        "podcaster_name": info.get("name", sess.podcaster),
        "guest_name": sess.guest_name,
        "topic": sess.topic,
        "turn": sess.turn,
        "transcript": sess.transcript,
    }


# ── Interview flow endpoints (auth required) ─────────────────────────

def _run_llm_tts(sess, user_text: str, text_only: bool = False, stt_ms: int = 0) -> ChatResponse:
    if not user_text.strip():
        raise HTTPException(400, "Empty message")

    t0 = time.time()
    messages = sess.get_messages_for_llm()
    messages.append({"role": "user", "content": user_text})
    try:
        response_text = llm.generate_response(messages, sess.podcaster)
    except Exception as e:
        raise HTTPException(500, f"LLM error: {e}")
    llm_ms = int((time.time() - t0) * 1000)

    response_audio = ""
    tts_ms = 0
    if not text_only:
        t0 = time.time()
        try:
            response_audio = tts.synthesize_b64(response_text, sess.podcaster)
        except Exception as e:
            raise HTTPException(500, f"TTS error: {e}")
        tts_ms = int((time.time() - t0) * 1000)

    sess.add_turn(user_text, response_text, stt_ms=stt_ms, llm_ms=llm_ms, tts_ms=tts_ms)

    return ChatResponse(
        user_text=user_text,
        chris_text=response_text,
        chris_audio=response_audio,
        turn=sess.turn,
        stt_ms=stt_ms,
        llm_ms=llm_ms,
        tts_ms=tts_ms,
    )


@app.post("/api/session/start", response_model=StartResponse)
async def start_session(req: StartRequest, user: dict = Depends(get_current_user)):
    sess = session.create_session(
        req.guest_name, req.topic, req.podcaster, user_id=user["id"]
    )

    info = llm.get_podcaster_info(req.podcaster)
    podcaster_name = info.get("name", req.podcaster)

    try:
        greeting_text = llm.generate_greeting(req.guest_name, req.topic, req.podcaster)
    except Exception as e:
        raise HTTPException(500, f"LLM error: {e}")

    sess.add_greeting(greeting_text)

    greeting_audio = ""
    if not req.text_only:
        try:
            greeting_audio = tts.synthesize_b64(greeting_text, req.podcaster)
        except Exception as e:
            raise HTTPException(500, f"TTS error: {e}")

    return StartResponse(
        session_id=sess.session_id,
        greeting_text=greeting_text,
        greeting_audio=greeting_audio,
        podcaster=req.podcaster,
        podcaster_name=podcaster_name,
    )


@app.post("/api/session/{session_id}/chat", response_model=ChatResponse)
async def chat(
    session_id: str,
    audio: UploadFile = File(...),
    text_only: bool = Form(False),
    user: dict = Depends(get_current_user),
):
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.user_id != user["id"]:
        raise HTTPException(403, "Not your session")

    t0 = time.time()
    audio_bytes = await audio.read()
    try:
        user_text = stt.transcribe(audio_bytes, audio.filename or "audio.webm")
    except Exception as e:
        raise HTTPException(500, f"STT error: {e}")
    stt_ms = int((time.time() - t0) * 1000)

    if not user_text:
        raise HTTPException(400, "Could not transcribe audio — too short or silent?")

    return _run_llm_tts(sess, user_text, text_only=text_only, stt_ms=stt_ms)


@app.post("/api/session/{session_id}/chat-text", response_model=ChatResponse)
async def chat_text(
    session_id: str,
    req: ChatTextRequest,
    user: dict = Depends(get_current_user),
):
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.user_id != user["id"]:
        raise HTTPException(403, "Not your session")
    return _run_llm_tts(sess, req.text, text_only=req.text_only)


@app.get("/api/session/{session_id}/transcript")
async def get_transcript(session_id: str, user: dict = Depends(get_current_user)):
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.user_id != user["id"]:
        raise HTTPException(403, "Not your session")
    return {"turn": sess.turn, "transcript": sess.transcript}


@app.post("/api/session/{session_id}/end", response_model=EndResponse)
async def end_session_endpoint(session_id: str, user: dict = Depends(get_current_user)):
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.user_id != user["id"]:
        raise HTTPException(403, "Not your session")

    session.end_session(session_id)
    transcript_md = sess.get_transcript_md()

    md_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "sessions", f"{session_id}.md",
    )
    with open(md_path, "w") as f:
        f.write(transcript_md)

    return EndResponse(transcript_md=transcript_md, turns=sess.turn)


# ── Static files ──────────────────────────────────────────────────────

if os.path.exists(WEB_DIR):
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
