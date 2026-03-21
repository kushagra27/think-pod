# think-pod 🎙️

A thinking exercise disguised as a podcast. Choose a podcaster, get interviewed by their AI clone, and turn your raw thinking into structured content.

## How it works

1. **Pick a podcaster** — their voice, style, and question patterns
2. **Have a conversation** — they interview you on any topic
3. **Get output** — transcript, key themes, article drafts

## Project Structure

```
├── src/
│   ├── pipeline/              # Data collection & transcription
│   │   ├── transcribe_groq.py   # RSS → download → chunk → Groq Whisper
│   │   ├── scraper.py           # Podscripts.co scraper (backup)
│   │   └── download_and_transcribe.py  # Local Whisper (backup)
│   └── interview/             # Conversation engine
│       └── podcast_session.py   # Interactive interview session
├── data/
│   ├── transcripts/           # Full episode transcripts
│   │   └── chris-williamson/    # 9 episodes, timestamped
│   ├── personas/              # Extracted podcaster profiles
│   │   ├── chris_williamson_v1.md
│   │   └── chris_williamson_v2.md  # 30KB comprehensive profile
│   └── sessions/              # Interview session transcripts
├── planning/
│   ├── DEVELOPMENT_PLAN.md    # Full roadmap & architecture
│   └── PROGRESS.md            # Progress log
├── docs/
│   └── ADD_PODCASTER.md       # Guide: adding a new podcaster
└── audio/                     # Downloaded episodes (gitignored)
```

## Current State

| Phase | Status |
|-------|--------|
| 1. Data Collection | ✅ Done (9 Chris Williamson episodes) |
| 2. Persona Extraction | ✅ Done (comprehensive v2 profile) |
| 3. Conversational AI | ✅ MVP (text-based interview loop) |
| 4. Voice Cloning | 🔜 Next |
| 5. Real-Time Audio | ⬜ Planned |
| 6. Video Avatar | ⬜ Planned |
| 7. Output Pipeline | ⬜ Planned |

## Stack

- **Transcription**: Groq Whisper API
- **Persona**: Claude with custom system prompt from transcript analysis
- **Data source**: Podcast RSS feeds

## Docs

- [Development Plan](planning/DEVELOPMENT_PLAN.md) — full roadmap, architecture, tech decisions
- [Progress Log](planning/PROGRESS.md) — what's been done, day by day
- [Add a Podcaster](docs/ADD_PODCASTER.md) — step-by-step guide for new personas

## License

MIT
