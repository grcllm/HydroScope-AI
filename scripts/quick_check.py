import os
import sys
from pathlib import Path

# Ensure project root is on sys.path and DATA_DIR is set BEFORE importing modules
ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATA_DIR", str(ROOT / "dpwh_agent" / "data"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dpwh_agent.agents.agent1_fetch import agent1_run
from dpwh_agent.agents.agent2_process import agent2_run
from dpwh_agent.agents.agent3_answer import agent3_run


def main():
    # DATA_DIR is already set above prior to imports
    path = agent1_run()
    df = agent2_run(path)
    q = "highest approved budget in NCR"
    print(agent3_run(q, df))


if __name__ == "__main__":
    main()
