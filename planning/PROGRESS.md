# Think-Pod — Progress Log

## 2026-03-20 — Day 1

### Data Pipeline
- Built RSS feed parser for Modern Wisdom (1071 episodes found)
- Attempted podscripts.co scraping — hit rate limits at ~10 requests
- Attempted YouTube transcript API — VPS IP blocked by YouTube
- Attempted local Whisper (faster-whisper, small model, CPU) — 1.3x realtime, too slow
- **Switched to Groq Whisper API** — blazing fast, high quality
- Pipeline: download MP3 → ffmpeg split to 10-min chunks (mono 16kHz 48k) → Groq API
- Bottleneck is ffmpeg splitting (~3 min per episode), not transcription

### Persona Extraction
- v1 persona manually extracted from Gurwinder episode
- Identified: opening patterns, question types, verbal tics, intellectual interests

### MVP Interview
- Built text-based interview loop using Chris persona
- Tested with Kush on "early stage startup learnings" — ~10 exchanges
- Worked well — natural flow, good question depth, proper topic bridging
- Saved full transcript with auto-extracted themes and article angles

### Repo
- Created github.com/kushagra27/think-pod
- Initial commit: pipeline code, persona, transcripts, session

---

## 2026-03-21 — Day 2

### Data Pipeline
- Groq pipeline ran overnight — **9 episodes fully transcribed** (#1065–#1073)
- ~970KB of transcript data total

### Persona Extraction
- v2 persona: deep AI-assisted analysis of all 9 transcripts
- 30KB comprehensive profile covering verbal DNA, conversation architecture, question taxonomy, intellectual identity, emotional palette, guest dynamics
- Includes ready-to-use system prompt

### Documentation
- Created `docs/ADD_PODCASTER.md` — full guide for adding new podcasters
- Created `planning/DEVELOPMENT_PLAN.md` — full roadmap with phases
- Restructured repo: `src/`, `data/`, `planning/`, `docs/`

### Next Up
- Voice cloning (Phase 4)
- Parallel: other agents adding more podcaster personas
