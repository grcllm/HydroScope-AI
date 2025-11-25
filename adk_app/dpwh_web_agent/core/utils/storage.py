import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Toggle saving via environment; default is OFF (no sessions are saved)
# Set SAVE_SESSIONS=1 to enable persistence.
SAVE_SESSIONS = str(os.environ.get("SAVE_SESSIONS", "0")).lower() in {"1", "true", "yes", "on"}

SESSION_DIR = Path(os.environ.get("SESSION_DIR", "./sessions"))
if SAVE_SESSIONS:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

def save_session(session_id: str, data: dict):
    """Persist session data if SAVE_SESSIONS is enabled; otherwise no-op."""
    if not SAVE_SESSIONS:
        return
    path = SESSION_DIR / f"{session_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_last_session():
    """Load the most recent session if persistence is enabled; otherwise return None."""
    if not SAVE_SESSIONS:
        return None
    files = sorted(SESSION_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)

def new_session_id():
    # use timezone-aware datetime
    return datetime.now(timezone.utc).strftime("session-%Y%m%dT%H%M%SZ")
