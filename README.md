# think-pod 🎙️

A thinking exercise disguised as a podcast. Choose a podcaster, get interviewed by their AI clone, and turn your raw thinking into structured content.

## How it works

1. **Pick a podcaster** — their voice, style, and question patterns
2. **Have a conversation** — they interview you on any topic
3. **Get output** — transcript, key themes, article drafts

## Current State (MVP)

- ✅ RSS feed → audio download → Groq Whisper transcription pipeline
- ✅ Chris Williamson persona (extracted from 8 episode transcripts)
- ✅ Conversational AI interview loop (text-based)
- ✅ Transcript saving with auto-extracted themes & article angles

## Stack

- **Transcription**: Groq Whisper API (via chunked audio)
- **Persona**: Claude with custom system prompt derived from real transcripts
- **Data source**: Podcast RSS feeds (Megaphone)

## Roadmap

- [ ] Voice cloning (ElevenLabs) — hear the podcaster ask questions
- [ ] Real-time audio loop (STT → LLM → TTS)
- [ ] Video avatar (Simli/Tavus) — "across the table" experience
- [ ] Output pipeline — auto-generate articles, threads, posts from transcript
- [ ] Multi-podcaster support
- [ ] Web/mobile frontend

## Project Structure

```
├── chris_persona.md           # Extracted interviewer persona
├── transcribe_groq.py         # RSS → download → chunk → Groq Whisper
├── podcast_session.py         # Interactive interview session (CLI)
├── transcripts/               # Full episode transcripts
│   └── chris-williamson/      # 8 episodes, timestamped
├── sessions/                  # Interview session transcripts
└── audio/                     # Downloaded episodes (gitignored)
```

## License

MIT
