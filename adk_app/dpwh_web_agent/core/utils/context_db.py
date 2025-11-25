"""
SQLite-based conversation context storage.

Stores user questions, agent responses, and extracted context (entities like cities, regions, contractors)
to enable contextual follow-up questions.

Example:
    User: "Show me projects in Quezon City"
    Agent: [stores context: city=Quezon City]
    User: "What's the total budget?" (implicitly means: in Quezon City)
    Agent: [retrieves context and applies filter]
"""
from __future__ import annotations
import sqlite3
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
import threading

# Database location
DB_DIR = Path(os.environ.get("CONTEXT_DB_DIR", "./data"))
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "conversation_context.db"

# Thread-local storage for connections
_thread_local = threading.local()


def _get_connection() -> sqlite3.Connection:
    """Get or create a thread-local database connection."""
    if not hasattr(_thread_local, 'conn') or _thread_local.conn is None:
        _thread_local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _thread_local.conn.row_factory = sqlite3.Row
        _init_db(_thread_local.conn)
    return _thread_local.conn


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize database schema if not exists."""
    cursor = conn.cursor()
    
    # Sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            last_activity TEXT NOT NULL,
            metadata TEXT
        )
    """)
    
    # Conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            user_message TEXT NOT NULL,
            agent_response TEXT,
            context_extracted TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions (session_id)
        )
    """)
    
    # Context store (key-value per session)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS context_store (
            session_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (session_id, key),
            FOREIGN KEY (session_id) REFERENCES sessions (session_id)
        )
    """)
    
    # Indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversations_session 
        ON conversations(session_id, timestamp DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_context_session 
        ON context_store(session_id)
    """)
    
    conn.commit()


def create_session(session_id: Optional[str] = None) -> str:
    """Create a new session and return its ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    
    if session_id is None:
        session_id = datetime.now(timezone.utc).strftime("session-%Y%m%d-%H%M%S-%f")
    
    now = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        INSERT OR REPLACE INTO sessions (session_id, created_at, last_activity, metadata)
        VALUES (?, ?, ?, ?)
    """, (session_id, now, now, json.dumps({})))
    
    conn.commit()
    return session_id


def log_conversation(
    session_id: str,
    user_message: str,
    agent_response: str = "",
    context_extracted: Optional[Dict[str, Any]] = None
) -> int:
    """Log a conversation turn and return the conversation ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    context_json = json.dumps(context_extracted) if context_extracted else None
    
    cursor.execute("""
        INSERT INTO conversations (session_id, timestamp, user_message, agent_response, context_extracted)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, now, user_message, agent_response, context_json))
    
    # Update session last activity
    cursor.execute("""
        UPDATE sessions SET last_activity = ? WHERE session_id = ?
    """, (now, session_id))
    
    conn.commit()
    return cursor.lastrowid


def update_context(session_id: str, context: Dict[str, Any]) -> None:
    """Update context for a session. Merges with existing context."""
    conn = _get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    
    for key, value in context.items():
        if value is not None:
            value_json = json.dumps(value) if not isinstance(value, str) else value
            cursor.execute("""
                INSERT OR REPLACE INTO context_store (session_id, key, value, updated_at)
                VALUES (?, ?, ?, ?)
            """, (session_id, key, value_json, now))
    
    conn.commit()


def get_context(session_id: str) -> Dict[str, Any]:
    """Retrieve all context for a session."""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT key, value FROM context_store WHERE session_id = ?
    """, (session_id,))
    
    context = {}
    for row in cursor.fetchall():
        key = row['key']
        value = row['value']
        try:
            context[key] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            context[key] = value
    
    return context


def get_conversation_history(session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent conversation history for a session."""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, timestamp, user_message, agent_response, context_extracted
        FROM conversations
        WHERE session_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (session_id, limit))
    
    history = []
    for row in cursor.fetchall():
        item = {
            'id': row['id'],
            'timestamp': row['timestamp'],
            'user_message': row['user_message'],
            'agent_response': row['agent_response'],
        }
        if row['context_extracted']:
            try:
                item['context_extracted'] = json.loads(row['context_extracted'])
            except (json.JSONDecodeError, TypeError):
                item['context_extracted'] = {}
        history.append(item)
    
    return list(reversed(history))  # Return chronological order


def clear_context(session_id: str, keys: Optional[List[str]] = None) -> None:
    """Clear context for a session. If keys provided, only clear those keys."""
    conn = _get_connection()
    cursor = conn.cursor()
    
    if keys:
        cursor.execute(f"""
            DELETE FROM context_store 
            WHERE session_id = ? AND key IN ({','.join('?' * len(keys))})
        """, [session_id] + keys)
    else:
        cursor.execute("""
            DELETE FROM context_store WHERE session_id = ?
        """, (session_id,))
    
    conn.commit()


def delete_session(session_id: str) -> None:
    """Delete a session and all its data."""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM context_store WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    
    conn.commit()


def get_or_create_session(session_id: Optional[str] = None) -> str:
    """Get existing session or create a new one."""
    if session_id:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
        if cursor.fetchone():
            return session_id
    
    return create_session(session_id)


# Cleanup on module unload
import atexit

def _cleanup():
    if hasattr(_thread_local, 'conn') and _thread_local.conn:
        _thread_local.conn.close()

atexit.register(_cleanup)
