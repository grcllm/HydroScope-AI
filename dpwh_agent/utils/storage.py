import json
import os
from datetime import datetime, timezone
from pathlib import Path

SESSION_DIR = Path(os.environ.get("SESSION_DIR", "./sessions"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

def save_session(session_id: str, data: dict):
    path = SESSION_DIR / f"{session_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_last_session():
    files = sorted(SESSION_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)

def new_session_id():
    # use timezone-aware datetime
    return datetime.now(timezone.utc).strftime("session-%Y%m%dT%H%M%SZ")