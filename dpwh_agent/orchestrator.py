import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the repository root and allow it to override existing env vars
_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=_ROOT / ".env", override=True)

from datetime import datetime, timezone

# Ensure the project root is on sys.path when running this file directly
if __package__ is None or __package__ == "":
    # This file lives at <project_root>/dpwh_agent/orchestrator.py
    # We need <project_root> on sys.path so that "dpwh_agent" is importable
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dpwh_agent.agents.agent1_fetch import agent1_run
from dpwh_agent.agents.agent2_process import agent2_run
from dpwh_agent.agents.agent3_answer import agent3_run
from dpwh_agent.utils import storage

# Agentic imports
from dpwh_agent.agentic.gemini_client import build_client, default_config, DEFAULT_MODEL
from dpwh_agent.agentic import tools as agentic_tools


# Google ADK Version
# def orchestrator_run(query: str, session_id: str = None):
#     # create or load session
#     if not session_id:
#         session_id = storage.new_session_id()
#         session_data = {
#             "session_id": session_id,
#             "started_at": datetime.now(timezone.utc).isoformat(),
#             "queries": []
#         }

#         # fetch + process dataset once at start
#         dataset_path = agent1_run()
#         df = agent2_run(dataset_path)
#         session_data["dataset"] = dataset_path
#         storage.save_session(session_id, session_data)

#     else:
#         session_data = storage.load_session(session_id)
#         dataset_path = session_data.get("dataset")
#         df = agent2_run(dataset_path)

#     # run query
#     answer = agent3_run(query, df)

#     # append query/answer
#     session_data["queries"].append({
#         "question": query,
#         "answer": answer,
#         "timestamp": datetime.now(timezone.utc).isoformat()
#     })

#     storage.save_session(session_id, session_data)

#     return {"session_id": session_id, "answer": answer}


# CLI Version
def _agentic_chat_loop(df):
    """Agentic CLI loop using Gemini function-calling with streaming output."""
    # Initialize tools with dataframe
    agentic_tools.set_dataframe(df)
    tool_callables = agentic_tools.tools_list()
    print(f"[agentic] Tools registered: {len(tool_callables)}; model: {DEFAULT_MODEL}")

    # Attempt to build client once up-front; if it fails, run deterministic loop
    try:
        client = build_client()
    except Exception as e:
        print(f"Agentic initialization failed → falling back to deterministic answers. Reason: {e}")
        while True:
            user_msg = input("Ask a question (or type 'exit'): ")
            if user_msg.lower() == "exit":
                return
            answer = agent3_run(user_msg, df)
            print("Agent:", answer)
        return

    # Simple rolling memory (last 5 turns)
    memory_limit = int(os.environ.get("MAX_MEMORY_TURNS", "5"))
    history: list[dict] = []  # [{role:'user'|'model', 'text': str}]

    print("The Agent is now ready (agentic mode).")
    while True:
        user_msg = input("Ask a question (or type 'exit'): ")
        if user_msg.lower() == "exit":
            break

        # Build a compact history string for context
        # Keep it small to save tokens and respect limit
        ctx_lines = []
        for turn in history[-memory_limit:]:
            who = turn.get('role', 'user')
            text = turn.get('text', '')
            if not text:
                continue
            ctx_lines.append(f"{who}: {text}")
        context_blob = "\n".join(ctx_lines)

        prompt = user_msg if not context_blob else (
            f"Previous context (last {min(len(history), memory_limit)} turns):\n{context_blob}\n\nUser: {user_msg}"
        )

        print("Agent:", end=" ", flush=True)
        full_text = []
        try:
            cfg = default_config(tools=tool_callables)
            stream = client.models.generate_content_stream(
                model=DEFAULT_MODEL,
                contents=prompt,
                config=cfg,
            )
            for chunk in stream:
                # Prefer iterating explicit parts to avoid SDK warnings about non-text parts
                parts = getattr(chunk, "parts", None)
                if parts:
                    for p in parts:
                        t = getattr(p, "text", None)
                        if t:
                            print(t, end="", flush=True)
                            full_text.append(t)
                    continue
                # Fallback to chunk.text if parts are not available
                t = getattr(chunk, "text", None)
                if t:
                    print(t, end="", flush=True)
                    full_text.append(t)
            print()  # newline after streaming
        except Exception as e:
            # Fallback to deterministic path on error
            print(f"(fallback: {e})")
            answer = agent3_run(user_msg, df)
            print(answer)
            history.append({"role": "user", "text": user_msg})
            history.append({"role": "model", "text": answer})
            # Minimal session logging
            # Note: session persistence controlled by utils.storage
            try:
                from dpwh_agent.utils import storage as _storage
                sid = _storage.new_session_id()
                _storage.save_session(sid, {
                    "session_id": sid,
                    "queries": [{"question": user_msg, "answer": answer}],
                })
            except Exception:
                pass
            continue

        final_answer = "".join(full_text).strip()
        if not final_answer:
            # Model was silent; fallback to deterministic
            answer = agent3_run(user_msg, df)
            print(answer)
            final_answer = answer

        # Update memory
        history.append({"role": "user", "text": user_msg})
        history.append({"role": "model", "text": final_answer})
        # Minimal session logging
        try:
            from dpwh_agent.utils import storage as _storage
            sid = _storage.new_session_id()
            _storage.save_session(sid, {
                "session_id": sid,
                "queries": [{"question": user_msg, "answer": final_answer}],
            })
        except Exception:
            pass


def main():
    session_id = storage.new_session_id()
    session_data = {
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "queries": []
    }

    print("Wait! The Agent is fetching the latest dataset.")
    dataset_path = agent1_run()

    print("Hold on! The Agent is processing dataset.")
    df = agent2_run(dataset_path)

    # Prefer Parquet fast-path if requested and available
    # (agent2_run may already write parquet; if we had a fast-path loader, it would live in agent1/2)

    # Mode toggle
    agentic_mode = str(os.environ.get("AGENTIC_MODE", "1")).lower() in {"1", "true", "yes", "on"}

    if agentic_mode:
        _agentic_chat_loop(df)
        # Persist session minimal log
        storage.save_session(session_id, session_data)
    else:
        print("The Agent is now ready (deterministic mode).")
        while True:
            query = input("Ask a question (or type 'exit'): ")
            if query.lower() == "exit":
                storage.save_session(session_id, session_data)
                break

            answer = agent3_run(query, df)
            print("Agent:", answer)

            session_data["queries"].append({
                "question": query,
                "answer": answer,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            storage.save_session(session_id, session_data)


if __name__ == "__main__":
    main()
