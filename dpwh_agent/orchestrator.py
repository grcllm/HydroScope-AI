from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timezone

from agents.agent1_fetch import agent1_run
from agents.agent2_process import agent2_run
from agents.agent3_answer import agent3_run
from utils import storage


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

    print("The Agent is now ready.")
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
