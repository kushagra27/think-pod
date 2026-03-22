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
│   ├── transcripts/           # Full episode transcripts per podcaster
│   │   ├── chris-williamson/
│   │   ├── lex-fridman/
│   │   ├── naval-ravikant/
│   │   └── alex-hormozi/
│   ├── personas/              # Extracted podcaster profiles + prompts
│   │   ├── chris_williamson_v2.md
│   │   ├── lex_fridman_v1.md
│   │   ├── naval_ravikant_v1.md
│   │   └── alex_hormozi_v1.md
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
| 1. Data Collection | ✅ Done for Chris; starter transcript sets added for Lex, Naval, and Alex |
| 2. Persona Extraction | ✅ Chris complete; starter personas added for Lex, Naval, and Alex |
| 3. Conversational AI | ✅ MVP with selectable podcasters |
| 4. Voice Cloning | 🔜 Next |
| 5. Real-Time Audio | ⬜ Planned |
| 6. Video Avatar | ⬜ Planned |
| 7. Output Pipeline | ⬜ Planned |

## Available Podcasters

- Chris Williamson - warm, rigorous, modern-self-improvement interviews
- Lex Fridman - calm, philosophical, technical and human
- Naval Ravikant - sparse, principle-driven, high-signal conversations
- Alex Hormozi - direct, tactical, operator-style coaching

## Stack

- **Transcription**: Groq Whisper API
- **Persona**: Claude with custom system prompt from transcript analysis
- **Data source**: Podcast RSS feeds

## Docs

- [Development Plan](planning/DEVELOPMENT_PLAN.md) — full roadmap, architecture, tech decisions
- [Progress Log](planning/PROGRESS.md) — what's been done, day by day
- [Add a Podcaster](docs/ADD_PODCASTER.md) — step-by-step guide for new personas

## Secret Safety

- Never commit API keys, `.env` files, private keys, or local credential files.
- Runtime secrets must come from environment variables or untracked local files only.
- Repo guardrails:
  - local git pre-commit hook in `.githooks/pre-commit`
  - GitHub Actions secret scanning via `.github/workflows/secret-scan.yml`
- Install local hooks once per clone:

```bash
./scripts/install-git-hooks.sh
```

## License

MIT
