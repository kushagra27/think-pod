"""Database router — picks SQLite (local) or Supabase (cloud) backend."""
from .config import LOCAL_MODE

if LOCAL_MODE:
    from .db_local import *  # noqa: F401,F403
else:
    from .db_supabase import *  # noqa: F401,F403
