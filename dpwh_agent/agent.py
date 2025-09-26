# orchestrator.py
from dotenv import load_dotenv
from huggingface_hub import Agent
load_dotenv()

from datetime import datetime, timezone
from typing import Optional, Dict, Any

# import your existing functions (adjust the module path if needed)
from dpwh_agents.agents.agent1_fetch import agent1_run
from dpwh_agents.agents.agent2_process import agent2_run
from dpwh_agents.agents.agent3_answer import agent3_run
from dpwh_agents.utils import storage


# --- Sub-agent "tools" (simple wrapper functions) ---
def fetch_tool() -> str:
    """
    Calls agent1 to fetch the dataset and returns the dataset_path (string).
    """
    return agent1_run()


def process_tool(dataset_path: str):
    """
    Calls agent2 to process the dataset and returns the processed dataframe (or object).
    """
    return agent2_run(dataset_path)


def answer_tool(query: str, df) -> Any:
    """
    Calls agent3 to compute the answer given the query and processed data.
    """
    return agent3_run(query, df)


# --- ADK-compatible entrypoint (root orchestrator) ---
def orchestrator_run(query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Root orchestrator function exposed to ADK.
    - query: input question from UI
    - session_id: optional to continue an existing session
    Returns a dict (ADK-friendly structured response).
    """
    try:
        # create new session if needed
        if not session_id:
            session_id = storage.new_session_id()
            session_data = {
                "session_id": session_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "queries": []
            }

            # fetch + process dataset once at session creation
            dataset_path = SUB_AGENTS["agent1_fetch"]()
            df = SUB_AGENTS["agent2_process"](dataset_path)

            session_data["dataset"] = dataset_path
            storage.save_session(session_id, session_data)

        else:
            session_data = storage.load_session(session_id) or {}
            dataset_path = session_data.get("dataset")
            if not dataset_path:
                # if dataset missing in existing session, fetch & process again
                dataset_path = SUB_AGENTS["agent1_fetch"]()
                session_data["dataset"] = dataset_path

            df = SUB_AGENTS["agent2_process"](dataset_path)

        # run the "answer" sub-agent (tool)
        answer = SUB_AGENTS["agent3_answer"](query, df)

        # append query/answer to session
        session_data.setdefault("queries", []).append({
            "question": query,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        storage.save_session(session_id, session_data)

        # Return structured result so ADK UI can render it nicely
        return {
            "session_id": session_id,
            "query": query,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        # surface errors in the response for debugging in the UI
        return {"error": str(e)}

root_agent = Agent(
    model="gemini-2.5-flash",
    name="dpwh_agent",
    description="You are an AI agent that helps users interact with the Department of Public Works and Highways (DPWH) data. You can fetch, process, and answer questions about DPWH datasets.",
    instruction=orchestrator_run,
    sub_agents={
    "agent1_fetch": fetch_tool,
    "agent2_process": process_tool,
    "agent3_answer": answer_tool,
    },
)



SUB_AGENTS = {
    "agent1_fetch": fetch_tool,
    "agent2_process": process_tool,
    "agent3_answer": answer_tool,
}
# --- optional: CLI mode for local debug (keeps your original workflow) ---
def main():
    session_id = storage.new_session_id()
    session_data = {
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "queries": []
    }

    print("Wait! The Agent is fetching the latest dataset.")
    dataset_path = SUB_AGENTS["agent1_fetch"]()

    print("Hold on! The Agent is processing dataset.")
    df = SUB_AGENTS["agent2_process"](dataset_path)

    print("The Agent is now ready.")
    while True:
        query = input("Ask a question (or type 'exit'): ")
        if query.lower() == "exit":
            storage.save_session(session_id, session_data)
            break

        answer = SUB_AGENTS["agent3_answer"](query, df)
        print("Agent:", answer)

        session_data.setdefault("queries", []).append({
            "question": query,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        storage.save_session(session_id, session_data)


if __name__ == "__main__":
    main()
