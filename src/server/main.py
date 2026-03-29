"""Think-Pod — FastAPI server with Supabase auth."""
import os
import re
import json
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
from .config import SUPABASE_URL, SUPABASE_ANON_KEY, CHECKPOINT_INTERVAL, PATTERNS_DIR, SESSION_DIR

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
    # Build public keys from JWKS — support both RSA and EC keys
    from jwt.algorithms import RSAAlgorithm, ECAlgorithm
    public_keys = {}
    key_algs = {}
    for key_data in jwks_data.get("keys", []):
        kid = key_data.get("kid")
        kty = key_data.get("kty", "")
        if not kid:
            continue
        if kty == "RSA":
            public_keys[kid] = RSAAlgorithm.from_jwk(key_data)
            key_algs[kid] = "RS256"
        elif kty == "EC":
            public_keys[kid] = ECAlgorithm.from_jwk(key_data)
            key_algs[kid] = key_data.get("alg", "ES256")

    # Decode header to find kid
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if kid not in public_keys:
        raise ValueError("Unknown key ID in JWT")

    claims = jwt.decode(
        token,
        key=public_keys[kid],
        algorithms=[key_algs[kid]],
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
    reflect: bool = False


class StartResponse(BaseModel):
    session_id: str
    greeting_text: str
    greeting_audio: str
    podcaster: str
    podcaster_name: str
    reflect: bool = False


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
    analysis: str | None = None
    reflect: bool = False


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
    if sess.reflect:
        _ensure_reflect_prompt(sess)
    return {
        "session_id": sess.session_id,
        "podcaster": sess.podcaster,
        "podcaster_name": info.get("name", sess.podcaster),
        "guest_name": sess.guest_name,
        "topic": sess.topic,
        "turn": sess.turn,
        "transcript": sess.transcript,
        "reflect": sess.reflect,
        "checkpoint_count": len(sess.checkpoint_notes),
    }


# ── Reflect prompt cache ──────────────────────────────────────────────
# Reflection-enhanced system prompts are cached per session ID so they
# persist across chat requests without rebuilding every turn.
_reflect_prompt_cache: dict[str, str] = {}


def _ensure_reflect_prompt(sess) -> None:
    """Build and cache the reflection-enhanced system prompt for this session if needed."""
    if not sess.reflect:
        return
    cache_key = sess.session_id
    if cache_key not in _reflect_prompt_cache:
        base_prompt = llm._load_persona(sess.podcaster)
        reflection_prompt = llm.get_reflection_system_prompt(base_prompt, sess.guest_name)
        _reflect_prompt_cache[cache_key] = reflection_prompt


# ── Interview flow endpoints (auth required) ─────────────────────────

def _run_llm_tts(sess, user_text: str, text_only: bool = False, stt_ms: int = 0) -> ChatResponse:
    if not user_text.strip():
        raise HTTPException(400, "Empty message")

    # Reflection: check if we need to run a checkpoint before this turn
    next_turn = sess.turn + 1
    if sess.reflect and next_turn > 0 and next_turn % CHECKPOINT_INTERVAL == 0:
        try:
            transcript_text = sess.get_transcript_text()
            if transcript_text:
                steering = llm.run_checkpoint_analysis(transcript_text)
                if steering:
                    sess.steering_note = steering
                    sess.steering_turns_remaining = 3
                    # Persist checkpoint to DB
                    sess.save_checkpoint(steering)
                    print(f"[reflect] Checkpoint {next_turn // CHECKPOINT_INTERVAL} fired for session {sess.session_id}")
        except Exception as e:
            print(f"[reflect] Checkpoint analysis failed: {e}")

    # Build the user message for LLM, optionally injecting steering note
    llm_user_text = user_text
    if sess.reflect:
        context_blocks: list[str] = []
        if sess.checkpoint_notes:
            recent_notes = sess.checkpoint_notes[-2:]
            context_blocks.append(
                "[PRIOR CHECKPOINT CONTEXT — invisible to guest, do not reference directly. "
                "Maintain trajectory from these earlier reflection notes:\n"
                + "\n\n".join(recent_notes)
                + "]"
            )
        if sess.steering_note and sess.steering_turns_remaining > 0:
            context_blocks.append(
                "[INTERNAL STEERING — invisible to guest, do not reference directly. "
                "Use this to guide your next question naturally in character:\n"
                + sess.steering_note
                + "]"
            )
            sess.steering_turns_remaining -= 1
            if sess.steering_turns_remaining <= 0:
                sess.steering_note = None
        if context_blocks:
            llm_user_text = "\n\n".join(context_blocks) + "\n\n" + user_text

    t0 = time.time()
    messages = sess.get_messages_for_llm()
    messages.append({"role": "user", "content": llm_user_text})
    try:
        # Use reflection-enhanced prompt if reflect mode
        _ensure_reflect_prompt(sess)
        cache_key = sess.session_id
        if sess.reflect and cache_key in _reflect_prompt_cache:
            response_text = llm._call_anthropic(messages, _reflect_prompt_cache[cache_key])
        else:
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

    # Store the original user text in the session (not the steering-injected version)
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
        req.guest_name, req.topic, req.podcaster, user_id=user["id"],
        reflect=req.reflect,
    )

    # If reflect mode, build and cache the reflection-enhanced system prompt
    if req.reflect:
        _ensure_reflect_prompt(sess)

    info = llm.get_podcaster_info(req.podcaster)
    podcaster_name = info.get("name", req.podcaster)

    try:
        if req.reflect and sess.session_id in _reflect_prompt_cache:
            messages = [{
                "role": "user",
                "content": f"Your guest today is {req.guest_name}. They want to discuss: {req.topic}. Welcome them warmly and kick things off with your first question. Keep it to 2-3 sentences max.",
            }]
            greeting_text = llm._call_anthropic(messages, _reflect_prompt_cache[sess.session_id])
        else:
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
        reflect=req.reflect,
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

    md_path = os.path.join(SESSION_DIR, f"{session_id}.md")
    with open(md_path, "w") as f:
        f.write(transcript_md)

    # Post-session reflection analysis
    analysis_text = None
    if sess.reflect and sess.turn >= 4:
        try:
            transcript_text = sess.get_transcript_text()
            prior_patterns = llm.load_latest_patterns(sess.guest_name)
            session_date = sess.created_at[:10] if sess.created_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            analysis_output = llm.run_post_session_analysis(
                transcript_text,
                prior_patterns,
                session_date=session_date,
                session_host=sess.podcaster,
                guest_name=sess.guest_name,
            )

            if analysis_output:
                # Save the analysis document
                analysis_doc = llm.extract_analysis_doc(analysis_output)
                analysis_path = os.path.join(SESSION_DIR, f"{session_id}-analysis.md")
                with open(analysis_path, "w") as f:
                    f.write(f"# Reflection Analysis — {sess.guest_name}\n")
                    f.write(f"# Session: {session_id}\n")
                    f.write(f"# Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n\n")
                    f.write(analysis_doc)

                # Save pattern JSON
                patterns = llm.extract_pattern_json(analysis_output)
                if patterns:
                    safe_guest = re.sub(r"[^\w]", "-", sess.guest_name.lower()).strip("-")
                    patterns_path = os.path.join(PATTERNS_DIR, f"{safe_guest}-{session_id}.json")
                    with open(patterns_path, "w") as f:
                        json.dump(patterns, f, indent=2)

                analysis_text = analysis_doc
        except Exception as e:
            print(f"[reflect] Post-session analysis failed: {e}")

    # Clean up in-memory reflect cache
    _reflect_prompt_cache.pop(session_id, None)

    return EndResponse(
        transcript_md=transcript_md,
        turns=sess.turn,
        analysis=analysis_text,
        reflect=sess.reflect,
    )


@app.get("/api/sessions/{session_id}/analysis")
async def get_session_analysis(session_id: str, user: dict = Depends(get_current_user)):
    """Get the reflection analysis document for a session, if it exists."""
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.user_id != user["id"]:
        raise HTTPException(403, "Not your session")

    analysis_path = os.path.join(SESSION_DIR, f"{session_id}-analysis.md")
    if not os.path.exists(analysis_path):
        raise HTTPException(404, "No analysis found for this session")

    with open(analysis_path) as f:
        analysis_text = f.read()

    return {"analysis": analysis_text, "session_id": session_id}


# ── Static files ──────────────────────────────────────────────────────

if os.path.exists(WEB_DIR):
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
