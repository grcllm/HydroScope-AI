from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[0]  
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_ADK_APP = _REPO_ROOT / "adk_app"
if str(_ADK_APP) not in sys.path:
    sys.path.insert(0, str(_ADK_APP))

from flask import Flask, render_template, request, jsonify
from typing import Any, Optional
import threading
from datetime import datetime

app = Flask(__name__)


@app.route("/")
def landing():
    """Landing page with Start Chat button."""
    return render_template("landing.html")


@app.route("/chat")
def chat_page():
    """Render the chat UI."""
    return render_template("index.html")


@app.post("/api/chat")
def api_chat():
    """Proxy chat requests to the ADK agent if available.

    Expects JSON: { "message": "..." }
    Returns JSON: { "reply": "...", "timestamp": "ISO" }
    """
    data = request.get_json(silent=True) or {}
    user_msg: str = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify({"reply": "Please type a message to begin.", "timestamp": datetime.utcnow().isoformat()}), 200


    if user_msg:
        user_msg = user_msg.replace('budjet', 'budget').replace('tren', 'trend').replace('regin', 'region')

    reply_text: Optional[str] = None
    try:
        reply_text = _ask_root_agent(user_msg)
        if reply_text:
            print("[api_chat] Reply from ADK root_agent")
    except Exception:
        print("[api_chat] ADK root_agent call failed", flush=True)
        reply_text = None

    if not reply_text:
        try:
            import importlib  
            _ensure_dpwh_dataset()
            try:
                dpwh_tools = importlib.import_module("dpwh_web_agent.dpwh_agent.agentic.tools")
            except Exception:
                dpwh_tools = importlib.import_module("adk_app.dpwh_web_agent.dpwh_agent.agentic.tools")
            reply_text = getattr(dpwh_tools, "answer_dpwh_question")(user_msg)
            if reply_text:
                print("[api_chat] Reply from dpwh tools" , flush=True)
        except Exception as e:
            print(f"[api_chat] dpwh tools path failed: {e}", flush=True)
            reply_text = None

    if reply_text and ('\n' in reply_text):
        lines = reply_text.split('\n')
        formatted_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('- ') and ':' in stripped:  
                formatted_lines.append('<li>' + stripped[2:] + '</li>')
            elif stripped and not stripped.startswith('Total'):  
                formatted_lines.append('<p>' + stripped + '</p>')
            else:
                formatted_lines.append(line)
        reply_text = '<div>' + ''.join(formatted_lines) + '</div>'

    if not reply_text:
        canned_openers = [
            "Here's a helpful response:",
            "Got it!",
            "Thanks for your message.",
            "Let me help with that.",
        ]
        opener = canned_openers[len(user_msg) % len(canned_openers)]
        reply_text = f"{opener} You said: ‘{user_msg}’. This is a simulated reply (ADK not available)."
        print("[api_chat] Falling back to simulated reply", flush=True)

    return jsonify({
        "reply": reply_text,
        "timestamp": datetime.utcnow().isoformat(),
    }), 200

_DATASET_INIT_LOCK = threading.Lock()
_DATASET_READY = False


def _ensure_dpwh_dataset() -> None:
    global _DATASET_READY
    if _DATASET_READY:
        return
    with _DATASET_INIT_LOCK:
        if _DATASET_READY:
            return
        try:
            import importlib  
            try:
                mem_mod = importlib.import_module("dpwh_web_agent.tools.memory")
            except Exception:
                mem_mod = importlib.import_module("adk_app.dpwh_web_agent.tools.memory")
            _load_precreated_dataset = getattr(mem_mod, "_load_precreated_dataset")
            _load_precreated_dataset()
            _DATASET_READY = True
            print("[dataset] Initialized via memory callback", flush=True)
        except Exception as e:
            print(f"[dataset] memory callback failed: {e}", flush=True)
            try:
                import importlib  
                import pandas as pd  
                try:
                    agent1_fetch = importlib.import_module("dpwh_web_agent.dpwh_agent.agents.agent1_fetch")
                    tools_mod = importlib.import_module("dpwh_web_agent.dpwh_agent.agentic.tools")
                except Exception:
                    agent1_fetch = importlib.import_module("adk_app.dpwh_web_agent.dpwh_agent.agents.agent1_fetch")
                    tools_mod = importlib.import_module("adk_app.dpwh_web_agent.dpwh_agent.agentic.tools")
                csv_path = getattr(agent1_fetch, "agent1_run")()
                df = pd.read_csv(csv_path)
                getattr(tools_mod, "set_dataframe")(df)
                _DATASET_READY = True
                print(f"[dataset] Initialized from CSV: {csv_path}", flush=True)
            except Exception as e2:
                print(f"[dataset] direct CSV init failed: {e2}", flush=True)
                _DATASET_READY = False


def _ask_root_agent(message: str) -> Optional[str]:
    """Try to call the ADK root agent directly and extract a text reply.

    This stays entirely within the existing dpwh_web_agent package; no extra files.
    """
    if not message or not message.strip():
        return None
    try:
        import importlib  
        root_agent = getattr(importlib.import_module("dpwh_web_agent.agent"), "root_agent")  
    except Exception:
        return None

    agent = root_agent

    def _extract_text(resp: Any) -> Optional[str]:
        if resp is None:
            return None
        if isinstance(resp, str):
            return resp
        for key in ("text", "reply", "content", "message"):
            try:
                if isinstance(resp, dict) and key in resp and isinstance(resp[key], str):
                    return resp[key]
                val = getattr(resp, key, None)
                if isinstance(val, str):
                    return val
            except Exception:
                pass
        try:
            return str(resp)
        except Exception:
            return None
    for name in ("run", "respond", "chat", "invoke", "ask", "call"):
        try:
            fn = getattr(agent, name, None)
            if callable(fn):
                resp = fn(message)
                text = _extract_text(resp)
                if text:
                    return text
        except Exception:
            continue
    try:
        if callable(agent):
            resp = agent(message)  
            text = _extract_text(resp)
            if text:
                return text
    except Exception:
        pass
    return None


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=3000)
