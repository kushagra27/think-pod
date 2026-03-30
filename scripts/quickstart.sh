#!/usr/bin/env bash
set -euo pipefail

# ── Think-Pod Quickstart ─────────────────────────────────────────────
# Sets up a local instance: venv, deps, API key, SQLite DB, and starts the server.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
VENV_DIR="$PROJECT_DIR/.venv"

echo ""
echo "🎙️  Think-Pod — Local Quickstart"
echo "================================="
echo ""

# ── 1. Check Python ──────────────────────────────────────────────────

if ! command -v python3 &>/dev/null; then
  echo "❌  Python 3 is required but not found. Install it first."
  exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
  echo "❌  Python 3.10+ required (found $PY_VERSION)"
  exit 1
fi

echo "✓  Python $PY_VERSION"

# ── 2. Create virtual environment ────────────────────────────────────

if [ ! -d "$VENV_DIR" ]; then
  echo ""
  echo "Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
  echo "✓  Virtual environment created at .venv/"
else
  echo "✓  Virtual environment exists"
fi

# Activate
source "$VENV_DIR/bin/activate"

# ── 3. Install dependencies ──────────────────────────────────────────

echo ""
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$PROJECT_DIR/requirements.txt"
echo "✓  Dependencies installed"

# ── 4. Configure API keys ────────────────────────────────────────────

echo ""
echo "─── API Key Configuration ───"
echo ""

if [ -f "$ENV_FILE" ]; then
  echo "Found existing .env file."
  # Source it to check what's set
  set +u
  source <(grep -v '^#' "$ENV_FILE" | grep '=' | sed 's/^/export /')
  set -u
fi

# Anthropic API key (required)
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "An Anthropic API key is REQUIRED for Think-Pod to work."
  echo "Get one at: https://console.anthropic.com/settings/keys"
  echo ""
  read -rp "Anthropic API key (sk-ant-...): " ANTHROPIC_API_KEY
  if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌  Anthropic API key is required. Exiting."
    exit 1
  fi
else
  echo "✓  Anthropic API key found"
fi

# Groq API key (optional — for voice input)
if [ -z "${GROQ_API_KEY:-}" ]; then
  echo ""
  echo "Groq API key enables voice input (speech-to-text via Whisper)."
  echo "Optional — skip for text-only mode."
  echo "Get one at: https://console.groq.com/keys"
  read -rp "Groq API key (gsk_...) or Enter to skip: " GROQ_API_KEY
fi

# Cartesia API key (optional — for voice output)
if [ -z "${CARTESIA_API_KEY:-}" ]; then
  echo ""
  echo "Cartesia API key enables voice output (text-to-speech)."
  echo "Optional — skip for text-only mode."
  echo "Get one at: https://play.cartesia.ai/keys"
  read -rp "Cartesia API key or Enter to skip: " CARTESIA_API_KEY
fi

# Write .env (local mode — no SUPABASE_URL means SQLite + no auth)
cat > "$ENV_FILE" <<ENVEOF
# Think-Pod local configuration
# No SUPABASE_URL = local mode (SQLite DB, no auth)

ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
GROQ_API_KEY=${GROQ_API_KEY:-}
CARTESIA_API_KEY=${CARTESIA_API_KEY:-}
ENVEOF

echo ""
echo "✓  Configuration saved to .env"

# ── 5. Initialize data directories ───────────────────────────────────

mkdir -p "$PROJECT_DIR/data/sessions"
mkdir -p "$PROJECT_DIR/data/patterns"
echo "✓  Data directories ready"

# ── 6. Summary ───────────────────────────────────────────────────────

echo ""
echo "================================="
echo "🎙️  Think-Pod is ready!"
echo "================================="
echo ""
echo "  Mode:  Local (SQLite, no auth)"
echo "  Voice: $([ -n "${GROQ_API_KEY:-}" ] && echo "Input ✓" || echo "Input ✗ (text only)")  $([ -n "${CARTESIA_API_KEY:-}" ] && echo "Output ✓" || echo "Output ✗ (text only)")"
echo ""
echo "  Start the server:"
echo "    cd $(basename "$PROJECT_DIR")"
echo "    source .venv/bin/activate"
echo "    uvicorn src.server.main:app --reload --port 8000"
echo ""
echo "  Then open: http://localhost:8000"
echo ""
echo "  Or use the CLI directly:"
echo "    python src/interview/podcast_session.py --podcaster naval-ravikant --reflect"
echo ""
