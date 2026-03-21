"""Think-Pod — FastAPI server."""
import base64
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import os
import time

from . import stt, llm, tts, session

app = FastAPI(title="Think-Pod", version="0.1.0")

# Serve frontend
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web")


class StartRequest(BaseModel):
    guest_name: str = "Guest"
    topic: str = "life, ideas, and the future"
    podcaster: str = "chris_williamson"


class StartResponse(BaseModel):
    session_id: str
    greeting_text: str
    greeting_audio: str  # base64 mp3


class ChatResponse(BaseModel):
    user_text: str
    chris_text: str
    chris_audio: str  # base64 mp3
    turn: int
    stt_ms: int
    llm_ms: int
    tts_ms: int


class EndResponse(BaseModel):
    transcript_md: str
    turns: int


@app.post("/api/session/start", response_model=StartResponse)
async def start_session(req: StartRequest):
    """Start a new interview session."""
    # Create session
    sess = session.create_session(req.guest_name, req.topic, req.podcaster)

    # Generate greeting
    try:
        greeting_text = llm.generate_greeting(req.guest_name, req.topic, req.podcaster)
    except Exception as e:
        raise HTTPException(500, f"LLM error: {e}")

    sess.add_greeting(greeting_text)

    # Generate greeting audio
    try:
        greeting_audio = tts.synthesize_b64(greeting_text)
    except Exception as e:
        raise HTTPException(500, f"TTS error: {e}")

    sess.save()

    return StartResponse(
        session_id=sess.session_id,
        greeting_text=greeting_text,
        greeting_audio=greeting_audio,
    )


@app.post("/api/session/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, audio: UploadFile = File(...)):
    """Send audio, get Chris's voice response."""
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    # 1. STT
    t0 = time.time()
    audio_bytes = await audio.read()
    try:
        user_text = stt.transcribe(audio_bytes, audio.filename or "audio.webm")
    except Exception as e:
        raise HTTPException(500, f"STT error: {e}")
    stt_ms = int((time.time() - t0) * 1000)

    if not user_text:
        raise HTTPException(400, "Could not transcribe audio — too short or silent?")

    # 2. LLM
    t0 = time.time()
    messages = sess.get_messages_for_llm()
    messages.append({"role": "user", "content": user_text})
    try:
        chris_text = llm.generate_response(messages, sess.podcaster)
    except Exception as e:
        raise HTTPException(500, f"LLM error: {e}")
    llm_ms = int((time.time() - t0) * 1000)

    # 3. TTS
    t0 = time.time()
    try:
        chris_audio = tts.synthesize_b64(chris_text)
    except Exception as e:
        raise HTTPException(500, f"TTS error: {e}")
    tts_ms = int((time.time() - t0) * 1000)

    # Update session
    sess.add_turn(user_text, chris_text)
    sess.save()

    return ChatResponse(
        user_text=user_text,
        chris_text=chris_text,
        chris_audio=chris_audio,
        turn=sess.turn,
        stt_ms=stt_ms,
        llm_ms=llm_ms,
        tts_ms=tts_ms,
    )


@app.post("/api/session/{session_id}/end", response_model=EndResponse)
async def end_session(session_id: str):
    """End session and get transcript."""
    sess = session.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    transcript_md = sess.get_transcript_md()

    # Save transcript as markdown too
    md_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "sessions", f"{session_id}.md",
    )
    with open(md_path, "w") as f:
        f.write(transcript_md)

    return EndResponse(transcript_md=transcript_md, turns=sess.turn)


# Serve frontend
if os.path.exists(WEB_DIR):
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
