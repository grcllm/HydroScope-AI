from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timezone

from agents.agent1_fetch import agent1_run
from agents.agent2_process import agent2_run
from agents.agent3_answer import agent3_run
from utils import storage

def main():
    # create a new session
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
            # save session before exit
            storage.save_session(session_id, session_data)
            break

        answer = agent3_run(query, df)
        print("Agent:", answer)

        # append query/answer to session data
        session_data["queries"].append({
            "question": query,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # optional: auto-save after every query
        storage.save_session(session_id, session_data)

if __name__ == "__main__":
    main()
