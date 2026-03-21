# Think-Pod — Development Plan

## Vision
A thinking exercise disguised as a podcast. Choose a podcaster, get interviewed by their AI clone (voice + video), and turn your raw thinking into structured content.

---

## Pipeline Overview

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  1. DATA     │ →  │  2. PERSONA  │ →  │  3. VOICE    │ →  │  4. VIDEO    │
│  COLLECTION  │    │  EXTRACTION  │    │  CLONING     │    │  AVATAR      │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
       ↓                  ↓                   ↓                   ↓
  RSS → Audio →     Transcript →        Audio samples →    Lip-synced
  Groq Whisper      Persona doc +       ElevenLabs          video stream
  → Transcripts     System prompt       voice clone         (Simli/Tavus)
                                              ↓
                                    ┌──────────────────┐
                                    │  5. REAL-TIME     │
                                    │  CONVERSATION     │
                                    │  LOOP             │
                                    └──────────────────┘
                                    User speaks → STT →
                                    LLM → TTS → Video →
                                    WebRTC to user
                                              ↓
                                    ┌──────────────────┐
                                    │  6. OUTPUT        │
                                    │  PIPELINE         │
                                    └──────────────────┘
                                    Transcript → Themes →
                                    Articles / Threads /
                                    Posts
```

---

## Phase 1: Data Collection ✅ DONE
**Status: Complete for Chris Williamson**

- [x] RSS feed parsing (1071 episodes found)
- [x] Audio download pipeline
- [x] Audio chunking (10-min segments, mono 16kHz 48kbps)
- [x] Groq Whisper transcription
- [x] 9 episodes fully transcribed (#1065–#1073)
- [x] Reusable pipeline (`src/pipeline/transcribe_groq.py`)
- [x] Documented process for adding new podcasters (`docs/ADD_PODCASTER.md`)

**Files:**
- `src/pipeline/transcribe_groq.py` — main pipeline
- `src/pipeline/scraper.py` — podscripts.co scraper (hit rate limits, backup option)
- `src/pipeline/download_and_transcribe.py` — local Whisper version (slow, backup)
- `data/transcripts/chris-williamson/` — 9 transcripts + index

---

## Phase 2: Persona Extraction ✅ DONE
**Status: Complete for Chris Williamson**

- [x] v1 persona (manual, from 1 transcript)
- [x] v2 persona (AI-assisted deep analysis of all 9 transcripts)
- [x] Verbal DNA documented (exact phrases, tics, timestamps)
- [x] Conversation architecture mapped (4 opening types, closing patterns)
- [x] Question taxonomy with real examples (8 types)
- [x] Intellectual identity profiled
- [x] Emotional palette mapped
- [x] Ready-to-use system prompt

**Files:**
- `data/personas/chris_williamson_v1.md` — initial persona
- `data/personas/chris_williamson_v2.md` — comprehensive 30KB profile

---

## Phase 3: Conversational AI ✅ MVP DONE
**Status: Text-based MVP working**

- [x] System prompt built from persona
- [x] Interview conversation loop (text, via Telegram)
- [x] Transcript saving with auto-extracted themes
- [x] Article angle suggestions
- [ ] Improve persona accuracy using v2 profile
- [ ] Add conversation memory (reference earlier answers)
- [ ] Add topic planning (pre-prepared question arcs)
- [ ] Multi-turn conversation state management

**Files:**
- `src/interview/podcast_session.py` — CLI interview session
- `data/sessions/` — saved session transcripts

---

## Phase 4: Voice Cloning 🔜 NEXT
**Status: Not started**

### What's needed
- ElevenLabs API key (or alternative: PlayHT, Cartesia)
- Clean audio samples of Chris (~1-5 min solo speaking)
- Voice clone creation
- TTS integration into conversation loop

### Tasks
- [ ] Extract clean solo audio segments from downloaded episodes
- [ ] Create ElevenLabs voice clone
- [ ] Build TTS wrapper that takes text → returns audio
- [ ] Test voice quality and latency
- [ ] Integrate with conversation loop (text response → voice output)

### Technical decisions
| Decision | Options | Recommendation |
|----------|---------|----------------|
| TTS Provider | ElevenLabs, PlayHT, Cartesia | ElevenLabs (best quality cloning) |
| Latency target | <500ms first byte | Cartesia if ElevenLabs too slow |
| Audio format | MP3, PCM, Opus | Opus for streaming, MP3 for storage |
| Streaming | Chunk-based vs full | Streaming (start playing before full gen) |

### Files to create
- `src/voice/clone.py` — voice clone creation
- `src/voice/tts.py` — text-to-speech wrapper
- `src/voice/samples/` — clean audio samples (gitignored)

---

## Phase 5: Real-Time Audio Loop
**Status: Not started**

### What's needed
- STT (speech-to-text): Groq Whisper or Deepgram
- LLM: Claude/GPT with persona prompt
- TTS: ElevenLabs voice clone (from Phase 4)
- Frontend: Web app with microphone access

### Architecture
```
User mic → WebSocket → Server
                         ↓
                    Groq Whisper STT
                         ↓
                    LLM (persona prompt)
                         ↓
                    ElevenLabs TTS (streaming)
                         ↓
              WebSocket → User speaker
```

### Options for the frontend
| Option | Pros | Cons |
|--------|------|------|
| **Vapi.ai** | Phone-callable, handles full loop, fast setup | Less control, costs per minute |
| **Custom web app** | Full control, can add video later | More to build |
| **LiveKit** | Open-source WebRTC, good for real-time | More infrastructure |
| **Twilio** | Phone number, battle-tested | Old-school, harder to customize |

### Tasks
- [ ] Choose frontend approach
- [ ] Build STT → LLM → TTS chain
- [ ] Measure end-to-end latency
- [ ] Handle interruptions (user speaks while AI is talking)
- [ ] Handle silence detection
- [ ] Add "thinking" filler sounds (natural pauses)

### Files to create
- `src/realtime/server.py` — WebSocket server
- `src/realtime/audio_loop.py` — STT → LLM → TTS chain
- `web/` — frontend (if custom)

---

## Phase 6: Video Avatar
**Status: Not started**

### What's needed
- Video avatar API (Simli, Tavus, or HeyGen)
- Audio stream from TTS → video avatar API
- WebRTC delivery to user

### Options
| Provider | Latency | Quality | Cost |
|----------|---------|---------|------|
| **Simli** | ~500ms | Good | API-based pricing |
| **Tavus** | ~800ms | Very good | Higher cost |
| **HeyGen** | ~1s | Good | Subscription-based |
| **D-ID** | ~1s | Decent | Per-minute pricing |

### Tasks
- [ ] Evaluate Simli vs Tavus (get API access)
- [ ] Create base video/photo of Chris for avatar
- [ ] Integrate audio stream → video avatar
- [ ] Combine with WebRTC frontend
- [ ] Test "across the table" experience

---

## Phase 7: Output Pipeline
**Status: Not started**

### What's needed
- Post-session transcript processing
- LLM-powered extraction and generation

### Outputs
- **Key themes** — auto-extracted from conversation
- **Article draft** — long-form piece from the discussion
- **Twitter thread** — key insights in thread format
- **LinkedIn post** — professional angle
- **Quotes** — best quotable moments
- **Action items** — if any emerged from the conversation

### Tasks
- [ ] Build transcript → structured extraction pipeline
- [ ] Build extraction → content generation templates
- [ ] Add export formats (Markdown, HTML, social-ready)

---

## Multi-Podcaster Support
**Status: Framework ready, only Chris Williamson populated**

The system is designed to support multiple podcasters:
- Each podcaster has their own `data/transcripts/<podcaster>/` dir
- Each has a persona doc in `data/personas/`
- Voice clones are separate per podcaster
- System prompts are swappable

### Podcasters to add
- [ ] Lex Fridman — deep, philosophical interviews
- [ ] Tim Ferriss — tactical, framework-heavy
- [ ] Andrew Huberman — scientific, protocol-focused
- [ ] Steven Bartlett — emotional, founder stories
- [ ] Joe Rogan — casual, wide-ranging

See `docs/ADD_PODCASTER.md` for the full process.

---

## Tech Stack (Current & Planned)

| Layer | Current | Planned |
|-------|---------|---------|
| Transcription | Groq Whisper API | Same |
| Persona | Manual + AI extraction | Same, more automated |
| Conversation AI | Claude Opus (via OpenClaw) | Claude/GPT, switchable |
| Voice | ❌ | ElevenLabs |
| Video | ❌ | Simli/Tavus |
| Frontend | Telegram (text) | Web app (WebRTC) |
| Storage | Local files + Git | Same, maybe S3 for audio |
| Hosting | VPS (Ubuntu 24.04) | Same + edge for latency |

---

## Open Questions

1. **Licensing** — Using real podcasters' voices and likenesses. Need to research legal implications or pivot to "inspired by" personas.
2. **Latency budget** — Can we hit <2s end-to-end (STT + LLM + TTS + Video)? Need to benchmark each layer.
3. **Monetization** — Per-session? Subscription? Free with output upsell?
4. **Speaker diarization** — Whisper doesn't separate host from guest. Needed for better persona extraction. Consider pyannote.
5. **Conversation quality** — How to make the AI go deeper rather than broader? Needs conversation planning / topic arc system.
