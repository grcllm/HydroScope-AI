from __future__ import annotations

import pandas as pd

from dpwh_web_agent.dpwh_agent.agents.agent1_fetch import agent1_run
from dpwh_web_agent.dpwh_agent.agentic import tools as dpwh_tools


def _load_precreated_dataset(*args, **kwargs) -> None:
    """ADK before_agent_callback that loads and registers the dataset.
    """
    try:
        csv_path = agent1_run()
        df = pd.read_csv(csv_path)
        dpwh_tools.set_dataframe(df)
        print(f"[dpwh_web_agent] Dataset ready: {csv_path}")
    except Exception as e:
        print(f"[dpwh_web_agent] Warning: failed to initialize dataset: {e}")
