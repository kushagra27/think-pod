"""Think-Pod configuration."""
import os
from pathlib import Path

# Load .env from project root if present (never committed to git)
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# API Keys — loaded from environment
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
CARTESIA_API_KEY = os.environ.get("CARTESIA_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Voice
CHRIS_VOICE_ID = "4ec2fc3a-5b02-4868-93df-26a1aa439922"
CARTESIA_MODEL = "sonic"

# LLM
LLM_MODEL = "claude-sonnet-4-20250514"

# Reflection mode
CHECKPOINT_INTERVAL = 5
ANALYSIS_MODEL = "claude-opus-4-6"

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PERSONA_DIR = os.path.join(BASE_DIR, "data", "personas")
SESSION_DIR = os.path.join(BASE_DIR, "data", "sessions")
PROMPTS_DIR = os.path.join(BASE_DIR, "data", "prompts")
PATTERNS_DIR = os.path.join(BASE_DIR, "data", "patterns")

os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(PATTERNS_DIR, exist_ok=True)
