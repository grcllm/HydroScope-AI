from __future__ import annotations

from google.adk.agents import Agent  # type: ignore

from ...tools import analytics_tools as dpwh_tools


analytics_agent = Agent(
    name="analytics_agent",
    description="Performs analytics and lookups on the DPWH dataset (budgets, counts, top contractors).",
    instruction=(
        "Use tools to compute answers directly from the dataset. Keep answers concise with pesos (₱)."
    ),
    tools=dpwh_tools.tools_list(),
)
