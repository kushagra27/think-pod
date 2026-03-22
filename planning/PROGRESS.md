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

---

## 2026-03-22 — Day 3

### Multi-Podcaster App
- Added selectable podcasters in the local dev app:
  - Chris Williamson
  - Lex Fridman
  - Alex Hormozi
  - Naval Ravikant
- Start screen now uses a dropdown selector with Chris selected by default.
- Backend now loads podcaster config dynamically from `data/podcasters.json`.
- Added `/api/podcasters` endpoint and wired podcaster selection through session start, LLM, and TTS flow.

### Voice Cloning
- Chris remains on existing validated Cartesia clone.
- Lex and Alex received new cloned voices.
- Naval had to be rebuilt from scratch because earlier source selection included mixed-speaker / Nivi contamination.

### Naval Rebuild
- Rebuilt Naval transcript corpus around official `nav.al` sources only.
- Deprecated mixed-speaker files as primary persona sources:
  - `a-motorcycle-for-the-mind.txt`
  - `curate-people.txt`
  - `in-the-arena.txt`
- Added clean official-source Naval transcript files including:
  - `pause-reflect-see-how-well-it-did.txt`
  - `it-is-impossible-to-fool-mother-nature.txt`
  - `groups-search-for-consensus-individuals-search-for-truth.txt`
  - other short-form official `nav.al` pieces
- Created `data/personas/naval_ravikant_v2.md`
- Rewrote `data/personas/naval_ravikant_system_prompt.md`
- Updated `data/podcasters.json` so Naval uses `naval_ravikant_v2.md`
- User personally validated reviewed `naval_*` solo clips as authentic Naval.
- Fresh Naval Cartesia clone now uses validated solo clips only.

### Local Dev Status
- Local dev server used for testing: `http://37.60.245.136:8001`
- Naval voice sounded good again in local Think-Pod testing.

### Important Workflow Notes
- Dev happens on this VPS only.
- Production remains on the separate DO box and should only be updated when Kush explicitly says to deploy.
- For future cross-channel continuity, use this file plus `planning/DEVELOPMENT_PLAN.md`, `planning/MVP_IMPLEMENTATION.md`, and `data/podcasters.json` as the canonical project handoff set.
