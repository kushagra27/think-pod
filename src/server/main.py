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
from .config import SUPABASE_URL, SUPABASE_ANON_KEY, CHECKPOINT_INTERVAL, PATTERNS_DIR, SESSION_DIR, LOCAL_MODE

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

_LOCAL_USER = {"id": "local", "email": "local@thinkpod", "user_metadata": {}}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> dict:
    """Extract and verify user from Supabase JWT. Returns {"id": ..., "email": ..., ...}.
    In local mode, returns a dummy user with no auth required."""
    if LOCAL_MODE:
        return _LOCAL_USER
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
    """Return public config for the frontend."""
    return {
        "supabase_url": SUPABASE_URL,
        "supabase_anon_key": SUPABASE_ANON_KEY,
        "local_mode": LOCAL_MODE,
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
    from .config import GROQ_API_KEY
    if not GROQ_API_KEY:
        raise HTTPException(400, "Voice input unavailable — GROQ_API_KEY not configured. Use text input instead.")

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


# ── Go Deeper ────────────────────────────────────────────────────────

def _compile_prior_sessions(
    user_id: str,
    current_session_id: str,
    guest_name: str,
    max_prior: int = 5,
) -> str:
    """Compile analysis docs and pattern JSONs from prior sessions."""
    from . import db as _db

    all_sessions = _db.list_user_sessions(user_id, limit=50)
    prior = [
        s for s in all_sessions
        if s["id"] != current_session_id
        and s["status"] == "ended"
        and s.get("guest_name", "").lower() == guest_name.lower()
    ][:max_prior]

    if not prior:
        return ""

    prior = list(reversed(prior))  # chronological (oldest first)

    sections = []
    for i, s in enumerate(prior, 1):
        sid = s["id"]
        analysis_path = os.path.join(SESSION_DIR, f"{sid}-analysis.md")
        if not os.path.exists(analysis_path):
            continue

        with open(analysis_path) as f:
            analysis = f.read()

        # Strip metadata headers
        lines = analysis.split("\n")
        cleaned_lines = [
            l for l in lines
            if not l.startswith("# Session:") and not l.startswith("# Date:")
        ]
        analysis_cleaned = "\n".join(cleaned_lines).strip()

        # Find pattern JSON for this session
        pattern_text = ""
        pattern_files = [
            f for f in os.listdir(PATTERNS_DIR)
            if f.endswith(".json") and sid in f
        ]
        if pattern_files:
            with open(os.path.join(PATTERNS_DIR, pattern_files[0])) as pf:
                pattern_text = pf.read()

        podcaster_info = llm.get_podcaster_info(s.get("podcaster", ""))
        host_name = podcaster_info.get("name", s.get("podcaster", ""))
        date_str = s["created_at"][:10] if s.get("created_at") else "unknown"

        section = f"### Session {i} — {host_name} x {s.get('guest_name', '')}, {date_str}\n"
        section += f"Topic: {s.get('topic', 'unknown')}\n\n"
        section += f"**Analysis:**\n{analysis_cleaned}\n\n"
        if pattern_text:
            section += f"**Pattern Data:**\n```json\n{pattern_text}\n```\n"

        sections.append(section)

    if not sections:
        return ""

    return "## PRIOR SESSIONS (oldest to newest)\n\n" + "\n---\n\n".join(sections)


def _build_go_deeper_prompt(
    transcript: str,
    analysis: str,
    patterns_json: str,
    prior_sessions: str = "",
) -> str:
    """Build the compiled Go Deeper prompt."""

    prior_section = ""
    if prior_sessions:
        prior_section = f"""I've done multiple ThinkPod sessions over time. I'm including the \
analysis and pattern data from prior sessions so you can see how my \
patterns have evolved. Some things to look for:

- Patterns that show up across every session regardless of host or \
topic — these are probably the real ones
- Contradictions that were identified early but still haven't been \
resolved in later sessions
- Avoidance topics that keep appearing — things I consistently \
deflect from no matter who's asking
- Whether my relationship to specific themes has shifted or stayed stuck
- Anything the individual analyses missed because they only had one \
conversation to work with

---

{prior_sessions}

---

"""

    prompt = f"""I just did something interesting — a thinking exercise called ThinkPod \
where I had a long conversation with an AI podcast host about my life, \
decisions, and what's going on underneath them. The conversation had a \
hidden layer tracking psychological patterns in what I said, and it \
produced an analysis afterward.

I'm sharing all of it with you — the conversation transcript, the \
analysis, and some structured pattern data. I'd love your help making \
sense of it.

A few things about how I'd like this to go:

- This is a collaborative exploration, not a diagnosis. I want to \
understand myself better, not be told what's wrong with me.
- Think of yourself as a thoughtful friend who's read my journal and \
wants to help me see what I can't see on my own — not a therapist \
delivering a report.
- Start by sharing what stood out to you most, then let me guide where \
we go from there. Ask me questions rather than making declarations.
- Don't just repeat what the analysis already says — I've read it. \
I'm looking for what's underneath it, connections I haven't made, \
patterns I might be blind to.
- The analysis is a starting point, not the final word. If you see a \
pattern it identified but didn't push far enough on — go further. \
If you think the analysis got something wrong or oversimplified \
something, say so. I want you to challenge the analysis too, not \
just build on it.
- If you notice contradictions between what I said and what I actually \
did, point them out — but as curiosity, not accusation. "I noticed \
something interesting" rather than "you're clearly doing X."
- Use frameworks if they're helpful (psychology, philosophy, whatever \
fits) but explain them in plain language and always tie them back to \
my specific situation.
- Look beyond the patterns to my relationship with the patterns \
themselves. If I seem very analytical about my own psychology, \
that's worth examining — am I using self-awareness as another \
way to stay in control? If I frame everything as growth, is that \
itself a pattern worth questioning?
- If I push back on something you say, take it seriously — I might be \
right, or I might be defending a blind spot. Either way, the \
pushback itself is worth exploring.
- Be honest. I'd rather hear something uncomfortable that's true than \
something reassuring that's vague.

Here's everything from my sessions:

---

{prior_section}## CURRENT SESSION

### Transcript

{transcript}

---

### Reflection Analysis

{analysis}

---

### Pattern Data

```json
{patterns_json}
```

---

I've read through the analysis and I'm ready to go deeper. What jumps \
out to you first?"""

    return prompt


@app.get("/api/sessions/{session_id}/go-deeper")
async def get_go_deeper_prompt(session_id: str, user: dict = Depends(get_current_user)):
    """Compile the Go Deeper prompt for a session."""
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.user_id != user["id"]:
        raise HTTPException(403, "Not your session")
    if sess.status != "ended":
        raise HTTPException(400, "Session must be ended first")

    # Load current session's analysis
    analysis_path = os.path.join(SESSION_DIR, f"{session_id}-analysis.md")
    if not os.path.exists(analysis_path):
        raise HTTPException(404, "No analysis found — run a reflection session first")

    with open(analysis_path) as f:
        analysis_text = f.read()

    # Strip metadata headers from analysis
    lines = analysis_text.split("\n")
    cleaned_lines = [
        l for l in lines
        if not l.startswith("# Session:") and not l.startswith("# Date:")
    ]
    analysis_cleaned = "\n".join(cleaned_lines).strip()

    # Get transcript from DB
    from . import db as _db
    messages = _db.get_session_messages(session_id)
    transcript_lines = []
    podcaster_info = llm.get_podcaster_info(sess.podcaster)
    host_name = podcaster_info.get("name", sess.podcaster)
    for m in messages:
        if m["role"] == "system":
            continue
        if m["role"] == "user" and m.get("turn_number", 0) == 0:
            continue  # skip setup prompt
        speaker = host_name if m["role"] == "assistant" else sess.guest_name
        transcript_lines.append(f"**{speaker}:** {m['content']}")
    transcript_text = "\n\n".join(transcript_lines)

    # Load current session's pattern JSON
    current_patterns_text = ""
    pattern_files = sorted([
        f for f in os.listdir(PATTERNS_DIR)
        if f.endswith(".json") and session_id in f
    ])
    if pattern_files:
        with open(os.path.join(PATTERNS_DIR, pattern_files[0])) as pf:
            current_patterns = json.load(pf)
            current_patterns_text = json.dumps(current_patterns, indent=2)

    # Compile prior sessions
    prior_sessions_text = _compile_prior_sessions(
        user_id=user["id"],
        current_session_id=session_id,
        guest_name=sess.guest_name,
        max_prior=5,
    )

    compiled = _build_go_deeper_prompt(
        transcript=transcript_text,
        analysis=analysis_cleaned,
        patterns_json=current_patterns_text,
        prior_sessions=prior_sessions_text,
    )

    return {"prompt": compiled, "session_id": session_id, "char_count": len(compiled)}


# ── Static files ──────────────────────────────────────────────────────

if os.path.exists(WEB_DIR):
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
