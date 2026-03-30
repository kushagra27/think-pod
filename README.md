# think-pod

A thinking exercise disguised as a podcast. Choose a podcaster, get interviewed by their AI clone, and walk away understanding yourself better.

## How it works

1. **Pick a host** — their voice, style, and question patterns
2. **Have a conversation** — they interview you on any topic
3. **Deep Reflection mode** — a hidden analytical layer tracks your psychological patterns, contradictions, and avoidance in real-time
4. **Get output** — transcript, reflection analysis, structured pattern data
5. **Go Deeper** — export everything into a prompt for claude.ai to explore your patterns further

## Quickstart (Local Mode)

Run Think-Pod on your machine with no account, no database setup, and no auth. Just an API key and go.

```bash
git clone <repo-url> && cd think-pod
./scripts/quickstart.sh
```

The setup script will:
- Create a virtual environment and install dependencies
- Prompt you for your Anthropic API key (required) and optional voice keys
- Write a `.env` file
- Initialize a local SQLite database

Then start the server:

```bash
source .venv/bin/activate
uvicorn src.server.main:app --reload --port 8000
```

Open **http://localhost:8000** — no login required in local mode.

Or use the CLI directly:

```bash
python src/interview/podcast_session.py --podcaster naval-ravikant --reflect
```

### API Keys

| Key | Required | What it does |
|-----|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Powers all conversations and analysis |
| `GROQ_API_KEY` | No | Enables voice input (speech-to-text via Whisper) |
| `CARTESIA_API_KEY` | No | Enables voice output (text-to-speech) |

Without the optional keys, Think-Pod runs in text-only mode.

## Cloud Mode

For multi-user deployment with authentication and hosted database, set these additional environment variables:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
```

When `SUPABASE_URL` is set, Think-Pod automatically switches to cloud mode:
- Supabase Auth (email/password + Google OAuth)
- Supabase PostgreSQL database
- Per-user session isolation

When `SUPABASE_URL` is not set, Think-Pod runs in local mode:
- No authentication (single user)
- SQLite database at `data/thinkpod.db`
- Zero external dependencies beyond Anthropic

## Available Hosts

| Host | Style |
|------|-------|
| **Chris Williamson** | Warm, rigorous, modern-self-improvement interviews |
| **Lex Fridman** | Calm, philosophical, deeply curious |
| **Naval Ravikant** | Sparse, principle-driven, high-signal |
| **Alex Hormozi** | Direct, tactical, operator-style coaching |

## Deep Reflection Mode

Toggle reflection mode when starting a session. Three mechanisms work together:

**Analytical Undertow** — A hidden layer appended to the host's system prompt that tracks desire vs. obligation, contradictions, avoidance patterns, shadow triggers, and emotional suppression. The host stays fully in character while steering toward depth.

**Checkpoints** — Every N exchanges (default 5), a separate analysis pass runs on the transcript and produces steering signals injected into the host's next response. The host naturally follows the signal without breaking character.

**Post-Session Analysis** — After the session ends, the full transcript is analyzed to produce:
- A reflection document (written like a perceptive friend, not a clinician)
- Structured pattern JSON for longitudinal tracking across sessions

## Go Deeper

After a reflection session, click "Go Deeper" to generate a compiled prompt containing your transcript, analysis, and pattern data. Paste it into [claude.ai](https://claude.ai) for a collaborative exploration of your patterns — the prompt is designed to push beyond the initial analysis.

## Project Structure

```
src/
  server/              # FastAPI backend
    main.py              # API endpoints
    llm.py               # LLM calls (conversation, checkpoints, analysis)
    db.py                # Database router (picks SQLite or Supabase)
    db_local.py          # SQLite backend (local mode)
    db_supabase.py       # Supabase backend (cloud mode)
    session.py           # In-memory session management
    config.py            # Configuration + mode detection
    stt.py               # Speech-to-text (Groq Whisper)
    tts.py               # Text-to-speech (Cartesia)
  interview/
    podcast_session.py   # Standalone CLI for interviews
data/
  personas/            # Host profiles + system prompts
  prompts/             # Analytical undertow, checkpoint, analysis, go-deeper prompts
  sessions/            # Transcripts + analysis docs
  patterns/            # Structured pattern JSON per guest
  transcripts/         # Source episode transcripts (training data)
web/                   # Frontend (HTML/JS/CSS)
scripts/
  quickstart.sh        # Local setup script
  test_reflect.py      # E2E test for reflection mode
```

## Stack

- **LLM**: Claude (Anthropic API)
- **STT**: Groq Whisper API (optional)
- **TTS**: Cartesia (optional)
- **Database**: SQLite (local) or Supabase PostgreSQL (cloud)
- **Auth**: None (local) or Supabase Auth (cloud)
- **Server**: FastAPI + Uvicorn

## Secret Safety

- Never commit API keys, `.env` files, or credentials
- Runtime secrets come from environment variables only
- Repo guardrails:
  - Local pre-commit hook (`.githooks/pre-commit`)
  - GitHub Actions secret scanning (`.github/workflows/secret-scan.yml`)
- Install local hooks: `./scripts/install-git-hooks.sh`

## Docs

- [Deep Reflection](docs/DEEP_REFLECTION.md) — how reflection mode works
- [Add a Podcaster](docs/ADD_PODCASTER.md) — guide for adding new host personas
- [Development Plan](planning/DEVELOPMENT_PLAN.md) — roadmap and architecture

## License

MIT
