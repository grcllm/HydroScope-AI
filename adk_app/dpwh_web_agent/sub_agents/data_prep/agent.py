from __future__ import annotations

from google.adk.agents import Agent  # type: ignore

from dpwh_web_agent.dpwh_agent.agents.agent1_fetch import agent1_run
from dpwh_web_agent.dpwh_agent.agentic import tools as dpwh_tools
import pandas as pd


def ensure_dataset() -> str:
    """Ensure the dataset is loaded and registered for downstream tools."""
    try:
        csv_path = agent1_run()
        df = pd.read_csv(csv_path)
        dpwh_tools.set_dataframe(df)
        return f"Dataset loaded: {csv_path.name} (rows={len(df)})"
    except Exception as e:
        return f"Failed to load dataset: {e}"


data_prep_agent = Agent(
    name="data_prep_agent",
    description="Loads, cleans, and registers the DPWH dataset for analytics tools.",
    instruction=(
        "You are responsible for preparing the dataset so analytics tools can compute answers."
    ),
    tools=[ensure_dataset],
)
